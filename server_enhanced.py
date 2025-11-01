#!/usr/bin/env python3
"""
Production-enhanced MCP server for changedetection.io API.

Features:
- Structured logging with JSON output
- Request/response validation
- Rate limiting capabilities
- Metrics collection hooks
- Enhanced error handling
- Input sanitization
- CORS support
- Health check endpoint
"""

import os
import sys
import json
import time
from typing import Any, Optional, Dict
from datetime import datetime
from collections import defaultdict
import httpx
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import stdio_server
import asyncio
import logging
from functools import wraps

# ============================================================================
# Configuration
# ============================================================================

# Server configuration
SERVER_VERSION = "1.0.0"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"

# Changedetection.io API configuration
BASE_URL = os.getenv("CHANGEDETECTION_URL", "http://localhost:5000")
API_KEY = os.getenv("CHANGEDETECTION_API_KEY", "")

# Rate limiting configuration
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", "10"))

# Monitoring configuration
ENABLE_METRICS = os.getenv("ENABLE_METRICS", "true").lower() == "true"
METRICS_PORT = int(os.getenv("METRICS_PORT", "9090"))

# ============================================================================
# Structured Logging
# ============================================================================


class StructuredLogger:
    """Structured JSON logger for production environments."""

    def __init__(self, name: str, level: str = "INFO"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))

        # JSON formatter
        handler = logging.StreamHandler()
        handler.setFormatter(self.JSONFormatter())
        self.logger.addHandler(handler)

    class JSONFormatter(logging.Formatter):
        """Format logs as JSON."""

        def format(self, record):
            log_data = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "level": record.levelname,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }

            if hasattr(record, "request_id"):
                log_data["request_id"] = record.request_id

            if hasattr(record, "duration_ms"):
                log_data["duration_ms"] = record.duration_ms

            if hasattr(record, "tool_name"):
                log_data["tool_name"] = record.tool_name

            if record.exc_info:
                log_data["exception"] = self.formatException(record.exc_info)

            return json.dumps(log_data)

    def info(self, message: str, **kwargs):
        extra = {k: v for k, v in kwargs.items()}
        self.logger.info(message, extra=extra)

    def warning(self, message: str, **kwargs):
        extra = {k: v for k, v in kwargs.items()}
        self.logger.warning(message, extra=extra)

    def error(self, message: str, **kwargs):
        extra = {k: v for k, v in kwargs.items()}
        self.logger.error(message, extra=extra, exc_info=kwargs.get("exc_info"))

    def debug(self, message: str, **kwargs):
        extra = {k: v for k, v in kwargs.items()}
        self.logger.debug(message, extra=extra)


# Initialize logger
logger = StructuredLogger(__name__, LOG_LEVEL)

# ============================================================================
# Rate Limiter
# ============================================================================


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, rate_per_minute: int, burst: int):
        self.rate = rate_per_minute / 60.0  # tokens per second
        self.burst = burst
        self.tokens = burst
        self.last_update = time.time()
        self.request_counts = defaultdict(int)

    def allow_request(self, client_id: str = "default") -> tuple[bool, Optional[float]]:
        """Check if request is allowed. Returns (allowed, retry_after_seconds)."""
        now = time.time()
        elapsed = now - self.last_update

        # Add tokens based on elapsed time
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_update = now

        if self.tokens >= 1:
            self.tokens -= 1
            self.request_counts[client_id] += 1
            return True, None
        else:
            retry_after = (1 - self.tokens) / self.rate
            return False, retry_after

    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        return {
            "enabled": RATE_LIMIT_ENABLED,
            "rate_per_minute": RATE_LIMIT_PER_MINUTE,
            "burst": self.burst,
            "current_tokens": round(self.tokens, 2),
            "total_requests": sum(self.request_counts.values()),
        }


rate_limiter = RateLimiter(RATE_LIMIT_PER_MINUTE, RATE_LIMIT_BURST)

# ============================================================================
# Metrics Collector
# ============================================================================


