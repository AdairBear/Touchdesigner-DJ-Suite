# Baseline Audit — Body Outline vs Aura Problem

**Date:** 2026-06-05
**Auditor:** Claude (read-only audit, no code modified, nothing pushed)
**Scope:** Why the generative overlay renders as an *aura covering the body* instead of an *outline of the body*.

---

## 1. Repo location + current state

- **Path:** `/Users/thomasadair/projects/touchdesigner-dj-suite` (local Mac, found via Spotlight)
- **Remote:** `https://github.com/AdairBear/Touchdesigner-DJ-Suite.git`
- **Branch:** `main`
- **Commits:** exactly **1** — `400eeb0 init: TouchDesigner DJ Suite`
- **Crucial fact: essentially none of the aura pipeline is committed.** Git shows the entire `touchdesigner/` directory (scripts + shader), `body_mask_sender*.py`, all the dated status docs, the tests, and every `.toe` except the original stub as **untracked (`??`)**. `dj_visuals.toe` and `python/movement_tracker.py` are modified-but-uncommitted. **The public GitHub repo is the empty Mar-12 skeleton; all real work is local-only.** An audit of the pushed state alone would see nothing of substance.
- **Last activity:** `.toe` files dated **2026-04-12 → 2026-04-26**; docs **2026-03-12 → 2026-04-24**. Project has been dormant ~6 weeks.
- **Live processes at audit time:** none (no TouchDesigner, no tracker, no OBS running) — safe to inspect.
- **Brain MCP:** queried (`open-brain`) — **zero** relevant memories on TD-DJ / DJ visuals (top hit 0.084, all trading noise). No prior decisions captured for this project.

### `.toe` inventory (binary — cannot fully introspect without TouchDesigner)
| File | Size | Modified | Note |
|---|---|---|---|
| `dj_visuals.toe` | 311 KB | Apr 18 23:10 | working file, **modified/uncommitted** |
| `dj_visuals.14.toe` | 311 KB | Apr 18 23:10 | full network |
| `dj_visuals.live_2026-04-18.toe` | 311 KB | Apr 18 | go-live build w/ Syphon baked in |
| `dj_visuals.live_2026-04-19.6.toe` | 25 KB | Apr 23 | **shrunk** — possible operator loss (see §6) |
| `dj_visuals.live_2026-04-19.11/.toe` | 21 KB | Apr 26 | smallest, most recent |
| `dj_visuals.6.toe` | 4.8 KB | Apr 12 | near-empty stub |
| `CrashAutoSave.dj_visuals.12.toe` | 301 KB | Apr 18 | crash recovery |

The 311 KB → 25 KB → 21 KB shrink across "live" files is a **regression flag** already noted in `GO_LIVE_CONFIRMED.md`: operators may have been cleared. Which `.toe` is canonical is **unconfirmed** without opening TD.

**Transport for the body mask is NOT OSC.** OSC (port 7000) carries only pose *landmarks/metrics*. The segmentation image travels through a **shared-memory mmap file**: `/tmp/djsam_bodymask.raw` (307,204 bytes = 4-byte uint32 frame counter + 640×480 uint8 grayscale). TD reads it via a Script TOP callback (`segmentation_mask_reader.py`).

---

## 2. What works (verified by code reading — "soft completion" confirmed)

**Body tracking — works, with caveats.**
- `python/movement_tracker.py` (MediaPipe Pose, `enable_segmentation=True`) → OSC landmarks to `127.0.0.1:7000` + segmentation mask to mmap. Confirmed streaming live on Apr 19 (`GO_LIVE_NOW.md`).
- Multi-person (≤4) is **naive**: `detect_people_regions()` just slices the frame into halves/quadrants and runs a pose model per slice (`movement_tracker.py:181`). Not true per-person detection; overlapping margins, no identity tracking.
- Recurring operational friction: camera-0 contention between `movement_tracker.py` and `body_mask_sender.py`; macOS camera permission scoped to Terminal (must launch tracker from Terminal, not Finder).

**Audio reactivity — plumbed, "soft complete".**
- Chain confirmed Apr 19: PreSonus Studio 1824c → `audio_in` → `audio_spectrum` (FFT) → `audio_reactive_mapper.py` → `audio_params` CHOP (bass/mid/high/onset → flame/turbulence/sparkle/bloom). `aura_compositor.py` auto-detects the device and pushes per-frame values into the shader uniforms.
- **The recurring blocker** (`GO_LIVE_NOW.md` Step 2): the GLSL TOP's uniform *names* (`uFlameIntensity`…`uTime`) were never written by the build script, so the per-frame values never reached the shader. This was hand-patched from the Textport repeatedly and never made durable — hence "soft completion." `td_render_diag.txt` shows `audio_params` ≈ 0 (no music at audit) but the wiring is intact.

**Output path — works.** `final_composite → output → syphonOut1` (`TDSyphonSpoutOut`, `active=True`) → OBS Syphon Client. Verified end-to-end Apr 18/24. Performance was the live pain point: TD cooked at **~7 FPS in editor mode** (must use Perform Mode / F1 for 30–60 FPS).

---

