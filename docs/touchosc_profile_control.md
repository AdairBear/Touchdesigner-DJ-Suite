# Switching graphics profiles live from TouchOSC

Tap a button on the iPad or iPhone, the look changes **inside the running show**
— no reload, no dropped frames. Safe mid-set.

| | |
|---|---|
| Layout file | `~/Desktop/DJ_Profiles.tosc` (plus `DJ_Profiles.xml` fallback) |
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

AirDrop `~/Desktop/DJ_Profiles.tosc` to the iPad and iPhone. Accept, and choose
**Open with TouchOSC**. It appears in TouchOSC's layout list.

### 4. Point TouchOSC at the Mac

In TouchOSC, open the connection settings (the gear / **OSC** tab) and set:

- **Host** — the IP from step 2
- **Port (outgoing)** — `7400`
- **Protocol** — UDP
- Leave incoming port at its default

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

I generated the `.tosc` but **could not load-test it** (that needs the TouchOSC
app), so it may not open. The XML beside it is the same layout in readable form.
If TouchOSC rejects the file, building it manually is quick and definitely works:

1. TouchOSC → **+** → new layout.
2. Add a **Button**. In its **OSC** tab set the address to `/dj/profile/UV_RAVE`,
   value `1` on press.
3. Set its label to `UV RAVE`.
4. Duplicate it four times, changing address and label each time to
   `DEEP_LASER`, `STROBE_ACID`, `VAPOR_UV`, `MONO_PULSE`.

That's the whole layout. The addresses are the only part that must be exact.

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
