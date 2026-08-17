# Audience-Interactive Chat → Graphics — Design Scope

> **Status:** design only. Nothing in this document has been built.
> **Date:** 2026-08-06
> **Depends on:** the shipped profile system (`dj_graphics_profiles.py`,
> `osc_profile_control.py`, `touchdesigner/profiles/`).

The vision: viewers in YouTube Live chat and Kniteforce Radio chat type plain
language — *"make it rain acid green"*, *"more strobes on the kick"* — and the
graphics change from their description. The audience becomes the VJ. Thomas
keeps override in both directions plus a kill switch.

---

## 0. The verdict up front

| Question | Answer |
|---|---|
| YouTube Live chat ingestible? | **Yes.** Official API, well-documented, cheap. |
| Kniteforce Radio chat ingestible? | **Technically yes, politically maybe.** Chat is a third-party SaaS widget (Embedded Chat) on a room Thomas does not own. Clean path = ask the station for a webhook. Details in §2.2. |
| Is this safe to point at a live show? | **Only under one architecture:** chat text never enters TouchDesigner, and the LLM is a *classifier over a closed enum*, never a code generator. §3–§4. |
| Biggest technical risk | Not the LLM. It's re-introducing the freeze. Mitigated by keeping the whole pipeline in a sidecar process (§3.1). |
| Biggest non-technical risk | **Photosensitive epilepsy.** An audience with a strobe verb is a real safety surface on a public stream. §4.5. |
| Rough effort | **11–17 dev-days** to a show-ready v1 including the flair. §9. |

---

## 1. What exists today (the ground this is built on)

Read this section as the contract the new work must not break.

### 1.1 The profile system

`touchdesigner/scripts/dj_graphics_profiles.py` — five looks (`UV_RAVE`,
`DEEP_LASER`, `STROBE_ACID`, `VAPOR_UV`, `MONO_PULSE`). A profile is **data, not
a node graph**: applying one rewrites a Table DAT and re-binds ~11 parameter
*expressions*. Nothing is created, deleted, or renamed.

Three properties of that file matter enormously here, and they are the reason
this feature is buildable at all:

1. **`validate_profile()` already exists** and enforces the neon/UV palette,
   the no-brown hue ban (15–50°), and range checks on every reactivity field.
2. **The two safety invariants are structural, not advisory.**
   `glow_size_expr()` has no branch that emits an unclamped blur
   (`GLOW_SIZE_HARD_CAP = 52.0`); `trail_valuemult_expr()` wraps everything in
   `min(..., 0.97)` so feedback cannot run away. A bad *value* is clamped, not
   shipped.
3. **The palette anchors are a named, finite set** — `CYAN`, `MAGENTA`, `ACID`,
   `PINK`, `VIOLET`, `BLUE`, `WHITE_HOT`.

That third point is the whole colour-safety story for this feature. *"Make it
rain acid green"* resolves to the existing `ACID` anchor. The audience never
supplies an RGB triple, so the neon/no-brown guard is never in play against
hostile input — the input space simply doesn't contain a bad colour.

### 1.2 The OSC control path

`touchdesigner/scripts/osc_profile_control.py` — an OSC In DAT on **UDP 7400**
plus a DAT Execute handler. Contract:

```
/dj/profile/STROBE_ACID   <any>      -- address carries the name
/dj/profile               "NAME" | <int index>
```

`parse_osc_profile_message()` is pure and unit-tested
(`tests/test_osc_profile_control.py`). Its default is **ignore**: unknown
address, unknown profile, or a button-release (falsy numeric arg) all return
`None`. That defensive default is exactly the posture audience input needs, and
the new verbs should extend this function rather than sit beside it.

### 1.3 The freeze discipline

The graphics froze the instant real music played. Root cause: a CHOP Execute DAT
whose `onValueChange` fired once per changed *sample* — hundreds of times per
frame on the cook thread — plus an unclamped blur size.

The rule that came out of it, and which this design inherits verbatim:

> **No new audio taps. No CHOP Execute DATs. Parameter expressions only.**
> Anything that must run repeatedly runs *outside* TouchDesigner.

`osc_profile_control.py` is compliant because a DAT Execute on an OSC In DAT
fires only when a UDP packet arrives — "a few times a night, not once per FFT
bin per frame." The audience feature must hold that same line, which is the
single strongest argument for §3.1.

