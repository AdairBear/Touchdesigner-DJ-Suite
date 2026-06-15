# Go-live checklist — Kniteforce Radio, 2026-04-18

Prepared after pipeline verification at ~23:00. State at checklist time:

- TouchDesigner: running, project **saved** as `/Users/thomasadair/projects/touchdesigner-dj-suite/dj_visuals.live_2026-04-18.toe` (311 KB, with `syphonOut1` wiring persisted + `.1.toe` auto-backup beside it)
- OBS: receiving feed, CPU 3.2%, **FPS 5.29 / 30** (TD is the bottleneck, not OBS)
- Pipeline end-to-end: **TD `out1` → Syphon `TDSyphonSpoutOut` → OBS `Syphon Client` source** — verified with jellybeans render visible in OBS preview

## Recovery cheat sheet

If TD crashes or the `syphonOut1` TOP goes missing, re-open `dj_visuals.live_2026-04-18.toe` — the Syphon wiring is baked into the file. If for any reason it still doesn't appear, paste this into the Textport (Dialogs → Textport and DATs) to rebuild:

```python
p = op('/project1')
s = p.create(syphonspoutoutTOP, 'syphonOut1')
s.inputConnectors[0].connect(op('/project1/out1'))
```

Then in OBS, the `Syphon Client` source should auto-reattach to `[TouchDesigner] TDSyphonSpoutOut`. If not, open the source's Properties dialog and reselect the server from the dropdown.

## Performance note

OBS is reading at 5.29 FPS because TD is cooking at ~7 FPS. The expensive path is `moviefilein1 → displace1 → geo1 → render → out1` (3D cube with displacement on a looping jellybean movie). If the visuals look too choppy on the stream:

- **Quick fix:** point Syphon at the 2D source directly. In Textport: `op('/project1/syphonOut1').inputConnectors[0].connect(op('/project1/moviefilein1'))`. Kills the 3D cube but jumps FPS to 30+.
- **Alternative:** disable `geo1`'s cooking while idle (right-click → Allow Cooking off) and re-enable only when you want the cube on screen.
- **Root cause** of the general slowness: leftover `movement_tracker` DATs from prior `dj_visuals` projects still try to `mmap` `/tmp/djsam_bodymask.raw` every frame and fail (visible in Textport: `[segmentation_mask_reader] mmap open error: mmap length is greater than file size`). Deferred for post-stream (task #10).

## Pre-stream checklist (T-15 min)

Visual:

1. Focus OBS. Confirm the scene picker shows "New Radio DJ Scene" (the solo-DJ scene with visuals + camera) — that is the selected scene right now.
2. Confirm `Syphon Client` source preview shows moving jellybeans. If black, see "Critical state warning" above.
3. Confirm the camera source (`Mr Arthur`) is also showing your live cam in the overlay.
4. Scrub the preview window's framing — logo readable, camera not clipping.

Audio:

5. OBS audio mixer: confirm the DJ audio source is unmuted and levels are hitting around -12 to -6 dBFS on the VU. If silent, check macOS Audio MIDI Setup and OBS Settings → Audio → Desktop Audio device.
6. Do a quick voice test — say "test" on mic, watch the meter move.

Streaming destination:

7. OBS Settings → Stream. Confirm:
   - Service: YouTube - RTMP (for tonight's target, per session notes)
   - Server: matches YouTube Studio's ingestion endpoint
   - Stream Key: set (this is the per-broadcast secret — YouTube rotates it per event; grab the current one from YouTube Studio → Go Live → Stream before starting)
8. Settings → Output → Streaming tab. Confirm:
   - Encoder: Apple VT H264 Hardware (or whatever was set)
   - Bitrate: 6000 Kbps for 1080p30 is the YouTube-recommended sweet spot
   - Keyframe interval: 2 seconds
9. Settings → Video. Canvas 1920×1080, Output 1920×1080, FPS 30.

Network:

10. Run a speed test — need sustained upload ≥ 8 Mbps for 6 Mbps stream with headroom.
11. If on wifi, consider plugging in Ethernet — stream drops hurt more than lower bitrate.

## Go-live sequence

1. In YouTube Studio, click **Go Live** on the scheduled broadcast (or create one). Copy the stream key to OBS if it changed.
2. In OBS: **Start Streaming** (big green button). Wait 10-15 sec.
3. Back in YouTube Studio: confirm the preview window shows incoming signal (green). Do NOT click "Go Live" in YT Studio yet.
4. Verify everything looks right in YT Studio preview for ~30 sec. Watch for: audio sync, video freezes, aspect ratio.
5. Click **Go Live** in YouTube Studio. You are now broadcasting to viewers.
6. Post the watch URL to whoever needs it (Kniteforce socials, Discord, wherever).

## During the stream

- Keep one eye on OBS bottom-right: bitrate bars should stay green. If they go yellow/red, network is congested.
- If OBS CPU goes above 60%, close Chrome tabs and any extra apps.
- If TD FPS drops below 5, consider the "Quick fix" above (Syphon → moviefilein1 direct).
- Do NOT touch the TD project file open dialog or Textport unless you know what you're doing — one wrong click and the syphonOut1 TOP can disconnect.

## End of stream

1. YouTube Studio: click **End Stream**.
2. OBS: **Stop Streaming**.
3. TouchDesigner: File → Save to overwrite `dj_visuals.live_2026-04-18.toe` with any final tweaks (it's already your working file).
4. Optional: download the YouTube broadcast's archive for a local backup.

## Known deferred issues (post-stream)

- **Task #10** — `movement_tracker.py` opens camera 0 at MovementTracker() init, which conflicts with `body_mask_sender.py` owning camera 0. Also loads 4 MediaPipe pose models w/ segmentation, which hangs TD onStart for minutes. The `HEADER_SIZE` mismatch (8 vs 4 bytes) was already fixed — camera conflict and model-load cost are the remaining blockers. Fix before the next gig by either (a) passing a camera handle around instead of opening fresh, or (b) making the MovementTracker lazy-init (don't open camera until `start()` is called).
- The background `segmentation_mask_reader` mmap error is benign tonight but noisy in the log. Remove the reader DAT from the project or point it at a valid mmap file.

## Emergency recovery

If TD crashes mid-stream:

1. Don't panic — OBS will keep streaming with the last Syphon frame frozen on screen until TD comes back (usually 2-5 seconds of static).
2. Relaunch TD — if the Desktop file `NewProject.1.toe` is there, open it, and immediately paste the 3-line Python from "Critical state warning" above into the Textport.
3. If TD won't launch (fatal dialog), kill it from Activity Monitor and hold Shift while clicking the file in File → Open. That skips onStart scripts.
4. Worst case: switch OBS to a static holding slide (one of the Kniteforce logo sources) while you restart TD.
