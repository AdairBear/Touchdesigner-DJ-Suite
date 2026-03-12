# TouchDesigner OSC Setup - Step-by-Step Tutorial

## Prerequisites
- TouchDesigner installed (any version 2020+)
- Movement tracker running (`python python/movement_tracker.py`)
- Basic familiarity with TouchDesigner interface (network editor, parameters panel)

---

## Part 1: Receive OSC Data (10 minutes)

### Step 1: Create New Project

1. **Open TouchDesigner**
2. **File** → **New Project** (or Cmd+N)
3. **File** → **Save As...** → Save as `dj_visuals.toe` in your project folder

### Step 2: Add OSC In CHOP

1. In the **network editor** (main canvas), **press Tab key**
2. A search box appears at your mouse cursor
3. Type **exactly**: `oscin` (all lowercase, no spaces)
   - You should see a dropdown list appear
   - Look for **"OSC In CHOP"** in the list
4. **Press Enter** or click on "OSC In CHOP"
   - A purple box labeled **oscinCHOP1** appears on the canvas
5. Click the **oscinCHOP1** box to select it (it will have a white outline)
6. Look at the **parameters panel** on the right side of the screen

**Note:** If nothing appears when you type `oscin`:
- Try typing just `osc` and look through the list
- Or go to the OP Create Dialog: press `/` key and search for "OSC In"
- CHOPs (Channel Operators) are purple/pink colored boxes

### Step 3: Configure OSC In CHOP

In the parameters panel, set these **exact values**:

**Network** page:
```
Protocol:        UDP
Network Address: 127.0.0.1
Port:            7000
```

**Data** page:
```
Output:          Channel per Address
Filter:          (leave empty)
Merge:           Last Value
```

**Common** page (leave defaults):
```
Active:          ✓ (checked)
```

### Step 4: Verify Data Reception

1. **Make sure your movement tracker is running**
   - Terminal should show "Movement Tracker started..."
   
2. **Look at the oscinCHOP1 box:**
   - Bottom-right corner should show a **number** (like "13" or "26")
   - This is the number of channels (OSC messages) being received
   
3. **View the data:**
   - **Right-click** on oscinCHOP1
   - Select **Viewers** → **Info CHOP**
   - A floating window shows all incoming channels
   
4. **Wave your hands in front of the camera:**
   - You should see values changing in real-time
   - Look for channels like:
     - `person1_left_hand_x`
     - `person1_motion_energy`
     - `num_people`

### ✅ Checkpoint 1
**You should see:** Multiple channels with live-updating values as you move.
**If not working:** Jump to Troubleshooting section below.

---

## Part 2: Create Simple Test Visual (15 minutes)

### Step 5: Add a Circle TOP

1. Press **Tab** key
2. Type `circle` and press **Enter**
3. A **circleTOP1** appears (TOP = Texture Operator, purple box)

### Step 6: Add a Null TOP for Preview

1. Press **Tab** key
2. Type `null` and press **Enter**
3. A **nullTOP1** appears
4. **Connect circleTOP1 → nullTOP1:**
   - Click the **right edge** of circleTOP1 (a white dot appears)
   - Drag to the **left edge** of nullTOP1
   - A wire connects them

### Step 7: View the Output

1. Click **nullTOP1** to select it
2. Press **Number 1 key** on keyboard
   - A viewer window opens showing a white circle on black
3. **Keep this viewer visible** while we add interactivity

### Step 8: Extract a Single OSC Channel

1. Press **Tab** key
2. Type `select` and press **Enter**
3. A **selectCHOP1** appears
4. **Connect oscinCHOP1 → selectCHOP1:**
   - Click right edge of oscinCHOP1
   - Drag to left edge of selectCHOP1

5. **Configure selectCHOP1:**
   - Click selectCHOP1 to select it
   - In parameters panel:
     ```
     Channel Names:  person1_motion_energy
     ```
   
6. **Verify it's working:**
   - Right-click selectCHOP1 → Viewers → Info CHOP
   - Should show just ONE channel: `person1_motion_energy`
   - Value changes as you move (0-100 range)

### Step 9: Scale the Values

We need to convert 0-100 range to something useful for visuals:

1. Press **Tab** key
2. Type `math` and press **Enter**
3. A **mathCHOP1** appears
4. **Connect selectCHOP1 → mathCHOP1**

5. **Configure mathCHOP1:**
   - Select mathCHOP1
   - In parameters panel:
     ```
     Range:
       From Range: 0 to 100
       To Range:   0.1 to 2.0
     ```
   - This maps motion (0-100) to scale (0.1-2.0)

### Step 10: Connect to Circle Radius

