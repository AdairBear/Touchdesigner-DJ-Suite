#!/usr/bin/env python3
"""
diagnose_obs_double_image.py — Run from terminal (not TouchDesigner)
Connects to OBS via WebSocket, lists all sources in the current scene,
and flags duplicate Syphon/NDI/Spout sources causing the double-image bug.

Usage:
    source venv/bin/activate
    pip install obsws-python
    python touchdesigner/scripts/diagnose_obs_double_image.py

OBS must have WebSocket Server enabled (Tools → WebSocket Server Settings)
"""

import sys
import json
from collections import defaultdict

OBS_HOST     = 'localhost'
OBS_PORT     = 4455
OBS_PASSWORD = ''   # Set this if you have a password configured in OBS

def main():
    try:
        import obsws_python as obs
    except ImportError:
        print('[diag] obsws-python not installed. Run:')
        print('       pip install obsws-python')
        sys.exit(1)

    print(f'[diag] Connecting to OBS at {OBS_HOST}:{OBS_PORT}...')
    try:
        cl = obs.ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASSWORD, timeout=5)
    except Exception as e:
        print(f'[diag] Connection failed: {e}')
        print('[diag] Make sure OBS is running and WebSocket Server is enabled:')
        print('[diag]   OBS → Tools → WebSocket Server Settings → Enable WebSocket Server')
        sys.exit(1)

    # Get current scene
    scene_resp = cl.get_current_program_scene()
    scene_name = scene_resp.current_program_scene_name
    print(f'[diag] Current scene: "{scene_name}"')

    # Get all items in current scene
    items_resp = cl.get_scene_item_list(scene_name)
    items = items_resp.scene_items
    print(f'[diag] Found {len(items)} sources in scene\n')

    # Categorize by source type
    syphon_sources  = []
    ndi_sources     = []
    spout_sources   = []
    other_sources   = []
    source_names    = defaultdict(list)

    for item in items:
        src_name = item.get('sourceName', 'unknown')
        src_type = item.get('inputKind', item.get('sourceType', 'unknown'))
        enabled  = item.get('sceneItemEnabled', True)

        source_names[src_name].append(item)

        entry = {'name': src_name, 'type': src_type, 'enabled': enabled,
                 'id': item.get('sceneItemId', '?')}

        src_lower = (src_name + src_type).lower()
        if 'syphon' in src_lower:
            syphon_sources.append(entry)
        elif 'ndi' in src_lower:
            ndi_sources.append(entry)
        elif 'spout' in src_lower:
            spout_sources.append(entry)
        else:
            other_sources.append(entry)

        status = '✓' if enabled else '✗ (disabled)'
        print(f'  [{status}] {src_name!r:40s} type={src_type}')

    # ── Diagnose double-image suspects ───────────────────────────────────────
    print('\n[diag] ── Double-image diagnosis ──')
    issues_found = False

    # Check for duplicate source names
    for name, instances in source_names.items():
        if len(instances) > 1:
            print(f'[diag] !! DUPLICATE SOURCE: "{name}" appears {len(instances)} times')
            print(f'[diag]    IDs: {[i.get("sceneItemId") for i in instances]}')
            print(f'[diag]    FIX: Delete all but one instance in OBS Scene Editor')
            issues_found = True

    # Check for multiple Syphon sources (common TD double-image cause)
    if len(syphon_sources) > 1:
        print(f'[diag] !! MULTIPLE SYPHON SOURCES ({len(syphon_sources)}):')
        for s in syphon_sources:
            print(f'[diag]    • "{s["name"]}" (id={s["id"]}, enabled={s["enabled"]})')
        print('[diag]    FIX: Keep only one Syphon source. In TouchDesigner,')
        print('[diag]         check for duplicate Syphon Out TOPs — each one creates')
        print('[diag]         a separate Syphon server visible to OBS.')
        issues_found = True
    elif len(syphon_sources) == 1:
        print(f'[diag] ✓ Single Syphon source: "{syphon_sources[0]["name"]}"')

    # Check for Syphon + Spout overlap (cross-protocol duplicate)
    if syphon_sources and spout_sources:
        print('[diag] !! Syphon AND Spout sources both present — likely double-image')
        print('[diag]    FIX: Use only one protocol. Syphon = Mac native (recommended)')
        issues_found = True

    if not issues_found:
        print('[diag] ✓ No obvious duplicates found')
        print('[diag]   If double-image persists, check TD for duplicate Syphon Out TOPs:')
        print('[diag]   In TD Textport: print([o.name for o in ops() if "syphon" in o.name.lower()])')

    print('\n[diag] ── Recommended next step ──')
    if issues_found:
        print('[diag] 1. Remove duplicate sources in OBS')
        print('[diag] 2. In TouchDesigner, search for duplicate Syphon Out TOPs')
        print('[diag] 3. Ensure only ONE Syphon Out → ONE OBS Syphon source')
    else:
        print('[diag] Double-image may be inside TD — check render chain:')
        print('[diag]   Over TOP → is it compositing twice?')
        print('[diag]   Feedback TOP → is it accumulating frames?')

    cl.disconnect()
    print('\n[diag] Done.')

if __name__ == '__main__':
    main()
