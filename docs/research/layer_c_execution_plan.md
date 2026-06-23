# Layer C Execution Plan — Gaussian Splatting Jungle Scene

**Written:** 2026-06-07  
**Status:** Plan only — no code. Gated on Phase 1 desk verification.  
**Branch discipline:** No Layer C code lands until Phase 1 merges to main.

---

## Prerequisites (must ALL be true before starting)

- [ ] Phase 1 (body outline / flame / lightning baseline) is **desk-verified and merged to main**. This is the only hard gate. Do not start Stage 0 until this is done.
- [ ] TDGS commercial license resolved (see Q1 below — email hello@lakeheckaman.com before streaming live)
- [ ] TDGS .tox downloaded: subscribe at `patreon.com/water__shed` ($4/month) or purchase the 1.3.1 post one-time (~$25–30)
- [ ] Chosen scene file downloaded and confirmed license-ok (see Q2 + scene priority order below)
- [ ] OBS scene "Layer C — Jungle Splat" created as **new scene, additive** — "New Radio DJ Scene" untouched

---

## Open Questions — Answered

### Q1: TDGS 1.3.1 — access path, cost, license

**Access:** `patreon.com/water__shed` — $4/month subscription (lowest tier) or ~$25–30 per individual post one-time purchase. No free tier for the .tox. No open-source distribution of TDGS 1.3.1.

**License:** **CC BY-NC-ND 4.0** — non-commercial use only by default.

**Commercial streaming blocker:** Thomas's monetized DJ streams = commercial use. The default CC BY-NC-ND 4.0 license explicitly prohibits this. You must get explicit written commercial permission before using TDGS in a live-streamed set.

**Action required before Stage 0:** Email **hello@lakeheckaman.com** — state that you are a solo VJ/DJ, describe the use case (Twitch/YouTube DJ stream), and ask for commercial use permission. Lake Heckaman is a solo creator — this is likely informal and quick, possibly free or a small one-time fee.

**If commercial permission is denied or takes too long:**
- **Fallback A:** yeataro/TD-Gaussian-Splatting (GitHub, free, macOS patched for Apple Silicon). Less polished, more style controls. Check its license before use — appears more permissive but verify.
- **Fallback B:** MetalSplatter (MIT, no restrictions) — requires custom Swift work to add Syphon bridge. Higher dev overhead.
- **Recommendation:** Subscribe $4/month to get the .tox and start desk testing while the commercial license email is in flight. Test before the license resolves — just don't stream live until it's confirmed.

---

### Q2: NorCal Redwood scenes

**Verdict: No pre-made NorCal redwood/sequoia Gaussian Splat scenes exist in the public corpus as of June 2026.**

Muir Woods, Armstrong Redwoods, Avenue of Giants, Fern Canyon — nothing has been captured and published as a downloadable .PLY in any platform (SuperSplat, Sketchfab, Luma AI, Polycam gallery, Scaniverse, Hugging Face).

**Three paths to a redwood scene:**

**Path 1 — Capture it yourself (recommended)**  
Drive 1–2 hours to Muir Woods, Armstrong Redwoods (Guerneville), or Henry Cowell Redwoods (Santa Cruz). Capture a 5–10 minute walking POV through the grove with iPhone + Polycam or Scaniverse. Upload to Luma AI cloud for training (no NVIDIA required, Standard plan ~$24/month retains commercial rights). Result: a scene you own, license-free, that is literally Thomas's own redwood forest. The only Layer C asset that can't be replicated by anyone else.

**Path 2 — Mononoke Forest as aesthetic proxy (immediate)**  
Yakushima cedar forest, Japan: towering ancient trees, dense moss canopy, volumetric light. Aesthetically nearly identical to NorCal old-growth — same scale, same primordial density. Scene ID `23ebe85c` on SuperSplat by studioduckbill. License must be confirmed with creator before streaming. This is Stage 1's primary scene candidate.

