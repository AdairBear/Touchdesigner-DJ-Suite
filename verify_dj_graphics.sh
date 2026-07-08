#!/usr/bin/env bash
# verify_dj_graphics.sh — pre-troubleshooting health check for the DJ_Graphics rig
# =============================================================================
# Run from Terminal BEFORE you start poking at TouchDesigner:
#     ./verify_dj_graphics.sh
#
# Each check prints PASS / WARN / FAIL. Exit code is 0 when nothing FAILed,
# 1 when any check FAILed (WARN never fails the run — it's advisory).
#
# Semantics:
#   FAIL  = the live pipeline is broken (tracker down, mmap stale, TD not up)
#   WARN  = advisory / hardware / routing that varies by setup
#   PASS  = good
#
# macOS only (uses BSD stat + system_profiler).
# =============================================================================

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MASK_READER="${REPO_ROOT}/touchdesigner/scripts/segmentation_mask_reader.py"
MMAP="/tmp/djsam_bodymask.raw"
MMAP_FRESH_SECS=5

fails=0
warns=0
passes=0

pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; passes=$((passes+1)); }
warn() { printf '  \033[33mWARN\033[0m  %s\n' "$1"; warns=$((warns+1)); }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; fails=$((fails+1)); }

echo "=============================================="
echo " DJ_Graphics health check — $(date '+%Y-%m-%d %H:%M:%S')"
echo " repo: ${REPO_ROOT}"
echo "=============================================="

# 1. movement_tracker.py running -------------------------------------------------
if pgrep -f 'movement_tracker.py' >/dev/null 2>&1; then
    pass "movement_tracker.py is running (pid $(pgrep -f 'movement_tracker.py' | tr '\n' ' '))"
else
    fail "movement_tracker.py is NOT running — start it with ./start_tracker.command"
fi

# 2. mmap exists AND fresh (<5 s old) -------------------------------------------
if [[ -f "${MMAP}" ]]; then
    mtime=$(stat -f %m "${MMAP}" 2>/dev/null || echo 0)
    now=$(date +%s)
    age=$((now - mtime))
    if (( age <= MMAP_FRESH_SECS )); then
        pass "${MMAP} is fresh (${age}s old, $(stat -f %z "${MMAP}" 2>/dev/null) bytes)"
    else
        fail "${MMAP} is STALE (${age}s old > ${MMAP_FRESH_SECS}s) — tracker frozen or not writing"
    fi
else
    fail "${MMAP} does not exist — tracker has never written the body mask"
fi

# 3. segmentation_mask_reader.py has no UTF-8 BOM (first byte is '#') ------------
if [[ -f "${MASK_READER}" ]]; then
    first3=$(head -c 3 "${MASK_READER}" | xxd -p 2>/dev/null)
    first1=$(head -c 1 "${MASK_READER}")
    if [[ "${first3}" == "efbbbf"* ]]; then
        warn "segmentation_mask_reader.py starts with a UTF-8 BOM — loader strips it (commit 28048db) but the on-disk file is not clean"
    elif [[ "${first1}" == "#" ]]; then
        pass "segmentation_mask_reader.py starts with '#' (no BOM)"
    else
        warn "segmentation_mask_reader.py first byte is not '#' (got '${first1}') — inspect the header"
    fi
else
    fail "segmentation_mask_reader.py not found at ${MASK_READER}"
fi

# 4. Serato Virtual Audio present (music routing) -------------------------------
if system_profiler SPAudioDataType 2>/dev/null | grep -qi 'Serato'; then
    pass "Serato Virtual Audio device present"
else
    warn "Serato Virtual Audio not found in SPAudioDataType — verify DJ audio routing (may be using 1824c/DDJ instead)"
fi

# 5. TouchDesigner running ------------------------------------------------------
if pgrep -f 'TouchDesigner' >/dev/null 2>&1; then
    pass "TouchDesigner is running"
else
    fail "TouchDesigner is NOT running — open ~/Desktop/DJ_Graphics.toe"
fi

# 6. OBS running ----------------------------------------------------------------
if pgrep -f 'OBS' >/dev/null 2>&1; then
    pass "OBS is running"
else
    warn "OBS is not running — start it if you're streaming/recording the Syphon feed"
fi

# 7. Insta360 Link + Studio 1824c present on USB --------------------------------
usb="$(system_profiler SPUSBDataType 2>/dev/null)"
if echo "${usb}" | grep -qi 'Insta360 Link'; then
    pass "Insta360 Link camera present on USB"
else
    warn "Insta360 Link not found on USB — camera unplugged or on a different bus"
fi
if echo "${usb}" | grep -qiE '1824c|Studio 1824'; then
    pass "PreSonus Studio 1824c present on USB"
else
    warn "PreSonus Studio 1824c not found on USB — audio interface unplugged?"
fi

# summary -----------------------------------------------------------------------
echo "=============================================="
if (( fails == 0 )); then
    echo -e " SUMMARY: \033[32mALL CLEAR\033[0m — ${passes} pass, ${warns} warn, ${fails} fail"
    echo "=============================================="
    exit 0
else
    echo -e " SUMMARY: \033[31m${fails} FAIL\033[0m — ${passes} pass, ${warns} warn, ${fails} fail"
    echo " Address the FAIL lines above before troubleshooting TD internals."
    echo "=============================================="
    exit 1
fi
