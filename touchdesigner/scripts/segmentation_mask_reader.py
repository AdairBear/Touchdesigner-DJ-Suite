# segmentation_mask_reader.py -- Script TOP callback for /project1/body_mask_top
# ============================================================================
# Reads the body segmentation mask that movement_tracker.py publishes into
# shared memory and hands it to TD as an RGBA texture for the outline / aura
# compositing chain.
#
# ---------------------------------------------------------------------------
# 2026-07-31 -- WHY THIS FILE WAS REWRITTEN
#
# The rig showed a checkerboard in OBS. The Syphon frame was ~100% transparent,
# which looked like an alpha-shader bug. It was not. A probe of the live network
# found the whole chain black at the source:
#
#     body_mask_top    640x480   rgb_max 0.000     <- HERE
#     fx_palette_apply 1280x720  rgb_max 0.000
#     final_composite  1280x720  rgb_max 0.000
#     syphonOut1       1280x720  rgb_max 0.000, alpha 0.000
#
# The reason was in this file. Its entire contents were:
#
#     import numpy as np
#     def onCook(scriptOp):
#         scriptOp.copyNumpyArray(np.zeros((480,640,4),dtype=np.float32))
#     def cook(scriptOp):
#         scriptOp.copyNumpyArray(np.zeros((480,640,4),dtype=np.float32))
#
# A stub that emits pure black and never opens the tracker's memory at all --
# `np.zeros((480,640,4))` is exactly the measured 640x480 black. Commit 23fd87b
# ("initial commit of pre-fable-session state") replaced 148 lines of working
# reader with those 4. Anything that reloads this DAT from disk -- and TWO
# things do, `_reload_mask.py` and
# `aura_compositor._force_reload_mask_reader_once()` -- therefore blanks the
# graphics permanently.
#
# Worse, `apply_complete_fix.py` copies THIS FILE into the DAT and then asserts
#     has_seqlock: ('_seq' in cb.text and 'djsam_bodymask_A' in cb.text)
# which the stub could never satisfy. The repair tool was installing the bug.
#
# Recovering the pre-stub version was not enough either: that one reads the
# LEGACY single-buffer layout (`/tmp/djsam_bodymask.raw` with a 4-byte header),
# and the tracker stopped writing that. It now publishes a SEQLOCK double
# buffer. So this file is written against what movement_tracker.py actually
# writes today, verified line by line against its `_init_mask_mmap` /
# `_write_mask`.
#
# ---------------------------------------------------------------------------
# THE WIRE FORMAT (movement_tracker.py:148-185)
#
#   /tmp/djsam_bodymask_A.raw   640*480 bytes, uint8, NO header
#   /tmp/djsam_bodymask_B.raw   same
#   /tmp/djsam_bodymask.seq     8 bytes, uint64 little-endian frame counter
#
#   Writer: write frame into buffer[counter % 2], THEN publish counter to .seq.
#   Reader: read seq, take buffer[seq % 2], re-read seq; if it changed mid-read
#           the frame was torn -- reuse the last good one rather than showing
#           a half-written frame. No locks, no msync, never blocks the writer.
#           (Removing msync is what fixed the read-during-writeback freeze.)
#
# SETUP IN TOUCHDESIGNER (unchanged):
#   Script TOP  "body_mask_top", 640x480, Callbacks DAT -> this Text DAT.
#
# ---------------------------------------------------------------------------
# DESIGN RULES, each one paying for a specific past failure:
#
#   1. ALWAYS output a full RGBA frame. Returning early leaves the Script TOP
#      showing black, which is indistinguishable from "the DJ is not in frame".
#   2. CACHE the last good frame and re-emit it on a duplicate/torn read, so a
#      slow tracker frame does not flicker the visuals to black.
#   3. SELF-HEAL a stale mmap. If the counter stops advancing for STALE_LIMIT
#      cooks, close and reopen -- the tracker may have restarted onto new
#      inodes, and a cached handle would point at the old ones forever. This is
#      the failure that survives a tracker respawn.
#   4. NEVER RAISE. An exception in a Script TOP callback stops the cook and
#      blacks the node; every failure path here degrades to "last good frame,
#      or black, and set a status flag" instead.
#   5. Report status on the TOP so a watchdog can SEE it, via
#      scriptOp.store('mask_status', ...).
# ============================================================================

import mmap
import os

import numpy as np

# Must match movement_tracker.py exactly.
BUF_A = "/tmp/djsam_bodymask_A.raw"
BUF_B = "/tmp/djsam_bodymask_B.raw"
SEQ_PATH = "/tmp/djsam_bodymask.seq"
MASK_W, MASK_H = 640, 480
MASK_BYTES = MASK_W * MASK_H

#: Cooks without the counter advancing before we assume the handles are stale
#: and reopen. At 60fps this is ~1s -- long enough not to thrash on a slow
#: tracker frame, short enough that a tracker restart recovers in about a second
#: rather than never.
STALE_LIMIT = 60

