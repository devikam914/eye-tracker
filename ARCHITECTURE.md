# System Architecture

## Component Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                         main_ui.py                              │
│  (Integration Layer - Runs calibration, launches UI)           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ui_controller.py                            │
│              (Main Application Window)                          │
│                                                                 │
│  ┌──────────────┬─────────────────────────┬─────────────────┐  │
│  │              │                         │                 │  │
│  │  Control     │   Interaction Canvas    │  System State   │  │
│  │  Panel       │   (70% width)           │  Panel          │  │
│  │  (10%)       │                         │  (20%)          │  │
│  │              │                         │                 │  │
│  │  ┌────────┐  │  ┌──────────────────┐  │  ┌───────────┐  │  │
│  │  │ Drift  │  │  │  Gaze Cursor     │  │  │ Gaze      │  │  │
│  │  │ Correct│  │  │  + Trail         │  │  │ Signal    │  │  │
│  │  └────────┘  │  │                  │  │  └───────────┘  │  │
│  │              │  │  Heatmap         │  │                 │  │
│  │  ┌────────┐  │  │                  │  │  ┌───────────┐  │  │
│  │  │ Toggle │  │  │  Demo Buttons    │  │  │ Tracking  │  │  │
│  │  │ Debug  │  │  │  (Snap-to)       │  │  │ Mode      │  │  │
│  │  └────────┘  │  │                  │  │  └───────────┘  │  │
│  │              │  │  Error Overlays  │  │                 │  │
│  │  ┌────────┐  │  │                  │  │  ┌───────────┐  │  │
│  │  │ Exit   │  │  └──────────────────┘  │  │ Eye State │  │  │
│  │  │ System │  │                         │  └───────────┘  │  │
│  │  └────────┘  │                         │                 │  │
│  │              │                         │  ┌───────────┐  │  │
│  └──────────────┴─────────────────────────┴──│ Calib     │──┘  │
│                                               │ Quality   │     │
│                                               └───────────┘     │
│                                                                 │
│                                               ┌───────────┐     │
│                                               │ Correction│     │
│                                               │ Layers    │     │
│                                               └───────────┘     │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    modules/gaze_engine.py                       │
│                   (Core Tracking Logic)                         │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  GazeEngine                                              │  │
│  │  ├─ FaceLandmarkDetector (from landmarks.py)            │  │
│  │  ├─ AxisNormalizer                                       │  │
│  │  ├─ RBFGazeMapper                                        │  │
│  │  ├─ ResidualCorrectionField                             │  │
│  │  ├─ GazeFilter (OneEuroFilter x2)                       │  │
│  │  └─ State Management                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  process_frame(frame) → state_dict                             │
│  get_calibration_quality() → metrics                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  modules/landmarks.py                           │
│              (MediaPipe Face Detection)                         │
│                                                                 │
│  FaceLandmarkDetector.process(frame) → (gx, gy, ear)          │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
Camera Frame
    │
    ▼
FaceLandmarkDetector
    │
    ├─ Face Landmarks (478 points)
    ├─ 3D Transformation Matrix
    └─ Eye Aspect Ratio (EAR)
    │
    ▼
GazeEngine.process_frame()
    │
    ├─ Normalize coordinates (AxisNormalizer)
    ├─ Map to screen (RBFGazeMapper)
    ├─ Apply corrections (ResidualCorrectionField)
    ├─ Smooth output (GazeFilter)
    └─ Handle blinks
    │
    ▼
State Dictionary
    │
    ├─ predicted_x, predicted_y (screen coordinates)
    ├─ gaze_x, gaze_y (normalized)
    ├─ ear (eye aspect ratio)
    ├─ face_detected (bool)
    ├─ tracking_mode ('3D' or '2D')
    ├─ stability (0.0-1.0)
    └─ is_blinking (bool)
    │
    ▼
UI Components
    │
    ├─ InteractionCanvas.update_display(state)
    │   ├─ Update cursor position
    │   ├─ Draw heatmap trail
    │   ├─ Check snap-to targets
    │   └─ Show error overlays
    │
    └─ SystemStatePanel.update(state, quality)
        ├─ Update gaze coordinates
        ├─ Draw stability bar
        ├─ Update tracking mode
        ├─ Draw EAR bar
        ├─ Update blink indicator
        └─ Update calibration grid
```

## Calibration Flow (Unchanged)

```
main_ui.py starts
    │
    ▼
49-Point Grid Collection
    │
    ├─ For each point (7x7 grid):
    │   ├─ Show target
    │   ├─ Collect 60 samples
    │   ├─ Filter outliers (IQR)
    │   └─ Store average
    │
    ▼
Validation Pass
    │
    ├─ Predict each point
    ├─ Calculate error
    └─ Recollect if error > 120px
    │
    ▼
Fit Normalizer & Mapper
    │
    ├─ AxisNormalizer.fit()
    ├─ Add edge anchors
    └─ RBFGazeMapper.fit()
    │
    ▼
Residual Correction (16 points)
    │
    ├─ Collect correction samples
    ├─ Calculate residuals
    └─ ResidualCorrectionField.fit()
    │
    ▼
