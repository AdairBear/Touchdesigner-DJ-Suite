# POMSKI Integration Plan
## Making POMSKI the Live Performance Layer

> Created: March 17, 2026
> Status: Planning Phase
> Decision: Integrate POMSKI as the performance engine between Pattern Library and Cubase

---

## 🎯 The Core Insight

**POMSKI is not competing with your pattern library — it's the live performance layer that brings it to life.**

### Current Gap
You have:
- ✅ Curated patterns (244 across 7 genres)
- ✅ Visual system (TouchDesigner OSC)
- ✅ AI orchestration (MCP)
- ❌ **Missing: Real-time performance manipulation**

### What POMSKI Adds
- **Live coding REPL** - Change patterns mid-performance
- **Algorithmic enhancement** - Euclidean rhythms, Markov chains, chaos systems
- **Harmony system** - Auto chord progressions
- **Real-time feedback** - Web UI shows what's playing
- **Tempo sync** - Ableton Link or MIDI clock

---

## 🏗️ Architecture: The Full Stack

```
┌────────────────────────────────────────────────────────────────┐
│                    MCP ORCHESTRATOR                            │
│  Claude agent with tools for pattern library + POMSKI control  │
└────────────────────────────────────────────────────────────────┘
            ↓ queries                    ↓ controls
    ┌───────────────┐          ┌─────────────────────────┐
    │  PATTERN LIB  │  feeds   │   POMSKI LIVE ENGINE    │
    │               │────────→ │                         │
    │ • 244 patterns│          │ • Real-time coding      │
    │ • YAML source │          │ • Algorithmic tools     │
    │ • Genre tags  │          │ • Harmony system        │
    └───────────────┘          │ • Web UI (port 8080)    │
                               │ • REPL (port 5555)      │
                               └─────────────────────────┘
                                         ↓ MIDI
                               ┌─────────────────────────┐
                               │        CUBASE           │
                               │  MIDI → Audio Engine    │
                               └─────────────────────────┘
                                         ↓ Audio
                               ┌─────────────────────────┐
                               │   AUDIO ANALYSIS        │
                               │  Bass RMS, Onset, etc.  │
                               └─────────────────────────┘
                                         ↓ OSC
                               ┌─────────────────────────┐
                               │    TOUCHDESIGNER        │
                               │   Reactive Visuals      │
                               └─────────────────────────┘
```

---

## 💡 Example Workflow

### User Request
> "Create a jungle track with complex breakbeats and add a breakdown at 32 bars"

### System Response

1. **MCP Orchestrator** queries Pattern Library:
   - Finds jungle bassline: `jungle/basslines/reese_wobble.yaml`
   - Finds breakbeat: `jungle/drums/amen_variation_3.yaml`

2. **Convert YAML → POMSKI** (automatic):
   ```python
   @composition.pattern("bass", 4)
   def jungle_bass():
       p.note(36, 0, 0.5, 120)  # Deep reese bass
       p.note(38, 1.75, 0.5, 110)
       # ... pattern continues
   ```

3. **Send to POMSKI REPL** (port 5555):
   ```python
   # Load base pattern
   jungle_bass()
   
   # Add algorithmic hi-hats
   @composition.pattern("hats", 1)
   def hats():
       for step in p.euclidean(7, 16):  # Euclidean rhythm
           p.hit_steps([step], pitch=42, velocity=80)
   
   # Set harmony
   composition.harmony("minor_dark", cycle_beats=16)
   ```

4. **POMSKI generates MIDI** → Cubase tracks 1-3

5. **Cubase plays** → Audio analysis extracts features

6. **OSC to TouchDesigner**:
   - Geometry: `particles` (jungle theme)
   - Colors: `#FF0000`, `#000000` (red/black jungle palette)
   - Sync: Bass RMS → particle spawn rate

7. **At bar 32, MCP sends POMSKI command**:
   ```python
   # Breakdown: mute drums, add filter sweep
   mute("hats")
   mute("snare")
   p.add_cc(channel=1, cc_number=74, value=0)  # Filter closed
   ```

8. **User sees/hears**:
   - Visual breakdown (particles slow down)
   - Audio breakdown (bass only, filter sweep)
   - Web UI shows muted patterns

---

## 🛠️ Implementation Roadmap

### Phase 1: Basic POMSKI Setup (1-2 days)

**Goal**: Get POMSKI running and sending MIDI to Cubase

#### Tasks:
1. Install POMSKI:
   ```bash
   cd ~/projects
   git clone https://github.com/ThinkInSound/POMSKI.git
   cd POMSKI
   pip install -e .
   ```