**Path 3 — GaussianWorld HuggingFace dataset (long shot)**  
`huggingface.co/datasets/GaussianWorld/scene_splat_49k` — 49K scenes, may contain undiscovered forest environments. No targeted search was possible from web; browse the dataset for forest candidates if other paths are blocked.

**Recommendation:** Use Mononoke Forest for Stage 1 (available now). In parallel, plan a Muir Woods capture trip for the authentic NorCal asset. The Mononoke proxy has the right feel for a Jungle/Breakbeat Hardcore set — don't wait on the redwood capture to start building.

---

## Architecture Note: Single-Active-Layer Override

**This is the most important change from the scoping doc to this plan.**

Thomas confirmed: one renderer active at a time. Layer C is only rendering when it is the active OBS scene. The scoping doc's concurrent-four-layers model is superseded.

**What this changes:**
- VRAM budget: Only Layer C active → ~1.5–2GB TDGS + ~1.5GB framebuffers = ~3–3.5GB. 580X has 8GB. This is **GREEN** headroom.
- CPU budget: TDGS bitonic sort only runs when Layer C is the active scene. Not a constant background load. CPU concern from scoping doc is substantially reduced.
- **Hardware verdict upgrades from YELLOW/AMBER to GREEN** under single-active-layer architecture.
- Gaussian count ceiling rises: 2M Gaussians is now realistic at 30+ FPS since nothing else is contending for GPU.

**The one new risk: cut-in stall.**  
If TDGS is paused (not sorting) when Layer C is off-scene, switching to it may produce a 0.5–1 second visual stall while the bitonic sort restarts. At 150–180 BPM, this is visible. **Workaround:** Let Layer C run in a TD Performance Monitor window for 2–3 seconds before cutting to it in OBS. Treat it as "pre-warm" before the cut, not a cold switch. Verify this at Stage 0 on the desk.

---

## Stage 0: Hardware proof-of-life (1–2 hours at desk)

**When:** Immediately after Phase 1 merges (no other prerequisite)  
**Goal:** Establish FPS baseline on the 580X under single-active-layer conditions

- [ ] Download TDGS sample `.toe` from Patreon (requires $4/month subscribe)
- [ ] Download Steam Studio CC0 .PLY (~2M Gaussians) from `note.com/steam_studio/n/ne9736d94f162` — license: CC0, zero risk, use strictly for benchmarking
- [ ] Load in TD, run at 1080p output with all other `.toe` files **closed** (single-active-layer simulation)
- [ ] Record FPS: Blowout OFF / ON, alpha threshold default / raised
- [ ] Verify Syphon Out → OBS receives the signal (add a Syphon Out TOP, add OBS Syphon Client source)
- [ ] Test cut-in stall: pause TD cook, let it idle 30 seconds, re-enable cook, measure how long before render is smooth
- [ ] Wire one CHOP value to a TDGS parameter to confirm parameter-driven reactivity works

**Go/no-go gates:**
- 30+ FPS at 2M Gaussians, single active: **GREEN → proceed to Stage 1**
- 15–29 FPS at 2M, 30+ FPS at 1M: **YELLOW → use ≤1.5M Gaussian scenes only**
- < 15 FPS at 1M Gaussians: **RED → evaluate MetalSplatter or dedicated Windows render box before proceeding**

**Log results to:** `docs/research/stage0_fps_log.md` (create at desk, 5 lines: FPS at 1M, 2M, 3M, with Blowout on/off)

---

## Stage 1: First scene live — Mononoke Forest

**When:** Stage 0 go/no-go = GREEN or YELLOW  
**Goal:** A jungle scene is rendering in OBS, OBS scene verified additive

**License resolution (do before streaming, can test before resolving):**
- Check SuperSplat scene page `superspl.at/scene/23ebe85c` for download toggle and displayed license
- If license is ambiguous: contact studioduckbill via SuperSplat profile or message before any live use
- If license contact is slow: fall back immediately to **Botanical Garden Victoria House** (`superspl.at/scene/6f697c4d`, CC-BY 4.0 confirmed) — attribute "simonbethke / Kiel Botanical Garden" in stream overlay

