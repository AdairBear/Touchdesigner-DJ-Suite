# TD-DJ-Suite — Desk Session Guide (v2 Network)

> Branch: `feat/td-network-v2-builder`
> Last updated: 2026-06-23

This is the current session guide for verifying the v2 TD network end-to-end.
The v2 builder (`touchdesigner/scripts/build_network_v2.py`) creates the full
operator chain programmatically — no manual wiring needed.

---

## Before you open TouchDesigner

```bash
git checkout feat/td-network-v2-builder && git pull
source venv/bin/activate
pytest tests/test_edge_outline.py tests/test_visual_mode.py -v
# Expect: 18 passed
```

---

## Step 0 — Build the v2 network in TD Textport

This replaces all manual wiring from the old Phase 1 guide.

1. Open **`dj_visuals.toe`** (311 KB at repo root — this is the canonical file).
2. Open the Textport: **Alt+T**.
3. Verify `REPO_ROOT` at the top of `build_network_v2.py` matches your machine:
   `/Users/thomasadair/projects/touchdesigner-dj-suite`
4. Run the builder — paste this in the Textport and press Enter:

   ```python
   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/build_network_v2.py').read())
   ```

5. Watch the Textport log. Each operator prints as it is created or reused.
   Expected final line: `[build_v2] === build complete ===`
6. The full chain will appear under `/project1`:
   ```
   segmentation_mask_reader (Text DAT)
   body_mask_top (Script TOP, 640×480)
     → edge_detect (Edge TOP, upscale to 1280×720)
     → edge_blur (Blur TOP)
     → fire_aura_glsl (GLSL TOP)  ─┐
     → lightning_glsl (GLSL TOP)  ─┤→ visual_switch (Switch TOP)
   zero_src (Constant TOP, black) ─┘      ↓
   oscin1 (OSC In CHOP, port 7000)   bloom_blur → bloom_post
   audio_in (Audio Device In CHOP)        ↓
   audio_spectrum (Audio Spectrum)   final_composite (Null TOP)
   aura_compositor (Execute DAT)          ↓
                                     syphonOut1 (Syphon/Spout Out TOP)
   ```

---

## Step 1 — Audio device: select PreSonus 1824c

The one remaining manual touch after the build.

- Click `audio_in` → Parameters → **Device** → select **PreSonus Studio 1824c**.
- (The bootstrap in `aura_compositor.py` tries to auto-select 1824c, but it
  may not fire until you verify it manually on first load.)

---

## Step 2 — Confirm the contour is a thin line

1. Start the tracker in a Terminal window:
   ```bash
   source venv/bin/activate
   python python/movement_tracker.py --max-people 1
   ```
2. Watch the Terminal log for lines like:
   ```
   contour px=NNNN (0.8% of 640x480) — thin outline if low, blob if high
   ```
   - **Good:** 0.3%–2% of frame → thin line ✓
   - **Bad:** >10% → blob still being emitted → stop and flag (something upstream re-filled the mask)
3. In TD, look at `body_mask_top` — it should show a **silhouette outline**, not a filled body.

---

## Step 3 — Confirm flame rides the contour

- View `fire_aura_glsl` output.
- **Good:** flame sits on/near the contour line and licks off it.
- **If still a body-covering haze:** reduce bloom:
  - In `bloom_blur`: drop `size` from 3 toward 1–2.
  - In `fire_aura.glsl`: reduce `expansion` / `flameExpand` terms.
  - Note what you changed in `logs/iteration_log.md`.

---

## Step 4 — Confirm flame↔lightning toggle

The Switch TOP is wired to `/visual/mode` via `oscin1` — no manual wiring needed.

**Test via config file:**

```bash
# Switch to lightning:
python -c "
import json, pathlib
p = pathlib.Path('configs/visual_mode.json')
p.write_text(json.dumps({'mode': 'lightning'}))
print('set lightning')
"

# Switch back to flame:
python -c "
import json, pathlib
p = pathlib.Path('configs/visual_mode.json')
p.write_text(json.dumps({'mode': 'flame'}))
print('set flame')
"
```

Or use the movement tracker's OSC sender — it reads `configs/visual_mode.json`
and emits `/visual/mode` 0.0 (flame) or 1.0 (lightning) on each poll cycle.

- **Good:** visual_switch index changes within ~1s of writing the file.
- **If no switch:** check OSC In CHOP `oscin1` is active on port 7000, and that
  `movement_tracker.py` is running (it's the OSC sender).

---

## Step 5 — Confirm audio uniforms arrive at the GLSL TOP

1. Play music through the PreSonus 1824c chain.
2. In `fire_aura_glsl` Parameters → scroll to the custom **Vectors** page.
3. Watch `value0x`–`value9x` — they should move with the audio.
   - **value5x** = `uMotionEnergy` (motion-driven)
   - **value5x** = `uBassEnergy` (bass)
   - Expect values >0.01 when music is playing.
4. If stuck at 0.0: `aura_compositor` Execute DAT may not be active. Verify:
   - `aura_compositor` Parameters → **Active** = On, **Frame Start** = On.
   - If the device wasn't 1824c, fix Step 1 and re-check.

---

## Step 6 — Syphon → OBS + Perform Mode

1. In OBS: add a **Syphon Client** source pointing at sender name
   **`TDSyphonSpoutOut`**.
2. Confirm the outline overlay appears in OBS preview (NOT "New Radio DJ Scene"
   — add this to a new dev/scratch scene per the sacred-scene rule).
3. In TD: press **F1** (Perform Mode). FPS should jump from ~7 (editor) to 30–60.
4. Log the observed FPS in `logs/iteration_log.md`.

---

## After the session — log your observations

Add an entry to `logs/iteration_log.md`:

```markdown
## Iteration N — YYYY-MM-DD

- Contour: thin / blob (px %, frame %)
- Flame look: rides contour / hazes
- Lightning toggle: works / needs fix
- Audio uniforms: moving / stuck at 0
- FPS in Perform Mode: N fps
- OBS output: confirmed / not yet
- Notes: ...
```

Then report back — I'll take the next step based on what you observed.

---

## OBS auto-switcher note (dormant — read before enabling)

`touchdesigner/scripts/obs_websocket_td.py` contains a beat-reactive scene
switcher targeting `'Layer 0 — Drop'` / `'Layer 0 — Build'` / `'Layer 0 — Baseline'`.
It is **not active** (not wired to a CHOP Execute DAT in the v2 network).
If you enable it, you must first **create those three scenes in OBS** — they don't
exist yet. The **"New Radio DJ Scene" is sacred and must never be touched** — the
SCENES dict is coded to never reference it. Enable the switcher only after those
scenes exist and you've tested it in a scratch OBS setup, never against the production
scene.
