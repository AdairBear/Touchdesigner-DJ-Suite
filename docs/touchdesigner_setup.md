# TouchDesigner OSC Configuration Guide

## Setup Instructions

### 1. Create OSC In CHOP

1. Open your TouchDesigner project
2. Add an **OSC In CHOP** to your network
3. Configure the OSC In CHOP:
   - **Network Address**: `127.0.0.1` (localhost)
   - **Port**: `7000`
   - **Protocol**: UDP

### 2. Expected OSC Messages

The movement tracker supports **multi-person tracking** and sends separate data for each person.

#### Per-Person Movement Data
Each person gets their own OSC namespace: `/movement/person1/...`, `/movement/person2/...`, etc.

- `/movement/person1/left_hand_x` - Left hand horizontal position (0-1)
- `/movement/person1/left_hand_y` - Left hand vertical position (0-1)
- `/movement/person1/right_hand_x` - Right hand horizontal position (0-1)
- `/movement/person1/right_hand_y` - Right hand vertical position (0-1)
- `/movement/person1/left_hand_height` - Left hand height relative to shoulder
- `/movement/person1/right_hand_height` - Right hand height relative to shoulder
- `/movement/person1/hand_spread` - Distance between hands (0-1)
- `/movement/person1/body_height` - Body center vertical position (0-1)
- `/movement/person1/head_x` - Head horizontal position (0-1)
- `/movement/person1/head_y` - Head vertical position (0-1)
- `/movement/person1/shoulder_tilt` - Shoulder angle
- `/movement/person1/motion_energy` - Movement intensity for this person (0-100)
- `/movement/person1/tracking_active` - 1.0 when tracking, 0.0 when lost

**Repeat for person2, person3, person4...**

#### Global Statistics
- `/movement/num_people` - Number of people currently tracked
- `/movement/avg_energy` - Average motion energy across all tracked people

### 3. Map OSC to Visual Parameters

#### For Multi-Person Tracking

1. Use a **Select CHOP** to isolate specific person's channels:
   ```
   Select: /movement/person1/*
   ```

2. Use **Math CHOPs** to scale/transform values:
   - Range: Remap 0-1 to your desired range
   - Smooth: Add smoothing for smoother visuals

3. Export to parameters:
   - Right-click on any parameter
   - Select "Export CHOP"
   - Connect to your OSC In CHOP channel

4. **Multiple people**: Create separate visual elements for each person:
   - Person 1 (DJ): Controls main visuals
   - Person 2 (Guest): Controls secondary layer or different effects
   - Use `/movement/num_people` to enable/disable multi-person features

### 4. Example Mappings

**Single DJ:**
```
person1/hand_spread → Camera Zoom
person1/motion_energy → Particle Spawn Rate
person1/body_height → Brightness/Intensity
person1/left_hand_height → Color Hue
```

**DJ + Guest:**
```
person1/motion_energy → Main particle system
person2/motion_energy → Secondary particle system
person1/hand_spread → Camera position X
person2/hand_spread → Camera position Y
num_people → Enable collaboration mode
avg_energy → Global intensity multiplier
```

### 5. Configure Number of People to Track

In the Python script, set `max_people` parameter:

```python
# Track 1 person (solo DJ)
tracker = MovementTracker(max_people=1)

# Track 2 people (DJ + guest) - Default
tracker = MovementTracker(max_people=2)

# Track up to 4 people
tracker = MovementTracker(max_people=4)
```

### 6. Test OSC Connection

1. Run the movement tracker (default: 2 people):
   ```bash
   python python/movement_tracker.py
   ```

2. In TouchDesigner, check the OSC In CHOP - you should see incoming data for each person
3. Have multiple people wave in front of the camera to verify values change
4. Person 1 will be shown in **Green**, Person 2 in **Blue**, Person 3 in **Yellow**, Person 4 in **Magenta**

### 7. Troubleshooting

**No data received:**
- Check port 7000 is not in use: `lsof -i :7000`
- Verify movement tracker is running
- Check firewall settings

**Only tracking one person:**
- People need to be reasonably separated in frame
- Check `max_people` setting in script
- Try positioning people in different horizontal zones

**Jittery values:**
- Add Smooth CHOP (smoothing=0.1-0.3)
- Use Lag CHOP for delayed smoothing
- Increase smoothing values in `movement_mappings.json`

**People swapping IDs:**
- This is expected when people cross paths
- Use tracking_active channel to detect when person is lost
- Consider using position-based logic in TouchDesigner

**Performance issues:**
- Reduce `max_people` to 2 for better FPS
- Lower camera resolution (currently 1280x720)
- Use model_complexity=0 (lite mode) in the code

---

**Status**: Ready for multi-person TouchDesigner integration  
**Default Mode**: 2-person tracking (DJ + guest)
