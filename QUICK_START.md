# Quick Start Guide

## Installation (No New Dependencies!)

All required packages are already installed for your existing system. No additional installation needed.

## Running the System

### Method 1: Full System with New UI (Recommended)

```bash
cd "eye-tracker/eye tracker"
python main_ui.py
```

**What happens:**
1. Your existing 49-point calibration runs (terminal-based)
2. Residual correction runs (16 points)
3. New 3-panel UI launches automatically
4. Real-time tracking begins

**Duration:** ~5-7 minutes for calibration, then continuous tracking

### Method 2: Test UI Layout Only

```bash
cd "eye-tracker/eye tracker"
python ui_controller.py
```

**What happens:**
- UI appears immediately
- No camera/tracking (just layout preview)
- Good for testing display setup

### Method 3: Original System (Fallback)

```bash
cd "eye-tracker/eye tracker"
python main.py
```

**What happens:**
- Your original system runs unchanged
- Terminal-based calibration
- OpenCV windows for tracking
- pyautogui cursor control

## First Run Checklist

Before running, ensure:

- [ ] Camera is connected and working
- [ ] Room has adequate lighting
- [ ] You're seated comfortably at normal viewing distance
- [ ] Screen brightness is comfortable
- [ ] No other applications are using the camera

## Calibration Tips (Same as Before)

1. **Head Position**: Keep your head still during calibration
2. **Gaze Focus**: Look directly at the white dot center
3. **Blink Normally**: System filters out blinks automatically
4. **Patience**: Each point takes ~3-4 seconds
5. **Recollection**: If a point fails validation, you'll recollect it

## Using the New UI

### Understanding the Layout

```
┌──────────┬─────────────────────────────────┬──────────────┐
│          │                                 │              │
│ CONTROLS │      INTERACTION CANVAS         │ SYSTEM STATE │
│          │                                 │              │
│  Drift   │   ┌─────────────────────┐      │  Gaze Signal │
│  Correct │   │                     │      │  X: 0.4523   │
│          │   │   Your cursor       │      │  Y: -0.1234  │
│  Toggle  │   │   appears here      │      │              │
│  Debug   │   │                     │      │  Tracking    │
│          │   │   Demo buttons      │      │  Mode: 3D    │
│  Exit    │   │   for testing       │      │              │
│  System  │   │                     │      │  Eye State   │
│          │   └─────────────────────┘      │  EAR: 0.245  │
│          │                                 │              │
│          │                                 │  Calibration │
│          │                                 │  Quality     │
│          │                                 │  [Grid viz]  │
└──────────┴─────────────────────────────────┴──────────────┘
```

### Reading the System State Panel

**Gaze Signal Section:**
- X, Y: Your current gaze coordinates (normalized)
- Stability bar: Green = stable, Red = unstable

**Tracking Mode Section:**
- Mode: 3D (with head compensation) or 2D
- Face: DETECTED (green) or LOST (red)

**Eye State Section:**
- EAR: Eye Aspect Ratio (higher = eyes open)
- Bar shows current EAR with blink threshold line
- Circle indicator: Green = eyes open, Red = blinking

**Calibration Quality Section:**
- Mean Error: Average prediction error in pixels
- Max Error: Worst point error in pixels
- Grid: 7x7 visualization (green = good, red = poor)

**Correction Layers Section:**
- Shows which correction systems are active
- Drift Offset: Current drift compensation values

### Using the Controls

**Drift Correction Button:**
- Use when cursor seems offset from your gaze
- Looks at screen center for 2-3 seconds
- Automatically adjusts offset

**Toggle Debug Button:**
- Shows camera feed in separate window
- Displays raw gaze values
- Useful for troubleshooting

**Exit System Button:**
- Clean shutdown
- Releases camera
- Closes all windows

### Keyboard Shortcuts

- **ESC**: Quick exit
- **R**: Trigger drift correction
- **SPACE**: Toggle debug mode

## Understanding the Cursor

The cursor is NOT a standard arrow. It's a custom gaze indicator:

**Normal Operation:**
- Soft circular blob (neon green)
- Size changes with stability (larger = more stable)
- Leaves a fading trail
- Outer ring shows stability (green/yellow/red)

**During Blink:**
- Cursor freezes in place
- Red flash ring appears
- Prevents jumpy movement

