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
three files to `~/Desktop`:

| File | What it is |
|---|---|
| `DJ_Profiles.tosc` | **Try this one.** zlib-compressed, the real format. |
| `DJ_Profiles_uncompressed.tosc` | Same document, no zlib wrapper. Try only if the first is rejected. |
| `DJ_Profiles.xml` | Byte-identical to the uncompressed one, for reading. |

AirDrop `DJ_Profiles.tosc` to the iPad and iPhone. Accept, and choose
**Open with TouchOSC**. It appears in TouchOSC's layout list.

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
