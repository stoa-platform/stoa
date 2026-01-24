# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.x.x   | :white_check_mark: |
| 1.x.x   | :x:                |

## Reporting a Vulnerability

We take the security of STOA Platform seriously. If you believe you have found a security vulnerability, please report it to us as described below.

### How to Report

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to:
- **Email**: security@gostoa.dev

Please include the following information in your report:

- Type of issue (e.g., buffer overflow, SQL injection, cross-site scripting, etc.)
- Full paths of source file(s) related to the manifestation of the issue
- The location of the affected source code (tag/branch/commit or direct URL)
- Any special configuration required to reproduce the issue
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

### Response Process

1. **Acknowledgment**: We will acknowledge receipt of your vulnerability report within 48 hours.
2. **Assessment**: Our security team will assess the vulnerability and determine its severity.
3. **Fix Development**: We will work on a fix for verified vulnerabilities.
4. **Disclosure**: Once the fix is ready, we will coordinate disclosure timing with you.

### Safe Harbor

We support responsible disclosure and will not take legal action against researchers who:

- Make a good faith effort to avoid privacy violations, destruction of data, and interruption of our services
- Only interact with accounts they own or with explicit permission
- Do not exploit a security issue beyond the minimum necessary to demonstrate it
- Report findings to us before disclosing them publicly

## Security Best Practices

When deploying STOA Platform:

1. **Use TLS everywhere** - All external endpoints should use HTTPS
2. **Rotate secrets regularly** - API keys, tokens, and passwords should be rotated
3. **Apply least privilege** - Use RBAC to limit access to minimum required
4. **Keep dependencies updated** - Regularly update all dependencies
5. **Monitor audit logs** - Review authentication and authorization events
6. **Use network policies** - Implement Kubernetes network policies for isolation

## Security Features

STOA Platform includes the following security features:

- **OIDC Authentication** via Keycloak
- **Role-Based Access Control (RBAC)** with four predefined roles
- **Multi-tenant isolation** with namespace separation
- **OPA Policy Engine** for fine-grained authorization
- **Audit logging** for all API operations
- **Secret management** via HashiCorp Vault integration