# Module-level state, persists across cooks.
_buf_mm = None  # [mmap, mmap] for A/B
_buf_fh = None
_seq_mm = None
_seq_fh = None
_last_seq = -1
_last_rgba = None  # cached good frame
_stale = 0
_status = "init"


def _close():
    """Drop every handle. Safe to call at any time, including twice."""
    global _buf_mm, _buf_fh, _seq_mm, _seq_fh
    for obj in list(_buf_mm or []) + [_seq_mm]:
        try:
            if obj is not None:
                obj.close()
        except Exception:
            pass
    for fh in list(_buf_fh or []) + [_seq_fh]:
        try:
            if fh is not None:
                fh.close()
        except Exception:
            pass
    _buf_mm = _buf_fh = None
    _seq_mm = _seq_fh = None


def _open():
    """Map the tracker's buffers. Returns True on success.

    Read-only ("rb" + ACCESS_READ): TD must never be able to corrupt the
    tracker's frames, and a read-only map cannot.
    """
    global _buf_mm, _buf_fh, _seq_mm, _seq_fh, _status
    _close()
    try:
        for p in (BUF_A, BUF_B, SEQ_PATH):
            if not os.path.exists(p):
                _status = "waiting: %s does not exist yet" % os.path.basename(p)
                return False
        if os.path.getsize(SEQ_PATH) < 8:
            _status = "waiting: .seq is short (tracker still starting)"
            return False
        for p in (BUF_A, BUF_B):
            if os.path.getsize(p) < MASK_BYTES:
                _status = "waiting: %s is short" % os.path.basename(p)
                return False

        _buf_fh, _buf_mm = [], []
        for p in (BUF_A, BUF_B):
            fh = open(p, "rb")
            _buf_fh.append(fh)
            _buf_mm.append(mmap.mmap(fh.fileno(), MASK_BYTES, access=mmap.ACCESS_READ))
        _seq_fh = open(SEQ_PATH, "rb")
        _seq_mm = mmap.mmap(_seq_fh.fileno(), 8, access=mmap.ACCESS_READ)
        _status = "open"
        return True
    except Exception as e:
        _status = "open failed: %s" % e
        _close()
        return False


def _read_seq():
    _seq_mm.seek(0)
    return int(np.frombuffer(_seq_mm.read(8), dtype=np.uint64)[0])


def _read_frame():
    """(rgba, seq) for the newest complete frame, or (None, seq) if torn."""
    seq = _read_seq()
    mm = _buf_mm[seq % 2]
    mm.seek(0)
    raw = mm.read(MASK_BYTES)
    # Seqlock re-check: if the writer published a new frame while we were
    # copying, our bytes may straddle two frames. Reuse the last good one.
    if _read_seq() != seq:
        return None, seq

    gray = (
        np.frombuffer(raw, dtype=np.uint8).reshape(MASK_H, MASK_W).astype(np.float32)
        / 255.0
    )
    rgba = np.empty((MASK_H, MASK_W, 4), dtype=np.float32)
    rgba[..., 0] = gray
    rgba[..., 1] = gray
    rgba[..., 2] = gray
    # Alpha carries the mask too, so downstream can key on it directly.
    rgba[..., 3] = gray
    return rgba, seq


def _black():
    return np.zeros((MASK_H, MASK_W, 4), dtype=np.float32)


def _publish(scriptOp):
    """Rule 5: make the state visible to anything that can read the node."""
    try:
        scriptOp.store("mask_status", _status)
        scriptOp.store("mask_seq", _last_seq)
    except Exception:
        pass


def cook(scriptOp):
    """Never raises. Always writes a frame. See DESIGN RULES above."""
    global _last_seq, _last_rgba, _stale, _status

    try:
        if _seq_mm is None and not _open():
            scriptOp.copyNumpyArray(_last_rgba if _last_rgba is not None else _black())
            _publish(scriptOp)
            return

        rgba, seq = _read_frame()

        if rgba is None:
            # Torn read -- normal under load, not an error.
            _status = "torn read at seq %d (using cached frame)" % seq
        elif seq == _last_seq:
            _stale += 1
            if _stale >= STALE_LIMIT:
                # Rule 3: the tracker probably restarted onto new inodes.
                _status = "stale %d cooks -- reopening" % _stale
                _stale = 0
                _last_seq = -1
                _open()
            else:
                _status = "duplicate frame %d (using cached)" % seq
        else:
            _last_rgba = rgba
            _last_seq = seq
            _stale = 0
            _status = "live seq %d" % seq

        scriptOp.copyNumpyArray(_last_rgba if _last_rgba is not None else _black())
        _publish(scriptOp)
    except Exception as e:
        # Rule 4: an exception here would black the node and stop the show.
        _status = "error: %s" % e
        try:
            scriptOp.copyNumpyArray(_last_rgba if _last_rgba is not None else _black())
            _publish(scriptOp)
        except Exception:
            pass


def onCook(scriptOp):
    cook(scriptOp)
