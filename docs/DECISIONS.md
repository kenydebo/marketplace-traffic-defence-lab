# Engineering decisions

## Explainability before automatic enforcement

Use a small Python recommender and committed synthetic fixtures. Each candidate can be reproduced from an input hash, baseline percentile and declared margin. Labels define lab ground truth and evaluation outcomes; HTTP 200, logged-in status, or a browser fingerprint do not establish legitimate intent in production. A separate holdout prevents choosing settings solely on the reported validation results. Holdout failure means insufficient evidence. Recommendations never promote themselves to Block.

## Separate policy layers

WAF handles endpoint-scoped edge observations, source restrictions, synthetic enforcement and TLS fingerprint context. The app handles verified identity and bounded query cost. App token-bucket replay cannot predict exact WAF behaviour: its rate rules use trailing windows and approximate enforcement. Count-mode evidence is a separate deployment gate. Shared browser JA4 values are explicitly present in both legitimate and abusive fixtures, so fingerprint-only blocking is excluded.

## Identity, fairness and evasion

Signed anonymous sessions preserve browsing allowance across app instances and reduce shared-IP buyer interference. They are not anti-bot proof. Session issuance is source-limited, but address rotation and new signed sessions remain bypasses. Product IDs share a route key, preventing per-ID quota resets. Login/session source limits deliberately expose the NAT trade-off in holdout evaluation. A future production design needs known integration identities, session integrity controls, business capacity signals and evidence across distributed sources.

## Availability and consistency

Redis Lua serializes one key's allowance updates on one primary. Atomicity is not durability across failover or a multi-region guarantee. On an outage, sensitive routes return 503 and browsing receives a small independent local allowance. Adding instances increases that fallback allowance, which is explicitly documented. Thread-per-request Python is adequate for a bounded fixture API, not a production server/load benchmark. There is no payment or inventory state.

## Private origin and cost-bounded topology

CloudFront VPC origin reaches an internal ALB. The origin secret authenticates forwarded metadata; network restrictions and the secret are layered. Fargate public IPs provide egress only, avoiding NAT cost; ingress is ALB-only. Redis uses TLS/authentication and encryption at rest. Private origin HTTP is a disclosed simplification. No custom domain, public admin endpoint or tunnel to a personal machine is required.

## Responsibilities and promotion gates

Proposed responsibilities: Security owns the detection hypothesis and evidence; the service owner validates capacity and buyer journeys; platform/SRE validates dependency failure and rollback; product reviews legitimate impact. These are hypothetical lab responsibilities, not accepted ownership at Faire.

Promotion needs representative labelled/triaged traffic, endpoint capacity measurements, segment-specific buyer-impact review, exclusions for approved integrations, versioned policy review, observation evidence, a narrow rollout, and an explicit rollback condition. The lab's 1% budget is a demonstration setting, not a business-approved production tolerance.