## 3. What doesn't work — the aura problem, with the exact code path

**Desired:** a thin, crisp **silhouette edge** (outline) with flames riding the line.
**Actual:** a thick glowing band that reads as an **aura enveloping the body**.

The overlay is built as an *aura by design, end to end.* `docs/TD_BODY_AURA_BUILD_GUIDE.md:3` states the intent outright: *"the aura wraps around his body silhouette."* That is the thing Thomas does **not** want — and the whole pipeline is engineered to produce it. Three compounding causes:

### Cause A — Python emits a *filled, fattened, feathered* silhouette (no contour extraction)
`movement_tracker.py:_process_segmentation` (and the identical `body_mask_sender.py:81-87`):
```python
binary = (combined > 0.5).astype(np.uint8) * 255   # SOLID FILLED silhouette
kernel = np.ones((5, 5), np.uint8)
binary = cv2.dilate(binary, kernel, iterations=2)  # grows the fill ~10px outward
binary = cv2.GaussianBlur(binary, (15, 15), 0)     # feathers the boundary into a ~15px ramp
```
This is the opposite of an outline. It is a solid blob, **expanded** and **soft-feathered**. Grepping the entire Python tree for `Canny` / `morphologyEx` / `MORPH_GRADIENT` / `erode` returns **nothing** — there is no contour/edge extraction on the Python side anywhere.

### Cause B — the Edge TOP exists, but it edges a *pre-blurred* blob → a fat fuzzy band
The TD network (confirmed live in `td_render_diag.txt`, Apr 24) is:
```
body_mask_top → edge_detect (Edge TOP, Sobel) → edge_blur (Blur size 4) → fire_aura_glsl[0]
```
So an edge step **is** present (the going-in hypothesis "no edge extraction" is **false**). But Sobel run on a Gaussian-blurred fill responds across the *entire* ~15px blur ramp, yielding a **thick gradient band**, not a 1-px line — then `edge_blur` (size 4) widens it further. The "edge" is already an aura-width band before the shader touches it.

### Cause C — the shader deliberately *expands and blooms* whatever it receives
`touchdesigner/shaders/fire_aura.glsl`:
- `:247` `float expansion = 0.02 + flameInt*0.04 + motion*0.03 + burst*0.08;`
- `:248` `float softEdge = smoothstep(0.0, expansion, edge);`  ← soft-thresholds = **widens** the band, more on louder audio / bigger motion
- `:244` `float flameExpand = edge * (0.5 + flameMix*0.5);` + FBM noise layers ← pushes flame **outward** from the edge (comment line 243: *"Expand flame outward from body edge"*)
- `:208-213` fallback: if the mask reads black, render a **full-frame radial gradient** ("ambient fire") — so a dropped/stale mask fills the *entire frame* with fire.

Then post: `flame_layers (+noise) → bloom_blur (Blur size 12) → bloom_post (Add)`. A size-12 bloom on a band-shaped source bleeds the glow inward over the body and outward into the scene. Net visual: **thick, glowing, body-hugging haze = aura.** Bloom + outward flame expansion is exactly why it reads as "covering" rather than "outlining."

**Summary of the bug path:** filled mask → dilate+blur (Python) → Sobel-on-blur (fat band) → blur again → shader soft-expansion + outward FBM flame → size-12 bloom. Every stage *widens and fills*; **no stage ever constrains output to a thin constant-width contour.**

---

## 4. Prior attempts (chronological)

> `logs/iteration_log.md` is the **unfilled template** — only the example "Iteration 0" exists; Thomas never logged real iterations there. The actual trail lives in the dated status docs and the `_fix_*` / `_diag_*` TD scripts. Reconstructed below.

- **Mar 12** — `PROJECT_ASSESSMENT.md`: Python tracker/OBS/launcher complete; `.toe` is a 3.7 KB empty stub; tests added (45). TouchDesigner visuals flagged as "the biggest gap." No aura yet.
- **Mar 17** — Phase 2 / OSC integration docs + README written. Pivot toward generative graphics over OSC.
- **Apr 12–18** — Aura pipeline built in TD: `build_aura_pipeline.py` constructs `body_mask_top → edge_detect → edge_blur → fire_aura_glsl → flame_layers → bloom → final_composite → syphonOut1`. `.toe` grows to 311 KB. Syphon→OBS verified at ~5–7 FPS (`GO_LIVE_CHECKLIST_2026-04-18.md`); performance, not outline shape, was the focus.
- **Apr 19** — `AUDIO_CHAIN_STATUS`: audio device bootstrap fixed (1824c). `GO_LIVE_NOW.md`: discovered the **GLSL uniforms were never wired** → aura wasn't reacting to audio. Hand-patched from Textport (the recurring failure mode: "the Textport paste looks like it didn't submit").
- **Apr 23 (Thursday)** — Pivot to a *different* visual concept: `chop_normalizer`, `beat_detector_setup`, `transient_router`, `procedural_animation`, `geometry_instancing_pipeline` — i.e. a **3D Tube-SOP / geometry-instancing** look driven by beats, *separate from* the body-aura. Suggests the aura look was being set aside rather than fixed.
- **Apr 24** — `GO_LIVE_CONFIRMED.md` (automated audit): render chain intact, Syphon active, but a **`.toe` size regression** (311 KB → 25 KB) and **camera unavailable** flagged. Thursday geometry scripts present but **not wired** into the `.toe`.
- **Apr 26** — last `.toe` saves (21 KB). Project goes dormant.

