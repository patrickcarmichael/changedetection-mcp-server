#!/usr/bin/env python3
"""
Health check endpoint for changedetection-mcp-server.

This script validates:
- Server responsiveness
- Changedetection.io API connectivity
- Environment configuration
- Resource availability
"""

import os
import sys
import asyncio
import httpx
import time
from typing import Dict, Any
from datetime import datetime


class HealthChecker:
    """Comprehensive health checker for the MCP server."""

    def __init__(self):
        self.base_url = os.getenv("CHANGEDETECTION_URL", "http://localhost:5000")
        self.api_key = os.getenv("CHANGEDETECTION_API_KEY", "")
        self.timeout = float(os.getenv("HEALTH_CHECK_TIMEOUT", "5.0"))
        self.checks_passed = 0
        self.checks_failed = 0
        self.warnings = []

    async def check_environment(self) -> Dict[str, Any]:
        """Check required environment variables."""
        status = "healthy"
        details = {}
        
        # Required variables
        required_vars = ["CHANGEDETECTION_URL", "CHANGEDETECTION_API_KEY"]
        
        for var in required_vars:
            value = os.getenv(var)
            if not value:
                status = "unhealthy"
                details[var] = "missing"
                self.checks_failed += 1
            else:
                details[var] = "configured"
                self.checks_passed += 1
        
        # Optional but recommended
        optional_vars = ["LOG_LEVEL", "RATE_LIMIT_ENABLED", "ENABLE_METRICS"]
        for var in optional_vars:
            value = os.getenv(var)
            if not value:
                self.warnings.append(f"{var} not set, using defaults")
        
        return {
            "check": "environment",
            "status": status,
            "details": details,
        }

    async def check_changedetection_api(self) -> Dict[str, Any]:
        """Check connectivity to changedetection.io API."""
        start_time = time.time()
        
        try:
            headers = {"x-api-key": self.api_key} if self.api_key else {}
            url = f"{self.base_url}/api/v1/systeminfo"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers=headers,
                    timeout=self.timeout
                )
                
                response_time = time.time() - start_time
                
                if response.status_code == 200:
                    self.checks_passed += 1
                    return {
                        "check": "changedetection_api",
                        "status": "healthy",
                        "response_time_ms": round(response_time * 1000, 2),
                        "api_version": response.json().get("version", "unknown"),
                    }
                elif response.status_code == 401:
                    self.checks_failed += 1
                    return {
                        "check": "changedetection_api",
                        "status": "unhealthy",
                        "error": "authentication_failed",
                        "message": "Invalid or missing API key",
                    }
                else:
                    self.checks_failed += 1
                    return {
                        "check": "changedetection_api",
                        "status": "unhealthy",
                        "error": f"http_error_{response.status_code}",
                        "response_time_ms": round(response_time * 1000, 2),
                    }
                    
        except httpx.TimeoutException:
            self.checks_failed += 1
            return {
                "check": "changedetection_api",
                "status": "unhealthy",
                "error": "timeout",
                "message": f"Request timed out after {self.timeout}s",
            }
        except httpx.ConnectError:
            self.checks_failed += 1
            return {
                "check": "changedetection_api",
                "status": "unhealthy",
                "error": "connection_refused",
                "message": f"Cannot connect to {self.base_url}",
            }
        except Exception as e:
            self.checks_failed += 1
            return {
                "check": "changedetection_api",
                "status": "unhealthy",
                "error": "unknown_error",
                "message": str(e),
            }

    async def check_dependencies(self) -> Dict[str, Any]:
        """Check Python dependencies."""
        status = "healthy"
        missing = []
        
        required_modules = {
            "mcp": "mcp",
            "httpx": "httpx",
            "dotenv": "python-dotenv",
        }
        
        for module, package in required_modules.items():
            try:
                __import__(module)
                self.checks_passed += 1
            except ImportError:
                missing.append(package)
                status = "unhealthy"
                self.checks_failed += 1
        
        return {
            "check": "dependencies",
            "status": status,
            "missing_packages": missing if missing else None,
        }

    async def check_system_resources(self) -> Dict[str, Any]:
        """Check system resources."""
        import psutil
        
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            
            status = "healthy"
            warnings = []
            
            if cpu_percent > 90:
                warnings.append("High CPU usage")
                status = "degraded"
            
            if memory_percent > 90:
                warnings.append("High memory usage")
                status = "degraded"
            
            if disk_percent > 90:
                warnings.append("High disk usage")
                status = "degraded"
            
            if status == "healthy":
                self.checks_passed += 1
            else:
                self.warnings.extend(warnings)
            
            return {
                "check": "system_resources",
                "status": status,
                "cpu_percent": round(cpu_percent, 2),
                "memory_percent": round(memory_percent, 2),
                "disk_percent": round(disk_percent, 2),
                "warnings": warnings if warnings else None,
            }
        except ImportError:
            # psutil not installed, skip this check
            return {
                "check": "system_resources",
                "status": "skipped",
                "message": "psutil not installed",
            }
        except Exception as e:
            return {
                "check": "system_resources",
                "status": "error",
                "error": str(e),
            }

    async def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks."""
        start_time = datetime.utcnow()
        
        # Run checks concurrently
        results = await asyncio.gather(
            self.check_environment(),
            self.check_changedetection_api(),
            self.check_dependencies(),
            self.check_system_resources(),
        )
        
        # Determine overall status
        statuses = [result["status"] for result in results]
        
        if "unhealthy" in statuses:
            overall_status = "unhealthy"
        elif "degraded" in statuses:
            overall_status = "degraded"
        else:
            overall_status = "healthy"
        
        end_time = datetime.utcnow()
        duration_ms = (end_time - start_time).total_seconds() * 1000
        
        return {
            "status": overall_status,
            "timestamp": start_time.isoformat() + "Z",
            "duration_ms": round(duration_ms, 2),
            "checks": results,
            "summary": {
                "total": self.checks_passed + self.checks_failed,
                "passed": self.checks_passed,
                "failed": self.checks_failed,
                "warnings": self.warnings if self.warnings else None,
            },
            "server": {
                "version": "1.0.0",
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            },
        }


async def main():
    """Run health check and exit with appropriate code."""
    checker = HealthChecker()
    result = await checker.run_all_checks()
    
    # Print JSON output
    import json
    print(json.dumps(result, indent=2))
    
    # Exit with appropriate code
    if result["status"] == "unhealthy":
        sys.exit(1)
    elif result["status"] == "degraded":
        # Exit 0 for degraded to allow container to stay up
        # but monitoring can detect the degraded state
        sys.exit(0)
    else:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
