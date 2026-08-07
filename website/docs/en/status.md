---
title: Service Status
description: Definitions and incident channels for the RunBuoy Global service and self-hosted deployments.
---

# Service status

RunBuoy does not currently publish an uptime percentage or a historical status dashboard. This page documents observable service endpoints and incident channels; it does not claim that the service is operational at the moment you read it.

## Global service

The hosted API base URL is `https://api.runbuoy.cloud`.

| Check | Meaning | What it does not guarantee |
| --- | --- | --- |
| [`/healthz`](https://api.runbuoy.cloud/healthz) | The API process is reachable and can return its configured region. | Database readiness, queue processing, push delivery, or end-to-end availability. |
| [`/readyz`](https://api.runbuoy.cloud/readyz) | The API reports that required application dependencies and migrations are ready to serve requests. | APNs delivery, a particular device connection, or future availability. |

An HTTP error, timeout, or failing readiness component is a useful diagnostic signal, not a complete incident assessment. Report suspected Global service incidents through [GitHub Issues](https://github.com/TANG617/RunBuoy/issues) without including tokens, pairing codes, or private run data.

Security incidents belong in [private vulnerability reporting](https://github.com/TANG617/RunBuoy/security/advisories/new), not a public issue.

## Self-hosted deployments

Self-hosted installations do not inherit the Global service status. Operators should monitor their own `/healthz` and `/readyz` endpoints, database, worker, APNs configuration, storage, backups, and retention jobs. The [self-hosting guide](/en/self-hosting) describes the deployment boundary.