**What was tried on the outline specifically:** an Edge TOP + edge-blur was added (the only deliberate "make it an outline" move), and `_fix_aura.py` / `_diag_aura.py` were written to repair uniform wiring and verify the chain. **What fell short:** the Edge TOP was placed *after* the Python dilate+blur and *before* a shader explicitly built to expand and bloom — so it never produced a thin outline. The outline-vs-aura shape was **never directly attacked**; effort went into audio reactivity, Syphon/OBS, performance, and a separate geometry concept.

---

## 5. The missing primitive

**A single, thin, constant-width contour that the stylization is *confined to* — and the removal of every step that widens or fills it.**

The pipeline has an edge *operator* but never produces an edge *result*, because the contour is (a) never extracted crisply, and (b) deliberately re-widened three times downstream. The missing primitive is **edge-confined rendering**: extract a clean 1–2 px body contour, then stylize *only that band*, with expansion and bloom turned down.

### Smallest possible fix (sketch only — not implemented)

**Option 1 — fix it at the source (recommended, ~5 lines, highest leverage).**
In `movement_tracker._process_segmentation` (and `body_mask_sender.py`), replace the dilate+blur *fill* with a morphological-gradient *contour*:
```python
binary = (combined > 0.5).astype(np.uint8) * 255
k = np.ones((3, 3), np.uint8)
outline = cv2.morphologyEx(binary, cv2.MORPH_GRADIENT, k)  # crisp ~1-2px contour
# outline = cv2.dilate(outline, k, iterations=1)           # optional: controlled thickness
mask_out = cv2.resize(outline, (MASK_W, MASK_H), interpolation=cv2.INTER_NEAREST)  # NEAREST, not LINEAR
```
`body_mask_top` now carries an outline, not a blob. The downstream Edge TOP becomes redundant (bypass it or feed the outline straight to the shader).

**Option 2 — fix it in TD (if Python is off-limits live).**
Feed a **crisp** binary mask (drop the Python GaussianBlur), keep `edge_detect`, but: set `edge_blur` size ≈ 1; in `fire_aura.glsl` cut the expansion terms (`expansion` → small constant, drop `flameExpand` outward bleed, constrain flame to `edge > 0.5` band); drop `bloom_blur` size 12 → ~2. This keeps the aura architecture but starves its widening.

**Either way the principle is the same:** generate flame *on a thin line*, do not generate a glow *and then try to shape it*.

### Also missing vs the desired outcome
- **Lightning toggle does not exist.** Only `fire_aura.glsl`. No lightning shader, no flames↔lightning switch anywhere. New work.
- **Color-shifting to music**: the fire palette exists and is bass-tinted, but full hue-cycling to audio is partial.

---

## 6. Open questions for Thomas (before build phase)

1. **Which `.toe` is canonical?** `dj_visuals.toe` (311 KB) or one of the shrunken 21–25 KB "live" files? The size regression may mean operators were lost. We need the real current network confirmed *in TouchDesigner* before building — the binary can't be diffed here.
2. **Fix at the Python source or in the TD network?** Option 1 (morphological-gradient contour in `movement_tracker.py`) is smallest and most robust, but changes the mask contract every `.toe` depends on. Option 2 keeps Python untouched but requires shader + TOP edits. Which surface do you want to own the outline?
3. **Outline thickness & style** — a hairline 1-px contour, or a 2–4 px "neon tube"? This sets whether we extract pure contour or contour-plus-controlled-dilate.
4. **Keep MediaPipe's filled segmentation at all?** Once we go to outline, the filled mask + dilate + 15 px blur is pure liability (it's also what caused the earlier 8-vs-4 byte `HEADER_SIZE` segfault). OK to delete the fill path entirely?
5. **Lightning** — is the flames↔lightning toggle in scope for the *baseline* build, or fast-follow after the outline is correct?
6. **One tracker or two?** `movement_tracker.py` (multi-person) and `body_mask_sender.py` (single-person) both grab camera 0 and both emit the same filled mask. Pick one as the source of truth before we change the mask format in two places.
7. **Commit the work?** The entire aura pipeline is uncommitted/local-only. Before refactoring, do you want a checkpoint commit so there's a baseline to diff against? (Not done in this audit — read-only.)

---

### Latent landmines noticed (not the aura bug, but will bite)
- `build_aura_pipeline.py:67` — the **inline fallback** mask reader still hardcodes `HEADER_SIZE = 8`, the exact mismatch that caused the TD `EXC_BAD_ACCESS` segfault. If the file-based DAT load ever fails and TD uses this fallback, the segfault returns.
- Camera-0 contention between the two trackers (documented as "Task #10", never resolved).
- GLSL uniform-name wiring is applied by hand from the Textport, not persisted by the builder — it silently un-sticks across `.toe` reloads.
