# Security Policy

## Supported Versions

We release patches for security vulnerabilities for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take the security of changedetection-mcp-server seriously. If you believe you have found a security vulnerability, please report it to us as described below.

### Where to Report

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to:
- **Email:** security@patrickcarmichael.com
- **Subject:** [SECURITY] changedetection-mcp-server vulnerability

### What to Include

Please include the following information:
- Type of vulnerability
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the vulnerability
- Any potential mitigations you've identified

### Response Timeline

- **Initial Response:** Within 48 hours
- **Status Update:** Within 7 days
- **Fix Timeline:** Depends on severity
  - Critical: 7-14 days
  - High: 14-30 days
  - Medium: 30-60 days
  - Low: Next release cycle

## Security Best Practices

### API Key Management

#### ✅ DO:
- Store API keys in environment variables
- Use secrets management services (AWS Secrets Manager, Azure Key Vault, etc.)
- Rotate API keys regularly (every 90 days recommended)
- Use different API keys for different environments
- Revoke compromised keys immediately

#### ❌ DON'T:
- Commit API keys to version control
- Share API keys in plain text
- Log API keys
- Include API keys in error messages
- Use the same key across environments

### Network Security

#### Docker Deployment

```bash
# Use internal networks
docker network create --internal mcp-network

# Limit exposed ports
docker run -p 127.0.0.1:8000:8000 changedetection-mcp-server
```

#### Kubernetes Deployment

```yaml
# Use NetworkPolicies
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: mcp-server-netpol
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
          role: authorized-client
```

### Input Validation

The server includes built-in input validation:

- URL validation for website monitoring
- UUID format validation for watch IDs
- String sanitization to prevent injection
- Maximum length enforcement
- Character filtering

### Rate Limiting

Enable rate limiting in production:

```bash
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_BURST=10
```

### CORS Configuration

Restrict CORS in production:

```bash
# ❌ Don't use in production
ALLOWED_ORIGINS=*

# ✅ Use specific origins
ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com
```

### Logging Security

#### Safe Logging Practices:

```python
# ✅ DO: Log without sensitive data
logger.info(f"Request to {endpoint}")

# ❌ DON'T: Log sensitive data
logger.info(f"API Key: {api_key}")  # NEVER DO THIS
```

The server uses structured logging that automatically filters sensitive information.

### Container Security

#### Dockerfile Best Practices (Already Implemented):

- ✅ Multi-stage builds
- ✅ Non-root user
- ✅ Minimal base image (slim)
- ✅ No package caches
- ✅ Security labels
- ✅ Health checks

#### Additional Recommendations:

```bash
# Scan images for vulnerabilities
docker scan ghcr.io/patrickcarmichael/changedetection-mcp-server:latest

# Or use Trivy
trivy image ghcr.io/patrickcarmichael/changedetection-mcp-server:latest

# Run with read-only filesystem
docker run --read-only --tmpfs /tmp changedetection-mcp-server
```

### Dependency Security

#### Automated Scanning

The CI/CD pipeline includes:
- Bandit (Python security linter)
- Safety (dependency vulnerability scanner)
- Trivy (container vulnerability scanner)

#### Manual Checks

```bash
# Check for known vulnerabilities
safety check

# Security audit
bandit -r . -f json -o security-report.json

# Update dependencies
pip list --outdated
```

### Authentication & Authorization

#### API Key Validation

```python
# API keys are validated on every request
headers = {"x-api-key": api_key}
```

#### Future Enhancements (Roadmap):

- OAuth 2.0 support
- JWT token authentication
- Role-based access control (RBAC)
- API key scoping

## Security Features

### Current Implementation

| Feature | Status | Description |
|---------|--------|-------------|
| Input Sanitization | ✅ | Prevents injection attacks |
| Rate Limiting | ✅ | Prevents abuse |
| CORS Protection | ✅ | Configurable cross-origin policies |
| Structured Logging | ✅ | No sensitive data leakage |
| Health Checks | ✅ | Validates security configuration |
| Container Hardening | ✅ | Non-root user, minimal attack surface |
| Secret Management | ✅ | Environment-based configuration |
| TLS/SSL | ⚠️ | Recommended at reverse proxy level |

### Planned Features

- [ ] API key rotation API
- [ ] Audit logging
- [ ] IP allowlisting
- [ ] Request signing
- [ ] Encrypted configuration support

## Vulnerability Disclosure Policy

We follow responsible disclosure principles:

1. **Private Disclosure:** Report security issues privately first
2. **Investigation:** We investigate and validate the report
3. **Fix Development:** We develop and test a fix
4. **Coordinated Release:** We coordinate public disclosure
5. **Credit:** We credit reporters (unless they prefer anonymity)

### Hall of Fame

We recognize security researchers who responsibly disclose vulnerabilities:

<!-- Will be updated as vulnerabilities are reported and fixed -->

## Security Updates

Subscribe to security updates:
- Watch this repository for releases
- Enable GitHub security alerts
- Follow [@patrickcarmichael](https://github.com/patrickcarmichael)

## Compliance

### Standards Adherence

- **OWASP Top 10:** Mitigations implemented for common vulnerabilities
- **CWE/SANS Top 25:** Protection against most dangerous software errors
- **NIST Cybersecurity Framework:** Aligned security practices

### Certifications

Currently pursuing:
- SOC 2 Type II compliance
- GDPR compliance for data handling

## Security Checklist for Deployment

Before deploying to production:

- [ ] API keys stored securely (not in code)
- [ ] Rate limiting enabled
- [ ] CORS configured with specific origins
- [ ] TLS/SSL enabled (at load balancer/reverse proxy)
- [ ] Container running as non-root user
- [ ] Security scanning completed
- [ ] Network policies configured
- [ ] Logging configured (no sensitive data)
- [ ] Health checks enabled
- [ ] Monitoring and alerting configured
- [ ] Backup and recovery plan in place
- [ ] Incident response plan documented

## Resources

### Internal Documentation

- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment best practices
- [README.md](README.md) - General documentation
- [healthcheck.py](healthcheck.py) - Health check implementation

### External Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [Kubernetes Security](https://kubernetes.io/docs/concepts/security/)
- [Python Security](https://python.readthedocs.io/en/stable/library/security_warnings.html)

## Contact

For security concerns:
- **Email:** security@patrickcarmichael.com
- **GPG Key:** Available upon request

For general questions:
- **GitHub Issues:** https://github.com/patrickcarmichael/changedetection-mcp-server/issues

---

**Note:** This security policy is subject to change. Please check back regularly for updates.

Last Updated: 2025-11-01
