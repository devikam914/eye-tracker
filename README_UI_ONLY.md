# Assistive Gaze Control - UI Only Version

A beautiful, accessible web-based interface for assistive communication and control.

## Features

- 🏠 **Home Dashboard** - Quick access to all features
- 📞 **Calling** - Emergency and family contact calling
- 🌐 **Web Browsing** - Integrated browser with virtual keyboard
- ⌨️ **Virtual Keyboard** - Full keyboard with text-to-speech
- ⚙️ **Settings** - Customize dwell time, theme, and contacts
- 🌓 **Dark/Light Mode** - Comfortable viewing in any environment

## Installation

### Requirements
- Python 3.8+
- Windows OS (for Phone Link integration)

### Setup

1. Install dependencies:
```bash
pip install pywebview
```

2. Run the standalone UI:
```bash
python "eye tracker/web_ui_standalone.py"
```

## Usage

### Mouse Control
- Click on any tile to activate
- Hover to see dwell animation
- Use back buttons to navigate

### Keyboard Shortcuts
- `ESC` - Exit application
- `Enter` - Confirm actions

## File Structure

```
eye-tracker/
├── eye tracker/
│   ├── web_ui_standalone.py    # Main entry point (no eye tracking)
│   └── web_ui/                 # Web interface files
│       ├── index.html          # Home page
│       ├── styles.css
│       ├── script.js
│       ├── calling.html        # Calling interface
│       ├── calling.css
│       ├── calling.js
│       ├── settings.html       # Settings page
│       ├── settings.css
│       ├── settings.js
│       ├── keyboard.html       # Virtual keyboard
│       ├── keyboard.css
│       ├── keyboard.js
│       ├── browsing_new.html   # Browser with keyboard
│       ├── browsing_new.css
│       └── browsing_new.js
└── README_UI_ONLY.md
```

## Customization

### Theme Colors
Edit the CSS files to change colors:
- Light mode: `#e8dcc8` (background), `#8b6f47` (accent)
- Dark mode: `#1a1d23` (background), `#2dd4bf` (accent)

### Dwell Time
Adjust in Settings page or modify default in `script.js`:
```javascript
let dwellTime = 2.0; // seconds
```

## Adding Eye Tracking (Optional)

If you want to add eye tracking functionality:

1. Install additional dependencies:
```bash
pip install opencv-python mediapipe numpy scipy
```

2. Add the eye tracking modules:
   - `modules/gaze_engine.py`
   - `modules/camera.py`
   - `modules/landmarks.py`
   - `modules/preprosessing.py`
   - `face_landmarker.task` (MediaPipe model)

3. Use `web_ui_controller.py` instead of `web_ui_standalone.py`

## License

MIT License - Feel free to use and modify!

## Contributing

Contributions welcome! Please feel free to submit a Pull Request.

## Support

For issues or questions, please open an issue on GitHub.
