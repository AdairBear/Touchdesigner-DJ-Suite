# setup_body_window.py -- one-shot TouchDesigner Textport setup
# ====================================================================
# GOAL: get a VISIBLE body-tracking screen up, tonight, bypassing the
# two broken chains (stale body_mask_top DAT + dark syphon path).
#
# RUN IN TD TEXTPORT (Alt+T), paste this ONE line:
#
#   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/setup_body_window.py').read())
#
# What it builds (all additive, nothing existing is deleted):
#   /project1/body_live          Script TOP  -> reads mmap, bold cyan outline
#   /project1/body_live_reader   Text DAT    -> the reader callbacks
#   /project1/body_window        Window COMP -> shows body_live, opens fullscreen-ish
# It ALSO re-syncs the real body_mask_top callbacks DAT with the correct
# 4-byte-header reader so the main pipeline gets its input back.
# ====================================================================

# ---- the reader that runs INSIDE the new Script TOP -----------------
# Reads /tmp/djsam_bodymask.raw (4-byte uint32 frame counter + 640x480 uint8),
# dilates the thin contour into a bold line with pure numpy (no cv2/scipy
# dependency), and outputs a bright cyan body outline on black.
_READER = r'''
import numpy as np
import mmap
import os
import struct

MASK_PATH = "/tmp/djsam_bodymask.raw"
MASK_W = 640
MASK_H = 480
HEADER_SIZE = 4
TOTAL_SIZE = HEADER_SIZE + MASK_W * MASK_H
DILATE_ITERS = 5          # how many pixels to fatten the outline by
COLOR = (0.15, 1.0, 1.0)  # cyan-ish (r, g, b), alpha follows the mask

_fh = None
_mm = None
_last_frame = -1
_last_rgba = None
_stale_count = 0
STALE_LIMIT = 180  # cooks the frame counter may freeze before we reopen (~3s)


def _open_mmap():
    global _fh, _mm
    for h in (_mm, _fh):
        try:
            if h is not None:
                h.close()
        except Exception:
            pass
    if not os.path.exists(MASK_PATH):
        _fh = _mm = None
        return False
    try:
        _fh = open(MASK_PATH, "r+b")
        _mm = mmap.mmap(_fh.fileno(), TOTAL_SIZE, access=mmap.ACCESS_READ)
        return True
    except Exception as e:
        print("[body_live] mmap open error: " + str(e))
        _fh = _mm = None
        return False


def _dilate(m, iters):
    # pure-numpy binary dilation: OR each pixel with its 4 neighbours.
    for _ in range(iters):
        out = m.copy()
        out[1:, :] = np.maximum(out[1:, :], m[:-1, :])
        out[:-1, :] = np.maximum(out[:-1, :], m[1:, :])
        out[:, 1:] = np.maximum(out[:, 1:], m[:, :-1])
        out[:, :-1] = np.maximum(out[:, :-1], m[:, 1:])
        m = out
    return m


def cook(scriptOP):
    global _mm, _last_frame, _last_rgba, _stale_count
    if _mm is None:
        if not _open_mmap():
            scriptOP.copyNumpyArray(np.zeros((MASK_H, MASK_W, 4), dtype=np.float32))
            return
    try:
        _mm.seek(0)
        frame_num = struct.unpack("<I", _mm.read(HEADER_SIZE)[0:4])[0]
        if frame_num != _last_frame or _last_rgba is None:
            _last_frame = frame_num
            _stale_count = 0
            raw = _mm.read(MASK_W * MASK_H)
            mask = np.frombuffer(raw, dtype=np.uint8).reshape((MASK_H, MASK_W))
            fat = _dilate(mask, DILATE_ITERS).astype(np.float32) / 255.0
            rgba = np.zeros((MASK_H, MASK_W, 4), dtype=np.float32)
            rgba[:, :, 0] = fat * COLOR[0]
            rgba[:, :, 1] = fat * COLOR[1]
            rgba[:, :, 2] = fat * COLOR[2]
            rgba[:, :, 3] = fat
            _last_rgba = rgba
        else:
            # Frame counter frozen -> mmap is stale (writer recreated the file).
            # Reopen fresh after STALE_LIMIT cooks so the visible screen self-heals
            # instead of silently freezing on a dead handle.
            _stale_count += 1
            if _stale_count >= STALE_LIMIT:
                _stale_count = 0
                _last_frame = -1
                _open_mmap()
        if _last_rgba is not None:
            scriptOP.copyNumpyArray(_last_rgba)
        else:
            scriptOP.copyNumpyArray(np.zeros((MASK_H, MASK_W, 4), dtype=np.float32))
    except Exception as e:
        print("[body_live] read error: " + str(e))
        _last_rgba = None
        _stale_count = 0
        _open_mmap()


def setup(scriptOP):
    _open_mmap()
'''


