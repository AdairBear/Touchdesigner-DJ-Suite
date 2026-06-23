# Product Registry
Last updated: 2026-04-21

A living master catalog of all active, planned, and completed projects. Updated each session as work progresses.

---

## How to Read This

- **Status**: `Active` | `Paused` | `Complete` | `Planned`
- **Stage**: `Concept` | `Design` | `Building` | `Testing` | `Live` | `Maintaining`
- **Next Action**: The single most immediate thing required

---

## Active Projects

---

### 1. Trident Forge
**Codename**: `trident` / `trident-forge`
**Category**: Algorithmic trading system (personal + potential product)
**Status**: Active
**Stage**: Building

**What it is**: A ghost/live trading pipeline for prop futures (Topstep 25k/50k accounts). Strategies run in ghost mode (paper validation) before being promoted to live. The system includes Pine Forge for strategy development and backtesting, an Open Improvement Brain for persistent memory of all diagnoses/fixes/parameter changes, and a health monitor that validates live performance against backtest expectations.

**What's working**:
- Ghost orchestrator live on VPS (9 agents: SIL Crusher, MNQ GMR, MGC GMR, Lucid Launcher, Lucid Cruiser, Avellaneda, Sanos iFVG across ghost25k/ghost50k/live variants)
- Conflux Engine (Databento live feed → relay) deployed and running
- TradersPost webhook integration via traderspost-mcp
- Open Improvement Brain (dual memory: Machinery Memory + Market Memory architecture designed)
- Trident Forge UI: all design decisions finalized — dark navy + purple, React/TypeScript/Vite/Tailwind, VPS at forge.themostboringdomain.app

**What's left**:
- [ ] UI scaffold — Vite + React + Tailwind setup, sidebar nav, first agent view shell
- [ ] Historical trade data persistence (SQLite trades.db with session-tagged schema)
- [ ] Hermes bridge: Redis `system:alerts` → Telegram (agents/hermes_bridge.py)
- [ ] Invariant-based watchdog (monitors data-flow correctness, not just process liveness)
- [ ] Exit events persisting to events.db (currently 0 trade.exit rows)
- [ ] Live account connection (blocked on manual VPS SSH → forge_signals.db ratio verification ≥ 0.95)
- [ ] MGC contract roll (MGCM2026 → MGCQ2026) — verify status
- [ ] Market Memory layer (regime states, calendar effects, session ATR baselines)
- [ ] Per-strategy terminal panels with Market Memory + Machine Memory in UI

**Next action**: Build UI scaffold — Vite + React + Tailwind, sidebar nav with agent roster, first agent view shell

**Blocked on**: Manual VPS SSH to verify entry/exit ratio before live account connect

**Connected projects**: Relay, traderspost-mcp

---

### 2. Relay (prop_futures_relay)
**Codename**: `relay`
**Category**: Trading infrastructure / VPS orchestration
**Status**: Active
**Stage**: Live

**What it is**: The VPS-deployed trading orchestrator running on 144.126.208.223. Hosts the ghost orchestrator on port 8100, relay on port 8001. Manages all 9 ghost strategy agents and handles signal routing from Databento → strategies → TradersPost webhooks.

**What's working**:
- All 9 ghost agents confirmed live and healthy post April 12 bug fixes
- Conflux Engine (Databento Live) running: SIL.c.0 + MNQ.c.0 + MGC feeds
- Telegram bot integration (/conflux status, on, off commands)
- Entry events persisting to events.db

**What's left**:
- [ ] Exit events not persisting to events.db (blocks all per-strategy P&L aggregation)
- [ ] Hermes bridge (Redis → Telegram alerts) — does not exist yet
- [ ] forge_signals.db ratio verification (manual SSH required)
- [ ] Live account connect decision (pending ratio verification)
- [ ] Prefill signal entry_price=0.0 bug (position manager not seeded from replay bars)
- [ ] "Could not seed position state" on restart (in-flight positions lost)