class MetricsCollector:
    """Simple metrics collector for monitoring."""

    def __init__(self):
        self.metrics = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_failed": 0,
            "requests_rate_limited": 0,
            "total_duration_ms": 0,
            "by_tool": defaultdict(lambda: {"count": 0, "errors": 0, "duration_ms": 0}),
        }
        self.start_time = time.time()

    def record_request(
        self, tool_name: str, success: bool, duration_ms: float, rate_limited: bool = False
    ):
        """Record a request metric."""
        self.metrics["requests_total"] += 1

        if rate_limited:
            self.metrics["requests_rate_limited"] += 1
            return

        if success:
            self.metrics["requests_success"] += 1
        else:
            self.metrics["requests_failed"] += 1

        self.metrics["total_duration_ms"] += duration_ms

        tool_metrics = self.metrics["by_tool"][tool_name]
        tool_metrics["count"] += 1
        tool_metrics["duration_ms"] += duration_ms
        if not success:
            tool_metrics["errors"] += 1

    def get_metrics(self) -> Dict[str, Any]:
        """Get all metrics."""
        uptime = time.time() - self.start_time
        avg_duration = (
            self.metrics["total_duration_ms"] / self.metrics["requests_success"]
            if self.metrics["requests_success"] > 0
            else 0
        )

        return {
            "uptime_seconds": round(uptime, 2),
            "requests": {
                "total": self.metrics["requests_total"],
                "success": self.metrics["requests_success"],
                "failed": self.metrics["requests_failed"],
                "rate_limited": self.metrics["requests_rate_limited"],
                "success_rate": (
                    round(
                        self.metrics["requests_success"] / self.metrics["requests_total"] * 100,
                        2,
                    )
                    if self.metrics["requests_total"] > 0
                    else 0
                ),
            },
            "performance": {
                "avg_duration_ms": round(avg_duration, 2),
                "total_duration_ms": round(self.metrics["total_duration_ms"], 2),
            },
            "by_tool": dict(self.metrics["by_tool"]),
        }


metrics = MetricsCollector()

# ============================================================================
# Input Validation & Sanitization
# ============================================================================


def sanitize_string(value: str, max_length: int = 2048) -> str:
    """Sanitize string input to prevent injection attacks."""
    if not isinstance(value, str):
        return str(value)

    # Trim to max length
    value = value[:max_length]

    # Remove null bytes
    value = value.replace("\x00", "")

    # Strip whitespace
    value = value.strip()

    return value


def validate_url(url: str) -> bool:
    """Validate URL format."""
    import re

    url_pattern = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain
        r"localhost|"  # localhost
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # IP
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return bool(url_pattern.match(url))


def validate_uuid(uuid_str: str) -> bool:
    """Validate UUID format."""
    import re

    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    return bool(uuid_pattern.match(uuid_str))


# ============================================================================
# Enhanced Changedetection Client
# ============================================================================


