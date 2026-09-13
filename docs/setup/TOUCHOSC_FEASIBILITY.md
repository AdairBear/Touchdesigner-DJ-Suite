# TouchOSC feasibility — live look-switching from a phone/tablet

*Assessment 2026-09-12. Question: is finishing TouchOSC the right route for live
switching (esp. the flame/lightning/ascii `/visual/mode` look-toggle), or is the
launcher picker + existing keypress/MIDI enough for now? Honest read, no yes-man.*

---

## Verdict up front

**For tomorrow's show: don't rely on TouchOSC. Use the launcher picker (opening
look, shipped) + the existing live switch (edit `visual_mode.json` / keypress on
`/visual/mode`).** TouchOSC is a genuinely nice on-the-go surface worth finishing
in an R&D window, but it is **not show-ready** and, importantly, **the look-toggle
this thread built (`/visual/mode`) is not on the TouchOSC surface at all yet** —
finishing it is more than "add a button."

---

## What already exists (real, and more than a stub)

| Piece | State | Notes |
|---|---|---|
| `python/make_touchosc_layout.py` (242 LoC) | **Built** | Generates a `.tosc` from **live** namespaces: profile buttons (`dj_graphics_profiles.PROFILES`), attractor knob faders (`attractor_engine.DJ_CHANNELS`), `KNOBS 0` reset, `CROWD ON`, `PANIC`, crowd gain. Verified `.tosc` schema for GROUP/BUTTON/LABEL. |
| `touchdesigner/scripts/osc_profile_control.py` | **Built** | TD-side **OSC In DAT** receiver on **port 7400** dispatching `/dj/profile/<NAME>` → `apply_profile()` (+ knob/panic/audience addresses). Send-only from the pad; TD receives. |
| `docs/touchosc_profile_control.md` | **Written** | Full runbook: generate → AirDrop → connect (UDP, host=Mac IP, send port 7400) → tap. Includes a hand-build fallback and an end-to-end test ladder. |

That covers the **graphics-profile** palette (UV_RAVE / DEEP_LASER / STROBE_ACID /
VAPOR_UV / MONO_PULSE) + attractor knobs + PANIC + audience. It is a real control
surface, mostly for a different switching system than the shader look-toggle.

## What's missing / not done

1. **No `.tosc` is committed, and none has ever been opened in the app.** The
   generator writes `DJ_Profiles.tosc` (+ fallbacks) to `~/Desktop`; the doc states
   plainly the schema is "verified against a real editor layout but **has still
   never been opened in the app**," and the **FADER** node type + the toggle
   `buttonType` are **reasoned, not verified**. So even the profile surface is
   **unverified on Thomas's actual iPad/iPhone**. (Last time the schema was reasoned
   not verified, the layout opened **empty** — commit `74d38bc`.)
2. **The `/visual/mode` look-toggle (flame/lightning/ascii) is NOT on the TouchOSC
   surface.** `make_touchosc_layout.py` builds profiles/knobs/panic/audience — there
   is **no** flame/lightning/ascii button and **no** `/visual/mode` address anywhere
   in it. The TouchOSC work to date does not touch the look chooser this thread built.
3. **Architectural conflict for `/visual/mode` specifically.** `/visual/mode` is
   currently **owned and rebroadcast by the tracker** — `movement_tracker.py`
   re-reads `visual_mode.json` and sends `/visual/mode` ~1×/second. If TouchOSC sent
   `/visual/mode` straight to TD, the tracker's next tick (~1 s later) would
   **overwrite it and the look would snap back**. So look-switching from TouchOSC
   can't just point at TD's OSC In — it needs a receiver that updates the single
   source of truth (`visual_mode.json`), which the tracker then broadcasts.
4. **Live-gig network fragility (inherent to TouchOSC, not a bug).** Requires the
   iPad + Mac on the **same non-guest wifi**, the Mac's IP hand-entered on each
   device (breaks on DHCP reassignment), and the macOS firewall allowing inbound UDP
   to TD. The doc calls the guest-network case "the single most common reason this
   silently does nothing."

## Concrete gaps + rough effort to finish look-switching

| Gap | Work | Rough effort |
|---|---|---|
| No look-toggle on the pad | Add a 3-button section (flame/lightning/ascii_lightning) to `make_touchosc_layout.py`, sending e.g. `/dj/visual/<name>` | ~1–2 h |
| No receiver that respects the source of truth | Add an OSC-In handler (osc_profile_control.py style, port 7400) that on `/dj/visual/<name>` **writes `visual_mode.json` `mode`** (tracker then broadcasts) — reuses the picker's writer, stays consistent with keypress + picker | ~1–2 h |
| `.tosc` never verified on device | Generate, open in the TouchOSC editor, confirm it renders (or hand-build per the doc's 5-min fallback), then verify on the iPad with TD up | ~1–3 h **with iPad + TD in hand** |
| Network prep | DHCP reservation for the Mac, firewall rule, same-wifi check | ~0.5 h |

**Total to TouchOSC look-switching, live + verified: ~half a day of desk work, most
of it on-device verification, not code** — and it inherits the unverified-layout risk.

## Tradeoff: picker-only vs finish-TouchOSC

- **Picker + keypress/JSON (available now, zero new risk):** the launcher picker
  (shipped, tested) sets the **opening** look; mid-set you switch by editing
  `visual_mode.json` `mode` (live ~1 s) or the existing keypress/MIDI on
  `/visual/mode`. Fully covers "choose at open" + "change during the set." No wifi,
  no unverified layout, nothing to fail in front of a crowd.
- **Finish TouchOSC (nice-to-have, R&D window):** buys **wireless, walk-the-floor**
  control and a physical pad of looks/knobs/panic. Worth it for that ergonomics —
  but it is a half-day incl. on-device verification, it depends on gig wifi, and the
  `/visual/mode` piece needs the source-of-truth receiver (gap #3) to not fight the
  tracker.

## Recommendation (no yes-man)

1. **Ship the show on the picker + keypress/JSON.** It is enough, and it is safe.
2. **Defer TouchOSC to a weekend R&D block**, and when finishing it:
   - **Verify the base `.tosc` on the actual device first** (or hand-build it) —
     that unverified layout is the real risk, ahead of any new feature.
   - Add look-switching the **right** way: TouchOSC → `/dj/visual/<name>` → a small
     OSC-In handler that **writes `visual_mode.json`** (one source of truth shared
     with the picker + keypress), **not** a direct `/visual/mode` send to TD (which
     the tracker would overwrite).
   - Finish the already-closer **profiles/knobs/panic** surface as the first
     deliverable; treat look-switching as an add-on once the pad is proven.

## Constraints honored
No change to the "New Radio DJ Scene"; the OBS auto-switcher stays off; nothing here
touches OBS at all (TouchOSC path is OSC→TD only). This document is assessment only —
no code changed for Job 2.