2. Start POMSKI:
   ```bash
   python subsequence/main.py
   ```
   - Web UI: http://localhost:8080
   - REPL: `nc localhost 5555` or Telnet

3. Configure Cubase MIDI:
   - Create virtual MIDI port (IAC Driver on macOS)
   - Set POMSKI MIDI output to virtual port
   - Create Cubase tracks listening to channels 1-16

4. Test simple pattern:
   ```python
   @composition.pattern("test", 1)
   def test():
       p.note(60, 0, 0.5, 100)  # Middle C
   ```
   - Confirm MIDI reaches Cubase
   - Confirm audio playback works

5. Test tempo sync:
   - Option A: Ableton Link (install Link plugin for Cubase)
   - Option B: MIDI clock from Cubase → POMSKI

**Success Criteria**:
- ✅ POMSKI Web UI loads
- ✅ REPL accepts commands
- ✅ MIDI appears in Cubase
- ✅ Audio plays from Cubase instruments
- ✅ Tempo synced

---

### Phase 2: Pattern Library Bridge (2-3 days)

**Goal**: Convert YAML patterns to POMSKI Python functions

#### Architecture:

```
patterns/
  jungle/
    basslines/
      reese_wobble.yaml   ──┐
                            │
    drums/                  │ yaml_to_pomski.py
      amen_variation.yaml ──┤     (converter)
                            │
  breakbeat/                │
    ... more patterns ...  ─┘
                            ↓
                  pomski_patterns/
                    jungle_patterns.py
                    breakbeat_patterns.py
                    techno_patterns.py
```

#### Tasks:

1. **Write Converter Script** (`yaml_to_pomski.py`):
   ```python
   from pathlib import Path
   import yaml
   
   def convert_pattern(yaml_path: Path) -> str:
       """Convert YAML pattern to POMSKI function."""
       with open(yaml_path) as f:
           data = yaml.safe_load(f)
       
       # Extract pattern info
       name = data['name']
       bpm = data['bpm']
       notes = data['sequence']  # Assuming MIDI note format
       
       # Generate POMSKI function
       code = f"""
   @composition.pattern("{name}", {len(notes) / 4})
   def {name.replace('-', '_')}():
       \"\"\"Generated from {yaml_path.name}\"\"\"
   """
       for note in notes:
           code += f"    p.note({note['pitch']}, {note['time']}, {note['duration']}, {note['velocity']})\n"
       
       return code
   ```

2. **Batch Convert All Patterns**:
   ```python
   def convert_all(patterns_dir: Path, output_dir: Path):
       for genre_dir in patterns_dir.iterdir():
           if genre_dir.is_dir():
               output_file = output_dir / f"{genre_dir.name}_patterns.py"
               with open(output_file, 'w') as out:
                   out.write(f"# Generated patterns for {genre_dir.name}\n\n")
                   
                   for yaml_file in genre_dir.rglob("*.yaml"):
                       pattern_code = convert_pattern(yaml_file)
                       out.write(pattern_code + "\n")
   ```

3. **Create Import Module** for POMSKI:
   ```python
   # pomski_patterns/__init__.py
   from .jungle_patterns import *
   from .breakbeat_patterns import *
   from .techno_patterns import *
   # ... more genres
   ```

4. **Test Loading in POMSKI**:
   ```python
   # In POMSKI REPL:
   import sys
   sys.path.append('/Users/thomasadair/projects/av-composer/pomski_patterns')
   from pomski_patterns import jungle_reese_wobble
   
   jungle_reese_wobble()  # Pattern plays!
   ```

**Success Criteria**:
- ✅ Converter handles all YAML pattern formats
- ✅ All 244 patterns converted to Python
- ✅ Patterns loadable in POMSKI REPL
- ✅ MIDI output matches original pattern data
- ✅ Pattern library tags preserved as metadata

---

### Phase 3: MCP Integration (3-4 days)

**Goal**: Claude can query patterns AND control POMSKI

#### MCP Tools to Create:

1. **`pomski_server.py`** (MCP server with POMSKI tools):

