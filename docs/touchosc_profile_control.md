# Switching graphics profiles live from TouchOSC

Tap a button on the iPad or iPhone, the look changes **inside the running show**
— no reload, no dropped frames. Safe mid-set.

| | |
|---|---|
| Layout file | `~/Desktop/DJ_Profiles.tosc` (plus two fallbacks — see below) |
| OSC port | **7400** (UDP) |
| OSC addresses | `/dj/profile/UV_RAVE`, `/DEEP_LASER`, `/STROBE_ACID`, `/VAPOR_UV`, `/MONO_PULSE` |

**Two ways to change the look, for two different moments:**

- **Pre-show** — open `touchdesigner/profiles/dj_launcher_<PROFILE>.toe`. Reloads TD.
- **Live** — TouchOSC. Instant, seamless, mid-set. *This document.*

---

## One-time setup

### 1. Turn on the receiver in TouchDesigner

Textport (**Alt+T**), paste `touchdesigner/scripts/osc_profile_control.py`.
It builds an OSC In DAT listening on **7400** and prints the addresses.
Re-pasting is safe. To remove: `osc_profile_teardown()`.

### 2. Find your Mac's IP address

```bash
ipconfig getifaddr en0
```

If that prints nothing you're on ethernet or a second adapter — try `en1`.
Note the number (like `192.168.1.42`). **If your router reassigns it, you'll have
to re-enter it** — worth setting a DHCP reservation before a real gig.

### 3. Get the layout onto the devices

Regenerate with `./venv/bin/python python/make_touchosc_layout.py`. It writes
four files to `~/Desktop`:

| File | What it is |
|---|---|
| `DJ_Profiles.tosc` | **Try this one.** zlib-compressed, the real format. |
| `DJ_Profiles_uncompressed.tosc` | Same document, no zlib wrapper. Try only if the first is rejected. |
| `DJ_Profiles.xml` | Byte-identical to the uncompressed one, for reading. |
| `DJ_Profiles_profiles_only.tosc` | **Fallback.** Profile buttons only, no fader in it. See *If the faders don't render* below. |

AirDrop `DJ_Profiles.tosc` to the iPad and iPhone. Accept, and choose
**Open with TouchOSC**. It appears in TouchOSC's layout list.

Take the fallback across too. It costs 2 KB and it is the difference between a
degraded pad and no pad.

### What's on the page

The generator reads every control channel **live**, from the module that owns
it, so regenerating always produces a complete surface:

| Section | Read from | Controls |
|---|---|---|
| Profile grid | `dj_graphics_profiles.PROFILES` | one button per look, auto-growing to a second column |
| Knob faders | `attractor_engine.DJ_CHANNELS` | CHAOS / MORPH / SPEED / TRAIL / SPREAD, each a **-1..1 offset** resting dead centre |
| Crowd gain | `audience_control.audience_addresses()` | `/dj/audience/gain`, resting at 1.0 |
| `KNOBS 0` | `osc_profile_control.ATTRACTOR_PREFIX` | zeroes every knob offset |
| `CROWD ON` | `audience_control.audience_addresses()` | toggles the audience on/off |
| `PANIC` | `audience_control.PANIC_ADDRESS` | the kill switch — momentary, red, bottom right |

**Add a knob to `DJ_CHANNELS`, regenerate, and it is on the pad.** That lockstep
is the point of the file: before it, the knobs and PANIC were hand-added in the
TouchOSC editor and destroyed by the next regeneration, which meant the newest
and least-rehearsed capability was the one with no button on it.

Nothing on the page receives. It is send-only in every control.

### 4. Point TouchOSC at the Mac

**Host and port are not stored in the layout file** — TouchOSC keeps connection
settings outside the document, so this step is required no matter how the layout
got onto the device.

In TouchOSC, tap the **chain-link (connections)** icon in the toolbar, open the
**OSC** tab, and on **Connection 1** set:

