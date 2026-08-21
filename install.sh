#!/usr/bin/env bash
# ==============================================================================
# install.sh - Installer for VirindaAI CLI & Daemon
# ==============================================================================
# Installs standalone symlinks 'virinda' and 'virindad' into ~/.local/bin
#
# Usage:
#   ./install.sh [OPTIONS]
#
# Options:
#   --prefix <dir>   Installation directory (default: ~/.local/bin)
#   --uninstall      Remove installed symlinks from prefix
#   --help, -h       Show this help message
# ==============================================================================

set -euo pipefail

# ANSI color codes
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BOLD="\033[1m"
NC="\033[0m"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VIRINDA_BIN="$SCRIPT_DIR/virinda"
VIRINDAD_BIN="$SCRIPT_DIR/virindad"
PREFIX="${HOME}/.local/bin"
UNINSTALL=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)
            PREFIX="$2"
            shift 2
            ;;
        --uninstall)
            UNINSTALL=true
            shift
            ;;
        --help|-h)
            echo -e "${BOLD}VirindaAI CLI Installer${NC}"
            echo -e "Usage: ./install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --prefix <dir>   Target directory for binaries (default: ~/.local/bin)"
            echo "  --uninstall      Remove 'virinda' and 'virindad' symlinks"
            echo "  --help, -h       Display this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use ./install.sh --help for usage instructions."
            exit 1
            ;;
    esac
done

if [ "$UNINSTALL" = true ]; then
    echo -e "${YELLOW}Uninstalling VirindaAI CLI and Daemon from $PREFIX...${NC}"
    for bin_name in virinda virindad; do
        target="$PREFIX/$bin_name"
        if [ -L "$target" ] || [ -f "$target" ]; then
            rm -f "$target"
            echo -e "  ${RED}✗${NC} Removed: $target"
        fi
    done
    echo -e "${GREEN}✔ VirindaAI uninstallation complete.${NC}"
    exit 0
fi

# Ensure executable permissions on source wrapper scripts
chmod +x "$VIRINDA_BIN" "$VIRINDAD_BIN" "$SCRIPT_DIR/install.sh"

# Ensure target directory exists
mkdir -p "$PREFIX"

echo -e "${BOLD}Installing VirindaAI to $PREFIX...${NC}"

# Create symlinks
ln -sf "$VIRINDA_BIN" "$PREFIX/virinda"
echo -e "  ${GREEN}✔${NC} Linked: ${BOLD}$PREFIX/virinda${NC} -> $VIRINDA_BIN"

ln -sf "$VIRINDAD_BIN" "$PREFIX/virindad"
echo -e "  ${GREEN}✔${NC} Linked: ${BOLD}$PREFIX/virindad${NC} -> $VIRINDAD_BIN"

# Check if PREFIX is in PATH
if [[ ":$PATH:" != *":$PREFIX:"* ]]; then
    echo ""
    echo -e "${YELLOW}${BOLD}Note:${NC} $PREFIX is not currently in your PATH."
    echo -e "Add it to your shell configuration by running:"
    echo -e "  ${BLUE}export PATH=\"$PREFIX:\$PATH\"${NC}"
    echo -e "or add that line to ${BOLD}~/.bashrc${NC} / ${BOLD}~/.zshrc${NC}."
fi

echo ""
echo -e "${GREEN}${BOLD}VirindaAI installed successfully!${NC}"
echo -e "Try running:"
echo -e "  ${BLUE}virinda status${NC}"
echo -e "  ${BLUE}virinda benchmark voice${NC}"
echo -e "  ${BLUE}virinda acceptance voice${NC}"
