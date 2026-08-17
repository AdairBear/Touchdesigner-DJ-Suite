# HIVE bring-up — the ordered runbook

> **Status as of 2026-08-17.** HIVE is built and unit-tested (757 tests green)
> and has **never been run against any of its three live systems**: OpenAI,
> the YouTube Live Chat API, and TouchDesigner. The remaining work is
> *integration*, not development.
>
> This document is the ordering. For what each component *is* and every flag it
> takes, read [`audience_chat_bridge_runbook.md`](audience_chat_bridge_runbook.md);
> this one does not repeat it. For why the architecture is shaped the way it is,
> read [`research/audience_interactive_graphics_scope.md`](research/audience_interactive_graphics_scope.md).

## How to read this

Each step has a **gate**: something that must be true before the next step is
allowed to start. The gates are the whole value of the ordering — every one of
them buys down a risk that is expensive to discover one step later, and most of
them are cheap to check.

Steps are marked:

| Mark | Meaning |
|---|---|
| 🤖 | Can be done from a terminal by an agent. No live system, no money. |
| ✋ | **Thomas's hands.** OAuth consent, paid API calls, the live TouchDesigner network, the iPad, the show. Do not attempt these unattended. |

**Two absolute rules for anyone (or anything) working this list:** no live show
and no paid API calls without Thomas saying so, in that moment, for that step.

---

## Step 0 — Get it off one disk 🤖 ✅ DONE 2026-08-17

The branch `feat/touchosc-generator-channels` was unpushed and carried the HIVE
chat commits stacked under its TouchOSC work, plus two untracked design docs.
On a machine with a failing SSD that is one bad sector from being the whole
feature.

- `feat/touchosc-generator-channels` → pushed, 24 commits.
- `docs/research/audience_interactive_chat_graphics.md` and
  `…_graphics_scope.md` → committed and pushed.
- Uncommitted tracker/compositor work → checkpointed to
  `baseline/wip-uncommitted-2026-08-17` **without touching the working tree**
  (`git stash create`, push the resulting object).

HIVE's chat commits also exist independently on `feat/audience-chat-bridge` and
`feat/embedded-chat-source`, both already on origin.

**Gate:** `git log origin/feat/touchosc-generator-channels` shows the HIVE
commits. ✅

---

## Step 1 — Review the classifications offline 🤖 ✅ HARNESS BUILT

```bash
cd python
../venv/bin/python -m chat_bridge.dryrun
```

Free, offline, no key, no network. Runs the real prefilter, the real structural
moderation screen, the real GATE 2 validator and the real arbiter over a 40-line
corpus that mixes ordinary chat with prompt injections, zalgo names, RTL
overrides, an RGB-triple colour request and a 60-second strobe request.

Committed sample output: [`hive_dryrun_sample_output.txt`](hive_dryrun_sample_output.txt).
Current agreement with the corpus: **39/40**.

Writing this harness immediately found two defects that 735 unit tests could
not, both fixed in `076f3ca` — see that commit message. The important one:
**HIVE would have run all night and emitted nothing**, with the log blaming the
model for what was a `sys.path` fault. That is what this step exists to catch,
and it caught it before a key was ever issued.

**Gate:** read the disagreements section at the bottom of the report. A
disagreement is a thing to understand, not to make go away by editing the
corpus.

---

## Step 2 — Review the classifications against the real model ✋ PAID

Everything above tests the *plumbing*. It cannot tell you whether GPT can
distinguish *"more strobes on the kick"* (a request) from *"this track is
strobing my brain"* (a complaint). That is the one question only a paid call
answers, and it is the question the go-live checklist calls *"are the
classifications actually fun?"*.

```bash
export OPENAI_API_KEY=sk-...        # this shell only — never a file in the repo
cd python
../venv/bin/python -m chat_bridge.dryrun \
    --engine openai --i-approve-paid-calls --limit 40
```

One interpreter completion over 40 messages on `gpt-4.1-mini`, plus one free
moderation call. Fractions of a cent. The harness refuses to run without both
the flag and the key, and no environment variable can grant the approval.

**Read `m018` first** — *"make the strobe 10 hz for 60 seconds"*. The offline
engine calls it `NUDGE:FLASH`; the corpus expects `ONESHOT:STROBE_BURST`. Either
is safe (the duration is taken from the ceiling, never from the model, and
that is asserted in `test_chat_dryrun.py`) but it tells you how the model reads
an explicitly dangerous request.

**Gate — and this is a real decision point, not a formality.** If the model
cannot reliably tell a request from a comment about the visuals, **stop and
switch to keyword matching.** The runbook already says this and it is right:
six verbs is genuinely fine keyword territory, and keyword matching is instant,
free, and unjailbreakable. Set a hard monthly spend cap on the key either way.

---

## Step 3 — YouTube OAuth and the quota measurement ✋

Two separate things, both hands-on.