**High Noise:**
- Cursor may jitter
- Yellow warning appears
- Outer ring turns red

## Common Scenarios

### Scenario 1: Face Lost
**What you see:**
- Red overlay on canvas
- "FACE LOST" message
- Cursor freezes

**What to do:**
- Look at the camera
- Ensure adequate lighting
- Remove obstructions (hands, hair)

### Scenario 2: High Movement
**What you see:**
- Yellow border on canvas
- "HIGH MOVEMENT" warning
- Stability bar shows red

**What to do:**
- Hold your head still
- Stabilize your seating position
- Wait for stability to improve

### Scenario 3: Drift Detected
**What you see:**
- Cursor offset from where you're looking
- Drift values increase in system panel

**What to do:**
- Press 'R' or click "Drift Correction"
- Look at screen center when prompted
- System auto-adjusts

## Performance Expectations

**Typical Metrics:**
- Mean Error: 40-60 pixels
- Max Error: 80-120 pixels
- Stability: 70-90%
- Update Rate: 20-30 FPS

**Good Calibration:**
- All grid points green or yellow
- Mean error < 50px
- Smooth cursor movement

**Poor Calibration:**
- Multiple red grid points
- Mean error > 80px
- Jumpy cursor

If calibration is poor, restart and ensure:
- Head was completely still
- Lighting was consistent
- You focused on each point

## Troubleshooting

### UI doesn't launch after calibration
**Check:**
- Console for error messages
- Tkinter is available: `python -c "import tkinter"`

**Solution:**
- Try running `ui_controller.py` standalone
- Check Python version (3.7+)

### Cursor not visible
**Check:**
- System panel shows "Face: DETECTED"
- Gaze X, Y values are updating
- Calibration completed successfully

**Solution:**
- Ensure face is visible to camera
- Check lighting conditions
- Restart calibration if needed

### Cursor very jumpy
**Check:**
- Stability bar (should be >50%)
- System panel for high noise warning

**Solution:**
- Hold head completely still
- Improve lighting
- Consider recalibration

### Debug window not showing
**Check:**
- Debug mode is ON (press SPACE)
- OpenCV can create windows

**Solution:**
- Try pressing SPACE again
- Check console for cv2 errors

### Performance is slow
**Check:**
- CPU usage
- Other applications running

**Solution:**
- Close unnecessary applications
- Reduce update rate (see customization guide)

## Tips for Best Results

1. **Lighting**: Bright, even lighting on your face
2. **Position**: Sit at normal viewing distance (50-70cm)
3. **Stability**: Use a stable chair, avoid swivel chairs
4. **Breaks**: Recalibrate every 30-60 minutes
5. **Drift**: Use drift correction frequently (every 5-10 minutes)

## What's Different from Original System?

| Feature | Original | New UI |
|---------|----------|--------|
| Calibration | Terminal-based | Same (unchanged) |
| Tracking Display | OpenCV window | 3-panel interface |
| Cursor | System cursor (pyautogui) | Custom gaze cursor |
| Telemetry | Console prints | Real-time panel |
| Error States | Text warnings | Visual overlays |
| Interaction | Keyboard only | Keyboard + dwell buttons |
| Debug Info | Always visible | Toggle on/off |

## Next Steps

After getting comfortable with the system:

1. **Customize**: Adjust colors, sizes, timings (see UI_IMPLEMENTATION.md)
2. **Integrate**: Connect to your call_demo applications
3. **Extend**: Add custom buttons or functionality
4. **Optimize**: Fine-tune for your specific use case

## Getting Help

If you encounter issues:

1. Check console output for errors
2. Review UI_IMPLEMENTATION.md for details
3. Review ARCHITECTURE.md for system design
4. Test original main.py to verify hardware
5. Run ui_controller.py to isolate UI issues

## Summary

**To get started right now:**

```bash
cd "eye-tracker/eye tracker"
python main_ui.py
```

Then:
1. Complete calibration (5-7 minutes)
2. Explore the UI
3. Test cursor tracking
4. Try keyboard shortcuts
5. Experiment with controls

The system maintains 100% of your original accuracy while providing a professional, transparent interface for assistive gaze control.

Enjoy your new interface! 🎯👁️
