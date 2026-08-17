# Audience-Interactive Chat → Graphics

**Design scope document. No code in this pass.**

Viewers in YouTube Live chat (and, pending the finding in §1.2, Kniteforce Radio
chat) type plain English — *"make it rain acid green"*, *"more strobes on the
kick"* — and the DJ_Graphics rig responds. The audience becomes the VJ. Thomas
keeps a hand on the wheel in both directions: he can override at any moment, and
one button returns the rig to a known-good look.

Status: **design only.** Nothing here is built. Effort, phasing and the keys
needed are in §7–§9.

---

## 0. The one architectural decision everything else follows from

**The audience never touches TouchDesigner. The audience votes on an enum.**

The existing rig already has exactly the right seam for this, and it was built
for a different reason:

```python
# touchdesigner/scripts/osc_profile_control.py
def parse_osc_profile_message(address, args) -> Optional[str]:
    ...
    return name if name in gp.PROFILES else None      # <- closed whitelist
```

`parse_osc_profile_message` is a pure function that maps an arbitrary UDP packet
to *either a name that exists in the registry, or None*. It is already unit
tested against garbage input (`test_unrecognised_addresses_ignored`,
`test_unknown_string_argument_ignored`, `test_out_of_range_index_ignored`). It
already fails closed. Built for TouchOSC buttons — but it is a general-purpose
untrusted-input airlock, and it is the correct place to terminate a public chat
feed.

So the whole system is: **turn English into a symbol from a closed set, then
push that symbol through the airlock that already exists.** Everything in §2 and
§3 is machinery in service of that one sentence.

### The layer diagram

```
YouTube Live Chat API ─┐
                       ├─► chat_bridge.py  (external process, its own venv)
Kniteforce feed ───────┘        │
                                │  ┌──────────────────────────────────────┐
                                ├─►│ 1. INTAKE    normalize, dedupe, cap  │
                                │  │ 2. MODERATE  OpenAI omni-moderation  │
                                │  │ 3. PREFILTER cheap regex gate        │
                                │  │ 4. INTERPRET LLM → JSON enum ONLY    │
                                │  │ 5. VALIDATE  reject anything off-list│
                                │  │ 6. ARBITRATE vote window + cooldown  │
                                │  └──────────────────────────────────────┘
                                │            │
                                │            ▼  ~1 decision per 30–60 s
                                │      pythonosc SimpleUDPClient
                                ▼            │
                          logs/ + state      ▼
                                    ┌────────────────────┐
                                    │ TD  OSC In DAT 7400│  <- EXISTING
                                    │ osc_profile_handler│  <- EXISTING (extended)
                                    └────────────────────┘
                                             │
                            ┌────────────────┴──────────────────┐
                            ▼                                   ▼
                   apply_profile('STROBE_ACID')      fx_audience Constant CHOP
                   (existing, whole-look)            (new, bounded scalars)
                            └────────────────┬──────────────────┘
                                             ▼
                            existing fx_* chain, parameter EXPRESSIONS only
```

This mirrors the pattern the repo already uses twice: `movement_tracker.py` is
an external process that sends OSC to port 7000; TouchOSC sends OSC to 7400.
The chat bridge is the third external OSC producer, launched by
`system_launcher.py` alongside the others. **No network I/O runs on TD's cook
thread.** That is a freeze-safety decision, and it is why the interpreter does
*not* live in `chatGPT_o1.tox` (see §6).

---

## 1. Chat ingestion

### 1.1 YouTube Live Chat

**Verdict: use the official API. The quota math works, and the stability is worth
the one-time OAuth setup for something running live in front of an audience.**

#### The endpoint

`liveChatMessages.list` still exists and is not deprecated — but as of a
**2025-07-14** docs update, Google now points at
**`liveChatMessages.streamList`** instead: a *server-streaming* connection that
pushes messages as they arrive rather than being polled. Their stated reason is
exactly ours — it "reduces the need for constant polling and helps to avoid
exceeding your quota."

One unresolved risk: `streamList` reads as gRPC-flavoured (its errors are gRPC
codes — `NOT_FOUND (5)`, `RESOURCE_EXHAUSTED (8)`), and it is **unverified
whether the Python `google-api-python-client` exposes it cleanly.** Phase 0 must
test this. The design does not depend on the answer: the bridge's ingestion
layer is written behind a `ChatSource` interface, so `streamList` and polled
`list` are two implementations of one seam, and the fallback is a config flag.

Get the `liveChatId` **once at startup**, not per poll:
`liveBroadcasts.list(part=snippet, mine=true, broadcastStatus=active)` →
`snippet.liveChatId`. This needs no hardcoded video ID, so the bridge finds
whatever stream is live. (Alternative:
`videos.list(part=liveStreamingDetails, id=…)` → `activeLiveChatId`, verified at
1 unit, but needs the ID up front.)

#### Quota — and an honest gap

Verified from Google's quota-cost page (last updated 2026-06-01):

- Default allocation is **10,000 units/day** for all endpoints combined, reset
  at midnight Pacific.
- Every `list` method in the published table costs **1 unit**.
- Since ~2026-06-01 `search.list` and `videos.insert` have their own separate
  100/day buckets and no longer draw on the 10,000. Irrelevant to us, but it
  means older blog arithmetic is stale.

**The gap: the quota table does not list the live-streaming endpoints at all.**
The page claims live-streaming methods are included, then jumps from
`i18nRegions` straight to `members` — no `liveChatMessages`, no `liveBroadcasts`.
This is a live documentation defect, not something the research missed. **Treat
any number a blog post quotes for `liveChatMessages.list` as unverified.**

