# Quick Start: TouchDesigner OSC Integration

**Ready to implement generative visual control in 3 easy steps!**

---

## 📋 What You're Building

Adding OSC receivers to TouchDesigner so the AV Composer orchestrator can control:
- **Geometry types** (particles, sphere, fractals, mesh)
- **Shader colors** (hex color palettes for visual themes)
- **Visual effects** (particle bursts, flashes, pulses)
- **Audio sync** (map bass → particles, onsets → flash, etc.)
- **Any parameter** (noise amplitude, rotation speed, blur, etc.)

---

## 🚀 3-Step Implementation

### Step 1: Read the DAT Scripts (5 min)

Open **[TOUCHDESIGNER_DAT_SCRIPTS.md](TOUCHDESIGNER_DAT_SCRIPTS.md)** to see all 6 Python scripts you'll copy-paste into TouchDesigner.

Each script is ready to use - just copy into a CHOP Execute DAT.

### Step 2: Implement in TouchDesigner (30-45 min)

Follow **[GENERATIVE_OSC_CHECKLIST.md](GENERATIVE_OSC_CHECKLIST.md)** step-by-step:

1. ✅ Create `osc_generative` OSC In CHOP (port 7000, filter `/td/gen/*`)
2. ✅ Add 6 CHOP Execute DATs with scripts from Step 1
3. ✅ Create required operators (Switch TOP, Constant TOPs, Table DAT, etc.)
4. ✅ Wire everything together
5. ✅ Enable all DATs

### Step 3: Test Everything (5-10 min)

Run the automated test suite:

```bash
cd /Users/thomasadair/projects/touchdesigner-dj-suite
python test_td_osc_integration.py
```

**What you'll see:**
- Geometry cycling through 4 types
- Colors changing (jungle red/black → techno blue/cyan → hardcore purple/pink)
- Flash effects every few seconds
- Particle bursts
- Console messages confirming OSC received

**If nothing happens:** See troubleshooting in the checklist.

---

## 📚 Full Documentation

- **[TOUCHDESIGNER_DAT_SCRIPTS.md](TOUCHDESIGNER_DAT_SCRIPTS.md)** - All 6 Python DAT scripts
- **[GENERATIVE_OSC_CHECKLIST.md](GENERATIVE_OSC_CHECKLIST.md)** - Step-by-step implementation
- **[docs/GENERATIVE_OSC_SETUP.md](docs/GENERATIVE_OSC_SETUP.md)** - Technical deep-dive
- **[test_td_osc_integration.py](test_td_osc_integration.py)** - Automated test suite

---

## 🎯 After Implementation

Once OSC integration works:

1. **Connect AV Composer:** Run pattern-based composition with visuals
2. **Add Audio Analysis:** Connect real-time audio features to sync mappings
3. **Expand Visuals:** Add more geometry types, effects, shaders
4. **End-to-End Test:** Cubase → audio → visuals → complete workflow

---

## 🆘 Need Help?

**Common issues:**

- **No OSC received:** Check port 7000, filter `/td/gen/*`, verify `osc_generative` CHOP has channels
- **DATs not executing:** Enable "Active" checkbox, verify "CHOPs" parameter points to `osc_generative`
- **Operators not found:** Check operator paths in scripts match your network layout
- **Python errors:** Open textport (Alt+T) to see detailed error messages

**Still stuck?** Check the checklist troubleshooting section or the DAT scripts doc.

---

## 💡 Pro Tips

1. **Start simple:** Implement geometry switcher first, test it works, then add more
2. **Use textport:** Press Alt+T to see print() output from DAT scripts
3. **Test incrementally:** After each DAT, send a test OSC message to verify
4. **Name consistently:** Use operator names from the scripts or update script paths
5. **Save often:** TouchDesigner can crash, save after each working step

---

**Let's build!** Open `dj_visuals.toe` and start with the checklist. 🎨🎵
