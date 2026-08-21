#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
VENV="${MARINA_VENV:-$ROOT/.venv}"
CONSTRAINTS_FILE="${MARINA_OVOS_CONSTRAINTS:-$ROOT/config/ovos/constraints-stable.txt}"
ADDONS_FILE="$ROOT/config/ovos/virinda-audio-overrides.txt"
PROFILE="${VIRINDA_OVOS_PROFILE:-stable}"
SKILL_DIR="${MARINA_OVOS_SKILL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/mycroft/skills}"
OVOS_CONFIG_DIR="${MARINA_OVOS_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/mycroft}"
PERSONA_DIR="${MARINA_PERSONA_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/ovos_persona}"
SYSTEMD_DIR="${MARINA_SYSTEMD_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user}"
INSTALL_CONFIG="${MARINA_INSTALL_CONFIG:-0}"
INSTALL_SERVICES="${MARINA_INSTALL_SERVICES:-1}"

if [[ "$PROFILE" != "stable" && "$PROFILE" != "local-voice" ]]; then
  echo "Unsupported VIRINDA_OVOS_PROFILE: $PROFILE" >&2
  exit 2
fi

"$PYTHON" -c 'import sys; raise SystemExit("Python 3.11+ is required") if sys.version_info < (3, 11) else None'
[[ -f "$CONSTRAINTS_FILE" ]] || { echo "Missing OVOS constraints: $CONSTRAINTS_FILE" >&2; exit 2; }

if [[ ! -x "$VENV/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -e '.[ovos]' 'ovos-core[mycroft,plugins,skills-essential]' -c "$CONSTRAINTS_FILE"
if [[ "$PROFILE" == "local-voice" ]]; then
  "$VENV/bin/python" -m pip install -c "$CONSTRAINTS_FILE" -r "$ADDONS_FILE"
fi

mkdir -p "$SKILL_DIR" "$PERSONA_DIR"
SKILL_TARGET="$SKILL_DIR/skill-virinda-ai.openvoiceos"
rm -rf "$SKILL_TARGET"
mkdir -p "$SKILL_TARGET"
cp -a "$ROOT/skills/skill-virinda-ai/." "$SKILL_TARGET/"
cp "$ROOT/config/ovos/virinda-persona.json" "$PERSONA_DIR/Marina.json"

if [[ "$INSTALL_CONFIG" == "1" ]]; then
  mkdir -p "$OVOS_CONFIG_DIR"
  CONFIG_TARGET="$OVOS_CONFIG_DIR/mycroft.conf"
  if [[ -e "$CONFIG_TARGET" ]]; then
    echo "Refusing to overwrite existing OVOS config: $CONFIG_TARGET" >&2
    echo "Merge config/ovos/mycroft.conf.example.json manually or use a fresh profile." >&2
    exit 3
  fi
  cp "$ROOT/config/ovos/mycroft.conf.example.json" "$CONFIG_TARGET"
fi

if [[ "$INSTALL_SERVICES" == "1" ]]; then
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemctl is unavailable; skipping systemd user units." >&2
  else
    mkdir -p "$SYSTEMD_DIR"
    stage="$(mktemp -d)"
    backup="$(mktemp -d)"
    cleanup() { rm -rf "$stage" "$backup"; }
    trap cleanup EXIT
    for unit in "$ROOT"/deploy/ovos/virinda-*.service "$ROOT"/deploy/ovos/virinda-*.target; do
      install -m 0644 "$unit" "$stage/$(basename "$unit")"
    done
    for unit in "$stage"/marina-*; do
      name="$(basename "$unit")"
      if [[ -f "$SYSTEMD_DIR/$name" ]]; then cp -a "$SYSTEMD_DIR/$name" "$backup/$name"; fi
    done
    # Render the actual venv path into ExecStart so MARINA_VENV works for both
    # the default checkout-local venv and custom deployment locations.
    for unit in "$stage"/virinda-*.service; do
      sed -i "s#@VIRINDA_VENV@#$VENV#g" "$unit"
    done
    install -m 0644 "$stage"/* "$SYSTEMD_DIR/"
    if ! systemctl --user daemon-reload; then
      for old in "$backup"/marina-*; do
        [[ -e "$old" ]] || continue
        install -m 0644 "$old" "$SYSTEMD_DIR/$(basename "$old")"
      done
      rm -f "$SYSTEMD_DIR"/virinda-*.service "$SYSTEMD_DIR"/virinda-*.target 2>/dev/null || true
      for old in "$backup"/marina-*; do [[ -e "$old" ]] && install -m 0644 "$old" "$SYSTEMD_DIR/"; done
      systemctl --user daemon-reload || true
      echo "Failed to reload user systemd manager; previous Marina units restored." >&2
      exit 4
    fi
  fi
fi

printf '%s\n' "Marina OVOS integration installed (profile: $PROFILE)."
printf '%s\n' "Virtualenv: $VENV"
printf '%s\n' "Skill: $SKILL_TARGET"
printf '%s\n' "Persona: $PERSONA_DIR/Marina.json"
[[ "$INSTALL_CONFIG" == "1" ]] && printf '%s\n' "OVOS config: $OVOS_CONFIG_DIR/mycroft.conf"
[[ "$INSTALL_SERVICES" == "1" ]] && printf '%s\n' "User services: $SYSTEMD_DIR/virinda-*.service"
printf '%s\n' 'Run: .venv/bin/marina doctor --services'
printf '%s\n' 'Core runtime: systemctl --user enable --now virinda-ovos-core.target'
printf '%s\n' 'Full voice runtime: systemctl --user enable --now virinda-voice.target'
printf '%s\n' 'Remove: scripts/uninstall-ovos.sh'