---

## 2. Chat ingestion — feasibility findings

### 2.1 YouTube Live — solved, official, cheap

**Path to the chat ID (no OAuth needed for read):**

1. `videos.list?part=liveStreamingDetails&id=<VIDEO_ID>` → `activeLiveChatId`.
   Cost: **1 unit**. Works with a plain API key.
2. Feed that `liveChatId` to the message reader.

> Avoid `liveBroadcasts.list?mine=true` — it requires full OAuth2 with
> `youtube.readonly`. The `videos.list` route above gets the same chat ID with
> an API key, provided Thomas knows his own video ID (he does; it's his stream).

**Reading messages — two methods:**

| Method | Model | Notes |
|---|---|---|
| `liveChatMessages.list` | Poll. Response carries `pollingIntervalMillis` and `nextPageToken`. | **Officially marked deprecated** in favour of `streamList`. Still functional. |
| `liveChatMessages.streamList` | Server-streaming HTTP connection; messages pushed as they arrive. | Google's stated recommendation: "reduces polling and quota consumption." Returns `RESOURCE_EXHAUSTED` if hit faster than YouTube's refresh rate. |

**Recommendation:** build the reader behind an interface with **`streamList` as
primary and `list` as fallback**. `streamList` is newer and less battle-tested in
the wild; a poll fallback costs ~30 lines and removes a single point of failure
mid-set.

**Quota.** Default allocation is **10,000 units/day**. The commonly cited cost
for `liveChatMessages.list` is **5 units/call**; `insert` (posting a message) is
**50 units**. ⚠️ *Neither figure appears in Google's current published quota-cost
table* — the table omits the live-chat methods entirely. **Verify both in the
Cloud Console quota calculator during Phase 0** before relying on the arithmetic.
If 5/call holds: honouring `pollingIntervalMillis` (typically 5–10 s) over a 4-hour
set is ~1,440–2,880 calls → **7,200–14,400 units**. That is *at or over* the daily
cap for a long set on the polling path — a concrete reason to prefer `streamList`,
and a reason to request a quota increase if the fallback ever becomes primary.

**Auth:** an API key suffices for reading. OAuth2 is only needed if the system
ever *posts* to chat (e.g. a bot replying "applied STROBE_ACID"). Recommend
**not** posting in v1 — on-screen acknowledgment (§8) achieves the same thing
without OAuth, without quota, and without a spam-report surface.

### 2.2 Kniteforce Radio — the finding

**What it actually is.** `kniteforce-radio.com` embeds a third-party SaaS chat
widget from **Embedded Chat** (`embedded-chat.com`), loaded via
`d2yy16lkdmfg04.cloudfront.net/resource/chat.js` into an iframe at
`embedded-chat.com/room/chat/?hash=292041`. Project token `9461`, room hash
`292041`. It is *not* Discord, not a self-hosted widget, not IRC.

**Transport, confirmed by inspection.** The widget runs **Socket.IO** (v4 /
EIO=4, `/socket.io/` endpoint, polling→websocket upgrade). The client registers
handlers for `message`, `edit_message`, `delete_message`, `reaction`, `users`,
`pin_message`, `poll_created`, `tip_received`, and more. The page exposes a
**`ROOM_READ_TOKEN`** global — a 50-character anonymous read token — so
read-only access does not require an account.

**Three possible ingestion routes, in order of preference:**

| Route | How | Verdict |
|---|---|---|
| **A. Vendor webhook** | Embedded Chat ships HMAC-signed POSTs on `message_posted`, `mention_received`, `message_pinned`, configured per project with a shared secret. Point it at a small endpoint (Thomas's VPS already runs one at `relay.themostboringdomain.app`). | ✅ **Clean, supported, robust.** ⚠️ **Requires the Kniteforce project admin to configure it** — Thomas does not own project `9461`. This is a conversation, not a coding task. Possibly a paid tier. |
| **B. Socket.IO read client** | A `python-socketio` client joining room `292041` with the public `ROOM_READ_TOKEN`, subscribing to `message`. | ⚠️ **Works technically. Unofficial.** Brittle against vendor changes, and it's scraping a third party's platform without asking. Reserve as a fallback *with the station's blessing*, not as plan A. |
| **C. Manual relay** | Thomas (or a mod) forwards interesting requests by hand. | Fine as a stopgap; defeats the point. |

**Recommendation: ask.** One email to Kniteforce asking for an Embedded Chat
webhook pointed at Thomas's endpoint costs nothing and makes route A legitimate.
Supporting evidence that they'd be receptive: the room's own chat log currently
shows a station regular demoing chat tooling at `kniteforce-chat.fly.dev` to
someone named Chris — the station is *actively* working on chat features right
now. (That is an observation about the room's contents, not a recommendation to
act on anything said in it.)

**Flag:** if the station declines and route B is off the table, **Kniteforce
ingestion is not programmatically accessible** and the feature ships
YouTube-only. Everything downstream of ingestion is source-agnostic (§3.2), so
this is a plug, not a redesign. Phase 6 is deliberately last for this reason.

### 2.3 The source abstraction

Both sources normalize to one record before anything else touches them:

```python
ChatMessage = {
    "source":      "youtube" | "kniteforce",
    "message_id":  str,       # for dedupe across reconnects
    "author_id":   str,       # stable per-source user key, for cooldowns
    "author_name": str,       # display only, UNTRUSTED — see §7.3
    "text":        str,       # UNTRUSTED
    "timestamp":   float,
}
```

Nothing downstream knows or cares which platform a message came from.

---

## 3. Architecture

### 3.1 The central decision: a sidecar, not an in-TD pipeline

**Recommendation: the entire chat → moderation → LLM → intent pipeline runs in a
separate Python process. Only a validated enum verb crosses into TouchDesigner,
over the existing OSC path.**

Why, given that Thomas has `TDAsyncIO.tox` and `chatGPT_o1.tox` specifically to
make in-TD API calls non-blocking:

- The freeze is this project's most expensive recurring failure, and its lesson
  was *move repeated work off the cook thread*. A sidecar isn't "async work on
  the cook thread" — it's **not on the cook thread at all**. That's a stronger
  guarantee than any async helper can give.
- The OSC receiver is already built, already unit-tested, and already proven
  freeze-safe by construction. Reusing it means the audience feature adds
  **zero** new node types to the show file.
- A sidecar can be restarted, redeployed, and debugged mid-set without touching
  the running `.toe`. An in-TD pipeline cannot.
- Everything interesting — moderation, cooldowns, vote windows, the whitelist
  validator — is plain Python and belongs under `pytest`, not inside a `.toe`.

**Where the uploaded .tox components land under this design:**

| Component | Assumed role | Placement |
|---|---|---|
| `chatGPT_o1.tox` | OpenAI chat completions in TD | **Prototyping / not in the live path.** Useful to sanity-check prompt behaviour interactively. The production interpreter is a sidecar HTTP call. |
| `TDAsyncIO.tox` | Non-blocking API calls in TD | **Held in reserve.** Needed only if a later phase moves something back in-TD (e.g. TTS triggered from TD directly). Not required for v1. |
| `ElevenLabs_0_3.tox` | TTS | **Optional, Phase 5.** Recommend running TTS in the sidecar (write WAV → TD plays a file) so a slow API call can never touch the cook thread. Use the `.tox` only if in-TD playback proves simpler and `TDAsyncIO` is wired. |
| `Chat_Agent.toe` | Working chat-agent reference | **Reference implementation** for prompt/response wiring. Mine it for patterns; don't put it in the show file. |
| `face_detector.tox` | Face detection | **Out of scope.** Noted as a future hook (audience-triggered effects keyed to Thomas's face). Not v1. |

⚠️ These roles are *assumed* from the brief. Verify each component's real
function in Phase 0 before committing to the table above.

### 3.2 Data flow

```
 YouTube Live Chat API ─┐
                        ├─► ingest ─► normalize ─► ChatMessage
 Embedded Chat webhook ─┘                              │
                                                       ▼
                                        ┌──────────────────────────┐
                                        │ 1. PREFILTER  (regex)    │  ~95% dropped, free
                                        │ 2. MODERATION (OpenAI)   │  free endpoint
                                        │ 3. RATE LIMIT (per user) │  in-memory
                                        └──────────────┬───────────┘
                                                       ▼
                                        ┌──────────────────────────┐
                                        │ 4. INTERPRETER (LLM)     │  text → {verb, intensity}
                                        │    structured enum out   │
                                        └──────────────┬───────────┘
                                                       ▼
                                        ┌──────────────────────────┐
                                        │ 5. VALIDATOR  ★          │  reject anything not in
                                        │    the whitelist gate    │  the enum. NEVER trust
                                        └──────────────┬───────────┘  the model's compliance.
                                                       ▼
                                        ┌──────────────────────────┐
                                        │ 6. ARBITER (vote window) │  N messages → 1 action
                                        │ 7. OVERRIDE / KILL GATE  │  Thomas always wins
                                        └──────────────┬───────────┘
                                                       ▼
                          OSC /dj/audience/<VERB> <intensity>  ──► UDP 7400
                                                       │
                        ┌──────────────────────────────┴──────────────────┐
                        │  TouchDesigner (unchanged discipline)           │
                        │  osc_profile_control → derive Profile object    │
                        │  → validate_profile() → write table + exprs     │
                        │  → TTL timer auto-reverts to base profile       │
                        └─────────────────────────────────────────────────┘
```

**★ Step 5 is the security boundary.** Everything left of it is untrusted text.
Everything right of it is a member of a finite enum. Chat text never crosses.

---

## 4. The whitelist — the safety design

### 4.1 The rule

> **The LLM is a classifier, not a code generator.** Its entire output space is
> `(verb ∈ 22 constants) × (intensity ∈ {low, med, high})` — 66 possible
> outputs, all enumerable, all pre-validated. It never emits GLSL, never emits
> Python, never emits a number, never emits a colour, never emits a node name.

Free-form shader or parameter generation is rejected on two independent grounds,
either of which is sufficient:

- **Freeze/crash risk.** New GLSL TOPs are this project's single most expensive
  failure mode — yellow-triangle compile errors, resolution mismatches, GPU
  load. The rig already runs `cookRate 30` to shed load.
- **Injection risk.** Audience chat is untrusted public input. Any path from
  chat text to executed code is a remote-code-execution channel on Thomas's
  show machine, dressed up as a feature.

### 4.2 Two tiers of action

**Tier 1 — PROFILE.** Select one of the five existing profiles. Direct reuse of
`apply_profile()`. Coarse but dramatic; the audience feels it instantly.

**Tier 2 — MODIFIER.** A bounded nudge *on top of* the currently active profile,
with a TTL and auto-revert. This is what makes the feature feel alive — five
profiles alone would go stale in ten minutes.

### 4.3 The verb table

Every verb maps to exactly one field on a `Profile` object. Intensity is a
**lookup, not arithmetic on model output** — the model picks a bucket, Python
owns the number.

| Verb | Profile field touched | low / med / high | Existing guard |
|---|---|---|---|
| `PROFILE_UV_RAVE` … `PROFILE_MONO_PULSE` (×5) | *whole profile* | — | `validate_profile()` |
| `COLOR_CYAN` / `_MAGENTA` / `_ACID` / `_PINK` / `_VIOLET` / `_BLUE` / `_WHITE` (×7) | `palette` — rotate named anchor to front | — | anchors are pre-validated constants |
| `STROBE_UP` / `STROBE_DOWN` | `kick_flash_gain`, `glow_kick_gain` | ±2 / ±5 / ±9 | `GLOW_SIZE_HARD_CAP`, §4.5 rate ceiling |
| `TRAILS_LONGER` / `TRAILS_SHORTER` | `trail_persistence` | ±0.02 / ±0.04 / ±0.06 | `TRAIL_VALUEMULT_HARD_CAP` |
| `FASTER` / `SLOWER` | `palette_period_s` | ÷ or × 1.3 / 1.7 / 2.2 | clamped 6–60 s |
| `SHAKE_MORE` / `SHAKE_LESS` | `shake_snare_px` | ±3 / ±7 / ±12 | clamped 0–20 px |
| `PUNCH_UP` / `PUNCH_DOWN` | `zoom_kick_gain` | ±0.06 / ±0.12 / ±0.20 | clamped 0–0.5 |
| `MODE_FIRE` / `MODE_LIGHTNING` / `MODE_CYCLE` | `mode` | — | `visual_switch` has exactly 2 inputs |
| `NOOP` | — | — | the model's "I don't know" — **must** be in the enum |

*(≈22 verbs. Tune the list during Phase 1 against how the rig actually looks.)*

### 4.4 The single enforcement point

A modifier is applied by **cloning the active `Profile`, mutating one field, and
running the result through the existing `validate_profile()`**. If it fails, it
is dropped and logged — not clamped-and-shipped, not partially applied.

```python
def derive(base: Profile, verb: str, intensity: str) -> Profile | None:
    if verb not in VERB_TABLE:            # gate 1: enum membership
        return None
    cand = clone(base)
    VERB_TABLE[verb](cand, DELTA[verb][intensity])   # gate 2: table-driven delta
    cand = clamp_to_bounds(cand)                      # gate 3: field bounds
    return cand if not validate_profile(cand) else None   # gate 4: shipped validator
```

**The property this buys:** *there is no code path from audience input to the
live rig that bypasses `validate_profile()`.* Audience-driven changes are held to
exactly the same standard as Thomas's own hand-authored profiles — and that
standard is already enforced by `tests/test_dj_graphics_profiles.py`.

**Required small change to existing code:** `apply_profile()` currently takes a
registry *name*. Add `apply_profile_object(prof: Profile)` and have
`apply_profile(name)` delegate to it. Purely additive; the existing signature and
tests are untouched.

### 4.5 Photosensitive epilepsy — a real constraint, flagged

This is the one risk the brief didn't raise and it deserves its own line. Giving
a public audience a `STROBE_UP` verb on a livestream is a genuine safety surface,
not a theoretical one.

Design response:

1. **Hard ceiling = the shipped `STROBE_ACID` profile.** No stack of audience
   modifiers may produce flash/glow values exceeding what that profile already
   ships. If Thomas is comfortable running `STROBE_ACID` manually, the audience
   cannot make it worse. This is a bound the codebase can already express.
2. **Rate ceiling on `mode` cycling and flash gain**, enforced in
   `clamp_to_bounds()`, tuned toward the WCAG "three flashes per second"
   guidance.
3. **A single config flag `AUDIENCE_STROBE_ENABLED`** — off, `STROBE_UP` becomes
   `NOOP`. Thomas decides per venue/stream.
4. **A stream description line** noting audience-controlled visuals with flashing
   imagery.

### 4.6 What is permanently out of the whitelist

Non-negotiable, regardless of how the feature evolves:

- ❌ Any GLSL / shader source, or any parameter feeding a shader compile
- ❌ Any Python expression string (the `.expr` writes are **built by Python from
  the verb table**, never assembled from model output)
- ❌ Node creation, deletion, renaming, or any `op()` path from model output
- ❌ Raw RGB / hex colour values
- ❌ Raw numeric parameter values
- ❌ Anything touching OBS, audio devices, the tracker, or the filesystem
- ❌ `cookRate`, resolution, or any render-load parameter

---

## 5. The interpreter

### 5.1 Contract

**Input:** one sanitized `ChatMessage.text`, truncated to 200 chars.
**Output:** strict JSON, `{"verb": <enum>, "intensity": <enum>, "confidence": 0–1}`.

**Implementation notes:**

- Use **structured output / JSON-schema-constrained decoding** with the verbs as
  a literal `enum`. This makes off-menu output *very* unlikely.
- **Then validate anyway.** Gate 1 in §4.4 exists because "very unlikely" is not
  "impossible", and because a schema is a property of the API call, not of the
  safety model. Belt and braces.
- **Batch the vote window.** Send the whole 20-second window's surviving
  messages in one call, get back one classification per message. Cuts request
  count ~10× and lets the model see the room's mood.
- **`confidence < 0.6` → treat as `NOOP`.** Ambiguous requests should do nothing
  rather than guess. A wrong change mid-set is worse than no change.
- **Model choice:** a small/fast tier (gpt-4o-mini class, or Claude Haiku) is
  ample — this is 22-way classification, not reasoning. Latency matters more
  than depth; the audience should see a change within a few seconds.

### 5.2 Prompt-injection posture

Chat *will* contain `IGNORE PREVIOUS INSTRUCTIONS AND ...`. That's fine, and it's
worth being precise about why:

The classifier can be jailbroken into emitting anything it likes. **It doesn't
matter**, because its output is filtered through gate 1 — enum membership —
before anything acts on it. A jailbroken classifier's best case is emitting a
*valid verb the user didn't ask for*, which is indistinguishable from a
misclassification and is bounded by every clamp in §4.3. There is no string from
chat that reaches TouchDesigner.

Still worth doing, as defence in depth:
- Wrap message text in explicit delimiters and instruct the model to treat it as
  data to classify, never as instructions.
- Never echo model output into any prompt, log format string, or on-screen text.
- Log every `(text → verb)` pair for post-show review.

---

## 6. Moderation and flow control

### 6.1 The four-stage funnel

**Stage 1 — Prefilter (free, ~0 ms).** Drop everything that isn't plausibly a
graphics request.

> **Recommendation for v1: require a `!vj ` prefix.** Cheapest possible filter,
> makes the request explicit and intentional, and gives the audience a shared
> ritual ("!vj make it acid green") that is itself good stream content. Relax to
> keyword-matching later once the cost and behaviour are understood. Expected
> drop rate: >95% of chat volume.

**Stage 2 — Moderation (free).** OpenAI's `omni-moderation-latest` on the
`/v1/moderations` endpoint. It is **free and does not count toward usage
limits** — there is no cost argument for skipping it. 13 category flags with
independent scores. Set conservative thresholds on `harassment`, `hate`,
`sexual`, `violence`, `self-harm`. Anything flagged is dropped silently — never
acknowledged on screen, never surfaced, never spoken.

Also apply a local banned-words list for scene-specific and per-name terms the
API won't catch, and note that Embedded Chat's Pro tier runs the same
`omni-moderation` model upstream — so Kniteforce messages may arrive
pre-moderated. Don't rely on it; run our own pass regardless.

**Stage 3 — Rate limiting.**

| Limit | Value | Why |
|---|---|---|
| Per-user cooldown | 60 s | one voice, one vote |
| Global minimum dwell | 20 s between applied changes | **the anti-thrash guarantee** |
| Hourly change budget | 60 | bounds API cost and visual churn |
| Per-user daily cap | 30 | blunts a single determined spammer |

**Stage 4 — Arbitration.** *"Whose request wins"* — the answer is: **nobody's.
The room's does.**

A rolling **20-second vote window**:

1. Collect all surviving `(user, verb, intensity)` in the window.
2. Deduplicate by `author_id` — last request per user wins.
3. **Modal verb wins.** Ties break toward the most recent.
4. **Intensity escalates with agreement**: 1 voter → their intensity; 3+ voters
   on the same verb → bump one level ("the room is shouting for strobes").
5. Apply exactly one change. Reset the window.

A vote window handles the 100-message thrash case *by construction* — 100
messages in 20 s produce exactly one visual change, and it's the one the room
actually wanted. A queue would produce 100 changes; a plain cooldown would
produce one change chosen by whoever typed fastest. Neither is what the feature
is for.

### 6.2 Modifier lifetime

Modifiers are **ephemeral**. Each carries a TTL (default 90 s), after which the
rig reverts to the active base profile.

**Critical: the TTL timer lives in TouchDesigner, not in the sidecar.**

If the sidecar's job were "send a revert later", then a sidecar crash leaves the
rig stuck in whatever the last audience change was — the alarm riding the broken
path, exactly the failure mode from the fail-loud rule. Instead, TD arms a Timer
CHOP on each modifier; `onDone` fires once and calls `apply_profile(base)`.
**The revert survives the death of everything upstream of it.**

Freeze-safe: a Timer CHOP `onDone` fires once per TTL, not per frame.

---

## 7. Thomas's override

### 7.1 Priority model

| Level | Source | Effect |
|---|---|---|
| 0 | **Kill switch** | Audience disabled, instant revert to known-good. Latched until explicitly re-armed. |
| 1 | **Thomas — OSC / TouchOSC (port 7400)** | Applies immediately, sets base profile, opens a **90-second audience lockout**. |
| 2 | **Thomas — chat/voice command** | Same as level 1. Convenience path, same authority. |
| 3 | **Audience vote** | Applies only if levels 0–2 are quiet. |

The 90-second lockout after any manual change matters: when Thomas reaches for
the iPad mid-set, he's making a decision about *this drop*. The audience should
not undo it four seconds later.

### 7.2 The kill switch — defence in depth

One button, two independent effects, because one of them must work even if the
other's process is gone:

1. **Sidecar side:** `audience_enabled = False`. Stops emitting verbs.
2. **TD side:** a latch the OSC handler checks. **Even a runaway or compromised
   sidecar cannot drive the rig while the latch is set.**

Plus: `apply_profile(base)` fires immediately, returning to a known-good look
within one cook.

Surfaces: a big red TouchOSC button on `/dj/audience/kill`, a sidecar CLI/hotkey,
and — the true last resort — quitting the sidecar process, after which the TD-side
TTL timers (§6.2) return the rig to base within 90 s on their own.

**Test the alarm, not just the happy path.** Phase 1's acceptance criterion is
killing the sidecar mid-modifier and *observing* the auto-revert, not reasoning
that it should happen.

### 7.3 Thomas's own input channel

Reuse the existing OSC contract. Add:

```
/dj/audience/kill      1        -- latch off + revert to base
/dj/audience/arm       1        -- clear the latch
/dj/audience/base/<PROFILE>     -- set base (what modifiers revert TO)
/dj/audience/<VERB> <intensity> -- Thomas firing a verb directly
```

All of these extend `parse_osc_profile_message()`, inheriting its ignore-by-default
posture and its existing test file.

A **voice** channel (Thomas speaking → Whisper → same verb table) is a natural
Phase 5+ addition — the whitelist is already source-agnostic, so it's an ingestion
adapter, not new safety surface. Not v1.

---

## 8. Interaction flair (optional)

### 8.1 On-screen acknowledgment

*"@thibor triggered STROBE_ACID"* rendered as a TD Text TOP over the composite for
~4 seconds.

⚠️ **This is a second injection surface, and it is easy to miss.** The username is
attacker-controlled and the acknowledgment puts it on a public broadcast.

Required handling:
- **Render the verb name from our own constant table, never from model output.**
- Username: strip to `[A-Za-z0-9_ -]`, cap 20 chars, run through the same
  moderation pass as message text, plus a display-name banned list.
- A user in the mute list triggers the verb but is never named on screen.
- **Never render message text.** Only `@name` + our own verb constant.

Freeze-safe: a Text TOP parameter write on OSC arrival, plus a Timer CHOP to clear
it. No per-frame work.

### 8.2 ElevenLabs voice shoutouts

*"Shoutout to thibor — going acid green!"*

This is the **highest-risk piece of flair in the whole design** — TTS speaking
attacker-influenced text aloud on a public stream, where it is far harder to
retract than a text overlay.

Constraints if built:
- **Template-only.** `f"Shoutout to {name} — {VERB_PHRASE[verb]}"`, where
  `VERB_PHRASE` is our constant table. The only variable slot is the sanitized
  username. **Message text is never spoken, ever.**
- Stricter name sanitization than §8.1 — allowlist charset, and skip TTS entirely
  for names that don't survive it cleanly.
- **Off by default**, opt-in per set, covered by the kill switch.
- Synthesize in the **sidecar**, write a WAV, have TD play the file. A slow or
  hanging TTS API call must never be able to reach the cook thread.
- Rate limit hard — 1 shoutout per 5 minutes. It's a garnish; more than that and
  it eats the set.

---

## 9. Phased build plan

Each phase is independently shippable and independently abandonable. Phases 1–3
are gated by **dry-run mode** — the pipeline logs what it *would* do and changes
nothing — so the whole thing can be run against a real live set before it is ever
allowed to touch the rig.

| Phase | Scope | Exit criterion | Days |
|---|---|---|---|
| **0. Spikes** | Verify the five `.tox` components' real functions. Get a YouTube API key; pull `activeLiveChatId` off a real stream; **confirm live-chat quota costs in Cloud Console**. Email Kniteforce re: Embedded Chat webhook. | Chat messages printing to a terminal from YouTube. Quota numbers confirmed. Kniteforce answer in hand (yes/no/pending). | 1–1.5 |
| **1. Safety core** ★ | `apply_profile_object()`. Verb table + `derive()` + clamps. OSC verb extension. TD-side TTL timers. Kill-switch latch (both sides). **No chat, no LLM** — driven by a local test script. Full pytest coverage. | Every verb applies and auto-reverts. Killing the sidecar mid-modifier **observably** reverts within TTL. Tests green. | 3–4 |
| **2. Ingestion** | YouTube reader (`streamList` + `list` fallback), normalizer, dedupe, reconnect. Prefilter + moderation + rate limits. **Dry-run only.** | Runs a full 3-hour set logging intents, touching nothing. Zero crashes, zero dropped reconnects. | 2–3 |
| **3. Interpreter** | LLM classifier, structured enum output, validator gate, confidence floor. Still dry-run, then armed. | Review the Phase 2 log: ≥90% of `!vj` messages classified sensibly, zero off-enum outputs. Then arm. | 1.5–2 |
| **4. Arbitration** | Vote window, intensity escalation, budgets, override priority + lockout. | 100 synthetic messages in 20 s → exactly one change, and it's the modal verb. | 1.5–2 |
| **5. Flair** | On-screen acknowledgment (sanitized). ElevenLabs shoutouts, opt-in, off by default. | Overlay renders and clears. TTS speaks template-only text. Both covered by kill switch. | 1.5–2.5 |
| **6. Kniteforce** | Webhook receiver on the VPS + HMAC verification, or socket.io client. **Contingent on §2.2.** | Kniteforce messages appear as `ChatMessage` records, indistinguishable downstream. | 1–2 |

**Total: 11.5–17 dev-days.** Phase 1 is the one that must not be rushed — it is
the entire safety argument, and every later phase inherits it.

**Suggested first real-world outing:** run Phases 0–2 in dry-run across a
complete live set. The Phase 2 log is the honest input to deciding whether the
verb table is right, before a single audience message has moved a pixel.

---

## 10. API keys and running cost

| Service | Key | Needed from | Cost |
|---|---|---|---|
| **YouTube Data API v3** | API key (Google Cloud project) | Phase 0 | Free. 10,000 units/day. OAuth2 only if ever posting to chat — not in v1. |
| **OpenAI — moderation** | `OPENAI_API_KEY` | Phase 2 | **Free.** Does not count toward usage limits. |
| **OpenAI — interpreter** | same key | Phase 3 | Small-model classification, batched per vote window. A 4-hour set ≈ 700 windows ≈ **well under $1**. Negligible. |
| **ElevenLabs** | `ELEVENLABS_API_KEY` | Phase 5 | **The only real cost.** Per-character. Rate-limited to 1 shoutout / 5 min ≈ 48 short clips per 4-hour set. Budget per their current tier pricing. |
| **Embedded Chat** | HMAC shared secret | Phase 6 | Configured by *Kniteforce*, not Thomas. May require their Pro tier. |

All keys in `.env`, never committed — per the standing cross-project rule.

---

## 11. Open questions

1. **Kniteforce webhook — will the station say yes?** Blocks Phase 6 only.
   Everything else is unaffected.
2. **What are the five `.tox` components actually doing?** The §3.1 table is
   assumed, not verified. Phase 0 resolves it. If `chatGPT_o1.tox` turns out to
   wrap something the sidecar can't easily replicate, revisit §3.1 — but the
   sidecar argument stands on the freeze discipline regardless.
3. **`!vj` prefix or open keyword matching?** Recommend starting with the prefix.
   Reversible in one config line.
4. **Verb granularity.** 22 verbs is a first guess. The Phase 2 dry-run log will
   show what people actually ask for — expect to cut some and add others.
5. **Does the audience-visible latency feel right?** A 20-second vote window
   means up to 20 s between typing and seeing a change. That may read as broken.
   Mitigation: acknowledge *instantly* on screen (§8.1) even though the visual
   change lands at the end of the window. Worth testing early.
6. **Verify the live-chat quota figures.** The 5-units/call number is
   widely-cited but absent from Google's current published table. Phase 0.

---

## 12. Sources

- [LiveChatMessages: list — YouTube Live Streaming API](https://developers.google.com/youtube/v3/live/docs/liveChatMessages/list)
- [LiveChatMessages: streamList — YouTube Live Streaming API](https://developers.google.com/youtube/v3/live/docs/liveChatMessages/streamList)
- [Determine quota cost — YouTube Data API](https://developers.google.com/youtube/v3/determine_quota_cost)
- [Moderation — OpenAI API docs](https://developers.openai.com/api/docs/guides/moderation)
- [OpenAI Omni Moderation: How to Filter Text & Images for Free](https://www.analyticsvidhya.com/blog/2026/05/openai-omni-moderation/)
- [Embedded Chat — drop-in social chat for any website](https://www.embedded-chat.com/)
- [Kniteforce Radio](https://kniteforce-radio.com/) — chat platform identified by direct inspection of the live page (iframe `embedded-chat.com/room/chat/?hash=292041`, project token `9461`, Socket.IO transport, `ROOM_READ_TOKEN` global), 2026-08-06.
