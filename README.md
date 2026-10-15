# Marketplace Traffic Defence Lab

I built this demo to test endpoint traffic controls and review buyer impact before enforcement.

[Open dashboard](https://kenydebo.github.io/marketplace-traffic-defence-lab/) · [AWS validation](https://github.com/kenydebo/marketplace-traffic-defence-lab/actions/runs/38456472401)

```mermaid
flowchart TB
    subgraph Demo[Demonstrated lab]
        Visitor[Visitor] --> WAF[CloudFront + AWS WAF]
        WAF --> ALB[Private load balancer]
        ALB --> App[Two application instances]
        App <-->|Shared allowance| Redis[Private Redis]
        WAF --> Logs[WAF + application logs]
        App --> Logs
        Logs --> Dashboard[Dashboard: saved evidence]
        Sample[Labelled sample traffic] --> Script[Python rule proposals]
        Script --> Dashboard
        Script -->|Eligible Count proposals| WAF
    end
    subgraph Extension[Possible production extension]
        Detect[Python detections OR SIEM]
        Review[Investigate + propose new rule]
        SOAR[Optional SOAR: approvals, deployment, rollback]
        Live[Live dashboard: rule matches + buyer impact]
        Detect -.-> Review
        Review -.-> SOAR
        Live -.-> Review
    end
    Logs -.-> Detect
    Logs -.-> Live
    SOAR -.->|Deploy rule in Count| WAF
```

**Solid arrows:** demonstrated lab. **Dashed arrows:** possible extensions. Demo recommendations use labelled sample traffic; its dashboard displays saved results.

**Verified 13 October 2026:** 18 AWS checks, 12 local integration checks and six recommendation tests passed. AWS resources were removed and cleanup verified.

[Setup and design](docs/IMPLEMENTATION.md) · [Walkthrough](docs/DEMO.md) · [Runbook](docs/RUNBOOK.md)
