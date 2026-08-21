# OVOS user services

These units are a small local deployment profile for Linux systems where Virinda is installed in `%h/.venv`.

The Virinda installer installs these units by default. For a manual installation, copy them into `~/.config/systemd/user/`, reload the user manager, and enable the services:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/ovos/virinda-*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now virinda-messagebus.service
systemctl --user enable --now virinda-core.service
systemctl --user enable --now virinda-listener.service
systemctl --user enable --now virinda-audio.service
```

The units intentionally keep the service topology explicit. They do not attempt to hide OVOS failures behind Virinda-specific process management.

The installer places the Virinda skill under `${XDG_DATA_HOME:-$HOME/.local/share}/mycroft/skills/skill-virinda-ai.openvoiceos`. Override with `VIRINDA_OVOS_SKILL_DIR` when your deployment uses a different skill root.

Profiles:

```bash
VIRINDA_OVOS_PROFILE=stable ./scripts/install-ovos.sh
VIRINDA_OVOS_PROFILE=local-voice ./scripts/install-ovos.sh
```

The stable profile uses only the upstream OVOS stable lock. The local-voice profile additionally installs Virinda's separately validated Whisper.cpp and phoonnx add-ons.

## Service targets

Start the runtime in layers:

```bash
systemctl --user enable --now virinda-ovos-core.target
systemctl --user enable --now virinda-voice.target
```

`virinda-ovos-core.target` starts the message bus and `ovos-core`. `virinda-voice.target` adds Dinkum Listener and OVOS Audio, making it the hardware-facing profile.

Probe the stages independently:

```bash
.venv/bin/python scripts/ovos-runtime-smoke.py "virinda status" --stage core --require-services
.venv/bin/python scripts/ovos-runtime-smoke.py "virinda status" --stage voice --require-services
```


## Provisioning and removal

Use `scripts/first-boot-ovos.sh stable` for a stable first boot, or `scripts/first-boot-ovos.sh local-voice` for the Virinda-local voice add-ons. Set `VIRINDA_AUTO_START=1` to start the selected runtime after installation.

Use `scripts/uninstall-ovos.sh` to remove Virinda-owned OVOS units, skill, and persona. The uninstall script intentionally preserves the Virinda virtualenv and database unless those are removed separately.