1. **Click circleTOP1** to select it
2. In parameters panel, find **Radius** parameter (default 0.3)
3. **Right-click** on the **Radius** label (the word "Radius")
4. Choose **Export CHOP**
5. A popup appears - click the **CHOP** field dropdown
6. Navigate to **mathCHOP1**
7. Click **Channel** field dropdown
8. Select `person1_motion_energy`
9. Click **OK**

### Step 11: Test It!

1. Look at the viewer window (press 1 if closed)
2. **Wave your hands wildly** in front of the camera
3. **The circle should grow and shrink** with your movement!
4. Stand still - circle becomes small
5. Move fast - circle becomes big

### ✅ Checkpoint 2
**You should see:** Circle radius reacting in real-time to your movements.

---

## Part 3: Add Color Based on Hand Position (10 minutes)

### Step 12: Extract Hand Height

1. Create another **selectCHOP** (Tab → `select` → Enter)
2. Rename it: 
   - Right-click → **Name...**
   - Type `select_hand_height`
   - Press Enter
3. **Connect oscinCHOP1 → select_hand_height**

4. **Configure select_hand_height:**
   ```
   Channel Names:  person1_left_hand_height
   ```

### Step 13: Convert to Color Range

1. Create another **mathCHOP** (Tab → `math`)
2. Rename to `math_hand_color`
3. **Connect select_hand_height → math_hand_color**

4. **Configure math_hand_color:**
   ```
   Range:
     From Range: -0.5 to 0.5
     To Range:   0.0 to 1.0
   ```
   - Hand below shoulder = -0.5 → maps to 0.0 (blue)
   - Hand above shoulder = 0.5 → maps to 1.0 (red)

### Step 14: Apply Color to Circle

1. **Click circleTOP1** to select it
2. In parameters panel, go to **Color** page
3. Find **Color Map** → **Input Range**
4. Set **Start:** to 0, **End:** to 1

5. Find **Hue Range:**
   - **Right-click** on **Start** parameter
   - Choose **Export CHOP**
   - Select `math_hand_color` → `person1_left_hand_height`
   - Click OK

### Step 15: Test Color Changes

1. Look at viewer window
2. **Raise your left hand above shoulder** → Circle turns red/orange
3. **Lower your left hand below shoulder** → Circle turns blue/cyan
4. **Move your hand up and down** → Color smoothly transitions

### ✅ Checkpoint 3
**You should see:** Circle size reacts to overall movement, color reacts to hand height.

---

## Part 4: Multi-Person Setup (Optional - 10 minutes)

### Step 16: Add Second Person's Circle

1. **Select circleTOP1**
2. Press **Cmd+C** to copy
3. Press **Cmd+V** to paste
4. A **circleTOP2** appears
5. **Drag it to a different position** in the network

### Step 17: Map to Person 2

1. Create new **selectCHOP** for person 2:
   ```
   Channel Names:  person2_motion_energy
   ```

2. Create new **mathCHOP** with same range (0-100 → 0.1-2.0)

3. **Export to circleTOP2's Radius**:
   - Right-click circleTOP2 Radius → Export CHOP
   - Select the new math CHOP → `person2_motion_energy`

### Step 18: Composite Both Circles

1. Press **Tab** → type `composite` → Enter
2. **compositeTOP1** appears
3. **Connect:**
   - circleTOP1 → compositeTOP1 (left input)
   - circleTOP2 → compositeTOP1 (right input)

4. Connect compositeTOP1 → nullTOP1 (replace old connection)

5. **Configure compositeTOP1:**
   ```
   Operation: Add
   ```

### Step 19: Position Circles Separately

To see both circles:

1. **Click circleTOP1**
2. Add a **Transform TOP** before it:
   - Press **i** key (insert mode)
   - Type `transform` → Enter
   - Appears between circle and previous connection

3. **Configure transformTOP1:**
   ```
   Translate:
     t[0] (X): -0.3
   ```
   - Moves circle left

4. **Repeat for circleTOP2** but set X to +0.3 (moves right)

### ✅ Checkpoint 4
**You should see:** Two circles - left for person 1, right for person 2.

---

## Part 5: Polish and Performance (10 minutes)

### Step 20: Add Smoothing

OSC data can be jittery. Let's smooth it:

1. **After each selectCHOP**, add a **Lag CHOP**:
   - Press **i** with selectCHOP selected
   - Type `lag` → Enter

2. **Configure each lagCHOP:**
   ```
   Lag:     0.1
   Method:  Linear
   ```
   - This smooths motion over 100ms

### Step 21: Add Background

1. Press **Tab** → type `constant` → Enter
2. **constantTOP1** appears
3. **Configure constantTOP1:**
   ```
   Color:
     r: 0.05
     g: 0.05
     b: 0.1
   ```
   - Dark blue background

