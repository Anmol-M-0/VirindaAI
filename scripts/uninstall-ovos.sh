#!/usr/bin/env bash
set -euo pipefail

SYSTEMD_DIR="${VIRINDA_SYSTEMD_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user}"
SKILL_DIR="${VIRINDA_OVOS_SKILL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/mycroft/skills}"
PERSONA_DIR="${VIRINDA_PERSONA_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/ovos_persona}"
REMOVE_CONFIG="${VIRINDA_REMOVE_CONFIG:-0}"
REMOVE_PERSONA="${VIRINDA_REMOVE_PERSONA:-1}"
REMOVE_SKILL="${VIRINDA_REMOVE_SKILL:-1}"
REMOVE_SERVICES="${VIRINDA_REMOVE_SERVICES:-1}"

if command -v systemctl >/dev/null 2>&1 && [[ "$REMOVE_SERVICES" == "1" ]]; then
  systemctl --user disable --now virinda-voice.target virinda-ovos-core.target 2>/dev/null || true
fi

if [[ "$REMOVE_SERVICES" == "1" ]]; then
  rm -f "$SYSTEMD_DIR"/virinda-*.service "$SYSTEMD_DIR"/virinda-*.target 2>/dev/null || true
  if command -v systemctl >/dev/null 2>&1; then systemctl --user daemon-reload || true; fi
fi

if [[ "$REMOVE_SKILL" == "1" ]]; then rm -rf "$SKILL_DIR/skill-virinda-ai.openvoiceos"; fi
if [[ "$REMOVE_PERSONA" == "1" ]]; then rm -f "$PERSONA_DIR/Virinda.json"; fi
if [[ "$REMOVE_CONFIG" == "1" ]]; then rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/mycroft/mycroft.conf"; fi

printf '%s\n' 'Virinda OVOS integration removed.'
printf '%s\n' 'The Python virtualenv and Virinda database are intentionally preserved.'
printf '%s\n' 'Delete $VIRINDA_VENV and your data directory separately if a full wipe is desired.'