**Scene acquisition:**
- [ ] Attempt to download Mononoke Forest .PLY from `superspl.at/scene/23ebe85c` (download toggle must be enabled by creator)
- [ ] If unavailable: download Botanical Garden Victoria House (~305MB) — confirmed download-enabled, CC-BY 4.0
- [ ] Place downloaded file at `~/projects/touchdesigner-dj-suite/assets/splats/` (create directory)

**Build `dj_visuals_layer_c.toe`:**
- [ ] Create new TD project (never open dj_visuals.toe — keep them separate)
- [ ] Drag TDGS .tox into the network
- [ ] Point TDGS to the downloaded .PLY scene file
- [ ] Add Camera COMP with a simple Bezier path (3–5 waypoints through the scene)
- [ ] Wire **one OSC channel only**: `OSC In CHOP` (port 9001) → `/audio/onset_strength` → camera path `progress_speed` parameter
- [ ] Add `Syphon Out TOP` named `"LayerC_JungleSplat"`
- [ ] Play music through Studio 1824c; confirm camera moves forward on beats

**OBS scene (additive — verify production scene untouched):**
- [ ] In OBS: Add new scene **"Layer C — Jungle Splat"**
- [ ] Add source: Syphon Client → `LayerC_JungleSplat`, 1920×1080
- [ ] Confirm "New Radio DJ Scene" is still intact in OBS scene list (DO NOT TOUCH IT)
- [ ] Preview "Layer C — Jungle Splat" in OBS — confirm splat renders

**Hand off to Thomas for desk aesthetic review** before building any more reactive parameters.

---

## Stage 2: Audio-reactive expansion

**When:** Thomas has signed off on Stage 1 aesthetic at the desk  
**Goal:** All four OSC-reactive dimensions wired and tuned

- [ ] Add `OSC In CHOP` routing for remaining channels:
  - `/audio/bass_rms` → TDGS Blowout intensity + camera FOV (lerp)
  - `/audio/mid_rms` → alpha_threshold parameter
  - `/audio/high_rms` → GLSL post-process color grade hue rotation (add a `GLSL TOP` after TDGS render)
- [ ] Add `DOF TOP` driven by `/audio/bass_rms` (bass = lose focus at the edges)
- [ ] Tune Bezier camera path: design a 26-second loop (16 bars at 160 BPM) that reads well at performance speed
- [ ] Test cut-in stall with music playing: pre-warm Layer C, then cut OBS scenes, verify no visible stall

**Defer to Phase 2 of Layer C:** MIDI XY pad camera control, particle firefly overlays, instanced SOP.

---

## Stage 3: NorCal Redwood scene addition

**When:** Either (a) Thomas makes a capture trip, or (b) a community redwood PLY surfaces  
**Goal:** Add a second scene slot — same .toe, different .PLY

**Capture-your-own path (recommended):**
- [ ] Film 5–10 minute walking POV at Muir Woods, Armstrong Redwoods, or Henry Cowell Redwoods (iPhone, smooth gimbaled walk if possible)
- [ ] Upload to Luma AI cloud (Standard plan, ~$24/month — retains commercial rights)
- [ ] Download resulting .PLY → `~/projects/touchdesigner-dj-suite/assets/splats/redwood_[location].ply`
- [ ] Load in TDGS, benchmark FPS (large venue will be 2–4M Gaussians)
- [ ] If FPS < 30: prune Gaussians in SuperSplat editor → re-export as compressed .SPZ

**Integration (non-invasive asset swap):**
- In `dj_visuals_layer_c.toe`: add a second scene tab or a simple Python switcher that changes the TDGS `.ply` path parameter
- No structural changes to the .toe — just a file path swap
- In OBS: optionally add "Layer C — Redwood" as a second OBS scene with the same Syphon source (same Syphon name, different TD scene parameter)

