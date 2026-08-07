# Audience Chat Bridge — runbook

The safe core of the audience-interactive system from
`docs/research/audience_interactive_chat_graphics.md`. Viewers type plain
English in YouTube Live chat; the rig responds. Thomas can override at any
moment, and one tap returns everything to a known-good look.

**Status: built and unit-tested, never run against a live stream.** Nothing
here has seen a real chat feed, a real OpenAI response, or a real
TouchDesigner network. The go-live sequence at the bottom is the gate.

---

## What it is

One sentence: **the audience never touches TouchDesigner, the audience votes on
an enum.**

```
YouTube Live chat
      │
      ▼  python/chat_bridge/  (sidecar process, own venv, no audio, no asyncio)
   ┌──────────────────────────────────────────────────────┐
   │ 1. INTAKE     dedupe, 20 msg/s cap, deque(maxlen=500)│
   │ 2. MODERATE   local structural + OpenAI, FAILS CLOSED │
   │ 3. PREFILTER  keyword screen (cost, not safety)       │
   │ 4. INTERPRET  schema-bound LLM -> closed enum ONLY    │  gate 1
   │ 5. VALIDATE   plain Python, vs LIVE gp.PROFILES       │  gate 2
   │ 6. ARBITRATE  5 limiters, 30 s vote window, ceiling   │
   └──────────────────────────────────────────────────────┘
      │  ~1 decision / 30–60 s, as /dj/audience/* OSC
      ▼
   TouchDesigner, UDP 7400
      │
   audience_control.py     re-validates everything, independently   gate 3
      │
      ├─► apply_profile('STROBE_ACID')      (existing path, unchanged)
      └─► fx_audience Constant CHOP         (new, clamped scalars)
                │
                ▼  consumed INSIDE the existing hard caps            gate 4
          outline_glow.size, fx_trail_hsv.valuemult, fx_kick_bright, …
```

Every failure mode — LLM down, moderation down, quota gone, bridge crashed,
packet garbage — degrades to **the visuals stop changing**, never to *the
visuals break*.

---

## What Thomas must supply

Two things. Neither is in the repo, and neither can be.

### 1. An OpenAI API key

```bash
export OPENAI_API_KEY=sk-...
```

One key, two endpoints: the interpreter (a small per-stream cost) and
moderation (`omni-moderation-latest`, **free**). Set a **hard monthly spend
cap** on the key regardless — the prefilter suppresses most batches, but a cap
is cheaper than a surprise.

Without it the bridge refuses to start. That is deliberate: no key means
moderation fails closed on every message, which means the visuals would never
change and it would look like a bug.

### 2. YouTube access

**Reading your own live chat is user-scoped. An API key will not work for it.**

1. Cloud project → enable **YouTube Data API v3**.
2. OAuth client, type **Desktop app**. Download the JSON as
   `client_secrets.json`.
3. Scope: **`youtube.readonly`** only. Not `youtube.force-ssl` — that would
   also permit *posting* into chat, and the bridge must never be able to speak.
4. ⚠️ **Consent screen → publishing status → "In Production."**

> ### The 7-day trap
>
> A consent screen left in **"Testing"** has **all its refresh tokens revoked
> by Google after exactly 7 days.** Set the bridge up on a Tuesday and it is
> dead before the weekend's show — failing silently, as an auth error, at
> stream start.
>
> Setting it to "In Production" makes the refresh-token lifetime indefinite.
> Full Google verification is only needed to distribute an app publicly or to
> use restricted scopes; as the sole user of your own app you click through an
> "unverified app" warning once and never see it again.

The bridge alerts loudly on token-refresh failure (stderr banner + a
`level: CRITICAL` line in the NDJSON log) rather than logging a shrug, because
a dead token is otherwise indistinguishable from a quiet chat.

**Reading someone else's public stream** (e.g. the Kniteforce YouTube mirror)
needs only `YOUTUBE_API_KEY` and `--video-id`. No OAuth, no ownership, none of
the 7-day problem. It draws on the same 10,000-unit daily bucket.

---

## Install and run

```bash
python3 -m venv venv-chat
./venv-chat/bin/pip install -r requirements-chat.txt
export OPENAI_API_KEY=sk-...
cd python
```

### First: a dry run against a log, with no stream and no rig

```bash
../venv-chat/bin/python -m chat_bridge \
    --source replay --file ../logs/chat_bridge.ndjson --dry-run
```

`--dry-run` runs the entire pipeline and logs every decision **without opening
a socket to TouchDesigner**. This is how the interpreter gets reviewed before
it is ever allowed near the show.

