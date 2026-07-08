#!/usr/bin/env bash
# uninstall_daily_snapshot_launchd.sh — remove the native daily-snapshot launchd job
# =============================================================================
# Run from Terminal on the Mac:
#     ./scripts/uninstall_daily_snapshot_launchd.sh
#
# Boots the job out of launchd and deletes the installed plist. Idempotent:
# safe to run even if the job was never installed. Does NOT touch the source
# plist in the repo or the /tmp/dailysnapshot.log history.
# =============================================================================

set -euo pipefail

LABEL="com.thomasadair.dailysnapshot"
DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"

echo "=============================================="
echo " Uninstalling ${LABEL}"
echo "=============================================="

# 1. boot out of launchd (bootout, fallback to legacy unload) -------------------
if launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null; then
    echo "  ok    booted out of ${DOMAIN}"
elif [[ -f "${DEST}" ]] && launchctl unload "${DEST}" 2>/dev/null; then
    echo "  ok    unloaded (legacy)"
else
    echo "  ..    job was not loaded (nothing to boot out)"
fi

# 2. remove the installed plist ------------------------------------------------
if [[ -f "${DEST}" ]]; then
    rm "${DEST}"
    echo "  ok    removed ${DEST}"
else
    echo "  ..    no installed plist at ${DEST}"
fi

# 3. confirm gone --------------------------------------------------------------
if launchctl list 2>/dev/null | grep -q "${LABEL}"; then
    echo "  WARN  ${LABEL} still visible in 'launchctl list' — try logging out/in"
else
    echo "  PASS  ${LABEL} is no longer registered"
fi

echo "=============================================="
echo " Done. The repo source plist and /tmp/dailysnapshot.log were left intact."
echo "=============================================="
