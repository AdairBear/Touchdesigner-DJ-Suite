# Kniteforce Radio — Go Live Checklist
## Sunday 2026-04-19, 2:00pm PDT

You have three manual steps. Do them in order. Nothing else.

---

## Step 1 — Start the body tracker (Terminal, NOT double-click)

The `.command` file can't see the camera when launched from Finder/AppleScript because macOS scopes camera permission to Terminal.app on this machine.

Open **Terminal** (Spotlight → "Terminal") and paste:

```
/Users/thomasadair/projects/touchdesigner-dj-suite/start_tracker.command
```

Press Return. You should see lines like:

```
---- starting body tracker ...
Project: /Users/thomasadair/projects/touchdesigner-dj-suite
Python:  .../venv/bin/python
[movement_tracker] camera 0 opened 640x480
[movement_tracker] pose model ready
[movement_tracker] streaming...
```

Leave that Terminal window open for the duration of the stream.

If you see `OpenCV: not authorized to capture video` — macOS lost camera permission for Terminal. Fix: System Settings → Privacy & Security → Camera → make sure Terminal is ON.

---

## Step 2 — Wire the GLSL uniforms (TouchDesigner Textport)

This is the blocker that's been stopping the fire aura from reacting to anything. The shader expects 10 uniform **names** on the GLSL TOP's Vectors page, but the build script never filled them in. One paste and you're done.

1. Click on TouchDesigner to bring it forward.
2. If the **Textport** window isn't visible already, open it: **Dialogs → Textport and DATs** (or press `Alt+T`).
3. Click on the prompt line at the bottom of the Textport — the line that starts with `python >>>`.
4. If there's any leftover text on that line (we saw `print("hello")` from a previous debugging attempt), select it (triple-click) and hit Delete.
5. The uniform-wiring command is already in your clipboard. Paste with **⌘V**.
6. Press **Return**.

You should see output like:

```
UNIFORMS WIRED: ['uFlameIntensity', 'uTurbulence', 'uDistortion', 'uSparkle',
                  'uMotionEnergy', 'uBassEnergy', 'uMidEnergy', 'uHighEnergy',
                  'uBurstDecay', 'uTime']
```

**Clipboard contents (in case it got cleared — paste this manually):**

```python
g=op('/project1/fire_aura_glsl'); n=['uFlameIntensity','uTurbulence','uDistortion','uSparkle','uMotionEnergy','uBassEnergy','uMidEnergy','uHighEnergy','uBurstDecay','uTime']; [setattr(g.par,'uniformname'+str(i+1),v) for i,v in enumerate(n)]; g.cook(force=True); print('UNIFORMS WIRED:',[getattr(g.par,'uniformname'+str(i+1)).val for i in range(10)])
```

---

## Step 3 — Play a track and verify

At this point:

- Body tracker is streaming pose → OSC port 7000 → TD `/project1/osc_body_receiver`
- Body mask is streaming via mmap `/tmp/djsam_bodymask.raw` → TD `/project1/body_mask_top`
- GLSL shader uniforms are wired, so `aura_compositor.onFrameStart` per-frame values finally reach the shader
- TD `syphonOut1` is emitting `TDSyphonSpoutOut` → OBS Syphon Client

**Start Serato and play one track.** In TD Textport watch for lines like:

```
[audio] bass=0.42 mid=0.31 high=0.18 flame=0.51 sparkle=0.22 bloom=0.55
```

If `bass=0.0 mid=0.0 high=0.0` — the audio device isn't picking up Serato. Fix: in TD, select `/project1/audio_in`, check that Driver=default and Device=`PreSonus Studio 1824c`. If Serato is routed elsewhere, change to Built-in Microphone temporarily (room mic picks up speakers).

In OBS: you should see the fire aura flickering around your silhouette in the preview window.

---

## Step 4 — Go live

OBS → Start Streaming → confirm both YouTube and Twitch are green in the stream log.

Kniteforce Radio scene should already be loaded (`Profile: KF Radio 2026 — Scene: Kniteforce Twitch` is showing in the OBS title bar from the Textport screenshot).

---

## If the Textport paste looks like it didn't submit

This has been the recurring issue. Fallback: copy the uniform-wiring line below into a fresh **Text DAT** (right-click in TD network, Add Operator → DAT → Text). Paste the code, then right-click the DAT → `Run`. Same effect.

```python
g=op('/project1/fire_aura_glsl')
for i,v in enumerate(['uFlameIntensity','uTurbulence','uDistortion','uSparkle','uMotionEnergy','uBassEnergy','uMidEnergy','uHighEnergy','uBurstDecay','uTime']):
    setattr(g.par, 'uniformname'+str(i+1), v)
g.cook(force=True)
print('uniforms wired:', [getattr(g.par,'uniformname'+str(i+1)).val for i in range(10)])
```

---

## Known-good state reference

- `.toe`: `dj_visuals.live_2026-04-19.2.toe` (the 14.toe you see is a ghost from an accidental open; you can close it)
- Syphon sender name: `TDSyphonSpoutOut`
- OSC port: `127.0.0.1:7000`
- Mask mmap: `/tmp/djsam_bodymask.raw` (307204 bytes: 4B frame counter + 640×480 uint8)
- OBS scene: `Kniteforce Twitch` (profile `KF Radio 2026`)