- **Type** — UDP
- **Host** — the IP from step 2
- **Send Port** — `7400`
- Leave **Receive Port** at its default
- Make sure the connection is **enabled**

The layout's buttons send on connection **1**, so it must be that slot.

Both devices need the **same wifi as the Mac**, and it must not be a "guest"
network — those usually block device-to-device traffic, which is the single most
common reason this silently does nothing.

### 5. Tap a button

Open the layout, tap **STROBE ACID**. The visuals change immediately, and the
Textport prints `[osc_profile] -> STROBE_ACID`.

---

## Testing it end-to-end

Work up in three steps so a failure tells you *where* it is.

**1. Does the receiver work at all?** In the Textport, bypassing the network:

```python
op('/project1/osc_profile_handler')  # should exist
import dj_graphics_profiles as gp; gp.apply_profile('STROBE_ACID')
```
Look changes → the profile system is fine, so any problem is network-side.

**2. Does OSC arrive?** From the Mac, sending to itself:

```bash
./venv/bin/python -c "
from pythonosc.udp_client import SimpleUDPClient
SimpleUDPClient('127.0.0.1', 7400).send_message('/dj/profile/DEEP_LASER', 1.0)"
```
Look changes → the OSC path works and the problem is the iPad's wifi/host/port.

**3. Does the iPad reach the Mac?** Tap a button and watch the Textport. If step
2 worked and this doesn't, it is the network or the Host field — recheck the IP,
confirm both are on the same non-guest wifi, and check the Mac firewall
(System Settings → Network → Firewall) isn't blocking incoming UDP for TD.

---

## VERIFY BEFORE A SET — the faders are not confirmed

Read this once. It is short and it is the honest part.

`GROUP`, `BUTTON` and `LABEL` were checked against an authentic
editor-produced layout. **`FADER` was not** — there is no reference file on
this machine that contains one, so the node type name and its type-specific
properties (`response`, `bar`, `centered`, `cursor`, `orientation`) are
reasoned from the schema the buttons prove, not verified against the app. The
same applies to the toggle `buttonType` value used by `CROWD ON`.

The parts that decide whether a control appears at all — the `frame` rect, the
`visible` flag, the `<osc>` block, the `touch`/`x` values — are the same
elements every shipping button already uses. So the likely failure is cosmetic.
But "likely" is not "checked", and the last time this file's schema was
reasoned rather than verified, the layout **opened empty on the iPad**
(commit `74d38bc`).

**Open `DJ_Profiles.tosc` in the TouchOSC editor on the Mac and confirm, in
this order:**

1. **The profile buttons are still there and still tappable.** If the whole
   document is empty, stop — use `DJ_Profiles_profiles_only.tosc` and report it.
2. **Six faders are drawn** in the strip, below the grid, above the buttons.
3. **They run vertically**, not horizontally. If they are sideways, the
   `orientation` property is wrong — cosmetic, and the control still works.
4. **The five knob faders sit at their centre**, not at the bottom. A knob
   resting at an end stop means the show comes up already pushed to a full
   offset.
5. **`CROWD ON` latches.** Tap it: it should stay on until tapped again. If it
   springs back, `BUTTON_TOGGLE` is the wrong value and the audience is being
   enabled and immediately disabled — swap it for `2` in
   `make_touchosc_layout.py` and regenerate.
6. **`PANIC` does not latch.** It must be momentary.

**Then on the iPad, with TD running and the Textport open:**

7. Ride **CHAOS** from bottom to top. The Textport should show the offset
   crossing zero at centre and reaching ±1 at the stops. If it only ever goes
   0 → 1, the `scaleMin`/`scaleMax` partials are not being honoured and the
   knobs have lost half their range.
8. Tap **KNOBS 0** — every offset returns to zero.
9. Tap **PANIC** and confirm the audience lockout arms.

