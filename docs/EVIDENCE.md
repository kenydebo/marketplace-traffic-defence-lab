# Evidence and claim boundaries

`site/data/integration.json` records an actual local two-instance/Redis test. `site/data/recommendations.json` records synthetic replay and holdout metrics. `site/data/aws.json`, when present, records a new full-stack deployment attempt or live checks and cleanup. They are different evidence sources and should never be combined into a production efficacy claim.

The earlier interview exercise separately verified CloudFront/WAF with a mock API Gateway origin: normal traffic 200, synthetic marker 403, direct-origin guard 403, source-IP catalog blocking attributed to WAF logs, JA3/JA4 unchanged across User-Agent changes in one Python TLS stack, different curl fingerprints, and Count rollback. That earlier stack was deleted. It did not have ALB, Redis or an application fleet. Its raw account/IP-bearing files remain outside this public repository and are not copied into the dashboard.

Synthetic recommendation scenarios include a common fingerprint used by both legitimate and abusive traffic. The algorithm never blocks because of that value. Scenario fingerprints are descriptive fixture names, not real TLS hashes or AWS match values. Ground-truth labels are controlled by the generator and withheld from runtime enforcement.

Live WAF/app aggregates remove raw addresses, headers, account/resource identifiers and request bodies. Unlabelled live events can show controls operating, but do not establish a trusted legitimate baseline or production bot accuracy. Consequently their recommendation status is `insufficient_evidence_unlabelled_live_traffic`.

Cloud snapshots preserve the recommendation dataset hash used for that deployment. The committed history provides the matching fixture version. Later descriptive fixture corrections can change the dataset hash without changing generated policy settings; compare the versioned CloudFormation template when assessing deployment evidence. Log delivery is asynchronous, so a bounded log snapshot may be incomplete.

Structured app events include route, status, cost, limiter mode, pseudonymous actor/resource, instance, processing time, trace, and validated trusted edge JA4 when available. Not every edge event reaches the app; aggregate the two sources separately. Trace correlation requires trusted ingress handling and should not be assumed from a client-supplied value. App processing time excludes client/edge/network latency.
