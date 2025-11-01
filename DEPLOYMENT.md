# Deployment Guide

Complete guide for deploying changedetection-mcp-server to production environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Deployment Options](#deployment-options)
  - [Docker Compose](#docker-compose)
  - [Kubernetes](#kubernetes)
  - [Vercel Serverless](#vercel-serverless)
  - [AWS Lambda](#aws-lambda)
- [Security Considerations](#security-considerations)
- [Monitoring & Observability](#monitoring--observability)
- [Scaling](#scaling)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Docker 20.10+ and Docker Compose 1.29+
- Python 3.11+ (for local development)
- A running changedetection.io instance
- API key from changedetection.io

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `CHANGEDETECTION_URL` | Your changedetection.io instance URL | `http://localhost:5000` |
| `CHANGEDETECTION_API_KEY` | API key for authentication | `your-secret-key` |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `DEBUG` | `false` | Enable debug mode |
| `RATE_LIMIT_ENABLED` | `true` | Enable rate limiting |
| `RATE_LIMIT_PER_MINUTE` | `60` | Max requests per minute |
| `RATE_LIMIT_BURST` | `10` | Burst capacity for rate limiter |
| `ENABLE_METRICS` | `true` | Enable metrics collection |
| `METRICS_PORT` | `9090` | Port for metrics endpoint |
| `ENABLE_CORS` | `true` | Enable CORS |
| `ALLOWED_ORIGINS` | `*` | Comma-separated allowed origins |

---

## Deployment Options

### Docker Compose

**Best for:** Development, small deployments, and testing

#### Quick Start

1. **Clone the repository:**
   ```bash
   git clone https://github.com/patrickcarmichael/changedetection-mcp-server.git
   cd changedetection-mcp-server
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Start the stack:**
   ```bash
   docker-compose up -d
   ```

4. **Verify deployment:**
   ```bash
   docker-compose ps
   docker-compose logs mcp-server
   ```

#### Full Stack (with monitoring)

```bash
# Start with monitoring stack
docker-compose --profile monitoring up -d

# Access services:
# - MCP Server: http://localhost:8000
# - Changedetection.io: http://localhost:5000
# - Prometheus: http://localhost:9090
# - Grafana: http://localhost:3000 (admin/admin)
```

#### Production Configuration

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  mcp-server:
    image: ghcr.io/patrickcarmichael/changedetection-mcp-server:latest
    restart: always
    environment:
      CHANGEDETECTION_URL: ${CHANGEDETECTION_URL}
      CHANGEDETECTION_API_KEY: ${CHANGEDETECTION_API_KEY}
      LOG_LEVEL: INFO
      RATE_LIMIT_ENABLED: "true"
      ENABLE_METRICS: "true"
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M
```

### Kubernetes

**Best for:** Large-scale production deployments

#### Deployment Manifest

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: changedetection-mcp-server
  labels:
    app: mcp-server
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mcp-server
  template:
    metadata:
      labels:
        app: mcp-server
    spec:
      containers:
      - name: mcp-server
        image: ghcr.io/patrickcarmichael/changedetection-mcp-server:latest
        ports:
        - containerPort: 8000
          name: http
        - containerPort: 9090
          name: metrics
        env:
        - name: CHANGEDETECTION_URL
          valueFrom:
            configMapKeyRef:
              name: mcp-config
              key: changedetection-url
        - name: CHANGEDETECTION_API_KEY
          valueFrom:
            secretKeyRef:
              name: mcp-secrets
              key: api-key
        - name: LOG_LEVEL
          value: "INFO"
        - name: RATE_LIMIT_ENABLED
          value: "true"
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          exec:
            command:
            - python
            - healthcheck.py
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          exec:
            command:
            - python
            - healthcheck.py
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-server
  labels:
    app: mcp-server
spec:
  type: ClusterIP
  ports:
  - port: 8000
    targetPort: 8000
    name: http
  - port: 9090
    targetPort: 9090
    name: metrics
  selector:
    app: mcp-server
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: mcp-config
data:
  changedetection-url: "http://changedetection:5000"
---
apiVersion: v1
kind: Secret
metadata:
  name: mcp-secrets
type: Opaque
stringData:
  api-key: "your-api-key-here"
```

#### Deploy to Kubernetes

```bash
# Create namespace
kubectl create namespace mcp

# Apply manifests
kubectl apply -f k8s/ -n mcp

# Check deployment
kubectl get pods -n mcp
kubectl logs -f deployment/changedetection-mcp-server -n mcp
```

### Vercel Serverless

**Best for:** Serverless deployments with automatic scaling

#### Setup

1. **Install Vercel CLI:**
   ```bash
   npm i -g vercel
   ```

2. **Configure project:**
   ```bash
   vercel login
   vercel link
   ```

3. **Set environment variables:**
   ```bash
   vercel env add CHANGEDETECTION_URL
   vercel env add CHANGEDETECTION_API_KEY
   ```

4. **Deploy:**
   ```bash
   vercel --prod
   ```

#### Vercel Configuration

The `vercel.json` is already configured. Ensure you have:

```json
{
  "version": 2,
  "builds": [
    {
      "src": "api/serverless.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/api/(.*)",
      "dest": "api/serverless.py"
    }
  ],
  "env": {
    "CHANGEDETECTION_URL": "@changedetection-url",
    "CHANGEDETECTION_API_KEY": "@changedetection-api-key"
  }
}
```

### AWS Lambda

**Best for:** AWS-native serverless deployments

#### Using AWS SAM

```yaml
# template.yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Globals:
  Function:
    Timeout: 30
    MemorySize: 512
    Runtime: python3.11

Resources:
  MCPServerFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: ./
      Handler: api.serverless.handler
      Events:
        MCPApi:
          Type: Api
          Properties:
            Path: /api
            Method: POST
      Environment:
        Variables:
          CHANGEDETECTION_URL: !Ref ChangedetectionUrl
          CHANGEDETECTION_API_KEY: !Ref ChangedetectionApiKey
          LOG_LEVEL: INFO

Parameters:
  ChangedetectionUrl:
    Type: String
    Description: Changedetection.io URL
  ChangedetectionApiKey:
    Type: String
    Description: API Key
    NoEcho: true

Outputs:
  ApiUrl:
    Description: API Gateway endpoint URL
    Value: !Sub "https://${ServerlessRestApi}.execute-api.${AWS::Region}.amazonaws.com/Prod/api/"
```

Deploy:
```bash
sam build
sam deploy --guided
```

---

## Security Considerations

### API Key Management

- **Never commit API keys** to version control
- Use secrets management services:
  - AWS Secrets Manager
  - Azure Key Vault
  - HashiCorp Vault
  - Kubernetes Secrets

### Network Security

```bash
# Docker network isolation
docker network create mcp-network --internal

# Kubernetes NetworkPolicy
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: mcp-server-network-policy
spec:
  podSelector:
    matchLabels:
      app: mcp-server
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          role: frontend
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: changedetection
```

### Rate Limiting

Configure appropriate rate limits based on your load:

```bash
# For high-traffic environments
RATE_LIMIT_PER_MINUTE=300
RATE_LIMIT_BURST=50

# For development
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_BURST=10
```

### CORS Configuration

```bash
# Production - specify exact origins
ENABLE_CORS=true
ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com

# Development
ALLOWED_ORIGINS=*
```

---

## Monitoring & Observability

### Health Checks

```bash
# Check health
python healthcheck.py

# Docker health check
docker exec mcp-server python healthcheck.py

# Kubernetes
kubectl exec -it <pod-name> -- python healthcheck.py
```

### Prometheus Metrics

Access metrics at:
- Local: `http://localhost:9090/metrics`
- Docker: `http://mcp-server:9090/metrics`

Example queries:
```promql
# Request rate
rate(mcp_requests_total[5m])

# Error rate
rate(mcp_requests_failed[5m])

# Average latency
rate(mcp_total_duration_ms[5m]) / rate(mcp_requests_success[5m])
```

### Logging

Structured JSON logs for easy parsing:

```bash
# View logs
docker-compose logs -f mcp-server

# Filter by level
docker-compose logs mcp-server | jq 'select(.level=="ERROR")'

# Get request duration stats
docker-compose logs mcp-server | jq -r '.duration_ms' | awk '{sum+=$1; count++} END {print "Avg:", sum/count}'
```

### Grafana Dashboards

Import pre-built dashboards:
1. Access Grafana at `http://localhost:3000`
2. Login (admin/admin)
3. Import dashboard JSON from `monitoring/grafana/dashboards/`

---

## Scaling

### Horizontal Scaling

**Docker Swarm:**
```bash
docker service scale mcp-server=5
```

**Kubernetes:**
```bash
kubectl scale deployment mcp-server --replicas=5

# Or use HPA
kubectl autoscale deployment mcp-server --cpu-percent=70 --min=3 --max=10
```

### Load Balancing

**Nginx:**
```nginx
upstream mcp_backend {
    least_conn;
    server mcp-server-1:8000 max_fails=3 fail_timeout=30s;
    server mcp-server-2:8000 max_fails=3 fail_timeout=30s;
    server mcp-server-3:8000 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    server_name mcp.example.com;

    location / {
        proxy_pass http://mcp_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Troubleshooting

### Common Issues

#### Connection Refused

```bash
# Check if changedetection.io is running
curl http://localhost:5000/api/v1/systeminfo

# Check network connectivity
docker-compose exec mcp-server ping changedetection

# Verify environment variables
docker-compose exec mcp-server env | grep CHANGEDETECTION
```

#### Rate Limit Errors

```bash
# Increase rate limits
export RATE_LIMIT_PER_MINUTE=300

# Or disable temporarily
export RATE_LIMIT_ENABLED=false
```

#### Memory Issues

```bash
# Check memory usage
docker stats mcp-server

# Increase memory limit
docker-compose up -d --scale mcp-server=3 --memory=1g
```

### Debug Mode

Enable debug mode for detailed logging:

```bash
export DEBUG=true
export LOG_LEVEL=DEBUG
docker-compose up -d
docker-compose logs -f mcp-server
```

### Health Check Failures

```bash
# Run detailed health check
docker-compose exec mcp-server python healthcheck.py | jq

# Check specific components
curl -X POST http://localhost:8000/api/serverless \
  -H "Content-Type: application/json" \
  -d '{"action":"health_check","params":{}}'
```

---

## Backup & Recovery

### Configuration Backup

```bash
# Backup environment
cp .env .env.backup

# Backup volumes
docker-compose down
tar -czf backup.tar.gz data/ logs/
```

### Disaster Recovery

```bash
# Restore from backup
tar -xzf backup.tar.gz
cp .env.backup .env
docker-compose up -d
```

---

## Support

For issues and questions:
- GitHub Issues: https://github.com/patrickcarmichael/changedetection-mcp-server/issues
- Documentation: README.md

---

Made with ❤️ for production environments
