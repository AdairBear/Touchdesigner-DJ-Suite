#!/usr/bin/env bash
# install_daily_snapshot_launchd.sh — install the native daily-snapshot launchd job
# =============================================================================
# Run ONCE, from Terminal on the Mac (not the Cowork sandbox):
#     ./scripts/install_daily_snapshot_launchd.sh
#
# Copies the plist into ~/Library/LaunchAgents, loads it, and confirms it is
# registered. Runs the deterministic /snapshot Python tool at 22:00 daily,
# logging to /tmp/dailysnapshot.log — replacing the token-burning Claude wrapper.
#
# Idempotent: safe to re-run (it boots out any existing copy first).
# =============================================================================

set -euo pipefail

LABEL="com.thomasadair.dailysnapshot"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${REPO_ROOT}/scripts/${LABEL}.plist"
DEST_DIR="${HOME}/Library/LaunchAgents"
DEST="${DEST_DIR}/${LABEL}.plist"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"

echo "=============================================="
echo " Installing ${LABEL}"
echo "=============================================="

# 1. sanity-check the source plist ---------------------------------------------
if [[ ! -f "${SRC}" ]]; then
    echo "  FAIL  source plist not found: ${SRC}" >&2
    exit 1
fi
if ! plutil -lint "${SRC}" >/dev/null; then
    echo "  FAIL  plist failed plutil -lint: ${SRC}" >&2
    exit 1
fi
echo "  ok    plist is valid: ${SRC}"

# 2. copy into place -----------------------------------------------------------
mkdir -p "${DEST_DIR}"
cp "${SRC}" "${DEST}"
echo "  ok    copied -> ${DEST}"

# 3. (re)load — bootout any prior copy, then bootstrap (fallback: load) ---------
launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
if launchctl bootstrap "${DOMAIN}" "${DEST}" 2>/dev/null; then
    echo "  ok    bootstrapped into ${DOMAIN}"
else
    echo "  ..    bootstrap unavailable, falling back to legacy load"
    launchctl unload "${DEST}" 2>/dev/null || true
    launchctl load -w "${DEST}"
    echo "  ok    loaded (legacy)"
fi

# 4. confirm registered --------------------------------------------------------
if launchctl list 2>/dev/null | grep -q "${LABEL}"; then
    echo "  PASS  ${LABEL} is registered with launchd"
else
    echo "  WARN  ${LABEL} not visible in 'launchctl list' — check with:"
    echo "        launchctl print ${DOMAIN}/${LABEL}"
fi

echo "=============================================="
echo " Done. Job runs daily at 22:00 local time."
echo " Log:        /tmp/dailysnapshot.log"
echo " Test now:   launchctl kickstart -k ${DOMAIN}/${LABEL} && sleep 2 && tail -n 8 /tmp/dailysnapshot.log"
echo " Uninstall:  ./scripts/uninstall_daily_snapshot_launchd.sh"
echo ""
echo " You can now delete the old token-burning scheduled skill at:"
echo "   ~/Documents/Claude/Scheduled/daily-snapshot/SKILL.md"
echo "=============================================="
