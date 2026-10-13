# Five-minute demonstration

1. **Explain the buyer journey.** The sample API serves catalog/product/search requests, issues a signed anonymous session, authenticates one fixture account, and accepts a synthetic cart item. No real storefront, inventory or payment data exists.
2. **Show distributed enforcement.** Open the local integration evidence. Forty requests across two real app instances share one Redis allowance. Explain why two independent counters would double the initial allowance. Show the malformed-session and product-ID rotation checks.
3. **Review a recommendation.** Choose Catalog in the dashboard. Explain trusted calibration, the bounded candidate grid and labelled validation. Switch to the separate holdout. The replay result is synthetic, and the proposed edge rule remains Count.
4. **Show a recommendation that fails.** Choose Login, then the holdout. Its selected candidate passed validation but rejected 3.3% of legitimate holdout requests, above the explicit 1% lab budget. Withhold the proposal and discuss shared-network fairness, rather than hiding the adverse result.
5. **Show cloud evidence and rollback.** Read the actual AWS evidence type and checks. Identify CloudFront/WAF, the private ALB, application tasks and Redis. The separate rate probe exercises enforcement, then reverts to Count; it does not claim production calibration. Verify cleanup. Explain that a service owner must approve capacity and buyer-impact assumptions before a real rollout.

## Questions to defend

**What recommends the rules?** Our Python script: explicit percentile calculations, bounded candidates, labelled replay and a separate holdout. Its logic is reviewable. No ML classifier or external detection product decides policy.

**Can it recommend from arbitrary production logs?** Not responsibly yet. Live logs provide descriptive evidence, but unlabelled traffic does not supply ground truth or establish a trusted buyer baseline. The collector reports insufficient evidence rather than inventing detection accuracy. A production extension needs representative triage/labels and measured capacity.

**Why Redis and WAF?** WAF operates before the backend. Redis coordinates app limits using verified identity and query cost. They enforce different policies. WAF trailing-window enforcement is approximate; app Lua atomicity is scoped to one primary.

**What does JA4 prove?** A TLS-stack fingerprint is investigation context, not identity or malicious intent. A browser fingerprint appears in legitimate and abusive synthetic journeys. Our recommendation never blocks on that signal alone.

**What remains vulnerable?** Slow/distributed abuse, source/session rotation, fingerprint impersonation, and quota state loss on Redis failure/failover. The failure experiment demonstrates limited per-instance browsing availability and sensitive-route rejection, not global enforcement during outages.

**Where is the staff-level contribution?** Choosing measurable hypotheses, exposing buyer impact, assigning proposed responsibilities, withholding unsafe changes, separating enforcement layers, and shipping evidence with a rollback path. Portfolio lab results are not claimed as production experience at Faire.
