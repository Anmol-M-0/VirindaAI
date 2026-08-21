# Security Model

Marina is a local-first assistant, but local does not mean untrusted code should receive unrestricted authority. The security model is therefore built around **local boundaries, explicit authority, bounded data access, and auditable actions**.

## Trust zones

```text
Trusted local control plane
    ├─ Marina application service
    ├─ SQLite
    └─ local Unix socket (0600)

OVOS runtime boundary
    ├─ message bus
    ├─ listener
    ├─ core
    ├─ audio
    └─ skills

Explicitly authorized tools
    ├─ filesystem
    ├─ browser/network
    ├─ clipboard
    ├─ applications
    └─ future desktop/system actions

External systems
    ├─ OpenAI-compatible endpoints
    ├─ optional remote services
    └─ future satellites
```

## IPC

Marina's local Unix socket is permissioned `0600`. It should not be replaced with an unauthenticated TCP server.

The OVOS message bus is treated as a local/private control boundary. Do not expose it directly to untrusted networks. OVOS documents the bus as the central local IPC mechanism for its services.

## Tool authority

Every tool has a risk class:

- `read` — informational, normally allowed.
- `local_write` — changes local state, requires explicit approval.
- `external` — communicates with an external system, requires policy/approval as configured.
- `destructive` — can cause irreversible consequences, requires explicit approval and should receive additional UI confirmation.

Approval tokens are short-lived and single-use.

## Network safety

Browser/network tools validate targets and redirect destinations. Private, loopback, link-local, multicast, reserved, unspecified, and credential-bearing URLs are rejected.

This prevents common SSRF and credential-leak patterns but does not make arbitrary websites safe. The network boundary remains an external trust zone.

## Filesystem safety

The default write root is Marina's own data directory. Additional write roots are explicitly configured.

Avoid broad roots such as `/`, `/home`, removable volumes, or secrets directories unless the deployment intentionally requires that authority.

## Secrets

Never persist API keys into:

- SQLite conversation rows
- semantic event payloads
- audit summaries
- chat transcripts
- README/examples
- source-controlled configuration

Use the process environment, OS keyring, or another secret manager appropriate to the deployment.

## Privacy modes

Private mode is a policy state with persistence consequences. It disables durable transcript/context persistence and should also suppress optional proactive/capture features that would surprise a user.

When adding a new feature, document whether it can observe or persist:

- microphone audio
- transcript text
- screenshots
- camera frames
- clipboard text
- active-window metadata
- external API payloads

## Audit

Tool execution is logged locally with tool name, risk class, approval state, success/failure, and a short summary. Audit logs must not contain full secrets or unnecessarily sensitive payloads.

## Remote/satellite boundary

Future cross-device transports must authenticate and replay-protect messages. The current `SatelliteEnvelope` uses timestamps/nonces and HMAC verification as a transport primitive; it is not a substitute for an established OVOS/HiveMind production deployment.


## Broker trust boundary

The OVOS MessageBus and the Marina JobBroker are separate trust domains. The local OVOS bus is not a remote transport. If NATS is enabled across hosts, use TLS and scoped credentials, limit subjects per worker, and never place secrets or arbitrary shell commands into job payloads. Every consequential job must carry an idempotency key and approval state where required.
