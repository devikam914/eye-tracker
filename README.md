# Assistive Gaze Control UI

A beautiful, accessible web-based interface for assistive communication and control. This is the standalone UI version that works with mouse and keyboard - no eye tracking required!

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)

## ✨ Features

- 🏠 **Home Dashboard** - Clean, modern interface with quick access to all features
- 📞 **Calling** - Emergency (911) and family contact calling via Windows Phone Link
- 🌐 **Web Browsing** - Integrated browser with virtual keyboard
- ⌨️ **Virtual Keyboard (GazeType)** - Full keyboard with text-to-speech and phrase shortcuts
- ⚙️ **Settings** - Customize dwell time, theme, family contacts, and system preferences
- 🌓 **Dark/Light Mode** - Comfortable viewing in any lighting environment
- 🎨 **Modern UI** - Clean design with smooth animations and hover effects

## 📸 Screenshots

### Light Mode
- Clean beige background with brown accents
- Easy on the eyes for daytime use

### Dark Mode
- Dark gray background with teal accents
- Perfect for low-light environments

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Windows OS (for Phone Link integration)
- Webcam (for integrated eye tracking version)

### Installation

1. **Clone the repository**
```bash
git clone <your-repo-url>
cd eye-tracker
```

2. **Install dependencies**

For UI-only version:
```bash
pip install -r requirements.txt
```

For integrated eye tracking version:
```bash
pip install -r requirements_integrated.txt
```

3. **Run the application**

**UI-Only Version (No Eye Tracking):**
```bash
python "eye tracker/web_ui_standalone.py"
```

**Integrated Version (With Eye Tracking):**

Auto-calibration mode (default - calibration starts automatically):
```bash
python "eye tracker/web_ui_controller_integrated.py"
# Or double-click: launch_integrated.bat
```

Demo mode (manual calibration - click button to start):
```bash
python "eye tracker/web_ui_controller_integrated.py" --no-demo
# Or double-click: launch_integrated_demo.bat
```

### Calibration Process

When using the integrated eye tracking version with auto-calibration:

1. **Pass 1: 49-point grid calibration** (7x7 grid)
   - Look at each dot as it appears
   - Keep your head still
   - Takes about 2-3 minutes

2. **Pass 2: 16-point residual correction** (4x4 grid)
   - Corrects session-based offset
   - Improves accuracy
   - Takes about 1 minute

3. **Tracking starts automatically** after calibration
   - Look at buttons to hover
   - Dwell (hold gaze) to click
   - Default dwell time: 1.5 seconds


That's it! The UI will open in fullscreen mode.

## 🎮 Usage

### Mouse Control
- **Click** on any tile to activate it
- **Hover** over tiles to see the dwell animation
- Use **back buttons** to navigate between pages

### Keyboard Shortcuts
- `ESC` - Exit the application
- `Enter` - Confirm actions (where applicable)

### Features Guide

#### Home Page
- Four main tiles: Calling, Browsing, Virtual Keyboard, Settings
- Adjustable dwell time with +/- buttons
- Theme toggle (Light/Dark mode)
- Real-time date, time, and battery display

#### Calling Page
- **Emergency**: Quick dial 911
- **Call Family**: Call your configured family contact
- Set family contact in Settings page

#### Virtual Keyboard (GazeType)
- Full ABC, 123, and symbol keyboards
- Text composition area with character count
- Word predictions (coming soon)
- Quick phrase shortcuts
- Text-to-speech (Speak button)
- Copy text functionality
- Call button for quick access

#### Web Browsing (GazeBrowse)
- Search input with integrated keyboard
- Quick links: YouTube, Wikipedia, News, Weather
- Speak button for text-to-speech
- Opens searches in your default browser

#### Settings
- Adjust dwell time (0.5s - 5.0s)
- Toggle dark mode
- Bluetooth and Wi-Fi controls
- Configure family contact (name and phone)
- System shutdown/restart options

## 📁 Project Structure

```
eye-tracker/
├── eye tracker/
│   ├── web_ui_standalone.py    # Main entry point
│   └── web_ui/                 # Web interface files
│       ├── index.html          # Home page
│       ├── styles.css          # Home page styles
│       ├── script.js           # Home page logic
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
├── requirements.txt            # Python dependencies
├── README.md                   # This file
└── .gitignore                  # Git ignore rules
```

## 🎨 Customization

### Theme Colors

Edit the CSS files to customize colors:

**Light Mode:**
- Background: `#e8dcc8` (warm beige)
- Accent: `#8b6f47` (brown/tan)

**Dark Mode:**
- Background: `#1a1d23` (dark gray)
- Accent: `#2dd4bf` (teal/cyan)

### Dwell Time

Default dwell time is 2.0 seconds. Users can adjust it in the Settings page, or you can change the default in `script.js`:

```javascript
let dwellTime = 2.0; // seconds
```

### Adding Custom Phrases

Edit `keyboard.html` to add your own phrase shortcuts:

```html
<button class="phrase-card" data-text="Your custom phrase">Your custom phrase</button>
```

## 🔧 Configuration

### Family Contact

1. Open the application
2. Navigate to Settings
3. Enter family member name and phone number
4. Click "Save Contact"
5. The contact will be saved and used for the "Call Family" feature

### Phone Link Setup

For calling features to work:
1. Install Windows Phone Link app
2. Connect your phone
3. The app will use `tel:` protocol to initiate calls

## 🐛 Troubleshooting

### Application won't start
- Make sure Python 3.8+ is installed
- Verify pywebview is installed: `pip install pywebview`

### Calling doesn't work
- Ensure Windows Phone Link is installed and configured
- Check that your phone is connected

### Battery percentage shows "N/A"
- Battery Status API may not be supported in your browser engine
- This is normal and doesn't affect functionality

## 🚀 Future Enhancements

- [ ] Word prediction in virtual keyboard
- [ ] Voice commands
- [ ] Custom phrase categories
- [ ] Multi-language support
- [ ] Accessibility improvements
- [ ] Eye tracking integration (optional add-on)

## 📝 License

MIT License - Feel free to use and modify!

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 💬 Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Contact: [your-email@example.com]

## 🙏 Acknowledgments

- Built with [pywebview](https://pywebview.flowrl.com/)
- Icons from SVG library
- Inspired by assistive technology needs

---

Made with ❤️ for accessibility
