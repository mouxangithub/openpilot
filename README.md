[![openpilot on the comma 3X](https://i.imgur.com/Zwv9SaN.png)](https://comma.ai/shop/comma-3x)

What is openpilot?
------

[openpilot](http://github.com/commaai/openpilot) is an open source driver assistance system. Currently, openpilot performs the functions of Adaptive Cruise Control (ACC), Automated Lane Centering (ALC), Forward Collision Warning (FCW), and Lane Departure Warning (LDW) for a growing variety of [supported car makes, models, and model years](docs/CARS.md). In addition, while openpilot is engaged, a camera-based Driver Monitoring (DM) feature alerts distracted and asleep drivers. See more about [the vehicle integration](docs/INTEGRATION.md) and [limitations](docs/LIMITATIONS.md).

<table>
  <tr>
    <td><a href="https://youtu.be/NmBfgOanCyk" title="Video By Greer Viau"><img src="https://github.com/commaai/openpilot/assets/8762862/2f7112ae-f748-4f39-b617-fabd689c3772"></a></td>
    <td><a href="https://youtu.be/VHKyqZ7t8Gw" title="Video By Logan LeGrand"><img src="https://github.com/commaai/openpilot/assets/8762862/92351544-2833-40d7-9e0b-7ef7ae37ec4c"></a></td>
    <td><a href="https://youtu.be/SUIZYzxtMQs" title="A drive to Taco Bell"><img src="https://github.com/commaai/openpilot/assets/8762862/05ceefc5-2628-439c-a9b2-89ce77dc6f63"></a></td>
  </tr>
</table>

What is FrogPilot? 🐸
------

FrogPilot is a fully open-sourced fork of openpilot, featuring clear and concise commits striving to be a resource for the openpilot developer community. It thrives on contributions from both users and developers, focusing on a collaborative, community-led approach to deliver an advanced openpilot experience for everyone!

------
FrogPilot was last updated on:

**July 18th, 2025**

------

# Features

## 🔊 Alerts & Sounds
<details>
<summary>Alert Volume Controller</summary>

&nbsp;&nbsp;&nbsp;*Fine-tune the audio levels for each specific alert category to create a more personalized and less intrusive auditory experience*

- **Disengage Volume:** Adjust the volume for alerts like "Adaptive Cruise Disabled" or when the brake pedal is pressed
- **Engage Volume:** Control the volume for engagement confirmations, such as "openpilot engaged"
- **Prompt Volume:** Set the volume for non-critical prompts, like "Car Detected in Blindspot"
- **Warning Soft & Immediate Volume:** Configure the volume for more urgent warnings that require your attention

  **Location:** `FrogPilot → Alerts and Sounds → Alert Volume Control`
</details>

<details>
<summary>Custom Alerts</summary>

&nbsp;&nbsp;&nbsp;*Enable a variety of custom non-critical alerts to stay better informed on the road*

- **Goat Scream Steering Saturated Alert:** A unique and infamous alert that lets you know when the steering has reached its limit
- **Green Light Alert:** Get notified when the traffic light ahead turns green
- **Lead Departing Alert:** Get an alert when the lead car starts moving
- **Loud Blindspot Alert:** A louder alert for when a vehicle is detected in the blindspot when attempting to change lanes
- **Speed Limit Changed Alert:** Chimes whenever the posted speed limit changes

  **Location:** `FrogPilot → Alerts and Sounds → FrogPilot Alerts`
</details>

---

## 🛠 Device & System
<details>
<summary>Device Management</summary>

&nbsp;&nbsp;&nbsp;*Access a range of settings to manage your device's behavior*

- **Battery Shutdown Threshold:** Automatically shuts down the device if the 12V battery voltage drops below a set threshold to prevent drain
- **Device Shutdown Timer:** Powers down the device X minutes after the car turns off
- **Increase Thermal Limits:** Allow the device to run hotter than the comma-recommended limit for better performance in hot climates (use with caution)

  **Location:** `FrogPilot → System Management → Device Controls`
</details>

<details>
<summary>Screen Management</summary>

&nbsp;&nbsp;&nbsp;*Customize the on-device screen experience*

- **Screen Brightness (On-road/Off-road):** Set different screen brightness levels for when you are driving and when you are parked
- **Screen Recorder:** Enable a button on the driving screen to record the device's screen
- **Screen Timeout (On-road/Off-road):** Automatically turn off the screen after a set period of inactivity, with separate settings for on-road and off-road

  **Location:** `FrogPilot → System Management → Device Controls → Screen Settings`
</details>

<details>
<summary>Data & Logging Management</summary>

&nbsp;&nbsp;&nbsp;*Take control of your data privacy*

- **Disable Data Logging:** Stops local drive logging for privacy and reduced storage wear
- **Disable Uploads:** Blocks all cloud uploads for maximum privacy

  **Location:** `FrogPilot → System Management → Device Controls`
</details>

<details>
<summary>Backup & Restore</summary>

&nbsp;&nbsp;&nbsp;*Easily back up and restore your entire FrogPilot configuration*

- **FrogPilot Backups:** Backup/restore the entire FrogPilot software state
- **Toggle Backups:** Save or restore only your toggle configuration profiles

  **Location:** `FrogPilot → System Management → Data`
</details>

<details>
<summary>System Utilities</summary>

&nbsp;&nbsp;&nbsp;*Access useful utilities to maintain and troubleshoot your FrogPilot installation*

- **Flash Panda:** One-tap recovery/upgrade of the Panda CAN-interface firmware
- **Report a Bug or an Issue:** Submit bug reports or feature requests directly from the device
- **Reset Toggles to Default:** Restores every toggle to factory defaults

  **Location:** `FrogPilot → System Management → Utilities`
</details>

---

## 🚗 Driving Features
<details>
<summary>Longitudinal Control</summary>

&nbsp;&nbsp;&nbsp;*Customize the acceleration and braking behavior of your vehicle*

- **Acceleration Profile:** Choose "Sport" for quicker acceleration or "Eco" for a gentler, more efficient ride
- **Deceleration Profile:** Select "Sport" for more aggressive braking or "Eco" for smoother, more gradual stops
- **Human-Like Acceleration:** Mimic the acceleration of the lead vehicle for a more natural feel
- **Human-Like Approach:** Dynamically adjust following distance when approaching slower vehicles
- **Lead Detection Confidence:** Adjust the sensitivity for detecting vehicles ahead
- **Maximum Acceleration Rate:** Set a cap on how fast FrogPilot can accelerate
- **"Taco Bell Run" Turn Speed Hack:** Slow down for smoother turns at intersections

  **Location:** `FrogPilot → Driving Controls → Gas / Brake → Longitudinal Tuning`
</details>

<details>
<summary>Lateral Control</summary>

&nbsp;&nbsp;&nbsp;*Fine-tune the steering behavior of your vehicle*

- **Always On Lateral:** Keep lane-centering active even when cruise control is disengaged
- **Lane Change Customizations:** Enable automatic lane changes, set a delay, and define a minimum speed
- **Lateral Tuning:** Access advanced settings like "Force Turn Desires" and "NNFF" for more precise steering control
- **Pause Steering Below:** Temporarily pause steering assistance at low speeds

  **Location:** `FrogPilot → Driving Controls → Steering`
</details>

<details>
<summary>Conditional Experimental Mode (CEM)</summary>

&nbsp;&nbsp;&nbsp;*Let FrogPilot intelligently switch to Experimental Mode in situations where the model's end-to-end planning is beneficial*

- **Conditions:** Activate based on speed, upcoming curves, lead vehicles, navigation maneuvers, or when the model wants to stop
- **Status Widget:** Display the CEM status on the driving screen

  **Location:** `FrogPilot → Driving Controls → Gas / Brake → Conditional Experimental Mode`
</details>

<details>
<summary>Custom Driving Personalities</summary>

&nbsp;&nbsp;&nbsp;*Go beyond the standard driving profiles and fine-tune the following distance, acceleration, and braking responsiveness for each personality*

- **Profiles:** Customize the **Traffic**, **Aggressive**, **Standard**, and **Relaxed** profiles
- **Reset to Default:** Option to reset each personality's settings to their default values

  **Location:** `FrogPilot → Driving Controls → Gas / Brake → Customize Driving Personalities`
</details>

<details>
<summary>Speed Limit Controller (SLC)</summary>

&nbsp;&nbsp;&nbsp;*Automatically adjust the vehicle's cruise speed to match the current speed limit*

- **Source Priority:** Define the priority order for speed limit sources (Dashboard, Map Data, Navigation)
- **Speed Limit Offsets:** Set offsets to drive slightly above or below the posted limit
- **Visuals & Quality of Life:** Show the speed limit offset, require confirmation for new speed limits, and more

  **Location:** `FrogPilot → Driving Controls → Gas / Brake → Speed Limit Controller`
</details>

---

## 🗺️ Navigation Features
<details>
<summary>Custom Map Styles & Display</summary>

&nbsp;&nbsp;&nbsp;*Personalize your navigation view*

- **Big Map:** Expands the navigation map to cover most or all of the screen
- **Map Style:** Choose from various map styles like Mapbox Streets, Satellite, or Dark mode

  **Location:** `FrogPilot → Theme and Appearance → Navigation Widgets`
</details>

<details>
<summary>Navigate on Openpilot (Primeless)</summary>

&nbsp;&nbsp;&nbsp;*Enjoy full turn-by-turn navigation without needing a comma prime subscription*

- **Destination Search Provider:** Choose between MapBox, Amap, or Google for destination searches
- **Mapbox Setup:** View detailed instructions to set up your Mapbox API keys

  **Location:** `FrogPilot → Navigation`
</details>

<details>
<summary>Offline Maps</summary>

&nbsp;&nbsp;&nbsp;*Download map data for entire regions or countries directly to your device. This ensures that navigation and features like Speed Limit Controller work flawlessly even without an internet connection*

- **Automatic Updates:** Set a schedule for automatic map updates
- **Data Sources:** Select which countries and states to download

  **Location:** `FrogPilot → Navigation → Map Data`
</details>

---

## 🎨 User Interface
<details>
<summary>Custom On-Road UI Widgets</summary>

&nbsp;&nbsp;&nbsp;*Add useful widgets to your driving screen for a more informative experience*

- **Acceleration Path:** Colorize the driving path based on acceleration and deceleration
- **Adjacent Lanes:** Display driving paths for adjacent lanes
- **Blind Spot Path:** Show a red path for vehicles detected in your blind spot
- **Compass:** Display a compass to show your current driving direction
- **Driving Personality Button:** See and switch between driving personalities on the screen
- **Pedals Indicator:** Show on-screen indicators when the gas or brake pedals are used
- **Rotating Steering Wheel:** The on-screen steering wheel rotates in sync with your car's wheel

  **Location:** `FrogPilot → Theme and Appearance → Driving Screen Widgets`
</details>

<details>
<summary>Custom Themes & Appearance</summary>

&nbsp;&nbsp;&nbsp;*Completely change the look and feel of the openpilot UI*

- **Color Theme:** Swap the entire UI color palette
- **Icon Pack:** Replace default icons with themed packs
- **Holiday Themes:** Enable holiday-based visual themes
- **Rainbow Path:** The driving path turns into a Mario Kart-inspired "Rainbow Path"
- **Random Events:** Enable occasional fun Easter-egg graphics/sounds
- **Startup Alert:** Customize the startup message

  **Location:** `FrogPilot → Theme and Appearance → Theme`
</details>

<details>
<summary>Developer UI</summary>

&nbsp;&nbsp;&nbsp;*Get a behind-the-scenes look at openpilot's operation with detailed on-screen metrics*

- **Developer Metrics:** Display performance data, sensor readings, and system metrics
- **Border Metrics:** Use the screen border to show metrics like blind-spot warnings or steering torque
- **Developer Sidebar:** Show debugging info in a dedicated sidebar
- **Developer Widgets:** Display overlays for adjacent leads and the model's stopping point

  **Location:** `FrogPilot → Theme and Appearance → Developer UI`
</details>

<details>
<summary>Model & Path Visualization</summary>

&nbsp;&nbsp;&nbsp;*Customize how the driving path and lane lines are displayed on the screen*

- **Path/Lane/Edge Width:** Adjust the thickness of the driving path, lane lines, and road edges
- **Dynamic Path Width:** The path width changes based on the engagement state
- **"Unlimited" Road UI:** Extend the display of the road ahead as far as the model can see

  **Location:** `FrogPilot → Theme and Appearance → Model UI`
</details>

<details>
<summary>Quality of Life Visuals</summary>

&nbsp;&nbsp;&nbsp;*Improve your driving experience with these visual tweaks*

- **Camera View:** Choose between Auto, Driver, Standard, and Wide camera views
- **Driver Camera on Reverse:** Show the driver camera feed when the vehicle is in reverse
- **Standby Mode:** Let the screen sleep during long drives, waking instantly for alerts
- **Stopped Timer:** Replace the speed display with a timer when stopped

  **Location:** `FrogPilot → Theme and Appearance → Quality of Life`
</details>

---

# 🧰 How to Install

Easiest way to install FrogPilot is via this URL at the installation screen:

```
frogpilot.download
```

DO NOT install the **"FrogPilot-Development"** branch. I'm constantly breaking things on there, so unless you don't want to use openpilot, NEVER install it!

![](https://i.imgur.com/swr0kqJ.png)

---

# 🐞 Bug reports / Feature Requests

If you encounter any issues or bugs while using FrogPilot, or if you have any suggestions for new features or improvements, please don't hesitate to post about it on the Discord! I'm always looking for ways to improve the fork and provide a better experience for everyone!

To report a bug or request a new feature, make a post in the #bug-reports or #feature-requests channel respectively on the FrogPilot Discord. Please provide as much detail as possible about the issue you're experiencing or the feature you'd like to see added. Photos, videos, log files, or other relevant information are very helpful!

I will do my best to respond to bug reports and feature requests in a timely manner, but please understand that I may not be able to address every request immediately. Your feedback and suggestions are valuable, and I appreciate your help in making FrogPilot the best it can be!

---

# 📱 Discord

[Join the FrogPilot Community Discord!](https://discord.gg/frogpilot)

---

# 📋 Credits

* [AlexandreSato](https://github.com/AlexandreSato)
* [Crwusiz](https://github.com/crwusiz)
* [DragonPilot](https://github.com/dragonpilot-community)
* [ErichMoraga](https://github.com/ErichMoraga)
* [Garrettpall](https://github.com/garrettpall)
* [Mike8643](https://github.com/mike8643)
* [Neokii](https://github.com/Neokii)
* [OPGM](https://github.com/opgm)
* [OPKR](https://github.com/openpilotkr)
* [Pfeiferj](https://github.com/pfeiferj)
* [ServerDummy](https://github.com/ServerDummy)
* [Twilsonco](https://github.com/twilsonco)

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=FrogAi/FrogPilot&type=Date)](https://www.star-history.com/#FrogAi/FrogPilot&Date)

---

# ⚖️ Licensing

openpilot is released under the MIT license. Some parts of the software are released under other licenses as specified.

Any user of this software shall indemnify and hold harmless Comma.ai, Inc. and its directors, officers, employees, agents, stockholders, affiliates, subcontractors and customers from and against all allegations, claims, actions, suits, demands, damages, liabilities, obligations, losses, settlements, judgments, costs and expenses (including without limitation attorneys’ fees and costs) which arise out of, relate to or result from any use of this software by user.

**THIS IS ALPHA QUALITY SOFTWARE FOR RESEARCH PURPOSES ONLY. THIS IS NOT A PRODUCT.
YOU ARE RESPONSIBLE FOR COMPLYING WITH LOCAL LAWS AND REGULATIONS.
NO WARRANTY EXPRESSED OR IMPLIED.**

---

<img src="https://d1qb2nb5cznatu.cloudfront.net/startups/i/1061157-bc7e9bf3b246ece7322e6ffe653f6af8-medium_jpg.jpg?buster=1458363130" width="75"></img> <img src="https://cdn-images-1.medium.com/max/1600/1*C87EjxGeMPrkTuVRVWVg4w.png" width="225"></img>

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/FrogAi/FrogPilot)
