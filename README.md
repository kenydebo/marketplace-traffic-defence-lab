# Marketplace Traffic Defence Lab

I built this lab to test traffic controls for a marketplace without losing sight of the buyer. It brings together endpoint policy review, shared application limits, AWS WAF and evidence from an actual deployment.

[Open the dashboard](https://kenydebo.github.io/marketplace-traffic-defence-lab/) · [View the successful AWS run](https://github.com/kenydebo/marketplace-traffic-defence-lab/actions/runs/38456472401)

## What it demonstrates

- **Shared limits:** two application instances use the same Redis allowance, so adding an instance does not double a visitor's budget.
- **Endpoint controls:** browsing, product requests, search, login and cart activity have different limits and costs.
- **Buyer impact:** proposed application limits are tested against labelled examples and a separate dataset before an observation proposal is accepted.
- **Controlled rollout:** eligible WAF rules stay in Count mode. A separate test exercises blocking and rollback.

## Results

On 13 October 2026, **18 AWS checks, 12 local integration checks and six recommendation tests passed**.

In AWS, 40 requests across both application instances shared one allowance: 13 succeeded and 27 were rate limited. WAF logs confirmed the test blocks. Both AWS stacks were deleted and cleanup verified.

The login proposal was withheld: it rejected 3.3% of legitimate requests in the separate test dataset, above the lab's 1% budget.

## Scope

Recommendations use generated, labelled traffic. The script proposes rate limits; it does not identify malicious visitors from live logs. WAF thresholds come from the normal traffic baseline and require observation before enforcement. JA4 is supporting context, never a reason to block on its own.

The dashboard displays saved evidence. The disposable AWS environment has been removed.

## Possible production extension

I would add Python detections or integrate with a SIEM to flag suspicious traffic. After investigation, I would create endpoint-specific WAF rules, deploy them in Count mode, and use a live dashboard to review rule matches and potential buyer impact before enforcement. SOAR could coordinate approvals, deployment and rollback.

## Run it

[Local setup and AWS deployment](docs/IMPLEMENTATION.md#run-it) · [Five-minute walkthrough](docs/DEMO.md) · [Runbook](docs/RUNBOOK.md) · [Evidence](docs/EVIDENCE.md) · [Security](SECURITY.md)

Python · AWS CloudFront/WAF · Fargate · Redis · CloudFormation
