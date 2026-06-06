# segmentation_mask_reader.py -- Script TOP callback
# ====================================================================
# Reads the body segmentation mask from shared memory (mmap file)
# written by movement_tracker.py / body_mask_sender.py and loads it
# into a TOP texture for the aura compositing pipeline.
#
# SETUP IN TOUCHDESIGNER:
#   1. Create Script TOP  ->  name: "body_mask_top"
#      - Resolution: 640 x 480  (must match MASK_W/MASK_H in tracker)
#      - Pixel Format: 8-bit fixed (Mono)
#      - DAT: point to this script DAT
#   2. Create Text DAT  ->  name: "segmentation_mask_reader"
#      - Paste this script
#      - Set Script TOP's "Callbacks DAT" -> segmentation_mask_reader
#
# The Script TOP calls cook() every frame. We read the mmap, extract
# the grayscale mask, and write it into the TOP's numpy array.
# ====================================================================

import numpy as np
import mmap
import os
import struct

# Must match movement_tracker.py / body_mask_sender.py
# IMPORTANT: header is a single 4-byte uint32 frame counter.
# A previous 8-byte (+ timestamp) layout caused an mmap size mismatch
# because the file on disk is 4 + MASK_W*MASK_H bytes -- reading 8 bytes
# at offset 0 steals the first 4 pixels of the mask, and asking mmap
# for (8 + MASK_W*MASK_H) bytes fails because the file is 4 bytes short,
# which made the reader silently fall back to outputting black.
MASK_PATH = "/tmp/djsam_bodymask.raw"
MASK_W = 640
MASK_H = 480
HEADER_SIZE = 4   # 4B frame_counter (uint32, little-endian)
TOTAL_SIZE = HEADER_SIZE + MASK_W * MASK_H

# Module-level mmap handle (persists across cook calls)
_fh = None
_mm = None
_last_frame = -1


def _open_mmap():
    """Open or reopen the shared memory file."""
    global _fh, _mm
    if _mm is not None:
        try:
            _mm.close()
        except Exception:
            pass
    if _fh is not None:
        try:
            _fh.close()
        except Exception:
            pass
    if not os.path.exists(MASK_PATH):
        _fh = None
        _mm = None
        return False
    try:
        _fh = open(MASK_PATH, 'r+b')
        _mm = mmap.mmap(_fh.fileno(), TOTAL_SIZE, access=mmap.ACCESS_READ)
        return True
    except Exception as e:
        print('[segmentation_mask_reader] mmap open error: ' + str(e))
        _fh = None
        _mm = None
        return False


def cook(scriptOP):
    """Called every frame by the Script TOP.
    Reads the mmap mask and writes it into the TOP's pixel buffer.
    """
    global _mm, _last_frame

    # Open mmap if not yet open
    if _mm is None:
        if not _open_mmap():
            # No mask file yet -- output black
            scriptOP.copyNumpyArray(
                np.zeros((MASK_H, MASK_W, 4), dtype=np.float32)
            )
            return

    try:
        _mm.seek(0)
        header = _mm.read(HEADER_SIZE)
        frame_num = struct.unpack('<I', header[0:4])[0]

        # Skip if same frame (save GPU upload)
        if frame_num == _last_frame:
            return
        _last_frame = frame_num

        # Read mask body
        raw = _mm.read(MASK_W * MASK_H)
        mask = np.frombuffer(raw, dtype=np.uint8).reshape((MASK_H, MASK_W))

        # Convert to float32 RGBA for Script TOP
        # Mask goes into all channels so downstream TOPs can sample any channel
        mask_f = mask.astype(np.float32) / 255.0
        rgba = np.zeros((MASK_H, MASK_W, 4), dtype=np.float32)
        rgba[:, :, 0] = mask_f   # R
        rgba[:, :, 1] = mask_f   # G
        rgba[:, :, 2] = mask_f   # B
        rgba[:, :, 3] = mask_f   # A

        scriptOP.copyNumpyArray(rgba)

    except Exception as e:
        print('[segmentation_mask_reader] read error: ' + str(e))
        # Try to reopen next frame
        _open_mmap()


def setup(scriptOP):
    """Called once when the Script TOP is created or script is modified."""
    scriptOP.par.resolutionw = MASK_W
    scriptOP.par.resolutionh = MASK_H
    print('[segmentation_mask_reader] Expecting mask at ' + MASK_PATH + ' (' + str(MASK_W) + 'x' + str(MASK_H) + ')')
    _open_mmap()