### Then: log-only against a real stream, visuals untouched

```bash
../venv-chat/bin/python -m chat_bridge --source youtube --dry-run --duration 10800
```

Three hours, no visuals. This is the soak: it catches quota drift, memory
growth, and token expiry, and it produces the log the replay mode reads back.

### Live

```bash
../venv-chat/bin/python -m chat_bridge --source youtube
```

Or from the launcher suite, alongside the tracker and TouchDesigner:

```bash
CHAT_BRIDGE=1 OPENAI_API_KEY=sk-... python3 python/system_launcher.py
```

### Escape hatch — a token dies ten minutes before doors

```bash
../venv-chat/bin/python -m chat_bridge --source fallback --url https://youtube.com/watch?v=XXXX
```

`chat-downloader`, no auth, no quota, no Cloud project. Unofficial and it will
break without warning when YouTube changes its continuation-token format, so
keep it working and don't make it the default. (Explicitly **not** `pytchat`,
archived and read-only since 2021.)

---

## TouchDesigner side

Paste into the Textport (Alt+T), in this order:

```python
import audience_control
audience_control.install_audience_control()
```

That creates the `fx_audience` Constant CHOP and re-applies the current profile
so every expression picks up its audience-aware form. To close the door
completely:

```python
audience_control.audience_teardown()
```

**The CHOP's absence is the strongest kill switch there is.** Without it, every
expression is emitted in its original, byte-identical form, and there is no
term for the audience to write into at all.

`osc_profile_control.py` already listens on 7400 and now offers anything that
isn't `/dj/profile/*` to `audience_control`, so no new OSC In DAT is needed.

---

## Thomas's controls

| Control | OSC address | Effect |
|---|---|---|
| **PANIC** | `/dj/panic 1` | `UV_RAVE` + every audience channel zeroed + 5 min mute + vote window cleared. One tap. |
| Audience on/off | `/dj/audience/enable 0\|1` | master gate |
| Intensity | `/dj/audience/gain 0.0–1.0` | `0.3` = they can tint it; `1.0` = they're driving |
| Profile lock | `/dj/audience/lock_profile 0\|1` | audience keeps nudges + one-shots, loses profile votes |
| *(existing)* | `/dj/profile/<NAME>` | unchanged — **and now arms a 60 s audience lockout** |

Three things worth knowing:

- **His action wins and keeps winning.** Any `/dj/profile/*` tap arms a 60 s
  lockout. During it, audience votes are received, tallied and logged — and not
  applied. This prevents the failure everyone hits first: he picks `DEEP_LASER`
  for a breakdown and eight seconds later a pending vote flips it back.
- **The lockout is a timer, not a mode.** It self-clears. He never has to
  remember to re-enable anything.
- **Two independent kill paths.** The bridge listens on **7401** and stops
  emitting at the source; TouchDesigner gates `/dj/audience/*` on its own flag
  regardless of what the bridge does. Point TouchOSC's kill switch at both.
  Disabling the audience never disables his own buttons, because they are a
  different namespace and a different parser.
- **Physical fallback:** quitting the bridge process stops all audience input.
  No TD interaction required, and the rig continues on its current look.

⚠️ **The TouchOSC layout was not regenerated.** `make_touchosc_layout.py` still
emits the five profile buttons only; the addresses above must be added by hand
in TouchOSC, or the generator extended in a follow-up. That was left alone
deliberately — the `.tosc` schema was hand-fixed recently and is fragile, and
none of the safety behaviour depends on it.

---

## What the audience can and cannot do

| Verb | Targets | Effect |
|---|---|---|
| `PROFILE` | the five registry keys, read **live** from `gp.PROFILES` | `apply_profile()` — needs a quorum of 2 |
| `NUDGE` | `GLOW` `FLASH` `TRAILS` `SHAKE` `ZOOM` `SPEED` | one clamped scalar, summed across askers then clamped |
| `ONESHOT` | `STROBE_BURST` `COLOR_POP` `WHITEOUT` | a self-cancelling pulse, at the ceiling duration |

Colour words resolve to the named neon anchors already in
`dj_graphics_profiles.py` (`CYAN` `MAGENTA` `ACID` `PINK` `VIOLET` `BLUE`
`WHITE_HOT`). The audience cannot author an RGB triple, so it cannot route
around the `is_brown()` / `is_neon()` guards.

**Permanently out of reach, not "phase 2":** GLSL or shader source of any kind,
any string that gets `exec`/`eval`'d, TD parameter *expression* strings, node
creation/deletion/rename, raw RGB, resolution or cook rate, **the audio device
or audio chain**, OBS scenes, file paths, URLs, shell.

