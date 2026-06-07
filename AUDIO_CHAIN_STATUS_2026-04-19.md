# Audio reactivity status — 2026-04-19 10:25

## What's working
- Audio chain bootstrap in `aura_compositor.py` successfully auto-detects and selects the **PreSonus Studio 1824c** on load
- Final state confirmed in TD textport:
  - `[bootstrap] device -> AppleUSBAudioEngine:PreSonus:Studio 1824c:SC4M20100612:1,2`
  - `[bootstrap] audio_in: driver=default | device=... | active=True`
  - `[bootstrap] audio_spectrum max bin: 0.55498`  ← real audio arriving
- The 1824c is now visible in TD's device enumeration (it wasn't in earlier runs)

## What may still need attention
- **TD timeline was stuck at frame 543**. Transport ▶ button was lit (play state on) but frames weren't advancing in the editor — likely the aura pipeline is too expensive to cook at 60fps in editor mode.
- The Syphon output to OBS may still be at full speed independent of the editor UI cook rate — worth checking in OBS preview before the 2pm go-live.
- `audio_params AFTER FIX` section in the textport showed all zeros, but that output was captured BEFORE the bootstrap successfully pointed at the 1824c. Fresh values should populate once frames advance.

## Files modified this session
- `touchdesigner/scripts/aura_compositor.py` — robust device-priority bootstrap with full device enumeration printed, fallback chain: 1824c → blackhole/loopback → built-in mic. Also added a periodic `[audio]` diagnostic print every 120 frames (bass/mid/high/flame/sparkle/bloom).
- `touchdesigner/scripts/audio_reactive_mapper.py` — earlier bootstrap version (still active, runs on module load)

## Pre-stream checklist (for when you wake up)
1. Verify TD is actually cooking — check the FPS indicator in TD's top-left; if below 30 the aura pipeline needs to be slimmed or you'll need to jump into perform mode.
2. Check OBS preview of the Syphon source — if it's animated, the Syphon render path is working even if the editor is slow.
3. Save the .toe file with cmd+S from TD main window (NOT from the textport).
4. Play music → confirm fire aura reacts — look for pulsing bloom/flame intensity on bass hits.
5. If audio still flat, check `audio_params` channel values directly in TD by selecting the Constant CHOP and watching the value column.

## Outstanding tasks
- #17 Wire up audio reactivity chain — audio chain confirmed working, visual reactivity needs frame advance to verify
- #18 Fix OBS double-image overlay — NOT the branded overlays per your instruction; suspect TD Syphon output may be rendering doubled composition, or a second Syphon source
- #10 Get body-aura pipeline live for Sunday 2pm stream
