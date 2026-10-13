# Security boundaries

This repository is a synthetic educational lab. No payment, persistent cart, inventory data, production identity provider or security SLA is implemented. Do not target third-party services or deploy it as a production storefront.

The public dashboard is static, read-only, and contains sanitized evidence. It cannot mutate AWS policies or receive credentials. Session/origin/Redis/login secrets stay server-side. `.env`, `.local`, credential files and raw logs are ignored. Never commit AWS session tokens, CloudFormation resolved secret values or customer logs. GitHub Actions logs and artifacts must exclude secrets and raw WAF records.

Bearer sessions use HMAC, short expiry and constant-time signature checks; this is a bounded fixture mechanism, not a full identity platform. It has no refresh, revocation or cross-tenant authorization model. No ambient authentication cookies or permissive CORS are used. Arbitrary account headers grant no identity. Input size, route, method, search cost and cart quantity are bounded. The origin secret gates trusted CloudFront metadata. The application must not trust arbitrary X-Forwarded-For or client-supplied fingerprint values.

Redis atomicity holds on one primary. Global quotas, failover durability, distributed bot resistance and production throughput remain out of scope. Bounded browsing fallback is per instance. Anonymous session rotation, address rotation, fingerprint impersonation and low-rate abuse remain residual risks.

Responsible reports: open a GitHub issue with sanitized reproduction details for this lab. Never include credentials, personal data or targets outside the owned demonstration environment.
