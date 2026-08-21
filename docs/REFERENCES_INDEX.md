# External References

Marina intentionally depends on a small set of upstream contracts rather than importing the whole ecosystem indiscriminately.

## OVOS core references

- [OVOS release tracker / constraints](https://github.com/OpenVoiceOS/OpenVoiceOS) — compatibility/version-channel source of truth.
- [OVOS installation guide](https://github.com/OpenVoiceOS/OpenVoiceOS/blob/main/docs/installation.md) — supported pip/constraints installation model.
- [OVOS architecture specifications](https://github.com/OpenVoiceOS/architecture) — formal voice-OS data/interaction contracts.
- [OVOS message bus](https://github.com/OpenVoiceOS/ovos-messagebus) — local event transport.
- [OVOS bus client](https://github.com/OpenVoiceOS/ovos-bus-client) — Python client boundary.
- [OVOS test harness](https://github.com/OpenVoiceOS/ovos-test-harness) — cross-repository conformance/integration testing.

## Deployment references

- [OVOS installer](https://github.com/OpenVoiceOS/ovos-installer) — reference deployment path for a full OVOS installation.

## Marina rule

When an upstream project changes, update the compatibility matrix and reference documentation before changing Marina's production dependency set.