```python
from mcp.server import Server
import socket

app = Server("pomski-mcp")

# Socket connection to POMSKI REPL (port 5555)
pomski_socket = None

def connect_pomski():
    global pomski_socket
    pomski_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    pomski_socket.connect(('localhost', 5555))

@app.call_tool()
async def load_pattern(genre: str, pattern_id: str) -> str:
    """Load pattern from converted library."""
    command = f"""
from pomski_patterns.{genre}_patterns import {pattern_id}
{pattern_id}()
"""
    pomski_socket.send(command.encode())
    return f"Loaded {genre}/{pattern_id}"

@app.call_tool()
async def apply_euclidean(channel: str, pulses: int, steps: int) -> str:
    """Add Euclidean rhythm to channel."""
    command = f"""
@composition.pattern("{channel}_euclid", 1)
def euclid_{channel}():
    for step in p.euclidean({pulses}, {steps}):
        p.hit_steps([step], pitch=42, velocity=80)
euclid_{channel}()
"""
    pomski_socket.send(command.encode())
    return f"Added Euclidean {pulses}/{steps} to {channel}"

@app.call_tool()
async def set_harmony(style: str, cycle_beats: int = 16) -> str:
    """Set harmonic progression."""
    command = f"composition.harmony('{style}', {cycle_beats})\n"
    pomski_socket.send(command.encode())
    return f"Set harmony: {style}, cycle: {cycle_beats} beats"

@app.call_tool()
async def send_repl_command(code: str) -> str:
    """Send arbitrary Python code to POMSKI REPL."""
    pomski_socket.send(f"{code}\n".encode())
    return "Sent to POMSKI"

@app.call_tool()
async def mute_pattern(pattern_name: str) -> str:
    """Mute a running pattern."""
    command = f"mute('{pattern_name}')\n"
    pomski_socket.send(command.encode())
    return f"Muted {pattern_name}"

@app.call_tool()
async def unmute_pattern(pattern_name: str) -> str:
    """Unmute a pattern."""
    command = f"unmute('{pattern_name}')\n"
    pomski_socket.send(command.encode())
    return f"Unmuted {pattern_name}"
```

2. **Add to MCP DAW Engine** configuration:

```json
{
  "mcpServers": {
    "pomski-mcp": {
      "command": "python",
      "args": ["/Users/thomasadair/projects/av-composer/mcp/pomski_server.py"]
    }
  }
}
```

3. **Test MCP → POMSKI → Cubase chain**:
   - Claude: "Load jungle bassline"
   - MCP calls `load_pattern("jungle", "reese_wobble")`
   - POMSKI generates MIDI
   - Cubase plays audio
   - Audio analysis → OSC → TouchDesigner

**Success Criteria**:
- ✅ MCP server connects to POMSKI REPL
- ✅ All tools working (load, euclidean, harmony, mute, etc.)
- ✅ Claude can orchestrate multi-pattern compositions
- ✅ Error handling for POMSKI failures
- ✅ Full chain working: MCP → POMSKI → Cubase → Audio → TD

---

### Phase 4: Live Coding Workflow (2-3 days)

**Goal**: Seamless live performance with AI + human collaboration

#### Features:

1. **Performance Templates**:
   ```python
   # jungle_set_template.py
   def setup_jungle_set():
       """Pre-load jungle instruments and patterns."""
       # Load kick on channel 1
       load_pattern("jungle", "kick_909")
       
       # Load reese bass on channel 2
       load_pattern("jungle", "reese_wobble")
       
       # Set dark minor harmony
       composition.harmony("minor_dark", 16)
       
       # Mute everything (DJ will unmute during performance)
       mute("kick_909")
       mute("reese_wobble")
   ```

2. **MCP Agent Prompts** (genre-aware):
   ```markdown
   # System Prompt for Jungle Sets
   
   You are a jungle/drum & bass AI DJ assistant. When the user requests jungle tracks:
   
   1. Query pattern library for jungle basslines, breakbeats, and effects
   2. Load bass patterns first (foundation)
   3. Add complex breakbeats (Amen, Think, Apache variations)
   4. Apply Euclidean rhythms for hi-hats (common: 5/8, 7/16, 11/16)
   5. Use minor_dark or minor_dramatic harmony
   6. Set BPM 160-180
   7. For breakdowns: mute drums, add filter sweeps, reduce visual intensity
   8. For buildups: gradually unmute, increase effect complexity
   
   TouchDesigner visual mappings:
   - Geometry: particles or fractals
   - Colors: red/black or green/black
   - Effects: particle_burst on snare hits, flash on kick
   ```

3. **Web UI Dashboard** (POMSKI provides this):
   - Shows all running patterns
   - Tempo, transport control
   - Pattern list with mute/unmute buttons
   - Visual feedback for what's playing

4. **Combined Control**:
   - **User types to Claude**: "More aggressive, faster hi-hats"
   - **Claude sends MCP command**: `apply_euclidean("hats", 11, 16)`
   - **User also has REPL open**: Can directly code `p.markov(...)` for immediate changes
   - **Web UI updates**: Shows new Euclidean pattern playing