def _run():
    p = op('/project1')
    if p is None:
        print("[setup_body_window] ERROR: /project1 not found")
        return

    made = []

    # --- 1. reader DAT ------------------------------------------------
    try:
        dat = op('/project1/body_live_reader')
        if dat is None:
            dat = p.create(textDAT, 'body_live_reader')
            made.append('body_live_reader (DAT)')
        dat.text = _READER
        dat.nodeX, dat.nodeY = 0, 0
    except Exception as e:
        print("[setup_body_window] reader DAT error: " + str(e))
        return

    # --- 2. Script TOP ------------------------------------------------
    try:
        stop = op('/project1/body_live')
        if stop is None:
            stop = p.create(scriptTOP, 'body_live')
            made.append('body_live (Script TOP)')
        stop.par.callbacks = 'body_live_reader'
        stop.nodeX, stop.nodeY = 200, 0
        stop.cook(force=True)
    except Exception as e:
        print("[setup_body_window] Script TOP error: " + str(e))
        return

    # --- 3. Window COMP ----------------------------------------------
    try:
        win = op('/project1/body_window')
        if win is None:
            win = p.create(windowCOMP, 'body_window')
            made.append('body_window (Window COMP)')
        # Window COMP's operator parameter differs across TD builds
        # ('op' on current builds; 'top' does NOT exist -> AttributeError).
        # Probe the known candidates and set whichever the build exposes.
        _live_path = op('/project1/body_live').path  # '/project1/body_live'
        # Window COMP's display-source par is `winop` (confirmed on this build);
        # keep the others as cross-build fallbacks.
        _wpar = None
        for _nm in ('winop', 'op', 'displayop', 'top', 'node', 'operator'):
            _cand = getattr(win.par, _nm, None)
            if _cand is not None:
                try:
                    _cand.val = _live_path
                    _wpar = _nm
                    break
                except Exception:
                    pass
        if _wpar:
            print("[setup_body_window] window shows body_live via par." + _wpar)
        else:
            print("[setup_body_window] WARN: no operator par on Window COMP; "
                  "available pars: " + ", ".join(pp.name for pp in win.pars()))
        # Size / border pars are cosmetic and their names vary across builds.
        # Guard each independently so a missing par can NEVER stop the window
        # from opening — winopen.pulse() below is the one call that must run.
        for _pn, _pv in (('winw', 1280), ('winh', 720), ('borders', False)):
            try:
                _p = getattr(win.par, _pn, None)
                if _p is not None:
                    _p.val = _pv
            except Exception:
                pass
        win.nodeX, win.nodeY = 400, 0
        win.par.winopen.pulse()
    except Exception as e:
        print("[setup_body_window] Window COMP error: " + str(e))

    # --- 4. re-sync the REAL body_mask_top DAT (repair main pipeline) --
    try:
        bmt = op('/project1/body_mask_top')
        if bmt is not None:
            cb = bmt.par.callbacks.eval()
            if cb is not None and hasattr(cb, 'text'):
                fixed = open(
                    '/Users/thomasadair/projects/touchdesigner-dj-suite/'
                    'touchdesigner/scripts/segmentation_mask_reader.py'
                ).read()
                # Strip a leading UTF-8 BOM: TD's Python parser rejects U+FEFF
                # ("invalid non-printable character") and body_mask_top's DAT
                # would fail to compile, blacking out the main pipeline.
                cb.text = fixed.lstrip("\ufeff")
                bmt.cook(force=True)
                print("[setup_body_window] re-synced body_mask_top reader DAT")
    except Exception as e:
        print("[setup_body_window] body_mask_top re-sync skipped: " + str(e))

    print("=" * 60)
    print("[setup_body_window] DONE. Created: " + (", ".join(made) or "nothing new (refreshed existing)"))
    print("[setup_body_window] A window titled 'body_window' should now be")
    print("[setup_body_window] open showing a bright cyan outline of your body.")
    print("[setup_body_window] If it didn't pop, click /project1/body_window")
    print("[setup_body_window] and press its 'Open as Separate Window' pulse.")
    print("=" * 60)


_run()
