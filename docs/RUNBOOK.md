# Disposable lab operating runbook

## Normal operation

Refresh the GitHub AWS secrets (including the session token when supplied by the lab), update the expected account variable if the provider issued another account, and run the manual AWS workflow. Region is us-east-1. The runner discovers its source IPv4 /32 and supported availability zones. Application credentials are generated in Secrets Manager.

The verified GitHub run took about 30 minutes including creation, testing and cleanup. Allow time for CloudFront and Redis provisioning/deletion; the static dashboard can be demonstrated without keeping AWS resources running.

Only synthetic traffic targets this run's endpoint: one 40-request shared-limiter experiment and at most 120 requests for a separate scoped WAF probe, plus a small number of functional checks. The environment is not opened as a public interactive API or volumetric attack service.

Download `marketplace-sanitized-evidence` from the completed run. Inspect every check and cleanup status. Publishing new evidence requires reviewing the sanitized JSON and committing it under `site/data/aws.json`; no raw logs or private inventory are published.

## Cleanup and failure recovery

The workflow's always-run cleanup step removes only the two stacks listed in its run inventory after checking the project tag and strict naming pattern. CloudFormation waits for deletion and verifies absence. ECR is disposable and its owned images are deleted with its repository. AWS-generated secrets belong to the stack; Secrets Manager may schedule their final physical purge according to its service behaviour.

For a local run, use the same credentials and `python3 scripts/aws_lab.py cleanup`; ignored `.local/aws-run.json` contains the owned inventory. Do not delete it before cleanup.

If a GitHub runner is lost or cancelled, use the AWS console to find **only** `marketplace-traffic-lab-<GITHUB_RUN_ID>` and `marketplace-traffic-image-<GITHUB_RUN_ID>` carrying `Project=marketplace-traffic-defence-lab`. Delete the application stack first, then the image stack, and verify both are absent. If credentials expired, refresh them for the same account first; a new account cannot clean up an older account. Do not delete unrelated stacks, provider IAM roles or account-wide CloudFront resources. Provider expiry is a fallback, not evidence of verified cleanup.

## WAF rollback

The synthetic enforcement probe alone uses the `ProbeMode` parameter. Re-deploy the same template and parameters with `ProbeMode=Count`; the test uses `finally` to attempt this even on failure. Recommended endpoint policies and JA4 observations remain Count throughout. Deleting the entire disposable stack is the final recovery step.

## Dependency outage

Local test stops Redis, verifies bounded browsing and sensitive-route 503s, then restarts it. AWS dependency outage/failover is not exercised automatically. Confirm rate-limit mode in app events; do not interpret fallback responses as shared enforcement.