---

## Stage 4: Personal GoPro club walkthrough splat (deferred)

**When:** Thomas provides GoPro footage from a rave/club walkthrough  
**Gate:** This asset slot is reserved. Integration is file-replace once the .PLY is trained.

**Training path (cloud-only, no NVIDIA required):**
- Trim GoPro .MP4 to cleanest-lit segment (avoid peak strobe frames)
- Upload to Luma AI Standard plan (~$24/month)
- Cloud training → download .PLY
- Load in TDGS, benchmark FPS (large club space = 4–6M Gaussians — may need pruning)

**Known risks documented in scoping doc:** low-light ISO noise, strobe/laser discontinuity breaks SfM, crowd occlusion → ghost artifacts, large venue → Gaussian count pressure. Address in separate follow-on session when footage is available.

---

## Decision Points / Hold-Here Gates

| Condition | Action |
|---|---|
| Mononoke Forest download unavailable or license ambiguous | Use Botanical Garden Victoria House (CC-BY confirmed) — don't stall the build waiting on creator contact |
| TDGS commercial license denied by Lake Heckaman | Pivot to yeataro TD-Gaussian-Splatting (free, check license before commercial use) |
| Stage 0 FPS < 15 at 1M Gaussians | Evaluate MetalSplatter (needs custom Syphon dev) or plan for dedicated Windows render box for Layer C |
| Cut-in stall > 1 second (unacceptable at desk) | Keep `dj_visuals_layer_c.toe` always-cooked but at 1 FPS when inactive (reduce cook rate, not stop) — revisit at Stage 2 tuning |
| Personal redwood capture not feasible near-term | Mononoke Forest is aesthetically equivalent — ship Stage 1–2 with Mononoke, redwood is upside |

---

## What Is NOT in This Plan

- Concurrent multi-layer rendering — single-active-layer architecture; one renderer active at a time
- Any modification to "New Radio DJ Scene" — sacred, never touched
- Anything touching dj_visuals.toe (Phase 1/2 file) — Layer C is an independent .toe
- Anything touching the TF live-money path
- A MIDI controller camera mode (Phase 2 of Layer C, after Stage 2 is validated)
- Particle overlay / firefly instanced SOP (Phase 2 of Layer C)

---

## What Unblocks Stage 0

**Phase 1 merges to main.** That is the only gate. Everything else (TDGS subscription, scene file download, commercial license email) can run in parallel while waiting for Phase 1 desk verification. You can subscribe to Patreon and download the .tox today. You can email hello@lakeheckaman.com today. Stage 0 requires nothing except Phase 1 landed and the TDGS .tox in hand.

---

## Scene Priority Order (summary)

| Priority | Scene | License | Source | Status |
|---|---|---|---|---|
| **Benchmark** | Steam Studio CC0 PLY | CC0 — unrestricted | `note.com/steam_studio/n/ne9736d94f162` | Available now |
| **Stage 1 primary** | Mononoke Forest (Yakushima) | Unverified — contact studioduckbill | `superspl.at/scene/23ebe85c` | Pending creator contact |
| **Stage 1 fallback** | Botanical Garden Victoria House | CC-BY 4.0 confirmed | `superspl.at/scene/6f697c4d` | Available now |
| **Stage 3** | NorCal Redwood (personal capture) | Owned by Thomas | Muir Woods / Armstrong / Henry Cowell | Requires capture trip |
| **Stage 4** | Personal GoPro club walkthrough | Owned by Thomas | Existing GoPro footage | Requires Thomas to locate footage |

---

*Sources: prior scoping session `docs/research/layer_c_gaussian_splat_scope.md`, TDGS GitHub `github.com/lakeheck/TouchDesigner-GaussianSplat-ParticleSystem` (CC BY-NC-ND 4.0), Patreon `patreon.com/water__shed` ($4/month starting), SuperSplat `superspl.at`, Luma AI `lumalabs.ai`*
