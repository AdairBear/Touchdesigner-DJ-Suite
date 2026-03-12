# Multi-Person Tracking - Quick Guide

## ✅ What's New

The movement tracker now supports **simultaneous tracking of multiple people** (up to 4). Perfect for DJ performances with guests, collaborations, or group performances!

## 🎨 Visual Identification

Each person is color-coded:
- **Person 1**: 🟢 Green
- **Person 2**: 🔵 Blue  
- **Person 3**: 🟡 Yellow
- **Person 4**: 🟣 Magenta

## 🎛 Configuration

Edit the last line in `movement_tracker.py`:

```python
# Track 1 person (solo)
tracker = MovementTracker(max_people=1)

# Track 2 people (default - DJ + guest)
tracker = MovementTracker(max_people=2)

# Track 3 people
tracker = MovementTracker(max_people=3)

# Track 4 people (max)
tracker = MovementTracker(max_people=4)
```

## 📡 OSC Message Structure

### Per-Person Data

Each person gets their own OSC namespace:

```
/movement/person1/left_hand_x
/movement/person1/left_hand_y
/movement/person1/motion_energy
/movement/person1/tracking_active
...

/movement/person2/left_hand_x
/movement/person2/left_hand_y
/movement/person2/motion_energy
/movement/person2/tracking_active
...
```

### Global Statistics

```
/movement/num_people         # Currently tracked (0-4)
/movement/avg_energy          # Average motion across all people
```

## 🎯 TouchDesigner Setup

### Basic Multi-Person Setup

1. **OSC In CHOP** - Port 7000
2. **Select CHOP** - Filter by person:
   ```
   /movement/person1/*    # DJ's movements
   /movement/person2/*    # Guest's movements
   ```
3. **Map to visuals:**
   - Person 1 → Main visual layer
   - Person 2 → Secondary effects
   - Use `num_people` to trigger collaboration mode

### Example: Dual Control

```
Person 1 hand_spread → Camera Zoom
Person 2 hand_spread → Effect Intensity

Person 1 motion_energy → Particle System A
Person 2 motion_energy → Particle System B

num_people > 1 → Enable split-screen mode
```

## ⚡ Performance Tips

- **Default 2-person mode** provides best FPS (~25-30 fps)
- **4-person mode** more demanding (~15-20 fps)
- People need to be **reasonably separated** in frame
- **Horizontal positioning** works best (side-by-side)

## 🎭 Use Cases

### DJ + Special Guest
```python
max_people=2  # Default
```
- DJ controls main visuals
- Guest triggers special effects
- Combined energy creates climax moments

### DJ Duo/B2B
```python
max_people=2
```
- Each DJ controls their own visual layer
- Handoffs visualized through tracking
- Build energy together

### Live Performance Crew
```python
max_people=3 or 4
```
- Multiple performers
- Each person mapped to different visual element
- Choreographed visual sequences

## 🔧 How It Works

The tracker:
1. Divides camera frame into regions
2. Runs separate MediaPipe Pose detector for each region
3. Assigns person IDs based on position
4. Sends individual OSC streams for each person
5. Calculates global statistics

**Note**: Person IDs may swap if people cross paths - this is expected behavior with region-based tracking.

## 📊 What Gets Tracked (Per Person)

- Hand positions (left/right, x/y)
- Hand heights (relative to shoulders)
- Hand spread (distance between hands)
- Body height (vertical position)
- Head position
- Shoulder tilt
- Motion energy (movement intensity)
- Tracking status

## 🚀 Quick Test

1. Run the tracker:
   ```bash
   python python/movement_tracker.py
   ```

2. Position 2 people in frame (side-by-side works best)

3. Watch the preview - you should see:
   - Green skeleton on person 1
   - Blue skeleton on person 2
   - "People Tracked: 2/2" in top-left

4. Have each person wave - see their individual motion in TouchDesigner

## 💡 Creative Ideas

- **Call & Response**: Map person 1 to kicks, person 2 to snares
- **Visual Handoff**: Switch focus based on who's moving more
- **Collaboration Mode**: Combine energies for drop moments
- **Competitive Mode**: Split screen, highest energy wins more visual space
- **Formation Patterns**: Detect when people move in sync vs. opposition

---

**Default Setting**: 2-person tracking (DJ + guest)  
**Last Updated**: December 28, 2025