**OAuth.** Consent screen must be **"In Production"**, not "Testing" — a Testing
token expires in 7 days and will die mid-show. Scope is read-only; the bridge
must never be able to post. `docs/audience_chat_bridge_runbook.md` §2 has the
setup.

**The quota measurement, which is the actual risk.** Google's published quota
table **does not document the live-streaming endpoints at all**, so the cost of
`liveChatMessages.list` is genuinely unknown. The scope doc flags a widely
repeated "5 units/poll" figure as undocumented and unverified. The arithmetic:

| Cost per poll | 3-hour stream |
|---|---|
| 1 unit | comfortable |
| 5 units | **dies mid-show** |

So: start the bridge, poll for ~10 minutes, watch the Cloud Console quota
graph, and set `CHAT_BRIDGE_UNIT_COST` to what you actually measure. Do not
carry the assumption forward untested.

**Gate:** a measured number in `CHAT_BRIDGE_UNIT_COST`, and a token that is not
a 7-day Testing token.

---

## Step 4 — Three-hour log-only soak ✋ (start it, then leave it)

```bash
cd python
../venv/bin/python -m chat_bridge --source youtube --dry-run --duration 10800
```

`--dry-run` never opens a socket to TouchDesigner. Real chat, real moderation,
real classification, zero effect on any visuals. Run it against someone else's
live stream or your own test broadcast.

Watch for: memory growth, quota drift against the number measured in step 3,
token still alive at the end, and `interpreter_error` in the log — which after
`076f3ca` genuinely means the model, because the config fault that used to
impersonate it now raises at the first batch instead.

This also produces the log that `--source replay` reads back, so a bad night
can be re-examined offline afterwards.

**Gate:** three clean hours. This is the step that catches the slow failures,
and there is no way to shorten it.

---

## Step 5 — TouchDesigner bring-up ✋ SNAPSHOT FIRST

**Snapshot the `.toe` to `archive/toe/` before anything touches the live file.**
`install_audience_control()` modifies the running project. There is a
project-memory note that the `.toe` needs an explicit Cmd+S to persist, so a
change that looks applied may not survive a restart — and one that does may not
be revertible without the snapshot.

Then bring up the OSC path with the visuals still safe: send a single audience
message and confirm it arrives at `/dj/audience/...` and moves the right
`fx_audience` channel. The airlock it lands in is the same
`parse_osc_profile_message` whitelist the TouchOSC buttons have used all along
— that is the architectural bet, and this is where it gets its first real test.

**Gate:** a snapshot exists in `archive/toe/`, and one audience message visibly
moves one parameter.

---

## Step 6 — The control surface on the iPad ✋

The layout is already generated and on the Desktop, and **PANIC, CROWD ON,
CROWD GAIN and LOCK LOOK are all on it** — regenerate with
`./venv/bin/python python/make_touchosc_layout.py` if in doubt. AirDrop
`DJ_Profiles.tosc` to the iPad. Host and send port (**7400**, UDP) are *not*
stored in the layout; enter them once per device.

Test on the actual iPad, before doors, in this order:

1. **PANIC** — the only red control on the page. Momentary. Confirm it stops
   audience effect and holds the room for `PANIC_LOCKOUT_S` (300 s).
2. **LOCK LOOK** — the graduated response, new in `96a052d`. A toggle: the room
   keeps NUDGE and ONESHOT and loses PROFILE. Confirm it *holds* when pressed,
   rather than clearing on the lift.
3. **CROWD ON** — toggle, ships on. Confirm off actually silences the room.
4. A profile button — confirm it arms the 60-second operator lockout.

If the full layout will not render, `DJ_Profiles_profiles_only.tosc` is the
fader-free fallback and the set still has its profile buttons. `FADER` is the
one node type never verified against an authentic editor file.

**Gate:** PANIC works, on that iPad, with the show rig running. Nothing below
this line happens until it does.

---

## Step 7 — One supervised live show ✋

One. Supervised. A hand on the iPad the whole time, and a "flashing lights"
notice in the stream description.

Start with `LOCK LOOK` **on** — the room gets nudges and one-shots and cannot
vote the look out from under you. That is the lowest-blast-radius configuration
in which the audience still visibly affects the visuals, which is the whole
point of the feature. Unlock it when it feels safe, not before.

Afterwards: keep the NDJSON log. It replays.

---

## What is deliberately not in this list

- **Kniteforce as a second source.** Blocked on a volume check (scope §1.2) and
  on it being a third party's room. YouTube-only loses nothing.
- **The ack overlay and TTS shoutouts.** The only paths where audience-authored
  *characters* reach the broadcast. The sanitizer they need is built and tested;
  the Text TOP and the ElevenLabs route are not.
- **Anything that lets the audience reach a kill switch.** There is no OFF verb
  and there is not going to be one. PANIC is Thomas's, and nothing else's.
