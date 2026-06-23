# Layer C — Gaussian Splatting R&D Scoping

**Date:** 2026-06-06 (Sat 9:24 PM EDT)
**Status:** R&D scoping — NOT building. Gated on Phase 1 desk verification.
**Hard rule:** OBS "New Radio DJ Scene" is SACRED. All Layer C work is additive-only (new `.toe`, new OBS scene).
**Branch discipline:** No Layer C code lands on `feat/td-network-v2-builder` or `main` until Phase 1 ships.

---

## 1. State of the Art — Gaussian Splatting in TouchDesigner (June 2026)

### Derivative-native support

There is **no official Gaussian Splatting operator** from Derivative. Everything is third-party community work. The ecosystem has matured significantly since 2023, and as of 2025–2026 there are two credible paths.

### Path A — TDGS by Lake Heckaman (Patreon) — **RECOMMENDED**

**What it is:** A `.tox` drag-and-drop component that renders Gaussian Splat `.PLY` and `.SPZ` files inside TouchDesigner using a custom bitonic sort + GLSL render pipeline.

| Property | Detail |
|---|---|
| Version | 1.3.1 (released 2025, built for TD 2025.31760+) |
| macOS | Full macOS support added in 1.3.1 — explicitly confirmed on M1 MacBook Air |
| Intel Mac | TD requires discrete AMD GPU on Intel Mac (Thomas qualifies); Intel-specific reports absent from forums but AMD discrete + Metal should work via same macOS path |
| File formats | `.PLY` (standard uncompressed), `.SPZ` (compressed, ~70–90% size reduction) |
| Render output | Renders to a TOP — Syphon Out is trivial (TD-native, zero extra work) |
| Sort | CPU-side bitonic sort; "Blowout" mode dramatically reduces sort cost by pushing far splats off-screen |
| GPU | Uses GLSL shader for rasterization; macOS GLSL path was patched by community for Apple Silicon and should carry to Metal-capable AMD |
| TD custom GPU accel | NOT available on macOS (Metal/Vulkan CPOP path is unscheduled per Derivative) — TDGS works around this by doing sort CPU-side |
| Access | Lake Heckaman Patreon (`patreon.com/water__shed` / @water__shed) — $4/month tier; individual posts ~$25–30 one-time |
| Audio reactive | All parameters exposed as TD component parameters — scriptable from Python, driveable by CHOP |
| References | [Derivative community post](https://derivative.ca/community-post/asset/gaussian-splatting/69107) · [Radiance Fields feature](https://radiancefields.com/tdgs-for-gaussian-splatting-in-touchdesigner) · [TDGS 1.3.1 Patreon](https://www.patreon.com/posts/tdgs-1-3-1-for-145530480) · [YouTube demo (Mac compatible)](https://www.youtube.com/watch?v=wPw0OLlZ4sE) |

**Why this wins:** Everything stays inside TD. Syphon Out is one operator. Audio reactivity uses the same CHOP infrastructure already built in TD-DJ-Suite. No external process management.

### Path B — TD-Gaussian-Splatting by yeataro (GitHub, free)

An open-source TD component from a Chinese developer. Supports depth, DOF, relighting, stylization. The 2023-era version had a known GLSL incompatibility on macOS (original shader was Windows/NVIDIA-only; community patched for Apple Silicon). Still a point-cloud/particle-system approach with more style controls but less polished VJ workflow.

| Property | Detail |
|---|---|
| Cost | Free, open source |
| macOS | Patched for Apple Silicon; Intel Mac AMD untested |
| Stability | Active but less maintained than TDGS 1.3.1 |
| References | [GitHub: yeataro/TD-Gaussian-Splatting](https://github.com/yeataro/TD-Gaussian-Splatting) |

**Use case:** Better for artistically stylized/distorted splat work (relighting, depth effects). Path A first; Path B as alt if stylization is a priority.

### Path C — MetalSplatter → Syphon → TD (open source, MIT)

A native macOS/Metal Swift app by vade (Anton Marini) that renders `.PLY` files using Metal compute. Excellent performance on Metal-native hardware.

| Property | Detail |
|---|---|
| Cost | Free, MIT license |
| Syphon output | NOT built in — would require Swift dev to add (Metal texture → Syphon server) |
| macOS | Metal-native, best macOS performance |
| Audio reactive | No — standalone app, not scriptable from TD |
| References | [GitHub: scier/MetalSplatter](https://github.com/scier/MetalSplatter) · [CDM coverage](https://cdm.link/metal-on-macos-free-gaussian-splat-tool/) |

**Verdict:** Architecturally appealing but requires custom Swift development to add Syphon and any audio reactivity. Out of scope for Phase 1 Layer C MVP. Revisit if TDGS performance on Intel Mac is unacceptable.

### Path D — External Renderer (Unreal Engine 5 + Luma Plugin) → Syphon → TD

UE5 + Luma AI Unreal plugin renders Gaussian Splats via Metal on macOS. UE5 can output via Syphon (NDI/Syphon plugin). High-quality rendering ceiling, but:
- UE5 startup overhead (minutes), not VJ-friendly
- Luma plugin requires Luma cloud uploads to get `.PLY`
- Complex multi-app management during live performance
- Training (PostShot) is Windows/NVIDIA only

**Verdict:** Future exploration only. Not viable for Phase 1 Layer C MVP.

---

### Path ranking for Thomas (solo dev, Mac primary, VJ use case)

| Rank | Path | Why |
|---|---|---|
| **1** | TDGS (Path A) | TD-native, Syphon trivial, audio-reactive via CHOP, maintained, macOS support shipped in 1.3.1 |
| **2** | yeataro TD-GS (Path B) | Free, more style controls, but less production-hardened |
| **3** | MetalSplatter (Path C) | Best macOS performance but needs custom Syphon bridge dev |
| **4** | UE5 (Path D) | Overkill, Windows-native toolchain, not VJ-compatible |

---

## 2. Hardware Audit

### System

| Component | Spec |
|---|---|
| Machine | iMac 27" 2019 (iMac19,1) |
| CPU | 6-Core Intel Core i5, 3.7 GHz |
| RAM | 128 GB |
| GPU | AMD Radeon Pro 580X |
| VRAM | 8 GB |
| GPU API | Metal 2 (NO CUDA, NO ROCm on this platform) |
| Displays | 5K Retina built-in + 4K HISENSE TV + 1080p Samsung |

### Gaussian Splatting Performance Assessment

**Verdict: YELLOW — capable but with ceiling.**

The Radeon Pro 580X is a Polaris-generation AMD GPU from 2019 with Metal 2 support. It is NOT Apple Silicon and has no CUDA. Here's what that means for Gaussian Splatting:

**What works in its favor:**
- 8GB VRAM is adequate for scenes up to ~3M Gaussians (typical scene footprint is 1–2 GB for 1–2M Gaussian .PLY)
- Metal 2 is fully supported by TD's render pipeline on macOS
- Discrete GPU (not iGPU) — TD's macOS requirement for Intel is met
- 128 GB RAM absorbs large scene loads CPU-side

**What is a constraint:**
- TDGS bitonic sort is **CPU-bound** on macOS (Metal CPOP/compute pipeline not yet available in TD custom operators as of 2025–2026 per Derivative forum). On Intel i5 this is slower than Apple Silicon's unified memory architecture.
- At **alpha_threshold = 0** (all 2M+ Gaussians visible) on a complex outdoor scene, expect sort to be the bottleneck. "Blowout" mode mitigates by culling off-screen splats before sort.
- Target: **1–1.5M Gaussian scene at comfortable alpha threshold → 30–60 FPS at 1080p** is realistic. At 3M+ Gaussians with full alpha, may drop to 15–25 FPS.
- Training/capture (PostShot) is NVIDIA/Windows-only — but Thomas only needs runtime rendering, not training.

**Realistic Gaussian count budget for 30+ FPS at 1080p:**
- Comfortable zone: ≤1.5M Gaussians, moderate alpha threshold
- Risky zone: 2–3M Gaussians (use Blowout mode + raise alpha threshold)
- No-go live: 4M+ Gaussians without further optimization

**Unlock paths if hardware is the bottleneck:**
- **eGPU via Thunderbolt 3:** iMac 2019 has TB3 ports. An AMD Radeon RX 6800 XT in a TB3 enclosure (~$400–600 used) would give 16GB VRAM and a newer RDNA2 architecture. macOS eGPU support is deprecated in macOS Ventura/Sonoma — **this path is closed** unless Thomas is running macOS Monterey or earlier.
- **Windows box for splat rendering:** A secondary machine with NVIDIA GPU running TDGS on Windows → Spout output → NDI bridge → TD on Mac. Adds complexity, reduces latency-sensitive reactivity.
- **Luma AI cloud training only:** Keep Mac for runtime rendering (TDGS on Mac), use Luma AI or Polycam cloud to generate the initial `.PLY` from footage. Free tier limits Gaussian count. This is NOT a performance fix but eliminates need for local NVIDIA training hardware.

**Recommended first step before investing in any unlock:** Run the TDGS sample `.toe` on the 580X and benchmark FPS. If it hits 30+ FPS on the bundled sample, hardware is green. If it struggles, then evaluate paths above.

### Concurrent multi-layer rendering budget (CRITICAL UPDATE)

Thomas confirmed all layers run continuously and stay audio-reactive at all times — even when off-scene. There is no "pause when off-scene" optimization. When Thomas cuts to Layer C mid-set, it must already be in sync with the music. The iMac must sustain **four simultaneous TD renderers** at performance frame rates.

**Estimated concurrent VRAM budget at 1080p:**

| Layer | Process | Est. VRAM |
|---|---|---|
| Layer 0 — Baseline | Video playback, TD overhead | ~300 MB |
| Layer A — VJ Clips | Video decoding, compositing | ~500 MB |
| Layer B — Looping Env | Shader loop, audio reactivity | ~500 MB |
| Layer C — Jungle Splat | TDGS 1.5M Gaussian .PLY | ~1.5–2 GB |
| TD framebuffers + Syphon (×4 outputs) | Internal textures | ~1.5–2 GB |
| **Total estimate** | | **~4.5–5.5 GB** |

8GB VRAM total. ~4.5–5.5 GB concurrent load leaves 2.5–3.5 GB headroom. **VRAM is manageable** if Layer C scene stays ≤1.5M Gaussians and outputs at 1080p (not 4K).

**The real constraint is CPU, not VRAM.** TDGS's bitonic sort runs continuously on the Intel i5 even when Layer C is off-scene. At 1.5M Gaussians this is a constant CPU background load. Combined with audio_reactive_mapper.py (Python, continuous FFT) and 3 other TD processes, the 6-core Intel i5 @ 3.7 GHz is the actual bottleneck.

**Revised verdict: YELLOW/AMBER (single-machine concurrent limit).**
- Single machine, 4 concurrent layers: feasible with careful scene budgeting (≤1.5M Gaussians for Layer C, no 4K outputs)
- CPU monitoring at desk: watch total TD CPU % with all four `.toe` files open; target < 80% sustained
- If CPU pegs above 90% with all layers running: the unlock is a **dedicated Windows render machine** for Layer C (Spout → NDI → Mac OBS source), freeing the iMac CPU from the splat sort entirely

---

## 3. Jungle Scene Candidate Library

*Note: "jungle" in the public Gaussian Splat library = mostly East Asian forest aesthetics. Dense tropical rainforest (Amazon, Borneo-style) is essentially absent from the public corpus as of June 2026. Best candidates are atmospheric forest environments.*

### Top 3 Recommended Candidates

**Candidate 1 — Mononoke Forest (SuperSplat by studioduckbill)**
- **URL:** `https://superspl.at/` → search "Mononoke Forest"
- **Aesthetic:** Named after the ancient cedar forest from Princess Mononoke — based on Yakushima island's UNESCO forest (Japan). Towering moss-covered cedar trunks, dense canopy, dramatic volumetric atmosphere. Extraordinary visual match for Jungle/Breakbeat Hardcore 150–180 BPM — primordial, dense, ancestral.
- **Gaussian count:** Unknown (high quality, likely 2–4M) — verify before loading
- **File format:** PLY downloadable if creator enables toggle; SuperSplat also offers compressed export
- **License:** Per-creator on SuperSplat — must check scene page for download permission and license. Platform itself is MIT. If download is enabled, check for CC-BY or CC0 designation.
- **Streaming note:** Requires license verification before monetized stream. Contact studioduckbill directly via SuperSplat if license is ambiguous.
- **Why #1:** Best aesthetic match for the Jungle DJ double-meaning. Dense, cinematic, moody. Unlike anything else in the public corpus.

**Candidate 2 — Shirakoma Pond Moss Forest — Ultra High-Res 3DGS (SuperSplat by studioduckbill)**
- **URL:** `https://superspl.at/` → search "Shirakoma Pond"
- **Aesthetic:** Nagano, Japan — mossy forest surrounding a reflective volcanic lake. Mist, reflections, ancient texture. Strong "into the deep jungle" POV. "Ultra High-Res" label suggests 3–5M Gaussians — test on hardware before using live.
- **Gaussian count:** Likely 3M+ (labeled ultra high-res) — use Blowout mode, raise alpha threshold, monitor FPS carefully
- **License:** Same per-creator caveat as Mononoke Forest. Same creator, same contact path.
- **Streaming note:** Same license verification required.
- **Why #2:** Reflections + depth make this exceptionally reactive to camera path animations. The pond gives a natural DOF target.

**Candidate 3 — Botanical Garden Victoria House (SuperSplat by simonbethke)**
- **URL:** `https://superspl.at/scene/6f697c4d`
- **Scene ID:** `6f697c4d`
- **Aesthetic:** Tropical aquatic plants greenhouse at Kiel Botanical Garden (Germany) — coconut palms, sugar cane, rice, papayas, and mangroves. High botanical density, warm humid greenhouse light. VR-optimized. Aesthetic is "indoor tropical rainforest" — more manicured than jungle raw, but botanically convincing and streaming-safe.
- **Gaussian count:** ~305 MB splat file (moderate count, VR-performance tuned → likely 1–2M)
- **License:** **CC BY 4.0** — confirmed (StreamSplat platform allows creator to set per-scene license; simonbethke set CC-BY). Attribution required, commercial streaming permitted.
- **Why #3:** First license-confirmed tropical scene. CC-BY is clean — attribute "simonbethke / Kiel Botanical Garden" in stream overlay or credits. Smaller file → easier hardware validation. Use this ahead of Mononoke Forest if license contact is slow.

**Candidate 4 — Steam Studio CC0 PLY (hardware proof-of-life only)**
- **URL:** `https://note.com/steam_studio/n/ne9736d94f162`
- **Aesthetic:** High photographic quality ~2M Gaussian scene (product/object capture). NOT jungle-themed — use strictly for FPS benchmarking.
- **Gaussian count:** ~2M (stated)
- **License:** **CC0** — explicit public domain. Zero attribution. Unrestricted.
- **Why #4:** Zero-risk hardware benchmark. Load this first to gate FPS. Don't use live — aesthetic is wrong. Swap in Candidate 1–3 once hardware is validated.

### Additional Candidates (Lower Priority)

| Scene | Source | Aesthetic | License | Notes |
|---|---|---|---|---|
| Forest Scan | Polycam `poly.cam/explore/…` | Pacific NW forest, earthy | Per-creator | License unclear, worth checking |
| Tree (Scaniverse, Kana) | Sketchfab | Single large tree, open sky | CC BY (standard Sketchfab) | Single tree, not a full environment |
| Capture your own | Luma AI / Polycam / Scaniverse | YOUR jungle video | Yours | See §5 |

### On capturing your own jungle scene

If Thomas has existing video footage of jungle/outdoor environments — or can shoot a short walkthrough — **Luma AI cloud processing** (lumalabs.ai/capture) accepts iPhone video and returns a `.PLY` with no NVIDIA GPU required (cloud-side training). Free tier caps at a lower Gaussian count; paid tier produces full-resolution captures. This is the most direct path to a "real jungle" scene that is authentically resonant with the DJ identity.

---

## 4. Audio-Reactive Integration Plan

### Existing TD-DJ-Suite signal sources

| OSC channel | Signal type | Current use |
|---|---|---|
| `/audio/bass_rms` | Sub-bass energy, 0–1 | Fire aura shader uniforms |
| `/audio/onset_strength` | Beat/transient detection | Shader animation |
| `/audio/mid_rms` | (assumed) mid-range energy | Available |
| `/audio/high_rms` | (assumed) high-frequency energy | Available |

All signals come from `aura_compositor.py` → `audio_reactive_mapper.py` → OSC → TD. Layer C receives these in its own standalone `.toe` via a separate OSC In CHOP listening on the same port.

**All layers receive OSC continuously at all times — no active-scene gating.** When Thomas cuts to Layer C the camera is already moving with the music, the fog is already reacting to bass, the color is already shifting on hi-hats. A layer that wakes up on cut and catches up over 1–2 seconds breaks the energy flow of a 150–180 BPM set. OSC parameters update all layers all the time, background or foreground.

### What can a Gaussian Splat scene modulate?

```
 ┌──────────────────────────────────────────────────────────────────┐
 │ SIGNAL SOURCE            │  MODULATION TARGET         │ HOW      │
 │──────────────────────────│────────────────────────────│──────────│
 │ onset_strength           │ Camera path speed          │ CHOP→Py  │
 │ (beat hit = push forward)│ (lerp along Bezier)        │ script   │
 │──────────────────────────│────────────────────────────│──────────│
 │ bass_rms                 │ Splat "Blowout" intensity  │ CHOP→par │
 │ (kick = push + contract) │ (splats pulse outward)     │          │
 │──────────────────────────│────────────────────────────│──────────│
 │ bass_rms                 │ FOV / zoom                 │ CHOP→cam │
 │ (kick = zoom in)         │ (camera lens compression)  │ par      │
 │──────────────────────────│────────────────────────────│──────────│
 │ mid_rms                  │ Alpha threshold            │ CHOP→par │
 │ (mid energy = more splats│ (more splats visible)      │          │
 │  emerge from the forest) │                            │          │
 │──────────────────────────│────────────────────────────│──────────│
 │ high_rms                 │ Post-process color grade   │ CHOP→    │
 │ (hi-hat = color shift)   │ (hue rotation, saturation) │ GLSL top │
 │──────────────────────────│────────────────────────────│──────────│
 │ onset_strength            │ Particle overlay trigger  │ CHOP→    │
 │ (transient = firefly      │ (fireflies, light shafts) │ instSOP  │
 │  burst, light shaft)      │                           │          │
 │──────────────────────────│────────────────────────────│──────────│
 │ bass_rms                 │ DOF blur radius            │ CHOP→    │
 │ (bass = lose the edge)   │ (depth-of-field strength)  │ DOF TOP  │
 └──────────────────────────────────────────────────────────────────┘
```

### Camera path strategy

**Precomputed Bezier flythrough** is the right approach for live performance:
- Design the path offline in TD (set of waypoints through the jungle scene)
- `progress` parameter (0–1) on the path is the single runtime control
- `onset_strength` drives `progress` speed (tempo-locked forward movement)
- `bass_rms` drives `progress` jitter / oscillation (kick snaps camera position briefly)
- At BPM 150–180, one "bar" of 4 beats = ~1.6 seconds → a 16-bar flythrough section = ~26 seconds — design path to be loopable

**Alternative:** MIDI controller drives camera via XY pad. More expressive, less predictable. Save for Phase 2 of Layer C after basic OSC auto-fly is working.

### OSC routing diagram (text)

```
[Studio 1824c audio input]
       │
  audio_reactive_mapper.py
       │
  OSC Out → port 9001 (existing suite)
       │
  ┌────┴────────────────────────────────────────┐
  │ dj_visuals.toe (Phase 1/2/3 layers)         │
  │ Layer A: Body outline                        │
  │ Layer B: Aura / fire / lightning shaders     │
  └────────────────────────────────────────────┘
       │
       └──→ OSC bridge / same feed
                │
         dj_visuals_layer_c.toe (Layer C — independent .toe)
                │
         OSC In CHOP (port 9001, bind=false — listen-only)
                │
                ├── /audio/onset_strength → camera_speed CHOP
                ├── /audio/bass_rms      → blowout_intensity + DOF_blur
                ├── /audio/mid_rms       → alpha_threshold
                └── /audio/high_rms      → color_grade hue rotate
                         │
                    TDGS component (splat render TOP)
                         │
                    Post-process GLSL (color grade)
                         │
                    Particle overlay (fireflies, instanced SOP)
                         │
                    Syphon Out TOP → OBS Source "Layer C — Jungle Splat"
```

*Both `.toe` files can share the same OSC port (9001) because the OSC In CHOP in each project listens independently — no conflict.*

---

## 5. MVP Architecture + 3-Step Build Order

### Project structure

```
dj_visuals_layer_c.toe          ← independent .toe, never touches dj_visuals.toe
├── /base/audio
│   └── audio_in CHOP (Studio 1824c, same device as main suite)
│   └── OSC In CHOP (port 9001, listen-only)
├── /base/scene
│   └── TDGS component (drag .tox in)
│   └── [jungle.ply or jungle.spz]
│   └── Camera COMP (with Bezier path)
├── /base/fx
│   └── GLSL post-process TOP (color grade)
│   └── Particle instanced SOP (optional fireflies)
├── /base/output
│   └── Composite TOP (splat + particles)
│   └── Syphon Out TOP → "LayerC_JungleSplat"
└── /base/osc_reactive
    └── Python script: maps OSC signals → component parameters
```

### OBS scene setup (additive — never touch production)

New OBS scene: **"Layer C — Jungle Splat"**
- Source: Syphon Client → "LayerC_JungleSplat"
- Resolution: 1920×1080
- This scene lives ALONGSIDE "New Radio DJ Scene" — switch between them or composite via scene transitions
- During Phase 1 desk verification, this is ONLY running in a test context

### 3-step MVP build order

**Step 1 — Hardware proof of life (do this FIRST at desk)**
- Open TDGS sample `.toe` on the 580X
- Load Steam Studio CC0 `.PLY` (~2M Gaussians) — license-safe for testing
- Target: 30+ FPS at 1080p with Blowout mode off
- If FPS < 30: enable Blowout, raise alpha threshold, retest
- Record: FPS at baseline Gaussian count, note at what count it drops below 30
- **Go/no-go gate:** if hardware cannot reach 30 FPS on a 1M Gaussian scene, assess MetalSplatter (Path C) as render backend before building Layer C further

**Step 2 — Wire one OSC parameter**
- Create `dj_visuals_layer_c.toe`
- Add TDGS + camera path + OSC In CHOP
- Wire `/audio/onset_strength` → camera path `progress_speed` parameter
- Play music through Studio 1824c; confirm camera lurches forward on beats
- No full reactive suite yet — just the single-wire proof that OSC and splat coexist

**Step 3 — Stand up OBS scene (additive)**
- Add Syphon Out TOP (`LayerC_JungleSplat`)
- In OBS: add new scene "Layer C — Jungle Splat" → Syphon Client source
- Confirm splat renders in OBS scene preview
- Verify "New Radio DJ Scene" is untouched in OBS scene list
- **Hand off to Thomas at desk for visual evaluation** before building remaining reactive parameters

### Desk verification checklist (Thomas at rig)

After Step 3:
- [ ] Splat renders in TD at ≥30 FPS
- [ ] Camera moves forward on beat in Step 2 test
- [ ] OBS "Layer C — Jungle Splat" shows splat scene
- [ ] "New Radio DJ Scene" is untouched
- [ ] Scene aesthetic assessment — which candidate jungle/forest scene is compelling?
- [ ] Thomas's "video in mind" — if he has footage, start Luma AI cloud capture now

---

## Post-MVP Asset: Personal GoPro Club Walkthrough Splat (Follow-On Session)

**Status: Queued. Do NOT start until MVP is validated.**

Thomas has a personal GoPro video walking through an entire club at a rave — the complete physical environment of his DJ world, captured POV. Training a Gaussian Splat from this footage is the planned Layer C asset #2. Same renderer (TDGS), same `.toe`, just a different `.ply` swapped in.

### Why this is the right second asset

A personal rave-club walkthrough splat is the authentic capstone: the scene is literally the room where Thomas performs. When Layer C is live, he is literally inside his own world. No licensing ambiguity — he owns the footage.

### Flagged risks (must be addressed in the follow-on session)

| Risk | Severity | Notes |
|---|---|---|
| **Low-light / high ISO noise** | High | Strobe-lit clubs film poorly; frames shot in near-darkness confuse SfM. GoPro footage at ISO 1600+ trains into a noisy splat. Mitigation: pick the cleanest-lit segment of the video; use Postshot's denoising preprocessing if available |
| **Strobes and laser patterns** | High | Frame-to-frame lighting discontinuity breaks the structure-from-motion step entirely. Splat training assumes consistent lighting per viewpoint. Motion-inconsistent frames must be culled before training. |
| **Crowd occlusion** | Medium | People walking through the frame register as floating Gaussian artifacts. Dynamic objects → transient contamination → ghost people in the splat. Mitigation: slow walkthrough segments, avoid frames with dense crowd; Postshot/Luma AI have some dynamic-object masking |
| **Large space → high Gaussian count** | High | A full club interior at resolution will generate 4–6M+ Gaussians. 580X / 8GB VRAM + Intel i5 bitonic sort = serious performance risk. Mitigation: use aggressive Gaussian pruning / alpha threshold; may require dedicated Windows render box for this asset |
| **Training hardware** | Medium | Postshot (best quality trainer) is NVIDIA/Windows-only. Luma AI cloud (free/paid tier) runs in-browser, no local GPU needed — this is the viable Mac path. Polycam and Scaniverse are mobile-first but also cloud-train |

### Recommended training path (cloud-only, Mac-compatible)

```
GoPro .MP4 → trim to clean-lit segment (avoid peak strobe moments)
→ Luma AI cloud upload (lumalabs.ai/capture, Standard plan or higher)
→ Cloud training generates .PLY
→ Download .PLY → load in TDGS → benchmark FPS
→ If FPS < 30: prune Gaussians in SuperSplat editor → re-export
```

Luma AI Standard plan (~$24/month) retains commercial rights to your exports. Free tier limits max Gaussian count — likely insufficient for a full club space. Budget one month at paid tier for the training run.

### Follow-on session scope

A separate "Layer C asset #2 — personal GoPro club walkthrough splat training pipeline" session should cover:
1. GoPro footage prep: frame culling, denoising, strobe-frame rejection
2. Luma AI submission + parameter tuning for indoor/dark environments
3. Gaussian count benchmarking on 580X hardware
4. Pruning workflow if count is too high for 30 FPS
5. Swap `.ply` into `dj_visuals_layer_c.toe` — no `.toe` architecture changes needed

**This session cannot begin until Thomas can share or transfer the GoPro footage. The architecture is ready; only the asset is pending.**

---

## Summary

| Item | Decision |
|---|---|
| Renderer path | **TDGS 1.3.1 (Path A)** — TD-native, Syphon free, macOS supported — `patreon.com/water__shed` |
| Hardware | **YELLOW** — 580X/8GB/Metal viable at ≤1.5M Gaussians; CPU-bound sort is the real constraint |
| First test scene | Steam Studio CC0 PLY (~2M Gaussians) — license-safe, aesthetics irrelevant, FPS only |
| First streaming scene | Botanical Garden Victoria House (CC-BY, `superspl.at/scene/6f697c4d`) |
| Top aesthetic scene | Mononoke Forest (SuperSplat) — verify download toggle + license before streaming |
| MVP entry point | Load TDGS sample `.toe` → 30 FPS gate → one OSC wire → new OBS scene |
| Gate | Phase 1 desk verification must complete before Layer C build begins |
| OBS invariant | "New Radio DJ Scene" is never touched — Layer C is a net-new additive scene |
| Post-MVP asset | Personal GoPro club walkthrough splat — queued, follow-on session, Thomas to provide footage |

---

*Sources consulted:*
- [TDGS — Derivative community post](https://derivative.ca/community-post/asset/gaussian-splatting/69107)
- [TDGS 1.3.1 Patreon (Lake Heckaman)](https://www.patreon.com/posts/tdgs-1-3-1-for-145530480)
- [Radiance Fields — TDGS feature](https://radiancefields.com/tdgs-for-gaussian-splatting-in-touchdesigner)
- [YouTube — TDGS Mac Compatible demo](https://www.youtube.com/watch?v=wPw0OLlZ4sE)
- [TD Forum — Metal GPU acceleration wishlist](https://forum.derivative.ca/t/gpu-acceleration-for-custom-operators-on-macos-metal-touchdesigner-2025/749595)
- [TD Forum — Gaussian Splatting 2024 community post](https://forum.derivative.ca/t/gaussian-splatting-2024-03-04/439835)
- [MetalSplatter — GitHub (scier)](https://github.com/scier/MetalSplatter)
- [CDM — Metal macOS Gaussian Splat](https://cdm.link/metal-on-macos-free-gaussian-splat-tool/)
- [SuperSplat — The Home for 3DGS](https://superspl.at/)
- [Steam Studio — CC0 PLY download](https://note.com/steam_studio/n/ne9736d94f162)
- [Polycam — Forest Scan](https://poly.cam/explore/capture/370ef5b0-b01f-40aa-bf95-250cb1a64cb2/Forest+Scan)
- [yeataro/TD-Gaussian-Splatting — GitHub](https://github.com/yeataro/TD-Gaussian-Splatting)