So the arithmetic is done both ways. A 3-hour stream is 10,800 s:

| Cadence | Calls | @ 1 unit | @ 5 units |
|---|---|---|---|
| every 5 s | 2,160 | **2,160 — 22% of quota, ~4.6 streams/day** | 10,800 — **over budget, dies at ~2h47m** |
| every 2 s | 5,400 | 5,400 — 54%, fits | 27,000 — nowhere close |

If it's 1 unit (most likely, since every other `list` is), 5-second polling for a
3-hour show is comfortable with room for reruns. If it's 5, you'd be riding the
ceiling and a long set would fail *mid-show*. **Phase 1 does not exit until the
real cost is measured** — the Cloud Console quota graph shows it after ~10
minutes of polling. That measurement is a gate, not a nice-to-have.

`pollingIntervalMillis` comes back on every response and is the cadence Google
wants. Its documented meaning is only "wait this long before polling again" —
there is **no documented typical value or floor**, so the widely-repeated
"~5000 ms" is unverified. Enforcement is real: polling faster than YouTube's
refresh rate returns `RESOURCE_EXHAUSTED (8)`. **Honour the returned value as a
floor; never hardcode an interval.**

#### Auth — OAuth, and the 7-day trap

An API key is **not** sufficient; live chat is user-scoped. Read-only access
needs OAuth 2.0 with scope **`youtube.readonly`**. (`youtube.force-ssl` is only
needed if the bridge should ever *post* into chat — it shouldn't, so don't grant
it.)

> **⚠ The single most important operational detail in this document.**
>
> A Google Cloud OAuth consent screen left in **"Testing"** publishing status has
> **all its refresh tokens revoked by Google after exactly 7 days.** Set the
> bridge up on a Tuesday and it is dead before the following weekend's show —
> and it fails at the worst possible moment, silently, as an auth error at
> stream start.
>
> **Fix: set the consent screen to "In Production" immediately at setup.**
> Refresh-token lifetime then becomes indefinite. Full Google verification (with
> security audit) is only required to distribute an app *publicly* or to use
> restricted scopes; as the sole user of your own app you click through an
> "unverified app" warning once and never see it again.

This belongs on the go-live checklist, and the bridge should additionally
**fail loud** on token refresh failure — an alert, not a logged shrug — since a
dead token is otherwise indistinguishable from a quiet chat.

#### Quota increase — skip it

The Audit and Quota Extension Form is the only route past 10,000 units.
Turnaround is reported anywhere from weeks to months and requires justifying the
application against the YouTube API ToS. For a solo creator's visuals rig the
odds are poor, the wait is unbounded, and per the arithmetic above you almost
certainly don't need it.

#### Unofficial libraries — one survivor, use it only as an escape hatch

| Library | Status |
|---|---|
| **`pytchat`** | **Archived, read-only. Last push 2021-07-24.** Five years dead. Do not build on it. |
| **`chat-downloader`** | **Alive** — last push 2025-11-05, 1.2 k stars. PyPI (0.2.8, 2023) is stale; **install from git.** Best unofficial option. |
| `youtube-chat` | TypeScript/Node, not Python. Wrong stack. |
| `pytchat` forks | One-person forks, no community. Not a dependency to take. |

These scrape the InnerTube `get_live_chat` endpoint: no quota, no OAuth, no
Cloud project, no token expiry, works on any public stream. But they are
unofficial, ToS-grey, and break without warning when YouTube changes the
continuation-token format — historically failing as "worked last month, returns
empty today." **That is a bad property for something you depend on live.**

**Recommendation:** official API primary; `chat-downloader` (from git) wired
behind a `--source=fallback` flag as a documented escape hatch. It needs no
auth, which makes it genuinely valuable in exactly one scenario — a token dies
ten minutes before doors. Keep it working, don't make it the default.

#### Setup sequence (for the go-live checklist)

1. Cloud project → enable **YouTube Data API v3**.
2. OAuth client, type **Desktop app**, scope **`youtube.readonly`**.
3. **Consent screen → "In Production."** Click through the unverified warning.
4. `liveBroadcasts.list(mine=true, broadcastStatus=active)` once at startup →
   cache `liveChatId`.
5. Try `streamList`; fall back to `list` honouring `pollingIntervalMillis`.
6. **Watch the Cloud Console quota graph during stream one** to pin the real
   per-call cost, then set the bridge's hard stop below it.

### 1.2 Kniteforce Radio — feasibility finding

**Verdict: the native chat is CLOSED. But Kniteforce mirrors to YouTube Live,
and that mirror is ingestable with the machinery Phase 1 already builds.**
Conditional on one thing Thomas has to check himself — see "the open question."

#### What it actually is

Kniteforce Radio (`kniteforce-radio.com`, also `kniteforceradio.com`) is a
custom Laravel + Vue SPA. Audio is Airtime Pro / Icecast
(`kniteforce.out.airtime.pro/kniteforce_a`). The `/see` page puts a **YouTube
live video and an on-site chat widget side by side.**

The chat is **`embedded-chat.com`** — a third-party drop-in widget. This is read
straight out of their shipped JS bundle, not inferred:

```js
e.src = "//d2yy16lkdmfg04.cloudfront.net/resource/chat.js";
window.embeddedChatAsyncInit = function () {
    embeddedChat.setRoom("www.kniteforce-radio.com/"),
    embeddedChat.init("9461")            // project token
}
```