**Next action**: Manual SSH → pull forge_signals.db → verify entry/exit ratio ≥ 0.95 → decide on live connect

**Blocked on**: Thomas must do this manually (SSH access from scheduled tasks not available)

**Connected projects**: Trident Forge, traderspost-mcp

---

### 3. TD-DJ-Suite
**Codename**: `td-dj-suite`
**Category**: Creative / Live performance AV system
**Status**: Active
**Stage**: Testing

**What it is**: A real-time generative visual system for live 150-180 BPM Jungle/Breakbeat DJ sets. Multi-person body tracking (up to 4 people via MediaPipe) + audio analysis → OSC → TouchDesigner → fire aura generative visuals → Spout/NDI → OBS → live stream. Architecture: External Python → OSC → TD at < 100ms total latency.

**What's working**:
- Python movement tracker (MediaPipe pose detection → OSC on localhost:7000)
- Multi-person tracking (1-4 people, color-coded)
- Body segmentation mask via mmap
- Audio chain (PreSonus Studio 1824c detected, bass/mid/high values arriving)
- Fire aura GLSL shader (10 parameterized uniforms)
- OBS automation (obs-websocket-py)
- Test suite (45 tests)

**What's left**:
- [ ] **Thursday 2026-04-23 16:00**: Scripting session (scheduled) — writes all CHOP scripts, normalization, beat detection, transient router, geometry instancing, procedural animation, OBS WebSocket TD integration
- [ ] **Friday 2026-04-24 12:00**: Testing session (scheduled) — wires everything live, full system test
- [ ] Venv rebuild (corrupted hardcoded paths)
- [ ] Math CHOP normalization (MediaPipe raw -0.30 to 1.20 → 0.0 to 1.0)
- [ ] madmomTD (ioannismihailidis/madmomTD) — AI beat detection for 160+ BPM syncopated patterns
- [ ] Breakbeat transient routing: Kick → Twist SOP, Snare → Noise TOP, Bass → LFO CHOP
- [ ] Geometry instancing pipeline: Tube SOP → Twist → SOP to CHOP → CHOP to TOP (RGB, Fit to Square) → Geometry COMP
- [ ] Procedural animation: Swell (LFO → scale), Pulse (Noise → position), Flip (Kick → 180° orientation)
- [ ] OBS double-image fix (suspected duplicate Syphon source)
- [ ] TouchOSC manual override layer (v2 feature, post-Friday)

**Next action**: Thursday 4PM scripting session (scheduled — no action needed)

**Connected projects**: Open Orchestra (TouchOSC is relevant to both)

---

### 4. Open Orchestra
**Codename**: `open-orchestra`
**Category**: Music technology / New plugin product category (DAP)
**Status**: Active (Phase 0 live, consolidation in progress)
**Stage**: Building

**What it is**: A DAP — Digital Audio Platform — a new product category that runs as a CLAP/VST3 plugin inside any host DAW AND as a standalone production suite. Key innovation: bidirectional MIDI bridge — reads tempo/key from the host DAW and writes MIDI back to the host's piano roll. No existing DAW-as-plugin does this (Reason Rack is passive-only). Open Orchestra adds AI compositional intelligence + full bidirectional MIDI.

**Why "DAP" not "VST 4"**: Steinberg owns the VST trademark. Lineage: VST1 (1996) → VST2 (1999) → VST3 (2008) → CLAP (2022) → Open Orchestra (2026) as DAP — a new category, not a Steinberg successor.

**The Reason Parallel**: Reason Rack Plugin (2018) = DAW-inside-plugin, but passive instruments only. Open Orchestra differentiator = AI compositional intelligence + bidirectional MIDI.

**Three modes**:
- **Plugin Mode**: Runs as CLAP/VST3 inside Cubase, Ableton, Logic, etc. Reads host tempo/key, writes MIDI back to host piano roll
- **Standalone Mode**: Full DAW environment on Tracktion Engine — no host required
- **Bridge Mode**: Two DAWs via Ableton Link + IAC Driver — "Sister DAWs" workflow (e.g., Open Orchestra + Cubase as equals)

