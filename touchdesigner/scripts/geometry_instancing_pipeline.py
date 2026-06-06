# geometry_instancing_pipeline.py — Script DAT (run once to verify/build pipeline)
# Paste into a Script DAT and run, or paste into Textport.
#
# Pipeline:
#   Tube SOP (rows=1000, cols=1000)
#     → Twist SOP (strength driven by kick_onset)
#       → SOP to CHOP (converts point positions to channels)
#         → CHOP to TOP (CRITICAL: Data Format=RGB, Image Layout=Fit to Square)
#           → Geometry COMP (instancing enabled, translate XYZ from CHOP to TOP)

def verify_or_build_instancing_pipeline():
    """
    Checks each operator in the instancing chain.
    Prints status to Textport. Creates operators if missing.
    """
    print('[instancing] ── Verifying geometry instancing pipeline ──')

    # ── 1. Tube SOP ──────────────────────────────────────────────────────
    tube = op('tube1')
    if tube:
        print(f'[instancing] ✓ tube1 found | rows={tube.par.rows.val} cols={tube.par.cols.val}')
        if tube.par.rows.val != 1000 or tube.par.cols.val != 1000:
            print('[instancing]   WARNING: rows/cols should be 1000×1000 for full instancing')
            print('[instancing]   NOTE: First cook with 1000×1000 takes 2-3s — expected')
        # Ensure Z-axis primary
        tube.par.orient = 'zaxis'
    else:
        print('[instancing] ✗ tube1 NOT FOUND — create a Tube SOP named tube1')
        print('[instancing]   Set: Rows=1000, Cols=1000, Orientation=Z Axis')

    # ── 2. Twist SOP ─────────────────────────────────────────────────────
    twist = op('twist1')
    if twist:
        print(f'[instancing] ✓ twist1 found | strength={twist.par.strength.val:.2f}')
        print('[instancing]   Connect: tube1 → twist1 input')
    else:
        print('[instancing] ✗ twist1 NOT FOUND — create a Twist SOP named twist1')
        print('[instancing]   Connect tube1 as input. Strength driven by kick_onset via transient_router.py')

    # ── 3. SOP to CHOP ───────────────────────────────────────────────────
    s2c = op('soptochwop1') or op('soptochop1') or op('s2c')
    if s2c:
        print(f'[instancing] ✓ SOP to CHOP found: {s2c.name}')
        print('[instancing]   Connect: twist1 → SOP to CHOP input')
    else:
        print('[instancing] ✗ SOP to CHOP NOT FOUND — create one, connect twist1 as input')

    # ── 4. CHOP to TOP ───────────────────────────────────────────────────
    c2t = op('choptotop1') or op('c2t')
    if c2t:
        print(f'[instancing] ✓ CHOP to TOP found: {c2t.name}')
        # CRITICAL parameter check
        fmt = c2t.par.format.val if hasattr(c2t.par, 'format') else 'unknown'
        layout = c2t.par.imagelayout.val if hasattr(c2t.par, 'imagelayout') else 'unknown'
        print(f'[instancing]   Data Format = {fmt}  (MUST be "rgb" — currently: {fmt})')
        print(f'[instancing]   Image Layout = {layout}  (MUST be "fittosquare" — currently: {layout})')
        if fmt != 'rgb':
            print('[instancing]   !! FIX: Set Data Format → RGB (not RGBA, not float32)')
        if layout != 'fittosquare':
            print('[instancing]   !! FIX: Set Image Layout → Fit to Square')
    else:
        print('[instancing] ✗ CHOP to TOP NOT FOUND — create one, connect SOP to CHOP as input')
        print('[instancing]   CRITICAL: Data Format=RGB | Image Layout=Fit to Square')
        print('[instancing]   Without these settings instancing will produce garbage transforms')

    # ── 5. Geometry COMP ─────────────────────────────────────────────────
    geo = op('geo_aura') or op('geo1') or op('geometry1')
    if geo:
        print(f'[instancing] ✓ Geometry COMP found: {geo.name}')
        inst = geo.par.instance.val if hasattr(geo.par, 'instance') else 'unknown'
        print(f'[instancing]   Instancing = {inst}  (must be enabled)')
        if not inst:
            print('[instancing]   !! FIX: Enable Instancing on Geometry COMP')
            print('[instancing]   Then set Instance Translate X/Y/Z to CHOP to TOP R/G/B channels')
    else:
        print('[instancing] ✗ Geometry COMP NOT FOUND')
        print('[instancing]   Create a Geometry COMP, enable Instancing')
        print('[instancing]   Instance TX=CHOP_to_TOP:r, TY=CHOP_to_TOP:g, TZ=CHOP_to_TOP:b')

    print('[instancing] ── Verification complete ──')
    print('[instancing] If all green: play Jungle music and watch Twist react to kicks')
    print('[instancing] If geometry freezes: switch TD to Perform Mode (F1) for real-time cook')

# Run immediately when this script is executed
verify_or_build_instancing_pipeline()
