# OVOS Compatibility Policy

Virinda does **not** treat every repository in the OpenVoiceOS organization as a compatible dependency.
OVOS is a multi-repository ecosystem coordinated by release-channel constraints. The supported Virinda profile
must be assembled from one coherent OVOS release channel, not from arbitrary latest versions.

## Current decision

**Production default: OVOS stable channel + legacy Persona/OpenAI solver API.**

The current upstream stable constraints pin these core components to compatible minor-release ranges:

| Component | Stable constraint | Virinda role | Status |
|---|---|---|---|
| `ovos-core` | `>=1.3.1,<1.4.0` | assistant core | supported |
| `ovos-dinkum-listener` | `>=0.4.0,<0.5.0` | wake/VAD/STT lifecycle | supported |
| `ovos-audio` | `>=0.4.0,<0.5.0` | output/TTS lifecycle | supported |
| `ovos-plugin-manager` | `>=0.9.0,<0.10.0` | plugin loading | supported |
| `ovos-persona` | `>=0.6.23,<0.7.0` | conversation routing | supported |
| `ovos-openai-plugin` | `>=2.0.3,<2.1.0` | OpenAI-compatible LLM solver | supported in legacy solver mode |
| `ovos-ww-plugin-openwakeword` | `>=0.4.1,<0.5.0` | wake word | supported |
| `ovos-vad-plugin-silero` | `>=0.0.5,<0.1.0` | VAD | supported |
| `ovos-microphone-plugin-alsa` | `>=0.1.2,<0.2.0` | Linux capture | supported |
| `ovos-stt-plugin-whispercpp` | external to stable constraints | local STT | Virinda-tested add-on |

These ranges are taken from the current OVOS stable constraints. OVOS explicitly recommends installing with a
constraints file because the repositories are released independently. See the upstream constraints and installation
manual in `docs/REFERENCES.md`.

## Why the newer agent configuration is not the default

The current development line of `ovos-openai-plugin` has migrated from the legacy solver API to the new agent
framework. It requires `ovos-plugin-manager>=2.2.3a1` and `ovos-persona>=0.9.0a1`, and uses
`ovos-chat-openai-plugin`. Those requirements do **not** fit the current stable ranges above.

Therefore Virinda keeps that configuration under `config/ovos/experimental-agent/` and does not install it in the
production profile. This prevents a subtle dependency mixture where stable `ovos-persona` is combined with a newer
agent-only plugin.

## Profiles

### `stable`

Use this on the primary workstation/appliance.

- installs through the official OVOS stable constraints
- uses legacy `ovos-solver-openai-plugin`
- uses the stable Persona generation
- keeps wake/VAD/STT/TTS modular
- is the only profile covered by Virinda's production compatibility contract

### `experimental-agent`

Use this only when deliberately testing the newer OVOS agent framework.

- requires OVOS prerelease/testing components capable of providing `ovos-persona>=0.9.0a1`
- requires `ovos-plugin-manager>=2.2.3a1`
- uses `ovos-chat-openai-plugin`
- must be installed from a matching OVOS testing/alpha dependency set
- is **not** represented as a stable Virinda dependency extra

Until OVOS publishes a stable constraints set containing the new agent stack, Virinda will not call this profile
production-compatible.

## Compatibility rules

1. Never install arbitrary `@main` versions of multiple OVOS repositories into the production environment.
2. Always use one OVOS release-channel constraints file for core services.
3. Treat individually versioned optional plugins as add-ons and validate them separately.
4. Do not mix legacy solver APIs and agent APIs in one Persona configuration.
5. When OVOS changes a major/minor compatibility boundary, update this file and add a test before changing the
   supported profile.

## Practical install rule

For a real workstation, start from the OVOS reference install path and add Virinda on top. OVOS documents the stable
pip recipe as `ovos-core[mycroft,plugins,skills-essential]` with `constraints-stable.txt`. The Virinda installer now
keeps that channel explicit and writes the stable Persona profile.


## Compatibility snapshot

The repository includes `config/ovos/constraints-stable.txt`, a release-time snapshot of the OVOS stable constraints, and `config/ovos/compatibility.json`, the machine-readable Virinda compatibility matrix. The snapshot was refreshed on 2026-08-20 from the upstream stable constraints URL. OVOS's installation guidance recommends using a constraints file because the ecosystem is composed of separately released packages.

Virinda deliberately adds only four audio components outside that lock: Whisper.cpp STT 0.0.1 and phoonnx 1.3.3, plus exact pins for Silero VAD 0.0.5 and openWakeWord 0.4.1 within the stable lock's permitted ranges.

The hardware-free command `python scripts/ovos-smoke.py` verifies that those distributions are installed in the active virtual environment. It does not require audio hardware.

## Supported project matrix

See `docs/OVOS_SUPPORTED_STACK.md` for the reliability tiers. The short rule is:

- Tier A: use in production with the upstream stable constraints.
- Tier B: stable and suitable as a conservative local fallback.
- Tier C: Virinda-selected add-ons that require separate validation.
- Tier D: experimental, pre-release, deprecated, or legacy projects that must not silently enter production.

This keeps Virinda tied to a small known-good OVOS surface rather than the entire OpenVoiceOS GitHub organization.