### The photosensitivity ceiling

Not tunable, not voteable, not configurable, and not reachable from any OSC
address:

| | |
|---|---|
| Strobe flash rate | **2 Hz** (WCAG 2.3.1's general threshold is *more than 3 flashes per second*) |
| Strobe duration | ≤ 1.5 s |
| Strobe spacing | ≥ 20 s |
| Whiteout | ≤ 0.6 s, ≥ 30 s apart, a single ramped flash — not a repeating one |
| Colour pop | no flash at all; snaps a hue and holds it ≤ 2 s |

Enforced **twice, independently**: in the bridge's arbiter, and again in
`audience_control.py` with its own state. The constants are duplicated on
purpose — an independent check that shares its constants with the thing it is
checking is not independent. A test asserts the two copies agree so they cannot
silently drift.

Put a standing "flashing lights" notice in the stream description regardless.

### No audio, ever

Nothing in the bridge or in `audience_control.py` opens an audio device,
synthesises speech, or names the audio chain. TTS shoutouts remain a separate,
later, optional piece of work, and when they happen they route to their own
output device and their own OBS source. **`audio_in` is the reactivity source;
if TTS reaches it the visuals react to their own voice, and it means a new
audio tap — the thing the profile system exists to forbid.**

This is asserted against the source, not asked for politely:
`tests/test_chat_bridge.py::TestNoAudioPath`.

---

## Reading the log

`logs/chat_bridge.ndjson`, one JSON object per line.

| `event` | What it tells you |
|---|---|
| `message` | every message admitted (this is what `--source replay` reads back) |
| `moderation_reject` | with a reason: `flagged_text`, `zalgo_name`, `moderation_error` |
| `validator_reject` | with a reason: `unknown_profile`, `bad_verb`, `low_confidence` — **this is where a jailbreak attempt shows up** |
| `action` | a validated action and which limiter, if any, refused it |
| `window` | the vote tally, including during a lockout, so the log is never silent about what the room asked for |
| `emit` | what actually went out on the wire |
| `heartbeat` | every 30 s: queue depth, LLM calls/failures, drop counters. **Absence of these is the signal that the process died.** |
| `alert` | `level: CRITICAL`. Also printed as a banner on stderr. |

---

## Go-live checklist

- [ ] Consent screen is **"In Production"**, not "Testing"
- [ ] `OPENAI_API_KEY` set, with a hard monthly spend cap
- [ ] `--dry-run` replay reviewed: are the classifications actually *fun*?
      (If the interpreter can't tell "more strobes" from "this track is
      strobing my brain", stop and use keyword matching instead — genuinely
      fine for six verbs, and instant, free and unjailbreakable.)
- [ ] **Measure the real quota cost.** Google's quota table does not document
      the live-streaming endpoints at all, so the per-call cost of
      `liveChatMessages.list` is *unknown*. Watch the Cloud Console graph for
      ~10 minutes of polling, then set `CHAT_BRIDGE_UNIT_COST` to what you
      measure. At 1 unit a 3-hour stream is comfortable; at 5 it dies mid-show.
- [ ] 3-hour `--dry-run --duration 10800` soak: no memory growth, no quota
      drift, token still alive at the end
- [ ] `.toe` snapshotted to `archive/toe/` before `install_audience_control()`
      touches the live file
- [ ] PANIC tested, on the actual iPad, before doors
- [ ] "Flashing lights" notice in the stream description

---

## Not built (and why)

- **Ack overlay / TTS shoutouts** — flair, and the only paths where audience
  *characters* reach the broadcast. The sanitizer they need is already built
  and tested (`safe_display_name`); the Text TOP and the ElevenLabs route are
  not.
- **The in-TD `chatGPT_o1.tox` interpreter** — kept off the critical path on
  purpose. An in-TD interpreter puts the LLM call, its retries and its timeouts
  in the same process as the render, can't be unit-tested outside TD, can't be
  restarted without touching the show file, and can't be killed independently.
- **`face_detector.tox`** — no role in chat→graphics, and per-frame GPU cost on
  a rig already at `cookRate 30` to shed load.
- **Kniteforce as a second source** — blocked on the volume check in §1.2 of
  the scope doc: open `kniteforce-radio.com/see` during a live show and compare
  message volume between the embedded chat and the YouTube chat. The system
  ships YouTube-only and loses nothing.
- **`streamList`** — the polled `list` path is implemented behind the
  `ChatSource` seam; whether `google-api-python-client` can call the streaming
  variant cleanly is still unverified, and swapping it in is one class.