4. **Add another compositeTOP:**
   - Connect constantTOP → composite (bottom layer)
   - Connect your circles → composite (top layer)
   - Operation: Over

### Step 22: Add Glow Effect

1. Press **Tab** → type `blur` → Enter
2. Insert **blurTOP** after your composite
3. **Configure blurTOP:**
   ```
   Size:   20
   Filter: Gaussian
   ```

4. **Composite blur with original:**
   - Create new compositeTOP
   - Original → input 1
   - Blur → input 2
   - Operation: Add
   - Blend: 0.3

### ✅ Checkpoint 5
**You should see:** Smooth, glowing circles with nice background.

---

## Part 6: Save and Organize (5 minutes)

### Step 23: Organize Your Network

1. **Select all nodes** (Cmd+A)
2. Right-click → **Align Vertical** (or press **Shift+V**)
3. Drag nodes to arrange logically:
   - OSC input on left
   - Processing in middle
   - Output on right

### Step 24: Add Labels

1. Press **Tab** → type `text` → Enter (creates textDAT)
2. Type a label like "OSC INPUT"
3. Press **Cmd+T** to toggle text display mode
4. Position near oscinCHOP1

### Step 25: Save Your Work

1. **File** → **Save** (Cmd+S)
2. Test closing and reopening - settings should persist

---

## Testing Checklist

Run through these tests:

- [ ] OSC In CHOP shows 20+ channels
- [ ] Motion energy value updates as you move
- [ ] Circle grows when you move fast
- [ ] Circle shrinks when you stand still
- [ ] Color changes when you raise/lower hand
- [ ] Smooth motion (not jittery)
- [ ] Glow effect visible
- [ ] Two circles appear if 2 people in frame

---

## Common Parameters to Map

Now that you know how, try mapping these:

| OSC Channel | Visual Parameter | Mapping |
|-------------|-----------------|---------|
| `person1_motion_energy` | Particle spawn rate | 0-100 → 10-1000 |
| `person1_hand_spread` | Camera FOV/Zoom | 0-1 → 30-90 degrees |
| `person1_body_height` | Brightness multiplier | 0-1 → 0.5-2.0 |
| `person1_left_hand_y` | Color hue rotation | 0-1 → 0-360 |
| `num_people` | Enable/disable layers | 1 = solo, 2+ = collab |

---

## Troubleshooting

### No Channels in OSC In CHOP

**Check:**
1. Movement tracker is running (check terminal)
2. Port is exactly `7000` in both OSC In and Python
3. Protocol is `UDP`
4. Network Address is `127.0.0.1`

**Test OSC manually:**
```bash
python -c "from pythonosc import udp_client; c = udp_client.SimpleUDPClient('127.0.0.1', 7000); c.send_message('/test', 1.0)"
```
Should see a `/test` channel appear briefly.

### Values Not Changing

**Check:**
1. Camera permissions granted to Terminal/Python
2. Movement tracker window shows skeleton tracking
3. Right-click oscinCHOP → Viewers → Info CHOP shows live values
4. Try closing/reopening info window

### Circle Not Responding

**Check:**
1. Export is still connected (green text on parameter)
2. Right-click exported parameter → "Show CHOP"
3. Verify mathCHOP output range is reasonable (0.1 to 2.0)
4. Lag time isn't too high (should be 0.1 or less)

### Performance Issues

**Optimize:**
1. Lower camera resolution in movement_tracker.py (720 → 480)
2. Set `max_people=1` if tracking solo
3. In TouchDesigner: Edit → Preferences → Performance Monitor
4. Reduce blur size or disable glow effect

---

## Next Steps

Once this is working:

1. **Add More Visuals**: Try Noise TOP, Ramp TOP, Level TOP
2. **Create Presets**: Save different mapping combinations
3. **Add Feedback**: Route output back through effects
4. **Sync to Audio**: Add Audio Oscillator CHOP for beat detection
5. **Record Output**: Use Movie File Out TOP

---

## Quick Reference - Key Shortcuts

| Action | Shortcut |
|--------|----------|
| Create operator | Tab |
| Connect nodes | Click-drag from output to input |
| Insert operator | Select wire, press **i** |
| View output | Select TOP, press **1** |
| Info window | Right-click → Viewers → Info |
| Bypass operator | Click node, press **b** |
| Delete | Select, press Delete |
| Copy/Paste | Cmd+C / Cmd+V |
| Align nodes | Shift+V (vertical) Shift+H (horizontal) |

---

**You're Ready!** Follow this guide step-by-step and you'll have reactive visuals in under an hour. Each checkpoint is a good place to take a break and test.

**Questions?** Common issues are in Troubleshooting section.