**Success Criteria**:
- ✅ Templates for all 7 genres working
- ✅ MCP agent prompts genre-aware
- ✅ User can hybrid control (AI prompts + direct coding)
- ✅ Web UI provides visual feedback
- ✅ Performance feels fluid, no lag

---

### Phase 5: Advanced Features (Ongoing)

**Goal**: Production-ready live performance system

#### Features:

1. **MIDI Recording to Cubase**:
   - POMSKI patterns → record as MIDI clips
   - Post-performance editing in Cubase
   - Arrangement view workflow

2. **Audio Analysis Integration**:
   ```python
   # In audio analysis pipeline:
   def on_audio_features(features):
       bass_rms = features['bass_rms']
       onset = features['onset_strength']
       
       # Send to TouchDesigner (existing)
       osc_send('/td/sync/bass_rms', bass_rms)
       
       # NEW: Send to POMSKI for audio-reactive patterns
       if onset > 0.8:  # Strong onset
           pomski_send("trigger_effect('particle_burst')")
       
       if bass_rms > 0.7:  # Heavy bass
           pomski_send("increase_complexity('bass', 1.2)")
   ```

3. **Pattern Evolution System**:
   ```python
   @composition.pattern("evolving_bass", 8)
   def evolving():
       """Pattern gradually morphs over time."""
       base_notes = [36, 38, 40, 38]
       
       # Markov chain adds variations each loop
       for i, note in enumerate(base_notes):
           if random.random() > 0.7:  # 30% chance of variation
               note = p.markov(transitions, note)
           p.note(note, i, 0.5, 110)
   ```

4. **Multi-Genre Transitions**:
   ```python
   def crossfade_genres(from_genre: str, to_genre: str, bars: int = 8):
       """Gradually transition between genres."""
       steps = bars * 4  # Quarter note steps
       
       for step in range(steps):
           # Fade out old genre patterns
           old_volume = 1.0 - (step / steps)
           # Fade in new genre patterns
           new_volume = step / steps
           
           # Adjust per pattern
           set_volume(f"{from_genre}_bass", old_volume)
           set_volume(f"{to_genre}_bass", new_volume)
       
       # After transition, mute old genre
       mute_genre(from_genre)
   ```

5. **SKILL.md for Integration**:
   - Document all MCP tools
   - Usage patterns for Claude
   - Common workflows
   - Troubleshooting guide

**Success Criteria**:
- ✅ Can record full performances
- ✅ Audio-reactive POMSKI patterns working
- ✅ Genre transitions smooth
- ✅ Pattern evolution adds organic feel
- ✅ Documented in SKILL.md

---

## 🎓 Learning Path

### Week 1: Foundation
- [ ] Install POMSKI, get basic pattern playing
- [ ] Learn REPL commands (mute, unmute, tempo)
- [ ] Understand pattern decorator syntax
- [ ] Test MIDI → Cubase workflow

### Week 2: Integration
- [ ] Write YAML → POMSKI converter
- [ ] Convert 10 patterns (2 per genre)
- [ ] Test loading in POMSKI
- [ ] Fix any conversion bugs

### Week 3: MCP Tools
- [ ] Build pomski_server.py MCP server
- [ ] Implement 6 core tools (load, euclidean, harmony, mute, unmute, repl)
- [ ] Test Claude → POMSKI control
- [ ] Debug error handling

### Week 4: Performance
- [ ] Create genre templates
- [ ] Set up Web UI workflow
- [ ] Practice hybrid control (AI + manual)
- [ ] First full live performance test

---

## 📊 Why This Is Better Than Skipping

### Without POMSKI (original plan):
- ❌ Static patterns only
- ❌ No live manipulation
- ❌ No algorithmic enhancement
- ❌ No real-time feedback
- ✅ Simpler architecture

### With POMSKI (integrated):
- ✅ Live coding during performance
- ✅ Algorithmic tools (Euclidean, Markov, chaos)
- ✅ Harmony system for chord progressions
- ✅ Real-time feedback (Web UI)
- ✅ Pattern evolution and variation
- ✅ Audio-reactive pattern generation
- ✅ Multi-genre transitions
- ⚠️ More complex (but worth it)

### The Killer Feature:
**Claude can suggest, you can override, POMSKI executes, visuals react — all in real-time during a live performance.**

---

## 🚀 Next Action

**DECISION REQUIRED**: Do you want to commit to POMSKI integration?

- **YES** → Start Phase 1 (POMSKI installation and setup)
- **NO** → Continue with OSC integration only
- **MAYBE** → Do Phase 1 as a test, decide after seeing it work

Let me know and I'll guide you through whichever path you choose.