**Tech stack**: JUCE (plugin shell), Tracktion Engine (Standalone Mode), Ableton Link (sync), IAC Driver (MIDI bridge)

**Repository consolidation decision**: All related pieces are being unified into a single `open-orchestra` repo. The existing `mcp-daw-engine` local project becomes the core of Open Orchestra. Components being absorbed:
- `/Users/thomasadair/code/mcp-daw-engine` → **core repo** (rename/repurpose as open-orchestra)
- `/Users/thomasadair/Documents/Open Orchestra/open-orchestra/adapters/cubase_midi_remote.js` → Cubase adapter
- `/Users/thomasadair/projects/av-composer` → AV orchestration layer (music + visuals)
- `/Users/thomasadair/projects/norns-mcp-server` → Norns hardware integration
- `/Users/thomasadair/projects/orchestrator` (Pico Claw) → Norns orchestration bridge

**Current working components** (before consolidation):
- NoteWriter: writes MIDI to Cubase via IAC Driver ✓ (Phase 0 validated)
- MCP DAW Engine: 15+ tools, Cubase/Renoise/Redux adapters, Freesound/Spotify/AI Mastering APIs ✓
- AV Composer: 244-pattern library (7 genres), Phase 1 orchestration layer ✓ (partial Phase 2)
- Cubase MIDI Remote script: `cubase_midi_remote.js` ✓
- Norns MCP Server: OSC + Lua REPL + script management ✓
- Pico Claw: Norns orchestration with Cubase bridge ✓

**Pitch reframe**: Not competing with Cubase ($15M+, 5-7 years). New plugin category — $2-4M seed, 12-18 months to plugin beta. "Sister DAWs" framing.

**5-phase roadmap**:
- **Phase 0 (Now)**: NoteWriter working — MIDI write to Cubase via IAC Driver ✓
- **Phase 1 (1-6 months)**: DAP Plugin Alpha in JUCE — Plugin Mode, bidirectional MIDI bridge
- **Phase 2 (6-18 months)**: Public beta — CLAP + VST3, initial AI compositional tools
- **Phase 3 (Year 2)**: Standalone on Tracktion Engine + Bridge Mode (Ableton Link + IAC)
- **Phase 4 (Year 3-5)**: Full DAP — AI composition suite, TouchDesigner AV bridge, live performance

**What's left**:
- [ ] **Consolidation**: Merge all component repos into a single `open-orchestra` repo on GitHub
- [ ] Phase 1: JUCE project scaffold — Plugin Mode shell (CLAP/VST3), bidirectional MIDI
- [ ] AI compositional tools — define initial feature set
- [ ] Pitch deck / seed raise materials ($2-4M seed)
- [ ] TouchOSC: distributed performer control surface layer (post-Phase 1)

**Next action**: Consolidate all components into one `open-orchestra` repo; then scaffold JUCE plugin

**Connected projects**: TD-DJ-Suite (Phase 4 AV bridge), Jungle MIDI Forge (can connect but stays standalone), TouchOSC Integration Layer

---

### 5. traderspost-mcp
**Codename**: `traderspost-mcp`
**Category**: Developer tool / MCP server
**Status**: Active
**Stage**: Maintaining

**What it is**: A published MCP server (github.com/AdairBear/traderspost-mcp) that gives Claude direct access to TradersPost webhook trading. 11 tools covering strategy management, signal submission, trade history, position state, and health monitoring. Works in relay mode (with local prop_futures_relay) or standalone.

**What's working**:
- Full tool suite published and functional
- Integrates with prop_futures_relay for full context
- Security: webhook URLs never exposed in responses

**What's left**:
- [ ] Keep in sync as Relay/Trident Forge evolve
- [ ] Potential: add tools for regime state, market memory queries

**Next action**: No immediate action — maintain as relay evolves

**Connected projects**: Relay, Trident Forge

---

