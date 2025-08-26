# dashy - dragonpilot's All-in-one System Hub for You

A modern web-based dashboard for monitoring and controlling your dragonpilot/openpilot remotely.

## Usage

These files should be served by the Dashy backend server running on your comma device.

Access the interface by navigating to `http://<comma-device-ip>:5088` in Chrome browser.

## Files

- `index.html` - Main application
- `js/app.js` - Minified JavaScript bundle
- `css/styles.css` - Minified styles
- `icons/` - Favicon
- `pages/player.html` - HLS video player

## Features

- **Live Driving View** - Real-time WebRTC video with augmented reality overlay
- **File Browser** - Access and stream driving recordings
- **Settings Control** - Configure vehicle and display preferences

## 🎮 Usage

### Navigation
- **Driving View** - Live camera feed with lane lines and path visualization
- **Files** - Browse `/data/media/0/realdata` recordings
- **Local Settings** - Adjust display preferences

### Display Options
- Metric/Imperial units
- HUD mode for windshield projection

## Requirements

- dragonpilot/openpilot device (comma 3/3X)
- Chrome browser (recommended)
- Same network connection as vehicle

## 📄 License

Copyright (c) 2025 Rick Lan

This software is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).
You are free to share and adapt this work for non-commercial purposes, provided you give appropriate credit and distribute any modifications under the same license.

To view a copy of this license, visit:
http://creativecommons.org/licenses/by-nc-sa/4.0/

---

**Commercial Licensing:**
Use of this software for commercial purposes is strictly prohibited without a separate, paid license.
To purchase a commercial license, please contact ricklan@gmail.com.
