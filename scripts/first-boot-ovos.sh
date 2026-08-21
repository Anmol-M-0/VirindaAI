#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="${1:-stable}"

MARINA_OVOS_PROFILE="$PROFILE" MARINA_INSTALL_SERVICES=1 "$ROOT/scripts/install-ovos.sh"

if [[ "${MARINA_AUTO_START:-0}" == "1" ]]; then
  systemctl --user enable --now marina-ovos-core.target
  if [[ "$PROFILE" == "local-voice" ]]; then
    systemctl --user enable --now marina-voice.target
  fi
fi

printf '%s\n' "First-boot provisioning complete for profile: $PROFILE"