### 6. OpenClaw (Contributing)
**Codename**: `openclaw`
**Category**: Personal AI assistant infrastructure
**Status**: Active (using + contributing)
**Stage**: Live

**What it is**: Fork of openclaw/openclaw — a personal AI assistant that runs locally and delivers Claude across all messaging channels (WhatsApp, Telegram, Slack, Discord, iMessage via BlueBubbles, Signal, Teams, etc.). Voice Wake, Live Canvas, multi-agent routing. Last Thomas activity: Feb 2026.

**What's left**:
- [ ] Clarify current usage — is this running in Thomas's daily setup?
- [ ] Clarify what contributions Thomas has made / plans to make

**Next action**: Thomas to clarify current status and intended use

---

### 7. Jungle MIDI Forge
**Codename**: `jungle-midi-forge`
**Category**: Music utility / Live tool
**Status**: Active
**Stage**: Live

**What it is**: A web app for generating MIDI chord progressions, melodies, and arrangements. Handy tool for quickly producing genre-aware MIDI across 28 presets (jungle, house, synthwave, vaporwave, lo-fi, ambient, etc.). Standalone — not part of Open Orchestra, though the output is usable in any DAW.

**Live at**: [harmony-house.themostboringdomain.app](https://harmony-house.themostboringdomain.app) ✅ (was down Apr 8 — service re-enabled Apr 21)
**Stack**: Python 3 · Flask · mido · Gunicorn · Nginx · DigitalOcean
**Currently on**: Trading VPS (144.126.208.223) ⚠️ — should migrate to Non-Trading VPS (104.248.223.111)
**Local**: `/Users/thomasadair/projects/p2-products/jungle-midi-forge` (canonical) and `/Users/thomasadair/Documents/jungle-midi-forge`
**GitHub**: github.com/AdairBear/jungle-midi-forge

**What's left**:
- [ ] Clarify which local path is canonical (two copies found)
- [ ] Consider moving deployment from relay VPS to moltbot (keeps trading infra clean)

**Next action**: Consolidate to one local path; optionally migrate to moltbot

**Connected projects**: None (standalone)

---

### 8. Norns Ecosystem (Norns MCP Server + Pico Claw Orchestrator)
**Codename**: `norns` / `pico-claw`
**Category**: Music hardware / MCP server
**Status**: Active
**Stage**: Live

**What it is**: Two connected projects for AI control of the monome Norns hardware synthesizer:
- **Norns MCP Server** (`/Users/thomasadair/projects/norns-mcp-server`): Full MCP server exposing OSC control, Lua REPL injection, and script file management. Pairs with Pico Claw on a Norns Shield Pi and integrates with MCP DAW Engine for full studio orchestration.
- **Pico Claw Orchestrator** (`/Users/thomasadair/projects/orchestrator`): Lua orchestration library that runs on Norns, giving AI agents control over scripts, engines, and the Norns bridge to Cubase (test_cubase.py, bridge/).

**Architecture**: Telegram/Claude → PicoClaw (Norns Shield Pi) → [Norns MCP Server → OSC/REPL/Filesystem] + [DAW Engine Bridge → MCP DAW Engine → Cubase]

**What's left**:
- [ ] Clarify current Norns hardware setup and connection status
- [ ] Publish Norns MCP Server to GitHub

**Next action**: Clarify active hardware state

**Connected projects**: MCP DAW Engine, Open Orchestra

---

### 9. XBP (X Bookmarks Pipeline)
**Codename**: `xbp`
**Category**: Trading / Developer tool
**Status**: Active
**Stage**: Building

**What it is**: A Rust pipeline that converts X (Twitter) bookmarks into validated Pine Script trading strategies. Detects finance-related bookmark content, analyzes charts via vision LLM, generates Pine Script strategies ready for review/deployment.

**Tech**: Rust · Multi-provider LLM (Cerebras, xAI, Claude, OpenAI) · SQLite caching · CDP auto-consent for OAuth

**Features**: Parallel processing, persistent SQLite caching for idempotent reruns, daemon mode for continuous ingestion, per-bookmark LLM cost tracking, rich HTML email notifications, automatic OAuth reauth

**Local path**: `/Users/thomasadair/projects/xbp`
**GitHub**: Not published (local only)

**Next action**: Clarify current status and whether this is being actively run

**Connected projects**: Trident Forge (trading strategy generation pipeline)

---

## Complete Projects

---

### 10. Rapid-Serial-Presentation
**Codename**: `rapid-serial-presentation`
**Category**: Productivity / Personal tool
**Status**: Complete (published)
**Stage**: Live

**What it is**: A speed reading web app using Rapid Serial Visual Presentation (RSVP) technique. TypeScript. Published on GitHub.

**GitHub**: github.com/AdairBear/Rapid-Serial-Presentation

---

### 11. minecraftpacman
**Codename**: `minecraftpacman`
**Category**: Fun / Personal
**Status**: Complete
**Stage**: Maintaining

**What it is**: A browser-based Pacman game with Minecraft ghosts, built for Thomas's kids. JavaScript/HTML/CSS. Published on GitHub.

**Connected projects**: None

---

## Planned / Ideas (Unfleshed)

---

### 12. TouchOSC Integration Layer
**Codename**: `touchosc`
**Category**: Performance control
**Status**: Planned
**Stage**: Concept

**What it is**: A touchscreen control surface layer using TouchOSC (phone/tablet → OSC over WiFi) for manual override control during live performance. Relevant to both TD-DJ-Suite and Open Orchestra.

**For TD-DJ-Suite**: Faders for aura intensity, buttons for OBS scene switches, toggles for Twist SOP. Zero integration work — just add another OSC In CHOP.
**For Open Orchestra**: Potentially each performer gets their own control surface.

**Next action**: Build post TD-DJ-Suite baseline verification

---

## Registry Gaps (Thomas to Fill)

The following were discovered in local filesystem research and need clarification:

1. **OpenClaw** — Are you actively running this? What contributions have you made / plan to make?
2. **Binaural-Jungle** — Public GitHub repo, updated Apr 19 2026. What is this? No README found.
3. **cubase-themes-platform** — Found in projects/ but appears to be a Vite/React starter template. Is there a real project behind this?
4. **Kronos** — Financial foundation model (clone). Are you using/contributing, or was this research?
5. **apple-flow** — Fork of Apple-native AI assistant. Are you actively using this?
6. **XBP** — Is this actively running? Is it generating useful Pine Script output feeding into Trident Forge?
7. **omi (BasedHardware)** — AI wearable contribution. Still relevant?
8. **turboquant_plus** — TheTom/turboquant_plus contribution. Relationship to Trident Forge?
9. **Alpha Calculator** — Brain references this as a Trident Forge scaffold. Separate product or part of Trident?
10. **ebooklm** — Found in projects/ (and a VPS backup). What is this?
11. **moneyprinterv2** — Found in projects/. What is this?
12. **polymarket-mcp-server** — Found in projects/ (appears to be a clone/fork). Are you building on this or just researching?
13. **tradingview-mcp-jackson** — Found in projects/. What is this?
14. **skale** — Found in projects/. What is this?
15. **MCP DAW Engine canonicalization** — Currently local-only at `/Users/thomasadair/code/mcp-daw-engine`. Should this be published to GitHub? Is it also the same as the `MCP DAW Engine` folder in projects/?
16. **Jungle MIDI Forge dual location** — Found at both `projects/p2-products/jungle-midi-forge` AND `Documents/jungle-midi-forge`. Which is canonical?

---

## Maintenance Notes

- This file lives at `/Users/thomasadair/projects/touchdesigner-dj-suite/PRODUCT_REGISTRY.md`
- It is also logged to Open Brain under project `shared` with tag `product-registry`
- Update this file at the start or end of any session where project status changes
- The Open Brain entry should be refreshed whenever this file has significant changes