Load into UI
    │
    ├─ Create AssistiveGazeUI
    ├─ Load calibration data
    └─ Start tracking loop
```

## UI Update Loop (60 FPS)

```
Every 16ms:
    │
    ├─ Capture frame from camera
    │
    ├─ Process through GazeEngine
    │   └─ Returns state dictionary
    │
    ├─ Update InteractionCanvas
    │   ├─ Clear previous frame
    │   ├─ Draw heatmap
    │   ├─ Update cursor
    │   └─ Check error states
    │
    ├─ Update SystemStatePanel
    │   ├─ Update all metrics
    │   ├─ Draw bars/indicators
    │   └─ Update grid visualization
    │
    ├─ Update status bar
    │
    └─ Schedule next update
```

## Component Dependencies

```
ui_controller.py
    ├─ modules/gaze_engine.py
    │   ├─ modules/landmarks.py
    │   │   └─ mediapipe
    │   ├─ scipy.interpolate
    │   └─ numpy
    │
    ├─ modules/ui_components/canvas.py
    │   └─ modules/ui_components/cursor.py
    │
    ├─ modules/ui_components/system_panel.py
    │
    └─ modules/ui_components/control_panel.py
```

## File Sizes (Approximate)

```
gaze_engine.py          ~250 lines  (Core logic)
ui_controller.py        ~200 lines  (Main window)
canvas.py               ~180 lines  (Interaction area)
cursor.py               ~80 lines   (Cursor rendering)
system_panel.py         ~280 lines  (Telemetry display)
control_panel.py        ~120 lines  (Control buttons)
main_ui.py              ~350 lines  (Integration)
───────────────────────────────────
Total new code:         ~1,460 lines
```

## Memory Footprint

```
Component                Memory Usage
─────────────────────────────────────
Gaze history (100 pts)   ~1.6 KB
Cursor trail (5 pts)     ~80 bytes
Calibration data         ~4 KB
UI elements              ~50 KB
Tkinter overhead         ~5 MB
───────────────────────────────────
Total additional:        ~5.1 MB
```

## Performance Metrics

```
Operation                Time (avg)
─────────────────────────────────────
Frame capture            ~16 ms
Face detection           ~20 ms
Gaze processing          ~2 ms
UI rendering             ~5 ms
───────────────────────────────────
Total per frame:         ~43 ms
Target frame rate:       60 FPS (16.67 ms)
Actual achievable:       ~23 FPS (limited by face detection)
```

## Error Handling

```
Error State              UI Response
─────────────────────────────────────
Face not detected        → Red overlay + warning message
High gaze variance       → Yellow border + stability warning
Blink detected           → Freeze cursor + flash effect
Camera disconnected      → Error dialog + graceful exit
Calibration failed       → Prevent UI launch + error message
```

## Keyboard Shortcuts

```
Key         Action                      Handler
──────────────────────────────────────────────────
ESC         Exit system                 exit_system()
R           Drift correction            drift_correction()
SPACE       Toggle debug mode           toggle_debug()
```

## State Machine

```
                    ┌─────────────┐
                    │   STARTUP   │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │ CALIBRATION │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  UI LOADED  │
                    └──────┬──────┘
                           │
                           ▼
        ┌──────────────────┴──────────────────┐
        │                                     │
        ▼                                     ▼
┌──────────────┐                    ┌──────────────┐
│   TRACKING   │◄───────────────────│  FACE LOST   │
└──────┬───────┘                    └──────────────┘
       │
       ├─ Blink detected → Freeze cursor
       ├─ High noise → Show warning
       ├─ Drift → Suggest correction
       │
       ▼
┌──────────────┐
│     EXIT     │
└──────────────┘
```

## Integration Points

```
Original System          New System
─────────────────────────────────────────────
main.py                  main_ui.py
  ├─ Calibration           ├─ Same calibration
  ├─ Tracking loop         ├─ UI update loop
  └─ pyautogui.moveTo()    └─ Canvas cursor

landmarks.py             landmarks.py
  └─ (unchanged)           └─ (unchanged)

camera.py                camera.py
  └─ (unchanged)           └─ (unchanged)
```

## Extension Points

Future enhancements can be added by:

1. **New UI Components**: Add to `modules/ui_components/`
2. **New Tracking Features**: Extend `GazeEngine` class
3. **Alternative UIs**: Create new controller using `GazeEngine`
4. **Data Logging**: Add observers to `GazeEngine.process_frame()`
5. **Network Control**: Expose `GazeEngine` via API

## Testing Strategy

```
Unit Tests (Recommended)
├─ gaze_engine.py
│   ├─ Test OneEuroFilter
│   ├─ Test AxisNormalizer
│   ├─ Test RBFGazeMapper
│   └─ Test ResidualCorrectionField
│
Integration Tests
├─ Test calibration → UI flow
├─ Test state updates
└─ Test error handling

UI Tests
├─ Test cursor rendering
├─ Test panel updates
└─ Test keyboard shortcuts
```