It is **not** Discord, Mixlr, Twitch, Chatango, Cbox, Minnit, Arena.chat or
Facebook — zero matches for any of those across the site's bundles, and no
Discord invite linked anywhere on the site. *(Caveat: their Twitter/Facebook
profiles weren't opened, so this proves "no Discord is linked from the radio
site," not "no Discord exists.")*

#### 🚩 Why the native chat is a dead end

`embedded-chat.com` advertises HMAC-signed webhooks and JWT auth on paid plans —
but `embedded-chat.com/api/` is behind a login wall and **everything is scoped to
the room owner's account.** There is no public read endpoint, no polling API, no
bot interface. Configuring a webhook needs Kniteforce's own admin credentials.

**This is the flag: Thomas cannot ingest the native Kniteforce chat without
Chris Howell's cooperation.** Two options, in order of sanity:

1. **Ask Chris** to add a webhook pointing at a tunnel (or hand over a
   read-scoped token). A social problem, not a technical one — and the clean fix.
2. Reverse-engineer the iframe's socket transport. Undocumented, fragile,
   ToS-risky, and it will break silently. **Not recommended.**

#### ✅ The viable path: the YouTube mirror

Verified live during the research:

- Channel **"Kniteforce Revolution Official"** (`UC26-k5ZvVbKXU4V3aII6UkA`)
- `GET https://kniteforce-radio.com/api/stream-status` → `{"live":true,
  "videoId":"…"}` — **unauthenticated plain JSON, no key**
- The watch page carries `liveChatRenderer` + `conversationBar`, i.e. **live chat
  is enabled** on the mirror

So the pipeline is two steps and needs no gatekeeper:

1. Poll `/api/stream-status` for the current `videoId` (or use the websocket
   below to get it pushed).
2. Feed that `videoId` into the same `ChatSource` interface Phase 1 builds.

**Important difference from §1.1: Thomas does not own that channel.** For a
*public* stream's chat, the official API needs only an **API key** —
`videos.list(part=liveStreamingDetails, id=VIDEO_ID)` → `activeLiveChatId`, then
`liveChatMessages.list`. No OAuth, no ownership, none of the 7-day refresh-token
problem. Kniteforce ingestion is *simpler* to authenticate than his own channel.

It does, however, draw on **the same 10,000 unit/day bucket** as his own stream.
Two concurrent chat feeds double the burn. Since the per-call cost is
undocumented (§1.1), this makes the Phase 1 measurement more load-bearing, not
less. Mitigation if quota gets tight: poll the Kniteforce feed at a slower
cadence than his own — the audience there is secondary.

#### Two corrections to the raw research

Worth recording, because both would have caused real problems:

- **The Kniteforce research recommended `pytchat` for reading the mirror. Do not
  use it.** The parallel YouTube research established `pytchat` has been
  **archived and read-only since 2021-07-24**. Use `chat-downloader` (from git)
  if an unofficial reader is wanted, per §1.1.
- It also quoted **"5 units/poll"** for `liveChatMessages.list` as fact. That
  number is **not documented anywhere** — Google's quota table omits the
  live-streaming endpoints entirely (§1.1). Treat the quota arithmetic in this
  section as provisional until Phase 1 measures it.

#### 🎁 Bonus find — a free now-playing feed

Unrelated to chat, but directly useful to the rig. The site runs **Laravel Echo
over a Pusher-protocol websocket**, and the channels are **public** (no
`private-`/`presence-` prefix, so no auth handshake):

```js
// wsHost + key are redacted here — they are a third party's credentials, and
// this repo is public. Both are client-side values served in plain sight by
// kniteforce.radio's own page JS: re-read them from the Echo/Pusher init block
// in the site bundle when this idea is actually picked up.
wsHost: "<REDACTED — kfr-….osaris.workers.dev>"
key:    "<REDACTED — public Pusher app key from the site bundle>"
Echo.channel("now-and-next").listen("NowAndNextUpdatedEvent",  …)
Echo.channel("schedule").listen("ScheduleUpdatedEvent",        …)
Echo.channel("stream-status").listen("StreamStatusUpdatedEvent", …)
```

A local `pysher` client gets **pushed track changes in real time** — live
artist/title into TouchDesigner, and instant notification when a new stream goes
live (which removes the need to poll `/api/stream-status` at all). That is a
genuinely nice on-screen "NOW PLAYING" overlay for near-zero effort, and it is
*not* audience input, so it carries none of the §2 trust burden.

Filed as a separate, optional idea — not part of this build.

#### ⚠ The open question only Thomas can answer

**Is the YouTube mirror's chat actually populated?**

The `/see` page puts the on-site embedded chat *right next to* the video, so
Kniteforce regulars plausibly talk there rather than in YouTube's chat. The
research confirmed YouTube chat is **enabled**, not that anyone **uses** it.

> **Action: during a live Kniteforce show, open
> `https://kniteforce-radio.com/see` and compare message volume — left-hand
> embedded chat vs. the YouTube chat.**

- **YouTube chat is busy** → Phase 7 is ~3 h. It is a second `ChatSource`
  implementation with an easier auth story than his own channel.
- **YouTube chat is a ghost town** → the only real path is asking Chris Howell
  for an embedded-chat webhook. That is a conversation, not an engineering task,
  and it should happen *before* Phase 7 is scheduled.

This is why Phase 7 is last and independent: **the system ships YouTube-only and
loses nothing.** Kniteforce is upside, not a dependency.

---

## 2. The interpreter, and its boundary

### 2.1 What the LLM is allowed to emit

The interpreter's job is **classification, not generation.** It takes a batch of
chat lines and returns structured JSON conforming to a schema whose every field
is either a member of a closed enum or a number that gets clamped. It is
physically incapable of expressing "run this shader."

```jsonc
// The ENTIRE output surface. Nothing else is accepted.
{
  "actions": [
    {
      "user":    "<echoed back, used only for ack — never interpreted>",
      "verb":    "PROFILE" | "NUDGE" | "ONESHOT" | "NONE",
      "target":  "<enum member, see below>",
      "amount":  -1.0 .. 1.0,        // only meaningful for NUDGE
      "confidence": 0.0 .. 1.0
    }
  ]
}
```

**The three closed vocabularies:**

| Verb | `target` enum | Source of truth | Effect |
|---|---|---|---|
| `PROFILE` | `UV_RAVE` · `DEEP_LASER` · `STROBE_ACID` · `VAPOR_UV` · `MONO_PULSE` | `dj_graphics_profiles.PROFILES` keys | `apply_profile(name)` — the existing path |
| `NUDGE` | `GLOW` · `FLASH` · `TRAILS` · `SHAKE` · `ZOOM` · `SPEED` | new `fx_audience` CHOP channel names | writes one clamped scalar |
| `ONESHOT` | `STROBE_BURST` · `COLOR_POP` · `WHITEOUT` | new, fixed set | a decaying pulse, self-cancelling |
| `NONE` | — | — | message was not a request; discard |

Colour requests resolve to the **named neon anchors already defined** in
`dj_graphics_profiles.py` — `CYAN`, `MAGENTA`, `ACID`, `PINK`, `VIOLET`, `BLUE`,
`WHITE_HOT`. *"Make it rain acid green"* → the LLM emits
`{verb: "PROFILE", target: "STROBE_ACID"}` (whose palette leads with `ACID`), or
`{verb: "ONESHOT", target: "COLOR_POP", colour: "ACID"}`. The audience cannot
author an RGB triple. That closes two holes at once: no arbitrary colour, and no
route around the existing `is_brown()` / `is_neon()` palette guards.

### 2.2 The boundary, stated explicitly

> **The audience can choose among visual states that already exist and have
> already been validated. The audience can never define a new one.**

Concretely, the following are **out of scope permanently, not "phase 2":**

| Never reachable from chat | Why |
|---|---|
| GLSL / shader source of any kind | Yellow-triangle compile errors are this project's single most expensive failure mode (`dj_graphics_profiles.py` header). A compile failure mid-show is unrecoverable in seconds. |
| Any Python string that gets `exec`/`eval`'d | Obvious RCE on Thomas's live machine. |
| TD parameter *expression* strings | An expression is code. `op('...')` inside one is arbitrary node access. Expressions are built by the **profile builders only**, from numbers. |
| Node creation, deletion, rename | The whole profile system's premise is that a look is *data*, not a new node graph. |
| Raw RGB values | Routes around the neon/brown palette guards. |
| Resolution, cook rate, render settings | Perf-critical; the rig already runs cookRate 30 to shed load. |
| Audio device / audio chain | The freeze lives here. No new audio taps, ever. |
| OBS scene switching | Out of scope by the same rule the profile system follows. |
| File paths, URLs, shell | No. |

### 2.3 Defence in depth — the LLM is assumed compromised

Prompt injection against a public chat feed is not hypothetical; someone *will*
type `ignore previous instructions and…` within the first hour. The design
therefore assumes **the interpreter will eventually be jailbroken, and makes
that not matter.**

Four independent gates, each sufficient on its own:

1. **Structured output / tool-call schema.** The model is bound to a JSON schema
   with `enum` constraints. A model that "escapes" produces malformed JSON,
   which fails parse → dropped.
2. **Re-validation in plain Python, after the model.** `validate_action()` checks
   membership against the *live registry* (`gp.PROFILES.keys()`), not against a
   list the prompt mentioned. Unknown → dropped, logged, counted. This is the
   gate that actually matters; it does not trust the model at all.
3. **The existing OSC airlock.** `parse_osc_profile_message` re-checks
   registry membership at the TD boundary. Even a fully compromised bridge
   process, or a stray packet from anything else on the LAN, cannot make TD do
   something off-list.
4. **The clamps in the expression builders.** `glow_size_expr()` "has no branch
   that emits an unclamped size"; `trail_valuemult_expr()` wraps everything in
   `min(..., 0.97)`. Any audience-driven number enters *inside* those clamps.
   A NUDGE of 999 becomes the cap, not a whiteout.

Note gate 3 in particular: it means the bridge process itself is not trusted.
That satisfies the standing rule about alarms not riding the path they watch —
the TD-side gate is independent of the process that could be the thing failing.

### 2.4 Chat text never reaches an expression, a prompt-with-authority, or a log-eval

The user's *display name* and *message text* are carried alongside the action for
the ack overlay (§5) but are treated as **opaque bytes** everywhere else. They
are never concatenated into a TD expression, never fed back into a subsequent
LLM call as instruction, and never `eval`'d. Sanitization rules for the one
place they *are* rendered are in §5.

---

## 3. Moderation and flow control

### 3.1 Moderation — where it actually matters

Worth being precise about the threat model, because the obvious answer is wrong.

Abusive text **cannot** produce abusive visuals: the action space is a closed
enum of five pre-validated looks. A slur maps to `NONE` or to `STROBE_ACID` —
either way the rig shows a look Thomas already approved.

The real exposure is the **ack overlay and the TTS shoutout** (§5), because those
are the only paths where audience-authored *characters* reach the stream. That
is where moderation is load-bearing.

**Three layers:**

| Layer | Mechanism | Cost | Catches |
|---|---|---|---|
| 0 | YouTube's own chat moderation (owner settings + any mods) | free | the bulk, before it reaches the API |
| 1 | OpenAI **Moderation API** (`omni-moderation-latest`) on message text *and* on display name | **free** | hate / harassment / sexual / self-harm / violence, with per-category scores |
| 2 | Local deny-list + structural checks | free | slurs YouTube misses, zalgo, RTL-override, homoglyph names, excessive length |

Layer 1's free pricing is why moderation runs on *every* message rather than
only on ones that reach the ack path — it costs nothing and gives a per-user
abuse score for §3.2.

**Failure mode is fail-closed.** If the moderation call errors or times out
(300 ms budget), the message is treated as **failed moderation** — its action is
dropped and no ack is rendered. A moderation outage must not become an
open microphone. Consecutive failures raise an operator alert rather than being
swallowed; a silently-degraded moderation layer is precisely the "how would I
find out?" landmine the fail-loud rule exists to prevent.

### 3.2 Rate limiting — the 100-messages problem

Five independent limiters, cheapest first:

| Limiter | Value (starting point) | Purpose |
|---|---|---|
| **Per-user cooldown** | 1 accepted request / **90 s** | one viewer cannot drive the show |
| **Per-user daily cap** | 20 accepted / stream | limits a determined spammer |
| **Global intake cap** | 20 msg/s into the pipeline, bounded `deque(maxlen=500)`, drop-oldest | back-pressure; a raid cannot exhaust memory or budget |
| **LLM batch cadence** | one call per **10 s**, batching everything in the window | bounds cost and API rate |
| **Global action cooldown** | `PROFILE` 60 s · `NUDGE` 10 s · `ONESHOT` 6 s | **this is the seizure/thrash guard** |

The global action cooldown is a hard floor enforced in the bridge *and*
re-checked in TD, for the same reason as §2.3 gate 3.

There is also an **epilepsy/comfort ceiling** that is not negotiable by vote:
`STROBE_BURST` is capped in both frequency (≤1 per 20 s) and duration (≤1.5 s),
and `NUDGE GLOW`/`FLASH` inherit the existing `GLOW_SIZE_HARD_CAP` headroom.
A live stream with flashing visuals has a duty of care here, and the audience
must not be able to vote that away.

### 3.3 Arbitration — the vote window

Polling, batching, moderation and voting all ride the same clock:

```
 t=0                                                          t=30s
 ├─── 10s batch ────┼─── 10s batch ────┼─── 10s batch ────────┤
 │  intake+moderate │                  │                      │
 │  → 1 LLM call    │  → 1 LLM call    │  → 1 LLM call        │
 │  → N actions     │  → N actions     │  → N actions         │
 └──────────────────┴──────────────────┴──────────────────────┘
                                                              │
                                            TALLY: bucket by (verb,target)
                                            winner = max votes, ≥ QUORUM (2)
                                            ties → earliest first request wins
                                            cooldown gate → emit ONE OSC msg
```

**Why a window and not a queue.** A FIFO queue with a cooldown converts a burst
into a slow drip of stale requests — at minute 3 the rig would still be
executing minute 1's chat. Tallying discards staleness for free: 100 messages in
30 s become *one* visual change that reflects what the room actually wants.
The losing buckets are dropped, not deferred.

`NUDGE` actions accumulate differently — same-target nudges **sum then clamp**
(five people asking for more glow is a bigger nudge, up to the cap), rather than
competing. `ONESHOT` bypasses the vote but obeys its own tight cooldown, since a
1-second burst is low-stakes and immediacy is the fun of it.

**Quorum of 2** for `PROFILE` prevents one viewer flipping the whole look; a
single-viewer stream degrades gracefully to "nudges and one-shots only," which
is the right behaviour.

### 3.4 Degradation ladder

| Condition | Behaviour |
|---|---|
| LLM slow / erroring | skip the batch. **Never queue** pending batches — that is the burst-at-recovery bug. |
| Moderation erroring | fail closed (§3.1), alert after 3 consecutive |
| YouTube quota exhausted / stream ends | bridge idles, logs, keeps the last state; visuals stay on the current look |
| Bridge process dies | TD is unaffected — it simply stops receiving packets. The look freezes at whatever was last applied, which is always a validated look. |
| Bridge sends garbage | rejected by `parse_osc_profile_message` |

Note the last two: **every failure mode of the chat system degrades to "the
visuals stop changing," never to "the visuals break."** That is a consequence of
the enum-only design, and it is the main reason to accept the complexity.

---

## 4. Thomas's override

Two requirements, and they pull in opposite directions: his input must always
win, *and* the audience must not feel ignored. Resolved with a lockout window.

### 4.1 The controls

New TouchOSC page, alongside the existing five profile buttons (extend
`python/make_touchosc_layout.py`, which already generates the layout and is
tested against the address list):

| Control | OSC address | Effect |
|---|---|---|
| **PANIC** | `/dj/panic 1` | `apply_profile('UV_RAVE')` · zero every `fx_audience` channel · disable audience for 5 min · clear the vote window. One tap, known-good look, instantly. |
| **Audience ON/OFF** | `/dj/audience/enable 0\|1` | master gate |
| **Audience intensity** | `/dj/audience/gain 0.0–1.0` | global scale on every audience-driven scalar. `0.3` = "they can tint it"; `1.0` = "they're driving." A dial, not a switch. |
| **Profile lock** | `/dj/audience/lock_profile 0\|1` | audience keeps NUDGE + ONESHOT, loses PROFILE votes — the natural setting for a peak-time moment he wants to own |
| *(existing)* | `/dj/profile/<NAME>` | unchanged; now also arms the lockout |

### 4.2 Priority — his action wins, and keeps winning

When any `/dj/profile/*` arrives from TouchOSC, the handler applies it **and**
stamps `audience_lockout_until = now + 60 s`. During the lockout, audience
actions are received, tallied, acknowledged in the log — and not applied. This
prevents the failure everyone hits on their first build: Thomas picks
`DEEP_LASER` for a breakdown, and eight seconds later a pending vote flips it
back to `STROBE_ACID`.

The lockout is a *timer*, not a mode, so it self-clears. He never has to
remember to re-enable anything. PANIC uses a longer one (5 min) because PANIC
means something went wrong.

### 4.3 Two independent kill paths

Per the standing fail-loud rule — an alarm must not ride the path it watches —
the kill-switch does not depend on the bridge being healthy:

1. **Bridge-side gate.** `/dj/audience/enable 0` is also listened for by the
   bridge process, which stops emitting at the source.
2. **TD-side gate.** The extended `osc_profile_handler` keeps its own
   `audience_enabled` flag and *ignores audience-tagged packets when it is
   false* — regardless of what the bridge does. A hung, rogue, or
   still-flushing bridge cannot get through.

Audience-originated OSC therefore uses a **distinct address namespace**
(`/dj/audience/...`) from Thomas's own (`/dj/profile/...`), so the TD handler can
tell them apart and gate only one of them. This is the single most important
detail in §4: if both used the same address, the kill-switch would also kill
Thomas's own control.

### 4.4 Physical fallback

If TouchOSC or the network is the thing that's broken: quitting the
`chat_bridge` process (Ctrl-C, or `system_launcher.py`'s existing cleanup path)
stops all audience input, and the rig continues on its current validated look.
No TD interaction required.

---

## 5. Flair — ack overlay and TTS shoutouts

Both optional, both after the core works, and both are where audience *text*
finally reaches the stream — so both carry the moderation burden from §3.1.

### 5.1 On-screen acknowledgement

> `@raverkid_92 triggered STROBE_ACID`

A Text TOP composited into the existing chain, driven by a Table DAT the OSC
handler writes on each accepted action, with a fade driven by a parameter
expression (same discipline as everywhere else — no per-frame Python).

**Sanitizing the display name** — it is attacker-controlled text going on a
public broadcast:

| Rule | Reason |
|---|---|
| Truncate to 20 chars | layout, and log-flooding |
| Strip control chars, RTL-override (U+202E), zero-width, combining marks >2 | zalgo and text-reversal defacement |
| Whitelist to letters/digits/`_-.` after NFKC normalization | homoglyph impersonation |
| Reject if it fails moderation (§3.1 layer 1) | the name is the payload |
| Render the *verb+target*, never the message text | the message is unbounded; the target is an enum member. **This is the important one** — the on-screen string is `"@" + safe_name + " triggered " + ENUM`, where only one of three parts is variable. |

### 5.2 ElevenLabs shoutouts

`ElevenLabs_0_3.tox` is the right tool. Three constraints:

1. **Templated speech only.** Never speak the message. The spoken string is
   `f"{safe_name} says {friendly_name(target)}"` — one variable, already
   sanitized and moderated. Additionally strip anything that isn't
   pronounceable, and cap at ~40 chars, so a name cannot become a 30-second
   monologue.
2. **The TTS audio must not enter the audio-analysis chain.** This is a hard
   freeze/architecture constraint. `audio_in` is the reactivity source; if
   ElevenLabs output reaches it, the visuals react to their own voice, and worse,
   it means a new audio tap — the thing the profile system explicitly forbids.
   Route TTS to a separate output device → OBS as its own source. **Nothing
   touches `audio_in`.**
3. **Rate-limit hard** — ≤1 shoutout per 90 s, ducked under the music, and
   subject to its own on/off on the TouchOSC page. This is the feature most
   likely to become annoying by minute 40.

`ElevenLabs_0_3.tox` does HTTP from inside TD, which is exactly what
`TDAsyncIO.tox` exists to keep off the cook thread — see §6.

---

## 6. Where each of Thomas's .tox components lands

Straight assessment, including the two that are better used elsewhere:

| Component | Verdict | Reasoning |
|---|---|---|
| **`TDAsyncIO.tox`** | **Required, but only for §5.2.** | It is a hard dependency of `ElevenLabs_0_3.tox` — any HTTP from inside TD must not block the cook thread. If TTS is skipped, this isn't needed. |
| **`ElevenLabs_0_3.tox`** | **Use as-is, Phase 6.** | Right tool for the shoutout. Constraints in §5.2. |
| **`Chat_Agent.toe`** | **Mine it, don't ship it.** | A working reference for the OpenAI request/response plumbing and any callback idioms worth copying into the bridge. Not the live show file. |
| **`chatGPT_o1.tox`** | **Recommend against on the critical path.** | Putting the interpreter inside TD means the LLM call, its retries, and its timeouts all live in the same process as the render. Even with TDAsyncIO, an in-TD interpreter cannot be unit-tested outside TD, cannot be restarted without touching the show file, and can't be killed independently. The repo already has the better pattern — an external process emitting OSC (`movement_tracker.py`). Keep this .tox as the **fallback** if the external bridge proves awkward, and as the fastest way to prototype a prompt in Phase 0. |
| **`face_detector.tox`** | **Out of scope; recommend deferring indefinitely.** | No role in chat→graphics. It would add per-frame CPU/GPU cost to a rig already at `cookRate 30` specifically to shed load. If a "shoutout points at the DJ" flourish is wanted later, it's a separate piece of work with its own perf budget. |

The honest summary: of the five components, **two are on the critical path
(TDAsyncIO + ElevenLabs, and only for the optional flair), one is a reference,
and two are better left out.** The core system is an external Python process
plus an extension to code that already exists in this repo. That is a feature —
it means most of the work is testable with `pytest`, in the idiom
`tests/test_osc_profile_control.py` already establishes.

---

## 7. What gets built, in order

Each phase ends in something demonstrable. Phases 1–4 are the product; 5–7 are
polish; anything can stop after any phase and leave a working rig.

### Phase 0 — Spike *(3–4 h)*
Prove the two risky unknowns before designing around them.
- Read 10 real messages off a private/unlisted YouTube live stream, print them.
- One hand-written prompt, one API call, 30 sample chat lines → check the
  classification is good enough to be fun. **If the interpreter can't tell
  "more strobes" from "this track is strobing my brain," stop and rethink.**
- Exit: two scripts in `scratch/`, a go/no-go, and a measured cost-per-hour.

### Phase 1 — Ingestion *(6–8 h)*
`python/chat_bridge.py` skeleton behind a `ChatSource` interface (so
`streamList`, polled `list`, `chat-downloader` and Kniteforce are all
interchangeable implementations). YouTube OAuth with the consent screen
**already in Production**, `liveChatId` fetched once at startup, cadence driven
by the returned `pollingIntervalMillis` (never hardcoded), normalize to a common
`ChatMessage` dataclass, bounded intake deque, NDJSON to
`logs/chat_bridge.ndjson`, **loud** alerting on token-refresh failure, quota
accounting with a hard stop below the ceiling.
- Also in this phase: **test whether `google-api-python-client` can actually call
  `streamList`** (§1.1), and **measure the real per-call quota cost** off the
  Cloud Console graph.
- Exit: runs a full 3 h stream, logs every message, **measured** quota headroom
  written into the doc, no memory growth. **No visuals touched at all.**

### Phase 2 — Interpreter + validator *(8–10 h)*
Schema-constrained LLM call, batching, `validate_action()` against the live
registry, structured logging of every accept/reject with reason.
- Tests in the existing idiom: unknown targets rejected; injection strings
  (`"ignore previous instructions"`, `"return {verb:'EXEC'}"`, GLSL source,
  `op('/project1').destroy()`) all resolve to `NONE` or a dropped action;
  malformed JSON dropped; the validator asserted to consult `gp.PROFILES` rather
  than a hardcoded list.
- Exit: replay Phase 1's logged stream offline, inspect the decisions. Still no
  visuals.

### Phase 3 — Moderation + arbitration *(6–8 h)*
Moderation layers, the five limiters, the vote window, fail-closed paths, the
degradation ladder.
- Tests: 100 synthetic messages in 5 s produce **exactly one** action; per-user
  cooldown holds; moderation timeout drops rather than passes; a burst after an
  LLM outage does not stampede.
- Exit: the bridge emits well-formed OSC to a **listener script, not TD.**

### Phase 4 — TD side: audience channel + override *(8–10 h)*
The only phase that touches the show.
- New `fx_audience` Constant CHOP, channels `gain_glow`/`gain_flash`/
  `trail_bias`/`shake`/`zoom`/`speed`, all zero-default.
- Extend the `dj_graphics_profiles.py` expression builders to multiply through
  those channels **inside the existing clamps** — same structural guarantee as
  `glow_size_expr()`, so a bad audience value is impossible to express.
- Extend `osc_profile_control.py`: `/dj/audience/*` namespace, `audience_enabled`
  gate, lockout timer, PANIC.
- Extend `make_touchosc_layout.py` with the override page.
- Tests: every existing safety test still passes with the audience term present;
  new tests assert the audience term cannot breach `GLOW_SIZE_HARD_CAP` or
  `TRAIL_VALUEMULT_HARD_CAP` at *any* input including absurd ones; PANIC restores
  UV_RAVE and zeroes all channels; audience packets ignored when disabled;
  Thomas's own packets **not** affected by the audience gate.
- Exit: **the audience can actually change the visuals.** This is the milestone.

### Phase 5 — Ack overlay *(4–6 h)*
Text TOP + Table DAT + sanitizer, with the sanitizer tested against zalgo, RTL
override, homoglyphs, and 500-char names.

### Phase 6 — TTS shoutouts *(4–5 h)*
ElevenLabs via TDAsyncIO, separate audio route, hard rate limit, own kill.
Includes verifying with a scope/meter that TTS is **not** reaching `audio_in`.

### Phase 7 — Second chat source *(3 h, or blocked — see §1.2)*
**Do the volume check in §1.2 before scheduling this phase.**
- If the YouTube mirror's chat is busy: ~**3 h.** A second `ChatSource`
  implementation reading `kniteforce-radio.com/api/stream-status` → `videoId` →
  the same reader Phase 1 built. API-key auth only, no OAuth. Messages carry a
  `source` tag so the vote window can weight or separate the two rooms.
- If it's a ghost town: **blocked on a conversation with Chris Howell**, not on
  engineering. Ship YouTube-only.

### Phase 8 — Soak + dry run *(4–6 h)*
An unattended 3 h run against a real stream with visuals **disabled** (log-only),
to catch quota drift, memory growth, and token expiry. Then one full rehearsal
with a handful of friends in chat trying to break it — including deliberately
trying prompt injection.

### Effort summary

| | Hours |
|---|---|
| Core (Phases 0–4) — audience can drive the visuals | **31–40** |
| Flair (5–6) | 8–11 |
| Second source (7) | 3–10 |
| Soak (8) | 4–6 |
| **Total to show-ready** | **46–67 h** |

Realistically **two R&D weekends for the core**, a third for flair and the soak.
The core is the honest number to plan against; Phase 4 is where the risk is,
because it is the only phase that modifies the live show file's behaviour.

---

## 8. API keys and accounts

| Key | For | Cost | Notes |
|---|---|---|---|
| **Google Cloud OAuth 2.0 client** (client ID + secret + stored refresh token) | YouTube Data API v3 — reading live chat | free within 10,000 units/day | Scope `youtube.readonly`, Desktop-app client. **An API key will not work.** ⚠ **Consent screen must be "In Production" or the refresh token dies after 7 days** — §1.1. |
| **OpenAI API key** | interpreter **and** moderation | interpreter: small (see below); moderation: **free** | One key, two endpoints. |
| **ElevenLabs API key** | shoutouts (Phase 6, optional) | per-character | ~180 shoutouts × ~40 chars ≈ 7 k chars per 3 h stream — comfortably inside a low tier. |
| **Kniteforce platform credential** | Phase 7 | — | Depends on the finding in §1.2. |

All in `.env`, never committed — per the standing cross-project rule. The
refresh token in particular is long-lived and grants access to Thomas's YouTube
account; it belongs in `.env` (or Keychain), and the `.env` must stay gitignored.

**Interpreter cost.** One batched call per 10 s over 3 h = **1,080 calls**. With
the cheap-regex prefilter (§3) most batches are small; assume ~800 input tokens
and ~150 output tokens per call. That is roughly 0.9 M input / 0.16 M output
tokens per stream — a small single-digit dollar figure per stream on a
cheap-tier model, and less if the prefilter suppresses empty batches entirely
(which it will — most chat is not a request). Worth setting a **hard monthly
spend cap** on the OpenAI key regardless.

---

## 9. Risks, honestly

| Risk | Severity | Mitigation |
|---|---|---|
| **Phase 4 destabilizes the show file** | **High** | It is the only phase touching live behaviour. Every audience term goes *inside* an existing clamp; the existing safety test suite must pass unchanged before the new tests are even written. Snapshot the .toe first — the repo already has the `archive/toe/` precedent. |
| Interpreter classification is mediocre and it isn't fun | Medium | Phase 0 answers this for ~4 h before anything is committed. If it fails, the fallback is keyword matching — genuinely fine for six verbs, and it may be *better*: instant, free, and unjailbreakable. |
| **OAuth refresh token dies after 7 days** | **High — and it fails silently, at stream start** | Consent screen to "In Production" at setup (§1.1). Loud alert on refresh failure. On the go-live checklist. |
| Live-chat quota cost is undocumented | Medium | §1.1 — the arithmetic is fine at 1 unit/call, marginal at 5. Phase 1 gate is *measuring* it, not assuming it. |
| `streamList` unusable from the Python client | Low | Ingestion sits behind a `ChatSource` interface; polled `list` is the fallback, `chat-downloader` the second. Tested in Phase 0/1 before anything depends on it. |
| Kniteforce native chat is closed (**confirmed**) | Low | §1.2. The YouTube mirror is the path; Phase 7 is last and independent, so the system ships YouTube-only and loses nothing. |
| Two chat feeds share one 10,000-unit quota | Medium | §1.2. Poll Kniteforce slower than his own stream. Makes the Phase 1 cost measurement more load-bearing. |
| Audience gets bored / spams | Medium | The ack overlay (§5.1) is what makes it feel responsive; without it the audience can't tell it's working. That's an argument for pulling Phase 5 earlier if the first rehearsal feels flat. |
| Photosensitivity | **High, non-negotiable** | §3.2 ceiling. Not voteable. Consider a standing "flashing lights" notice in the stream description regardless. |
| Prompt injection | Low *by design* | §2.3. The reason this is Low is the enum, not the prompt. If the design ever drifts toward free-form output, it becomes High immediately. |

---

## 10. The one-paragraph version

An external Python process reads YouTube Live chat, moderates it for free,
batches it every ten seconds into a single schema-constrained LLM call that can
only emit members of a closed enum, tallies those into one decision per
thirty-to-sixty seconds, and pushes it through the same OSC whitelist the
TouchOSC buttons already use. TouchDesigner gains one new Constant CHOP of
clamped scalars and no new audio taps, no new GLSL, and no code path that
evaluates anything the audience typed. Thomas's own button always wins and arms
a sixty-second lockout; one PANIC tap restores UV_RAVE and mutes the room. Every
failure mode — LLM down, moderation down, quota gone, bridge crashed, packet
garbage — degrades to *the visuals stop changing*, never to *the visuals break*.