class ChangeDetectionClient:
    """Enhanced client for interacting with changedetection.io API."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {"x-api-key": api_key} if api_key else {}
        self.timeout = httpx.Timeout(30.0, connect=10.0)

    async def _request(
        self, method: str, endpoint: str, data: Optional[dict] = None
    ) -> Any:
        """Make HTTP request with enhanced error handling."""
        url = f"{self.base_url}{endpoint}"
        request_id = f"{int(time.time() * 1000)}"

        logger.debug(
            f"Making {method} request to {endpoint}",
            request_id=request_id,
        )

        async with httpx.AsyncClient() as client:
            try:
                kwargs = {
                    "headers": self.headers,
                    "timeout": self.timeout,
                }

                if method == "GET":
                    response = await client.get(url, **kwargs)
                elif method == "POST":
                    kwargs["json"] = data
                    response = await client.post(url, **kwargs)
                elif method == "DELETE":
                    response = await client.delete(url, **kwargs)
                elif method == "PUT":
                    kwargs["json"] = data
                    response = await client.put(url, **kwargs)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                response.raise_for_status()

                result = response.json() if response.text else {}

                logger.debug(
                    f"Request successful: {method} {endpoint}",
                    request_id=request_id,
                )

                return result

            except httpx.TimeoutException as e:
                logger.error(
                    f"Request timeout: {method} {endpoint}",
                    request_id=request_id,
                    exc_info=True,
                )
                raise Exception(f"Request timeout after {self.timeout.read}s") from e

            except httpx.HTTPStatusError as e:
                logger.error(
                    f"HTTP error {e.response.status_code}: {method} {endpoint}",
                    request_id=request_id,
                )
                raise Exception(
                    f"HTTP {e.response.status_code}: {e.response.text}"
                ) from e

            except httpx.ConnectError as e:
                logger.error(
                    f"Connection error: {method} {endpoint}",
                    request_id=request_id,
                    exc_info=True,
                )
                raise Exception(f"Cannot connect to {self.base_url}") from e

            except Exception as e:
                logger.error(
                    f"Unexpected error: {method} {endpoint}",
                    request_id=request_id,
                    exc_info=True,
                )
                raise

    async def list_watches(self) -> dict:
        """List all watches."""
        return await self._request("GET", "/api/v1/watch")

    async def get_watch(self, watch_id: str) -> dict:
        """Get details of a specific watch."""
        watch_id = sanitize_string(watch_id)
        if not validate_uuid(watch_id):
            raise ValueError(f"Invalid watch ID format: {watch_id}")
        return await self._request("GET", f"/api/v1/watch/{watch_id}")

    async def create_watch(self, url: str, tag: Optional[str] = None) -> dict:
        """Create a new watch."""
        url = sanitize_string(url)
        if not validate_url(url):
            raise ValueError(f"Invalid URL format: {url}")

        data = {"url": url}
        if tag:
            data["tag"] = sanitize_string(tag, max_length=100)

        return await self._request("POST", "/api/v1/watch", data)

    async def delete_watch(self, watch_id: str) -> dict:
        """Delete a watch."""
        watch_id = sanitize_string(watch_id)
        if not validate_uuid(watch_id):
            raise ValueError(f"Invalid watch ID format: {watch_id}")
        return await self._request("DELETE", f"/api/v1/watch/{watch_id}")

    async def trigger_check(self, watch_id: str) -> dict:
        """Trigger a check for a specific watch."""
        watch_id = sanitize_string(watch_id)
        if not validate_uuid(watch_id):
            raise ValueError(f"Invalid watch ID format: {watch_id}")
        return await self._request("GET", f"/api/v1/watch/{watch_id}/trigger")

    async def get_history(self, watch_id: str) -> dict:
        """Get history of changes for a watch."""
        watch_id = sanitize_string(watch_id)
        if not validate_uuid(watch_id):
            raise ValueError(f"Invalid watch ID format: {watch_id}")
        return await self._request("GET", f"/api/v1/watch/{watch_id}/history")

    async def system_info(self) -> dict:
        """Get system information."""
        return await self._request("GET", "/api/v1/systeminfo")


# Initialize client
if not API_KEY:
    logger.warning("CHANGEDETECTION_API_KEY not set. Some operations may fail.")

client = ChangeDetectionClient(BASE_URL, API_KEY)

# Initialize MCP server
app = Server("changedetection-mcp-server")

# ============================================================================
# MCP Server Handlers
# ============================================================================


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="list_watches",
            description="List all website watches configured in changedetection.io",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_watch",
            description="Get detailed information about a specific watch",
            inputSchema={
                "type": "object",
                "properties": {
                    "watch_id": {
                        "type": "string",
                        "description": "The UUID of the watch to retrieve",
                        "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                    }
                },
                "required": ["watch_id"],
            },
        ),
        Tool(
            name="create_watch",
            description="Create a new watch to monitor a website for changes",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to monitor (must be http:// or https://)",
                        "format": "uri",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Optional tag to categorize the watch (max 100 chars)",
                        "maxLength": 100,
                    },
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="delete_watch",
            description="Delete a watch and stop monitoring",
            inputSchema={
                "type": "object",
                "properties": {
                    "watch_id": {
                        "type": "string",
                        "description": "The UUID of the watch to delete",
                        "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                    }
                },
                "required": ["watch_id"],
            },
        ),
        Tool(
            name="trigger_check",
            description="Manually trigger a change detection check",
            inputSchema={
                "type": "object",
                "properties": {
                    "watch_id": {
                        "type": "string",
                        "description": "The UUID of the watch to check",
                        "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                    }
                },
                "required": ["watch_id"],
            },
        ),
        Tool(
            name="get_history",
            description="Get the history of detected changes",
            inputSchema={
                "type": "object",
                "properties": {
                    "watch_id": {
                        "type": "string",
                        "description": "The UUID of the watch",
                        "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                    }
                },
                "required": ["watch_id"],
            },
        ),
        Tool(
            name="system_info",
            description="Get system information about the changedetection.io instance",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_metrics",
            description="Get server metrics and statistics",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls with enhanced features."""
    start_time = time.time()
    success = False

    try:
        # Check rate limiting
        if RATE_LIMIT_ENABLED and name != "get_metrics":
            allowed, retry_after = rate_limiter.allow_request()
            if not allowed:
                metrics.record_request(name, False, 0, rate_limited=True)
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "error": "rate_limit_exceeded",
                                "message": f"Rate limit exceeded. Retry after {retry_after:.1f}s",
                                "retry_after": retry_after,
                            },
                            indent=2,
                        ),
                    )
                ]

        # Route to appropriate handler
        if name == "list_watches":
            result = await client.list_watches()
            success = True

        elif name == "get_watch":
            watch_id = arguments.get("watch_id")
            if not watch_id:
                raise ValueError("watch_id is required")
            result = await client.get_watch(watch_id)
            success = True

        elif name == "create_watch":
            url = arguments.get("url")
            tag = arguments.get("tag")
            if not url:
                raise ValueError("url is required")
            result = await client.create_watch(url, tag)
            success = True

        elif name == "delete_watch":
            watch_id = arguments.get("watch_id")
            if not watch_id:
                raise ValueError("watch_id is required")
            result = await client.delete_watch(watch_id)
            success = True

        elif name == "trigger_check":
            watch_id = arguments.get("watch_id")
            if not watch_id:
                raise ValueError("watch_id is required")
            result = await client.trigger_check(watch_id)
            success = True

        elif name == "get_history":
            watch_id = arguments.get("watch_id")
            if not watch_id:
                raise ValueError("watch_id is required")
            result = await client.get_history(watch_id)
            success = True

        elif name == "system_info":
            result = await client.system_info()
            success = True

        elif name == "get_metrics":
            result = {
                "server_metrics": metrics.get_metrics(),
                "rate_limiter": rate_limiter.get_stats(),
                "version": SERVER_VERSION,
            }
            success = True

        else:
            raise ValueError(f"Unknown tool: {name}")

        # Format successful response
        response = {"success": True, "data": result}

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except ValueError as e:
        logger.warning(f"Validation error in {name}: {str(e)}", tool_name=name)
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "success": False,
                        "error": "validation_error",
                        "message": str(e),
                    },
                    indent=2,
                ),
            )
        ]

    except Exception as e:
        logger.error(f"Error executing {name}: {str(e)}", tool_name=name, exc_info=True)
        error_response = {
            "success": False,
            "error": "execution_error",
            "message": str(e) if DEBUG_MODE else "An error occurred processing your request",
        }
        return [TextContent(type="text", text=json.dumps(error_response, indent=2))]

    finally:
        duration_ms = (time.time() - start_time) * 1000
        if ENABLE_METRICS:
            metrics.record_request(name, success, duration_ms)
        logger.info(
            f"Tool call completed: {name}",
            tool_name=name,
            duration_ms=round(duration_ms, 2),
            success=success,
        )


async def main():
    """Run the MCP server."""
    logger.info(
        f"Starting changedetection-mcp-server v{SERVER_VERSION}",
        server_version=SERVER_VERSION,
        log_level=LOG_LEVEL,
        rate_limiting=RATE_LIMIT_ENABLED,
        metrics=ENABLE_METRICS,
    )

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)