`DJ_Profiles_profiles_only.tosc` is **byte-for-byte identical** to the layout
that is already working on the iPad today. If anything above fails mid-set,
that file is a known-good pad, not a hopeful one.

---

## If the .tosc won't open — build it by hand (5 min)

The generated file's schema was verified against a real TouchOSC-editor layout,
but it has still never been opened in the app. If it misbehaves, build it by
hand — this path always works.

Do **[step 4 above](#4-point-touchosc-at-the-mac)** first; without the
connection nothing is sent no matter how the buttons are built.

**Build one button, then copy it.**

1. In the layout browser, create a new document (**+** / **File → New**).
   A canvas around **720 × 1280** matches the generated layout.
2. **Long-press** an empty part of the canvas (right-click on desktop) →
   **Create** → **Button**.
3. With the button selected, in the **Properties** panel set:
   - **Frame** — X `40`, Y `154`, W `640`, H `198`. Full-width and thumb-sized;
     you will be hitting this in the dark without looking.
   - **Type** — **Momentary**. (Not Toggle: a toggle sends `0` on the second tap
     and the look would not re-apply.)
   - **Color** — anything; pick per profile so the pad reads at a glance.
   - **Name** — `UV_RAVE`. Optional, but it keeps the layout readable.
4. Open the **Messages** panel, add an **OSC** message, and set:
   - **Enabled** and **Send** on; **Connection 1** ticked.
   - **Address** — the segments `dj`, `profile`, `UV_RAVE`, each a **CONSTANT**
     partial, so the address reads **`/dj/profile/UV_RAVE`**.
   - **Arguments** — one argument: type **VALUE**, value **x**,
     conversion **FLOAT**.
   - **Trigger** — var `x`, condition **ANY**. This sends `1` on press and `0`
     on release; TouchDesigner ignores the `0`, so the look fires once.
5. **Label it.** A TouchOSC button draws no text of its own, so the caption is a
   separate control. Long-press → **Create** → **Label**, then:
   - Set its **Frame** to the same X/Y/W/H as the button (`40, 154, 640, 198`).
   - **Interactive** — **off**, and **Background** — **off**. Otherwise the
     label swallows the tap and the button never fires.
   - **Text Size** `34`, **Text Color** white (black over lime or cyan).
   - In the **Values** panel, select the `text` value, type `UV RAVE` into
     **Default**, and engage the **Default = Current** lock so the caption
     survives loading.
   - Make sure the label sits **above** the button in the layer order — later
     controls draw on top.
6. Select the button *and* its label, copy, and paste four times. For each copy
   change only:

   | Frame Y | Address (last segment) | Caption |
   |---|---|---|
   | `376` | `/dj/profile/DEEP_LASER` | `DEEP LASER` |
   | `598` | `/dj/profile/STROBE_ACID` | `STROBE ACID` |
   | `820` | `/dj/profile/VAPOR_UV` | `VAPOR UV` |
   | `1042` | `/dj/profile/MONO_PULSE` | `MONO PULSE` |

7. Save, then press **play** to leave edit mode and tap a button. The Textport
   should print `[osc_profile] -> …`.

The **addresses are the only part that must be exact** — everything else is
cosmetic.

---

## Why buttons don't open a different .toe

Opening a `.toe` restarts TouchDesigner — several seconds of black output, which
is unusable with a crowd in front of you. The OSC path calls `apply_profile()`
inside the already-running network instead: it rewrites the palette table and
re-binds parameter expressions, so the change lands within a frame.

## Safety

- **No new audio taps.** This is a DAT Execute on an OSC In DAT — it fires when a
  UDP packet arrives, a few times a night, not once per FFT bin per frame. The
  freeze guarantees are unchanged.
- **A stray packet can't change the look.** An unrecognised address, an unknown
  profile name, or a button *release* are all ignored rather than guessed at.
- **OBS untouched.** Nothing in this path talks to OBS; Syphon stays overlay-only.
