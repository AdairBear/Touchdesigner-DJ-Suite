# particle_emitter_controller.py — Script CHOP / Execute DAT
# =============================================================
# Extracts body edge contour from the segmentation mask and generates
# particle emission points for the particlesGPU system.
# The contour points define WHERE fire particles spawn — along the
# body silhouette edge, creating the aura effect around Thomas.
#
# SETUP IN TOUCHDESIGNER:
#   1. This script is used as a Script CHOP callback or as a
#      standalone Execute DAT that writes into a Table DAT.
#
#   OPTION A — Script CHOP (recommended):
#      - Create Script CHOP  →  name: "emitter_points"
#      - Callbacks DAT: point to this script
#      - Outputs: tx ty tz (particle birth positions)
#                 nx ny nz (outward normals for emission direction)
#                 intensity (edge strength)
#
#   OPTION B — Feed into particlesGPU via SOP:
#      - Create Table DAT  →  name: "emitter_table"
#      - This script writes contour points into the table
#      - Convert Table → SOP → particlesGPU birth location
#
#   2. Inputs:
#      - body_mask_top (Script TOP from segmentation_mask_reader)
#      - body_channels  (Constant CHOP from osc_body_receiver)
# =============================================================

import numpy as np

# Number of emission points along the contour
MAX_EMIT_POINTS = 128
# How much to expand the contour outward (pixels) for the aura glow offset
CONTOUR_EXPAND = 4.0


def cook(scriptOP):
    """Called every frame by the Script CHOP.
    Reads body mask TOP, extracts edge contour, outputs emission points.
    """

    # Get the body mask texture
    mask_top = op('body_mask_top')
    if mask_top is None or mask_top.width == 0:
        return

    # Read mask as numpy array
    try:
        arr = mask_top.numpyArray(delayed=True)
        if arr is None:
            return
        # Take red channel (all channels are identical)
        mask = (arr[:, :, 0] * 255).astype(np.uint8)
    except Exception:
        return

    h, w = mask.shape

    # --- Edge detection via Sobel-like gradient ---
    # Shift mask in 4 directions and compute gradient magnitude
    pad = np.pad(mask, 1, mode='constant', constant_values=0)
    dx = pad[1:-1, 2:].astype(np.float32) - pad[1:-1, :-2].astype(np.float32)
    dy = pad[2:, 1:-1].astype(np.float32) - pad[:-2, 1:-1].astype(np.float32)
    edge_mag = np.sqrt(dx * dx + dy * dy)

    # Threshold to get edge pixels
    edge_threshold = 30.0
    edge_mask = edge_mag > edge_threshold

    # Get edge pixel coordinates
    ey, ex = np.where(edge_mask)

    if len(ex) == 0:
        # No body detected — emit nothing
        scriptOP.numSamples = 0
        return

    # Subsample to MAX_EMIT_POINTS evenly spaced along the contour
    if len(ex) > MAX_EMIT_POINTS:
        indices = np.linspace(0, len(ex) - 1, MAX_EMIT_POINTS, dtype=int)
    else:
        indices = np.arange(len(ex))

    num_pts = len(indices)
    scriptOP.numSamples = num_pts

    # Get motion energy for emission intensity modulation
    body_ch = op('body_channels')
    motion_energy = 0.0
    if body_ch is not None:
        try:
            idx = body_ch.chanIndex('motion_energy')
            if idx >= 0:
                motion_energy = float(body_ch[idx])
        except Exception:
            pass

    # Normalize motion energy to 0-1 range (raw can be 0-100+)
    motion_norm = min(motion_energy / 50.0, 1.0)

    # Compute outward normals from gradient
    for i, ci in enumerate(indices):
        px = ex[ci]
        py = ey[ci]

        # Normalize to -1..1 range (TD coordinate space, origin center)
        tx = (px / w) * 2.0 - 1.0
        ty = -((py / h) * 2.0 - 1.0)  # Flip Y (TD is Y-up)
        tz = 0.0

        # Normal direction (outward from body)
        gx = dx[py, px]
        gy = dy[py, px]
        mag = max(np.sqrt(gx * gx + gy * gy), 0.001)
        nx = (gx / mag)
        ny = -(gy / mag)
        nz = 0.0

        # Offset position slightly outward for glow
        offset = CONTOUR_EXPAND / w
        tx += nx * offset
        ty += ny * offset

        # Intensity: base edge strength + motion boost
        edge_str = min(edge_mag[py, px] / 255.0, 1.0)
        intensity = edge_str * (0.5 + 0.5 * motion_norm)

        # Write to Script CHOP channels
        scriptOP['tx'][i] = tx
        scriptOP['ty'][i] = ty
        scriptOP['tz'][i] = tz
        scriptOP['nx'][i] = nx
        scriptOP['ny'][i] = ny
        scriptOP['nz'][i] = nz
        scriptOP['intensity'][i] = intensity


def setup(scriptOP):
    """Initialize channels."""
    scriptOP.clear()
    for name in ['tx', 'ty', 'tz', 'nx', 'ny', 'nz', 'intensity']:
        scriptOP.appendChan(name)
    scriptOP.numSamples = MAX_EMIT_POINTS
    print("[particle_emitter_controller] Initialized with", MAX_EMIT_POINTS, "max points")
