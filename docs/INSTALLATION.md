# Installation and First Boot

This document describes the supported Linux installation model. Marina is designed for a user-scoped Linux desktop with systemd user services. The production voice stack is OVOS.

## Prerequisites

- Linux with systemd user services for the supported desktop deployment.
- Python 3.10+; Marina development and packaging are exercised across the project's supported Python matrix.
- A working user session for audio/desktop integrations.
- Network access only when installing OVOS packages or using a network-backed provider. The standalone Marina control plane itself can run offline.

For a managed OVOS installation, the upstream project recommends its installer or a pip install constrained by the stable channel. Marina's checked-in compatibility snapshot is under `config/ovos/constraints-stable.txt`.

## Development-only installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

export MARINA_DATA_DIR="$PWD/.local/marina"
marina status
marina ask "Hello Marina"
```

This path intentionally does not require OVOS, a microphone, a speaker, or a cloud provider.

## Production OVOS installation

Use the repository installer for the staged Marina deployment:

```bash
./scripts/first-boot-ovos.sh stable
```

For the optional local-voice profile:

```bash
./scripts/first-boot-ovos.sh local-voice
```

The first-boot flow is responsible for:

1. Creating or reusing the Marina virtual environment.
2. Installing the OVOS stable stack using a constraints file.
3. Installing Marina's packaged OVOS skill.
4. Installing Marina-owned systemd units.
5. Optionally installing Marina's OVOS configuration.
6. Running compatibility and environment diagnostics.

The installer is conservative around existing configuration: it does not overwrite an existing OVOS config unless explicitly requested.

## Service layers

Marina deliberately separates the runtime into two systemd targets:

```text
marina-ovos-core.target
  ├─ message bus
  └─ ovos-core

marina-voice.target
  └─ marina-ovos-core.target
      ├─ Dinkum Listener
      └─ OVOS Audio
```

This lets a developer validate the application/skill layer before introducing microphone or speaker dependencies.

Useful commands:

```bash
systemctl --user start marina-ovos-core.target
systemctl --user status marina-ovos-core.target

systemctl --user start marina-voice.target
systemctl --user status marina-voice.target
```

The upstream OVOS ecosystem also treats these services as independently managed components.

## Installation verification

Run the static compatibility checks:

```bash
python scripts/verify-ovos-compatibility.py
python scripts/ovos-smoke.py --profile stable
```

If the OVOS virtual environment is installed, run the live bus/core probe:

```bash
python scripts/ovos-runtime-smoke.py "marina status" --expect "Marina is online"
```

For the voice stage, add the required user services to the probe:

```bash
python scripts/ovos-runtime-smoke.py \
  "marina status" \
  --expect "Marina is online" \
  --require-services \
  marina-messagebus.service \
  marina-core.service \
  marina-listener.service \
  marina-audio.service
```

## Wake-word model

Marina does not ship a fake wake-word model. Install a real custom `hey_marina` model and point OVOS OpenWakeWord configuration at it. The model requirements and acceptance criteria are documented in `models/README.md`.

## Uninstall

```bash
./scripts/uninstall-ovos.sh
```

Uninstall is intentionally conservative and preserves Marina's local database unless you explicitly remove it.

## What a successful installation means

A successful installation has four independent layers:

1. **Package layer:** Marina imports and reports the expected version.
2. **Compatibility layer:** the selected OVOS packages satisfy the checked-in compatibility contract.
3. **Runtime layer:** MessageBus/Core can process a Marina utterance and produce a response event.
4. **Voice layer:** the physical microphone, wake word, VAD, STT, TTS, and speaker path work on the target host.

The first three can be validated in automation. The fourth is hardware/system dependent and must not be represented as passing when no hardware is present.
