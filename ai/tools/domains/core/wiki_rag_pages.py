"""Auto-generated openpilot Wiki RAG chunks. Run fetch_op_wiki_rag.mjs to refresh."""

from __future__ import annotations

from typing import Any

WIKI_RAG_PAGES: list[dict[str, Any]] = [
  {
    "id": "builtin_wiki_home_0",
    "title": "Wiki: Home",
    "tags": ["wiki","openpilot","comma","home"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Home
https://github.com/commaai/openpilot/wiki/Home

Quick Start
 Installing Physical Device
 Installing openpilot Software

Basic information
 Frequently Asked Questions
 Troubleshooting
 General Terms
 comma three and 3X

Vehicle Information
Find out specific vehicle limitations and modifications that members of the community make to their cars for a better openpilot experience.

Supported Brands
 Chevrolet / Buick / GMC / Cadillac
 Chrysler / Jeep / Dodge
 Ford / Lincoln
 Honda / Acura
 Hyundai / Kia / Genesis
 Rivian
 Mazda
 Nissan
 Subaru
 Tesla
 Toyota / Lexus
 Volkswagen

Development with openpilot""",
  },
  {
    "id": "builtin_wiki_faq_0",
    "title": "Wiki: FAQ (1/6)",
    "tags": ["wiki","openpilot","comma","faq"],
    "refresh": False,
    "text": """Source: openpilot Wiki — FAQ
https://github.com/commaai/openpilot/wiki/FAQ

◄ Home

Table of Contents
=================

    openpilot
      How do I report a bug?
      What is lateral control?
      What is longitudinal control?
      How does Lane Change Assist Work?
      How to change to a specific release?
      Where is my dashcam video footage stored? How can I stitch the segments together?
      When are my videos uploaded to the cloud?
      I get "Unrecognized car / dash cam mode" after installing Openpilot
    comma three
      Why won't my comma three turn on?
      What is a Dongle ID?
      Where can I find my Dongle ID?
      How do I delete my drives?
      How can I reset the device?
      What is the comma three hardware?
      Will the comma three kill my car battery?
      My storage space is filling up, How long are drive segments kept on my device?
    comma two
    comma prime
      What are comma points for?
    Development
      What is the openpilot development workflow? / What are the branches master, devel, and release?
      What do the LED colors mean?
      How can I contribute?
    Discord Help
      Before Asking a Question
      How do I search on discord?
      How do I read discord channel pins?
      How do I read the channel description?

openpilot

How do I report a bug?

Note: The comma team will not debug data from fork code as "it just takes too much time to be sidetracked by hidden and unclear changes". If your issue was produced on a fork, please try to reproduce it on either a master or release branch of comma's openpilot.

Use the search functionality of the comma.ai community Discord and of this GitHub Repository to confirm the strange behavior you noticed was already reported or not. Either way, continue to collect a segment ID for a comment, reply, or a new report of when this bug occured.

To do that, find and scrub to the segment (what's a segment?) of interest of your drive in comma connect, then click More Info and copy the segment ID to your clipboard by clicking on it. The segment ID is something like 50330d02g131d4393/000000cf--ef79431a8f/24. Paste your clipboard into any place that requests a route or segment ID.

Video of getting the segment ID from comma connect:

<img height="480">
""",
  },
  {
    "id": "builtin_wiki_faq_1",
    "title": "Wiki: FAQ (2/6)",
    "tags": ["wiki","openpilot","comma","faq"],
    "refresh": False,
    "text": """Source: openpilot Wiki — FAQ
https://github.com/commaai/openpilot/wiki/FAQ

400" alt="image" src="https://user-images.githubusercontent.com/5363/205464650-bec551fa-3320-4b3a-bdc6-63bea3cdb055.gif">

If your feedback is about the driver monitoring, make sure to include the segment ID with a description of the driver monitoring issue. This is more effective if you have driver video recording turned on in the settings. If not, turn it on now, and when it happens again, and report that incident.

If your feedback is about the driving behavior, go to #start-here and paste/share the segment ID with a description of the issue. 

You are also advised to tell your device to upload all related files, especially if you have a device with small storage due to space reclamation, but if you forget, comma staff can initiate that as well. You can initiate uploading by clicking on the Files button and selecting upload ## files under "All files". 

Screenshot of a #driving-feedback bug report on the comma.ai community Discord:

Screenshot of Files menu to click to upload all files of a drive. Click on upload ## files under "All files":

<img height="400" alt="image" src="https://user-images.githubusercontent.com/5363/188815682-6694c2f8-1d77-468e-9152-75a709477c9a.png">

What is lateral control?
In openpilot, lateral control means that openpilot can control your steering wheel.

What is longitudinal control?
In openpilot, longitudinal control means that openpilot can control gas and brake. If a car uses stock longitudinal control, that means the stock system that came with you car is in control.

How does Lane Change Assist Work?
Lane Change Assist only works at or above 30 mph/49 km/h. Activate the turn signal and, when it is safe to change lanes, gently nudge the wheel in the direction of the turn signal. Always pay attention when changing lanes, openpilot has limited or no ability to check if changing lanes is safe.

How to change to a specific release?

See the instructions for how to checkout a specific release.

When are my videos uploaded to the cloud?
With comma prime, low quality videos and condensed logs are uploaded constantly. When your device connects to Wi-Fi and the vehicle is stopped, it can upload the full logs and high quality videos if""",
  },
  {
    "id": "builtin_wiki_faq_2",
    "title": "Wiki: FAQ (3/6)",
    "tags": ["wiki","openpilot","comma","faq"],
    "refresh": False,
    "text": """Source: openpilot Wiki — FAQ
https://github.com/commaai/openpilot/wiki/FAQ

they are queued to upload from comma connect, or requested for training.

Where is my dashcam video footage stored? How can I stitch the segments together?

Videos are stored on the device in /data/media/0/realdata as 1 minute segment directories.  Each directory contains the log data and video in hevc form.  You can stitch these videos together using this Linux command:

cat fcamera1.hevc fcamera2.hevc fcamera3.hevc > output.hevc

The Windows equivalent for binary file concatenation would be
copy /b fcamera1.hevc+fcamera2.hevc+fcamera3.hevc output.hevc

If you rename the videos in sequence, you can use the shorter command:

cat fcamera > output.hevc

Yet another option that doesn't require any renaming, simply change the date and time to match the start of your drive:
cd /sdcard/realdata
find . -type f -wholename "2020-08-01--09-01-14--/.hevc" -exec cat {} + > drive.hevc

The output.hevc file can be uploaded to YouTube straight away, or played in VLC. But many others won’t know what to do with a .hevc file. So if sending, then download ffmpeg and convert it first. To make a .mpg copy for emailing etc., put the output.hevc file in the same folder as the ffmpeg program, then run a command like
ffmpeg -I output.hevc -qscale:v 1 output.mpg

Step by step guide for accessing video files here.

I get "Unrecognized car / dash cam mode" after installing Openpilot
If your car is on the compatibility list, follow these steps to fingerprint your car: https://github.com/commaai/openpilot/wiki/Fingerprinting

comma three

Why won't my comma three turn on?
The comma three is designed to be setup in the car. The USB-C to USB-C cable will only work when attached to the car harness in the vehicle. If you wish to power on the device inside, you must use a USB-A to USB-C cable and a wall charger.

What is a Dongle ID?
The Dongle ID is what identifies your device. It can be used to look up drives, and troubleshoot.

Where can I find my Dongle ID?
The device Dongle ID is found in Settings -> Device -> Dongle ID. If your device is paired with comma connect, you can also log into connect.comma.ai and grab your Dongle ID from the device list in the sidebar.

How do I delete my drives?""",
  },
  {
    "id": "builtin_wiki_faq_3",
    "title": "Wiki: FAQ (4/6)",
    "tags": ["wiki","openpilot","comma","faq"],
    "refresh": False,
    "text": """Source: openpilot Wiki — FAQ
https://github.com/commaai/openpilot/wiki/FAQ

Perform a factory reset to delete your drives fully (answer below this one). An uninstall / reinstall of openpilot will still keep the drives preserved on the device.

How can I reset the device?
You can uninstall openpilot by heading into Settings -> Software, scrolling to the bottom and tapping "uninstall". The device will be ready to install new software.

You can install a custom fork using the comma installer URL (https://installer.comma.ai/<user>/<branch>). For example, to install the master-ci branch you should enter https://installer.comma.ai/commaai/master-ci. See How to change to a specific release?

You can also factory reset the device by tapping and holding on the comma logo while the device boots. After that, the factory reset screen will come up.

If the device is in a bad state and you cannot factory reset it normally, you should check out the agnos repository for instructions to re-flash it using fastboot from a computer or laptop.

What is the comma three hardware?
Read more on the comma three page.

Will the comma three kill my car battery?
It shouldn't.  The comma three is designed to turn off after 30 hours of inactivity, or after a shorter amount of time if it senses the car battery is running low.

My storage space is filling up, How long are drive segments kept on my device?
Videos are saved on your device until additional space is needed.  When less than 5GB or 10% of the drive space remains, the oldest segments will be deleted to clear up room.  On the comma three 32GB stores approximately 1 hour of footage. The more storage you have, the more driving video you can store. The 250GB stores approximately 15 hours of footage, while the crosscountry edition with 1TB storage can save stores approximately 60 hours of footage. The oldest segments will be deleted to make room for new segments even if the old segments have not been uploaded. Want your video footage saved for longer? – Sign up for comma prime for 1 year of video storage.

comma two

The comma two is no longer supported. The most recent software release for the comma two is 0.8.13.1. Hot fixes may be pushed to the commatwomaster branch, but no new features will be released. Read m""",
  },
  {
    "id": "builtin_wiki_faq_4",
    "title": "Wiki: FAQ (5/6)",
    "tags": ["wiki","openpilot","comma","faq"],
    "refresh": False,
    "text": """Source: openpilot Wiki — FAQ
https://github.com/commaai/openpilot/wiki/FAQ

ore on the comma two page.

comma prime

What are comma points for?

What aren't they for? Same thing as Reddit karma.

Development

What is the openpilot development workflow? / What are the branches master, devel, and release?
Read this Medium post on Externalization.

What do the LED colors mean?
The LED indicates the status of the panda.

 White: CAN send enabled
 Red: This is your panda's heartbeat(power). It fades in and out
 Green: Bad firmware or firmware flashing (only green, fast)
 Blue (static): CAN detected
 Blue (fades in and out): power saving

How can I contribute?

To contribute to the openpilot codebase:
 Know Python / C++ (depends on which part of OP you want to contribute to)
 Learn Git and Github Pull Requests
 Read comma's blog posts related to development: https://blog.comma.ai/ (older posts on https://comma-ai.medium.com/)
 Read the openpilot CONTRIBUTING.md file
 Look at the issues page on Github (Particularly the "good first issue" label: https://github.com/commaai/openpilot/labels/good%20first%20issue)
 Read through the code and understand the architecture
 Search Discord with any questions you think of before asking (as per #guidelines )

If you're not into coding, feel free to join the comma pencil movement! You can help comma train their driving model by annotating driving data.

Join the Discord and check out the pinned messages in the #comma-pencil channel!

Discord Help

comma.ai is a very open company.  Their developers spend a lot of time on the Discord Server working with users and collaborating with other community developers.  This is awesome.  <u>But please don't abuse this.</u>  Asking questions that have already been answered is a waste of everyone's time.  Wasting developer time means slower improvements for us all.

Before Asking a Question
Please follow the instructions on the #Guidelines channel, specifically:

• Is it answered on https://comma.ai/faq ?
• Is it answered on https://wiki.comma.ai/ ?
• Is the answer found in the pins of a related channel? (Discord Pins)
• Has the question been asked before? (Discord Search)
• Have you read the channel description to confirm this is the correct place for your question?

Ho""",
  },
  {
    "id": "builtin_wiki_faq_5",
    "title": "Wiki: FAQ (6/6)",
    "tags": ["wiki","openpilot","comma","faq"],
    "refresh": False,
    "text": """Source: openpilot Wiki — FAQ
https://github.com/commaai/openpilot/wiki/FAQ

w do I search on discord?
Basic word searching is simple, but you may have better luck if you use search modifiers:

So if you have a question about a Toyota Camry you should search in the #toyota-lexus channel such as: in:#toyota-lexus <search term>

How do I read discord channel pins?
On the web app, it is as simple as clicking on the pin icon in the top right of the channel:

On the mobile app pins can be found by dragging from the right edge of the screen to the left.

How do I read the channel description?
On the desktop/web app, the channel description is located at the top of the page.  If the description is truncated, you can click on it to read the entire contents:

On the mobile app the channel description can be found by dragging from the right edge of the screen to the left.""",
  },
  {
    "id": "builtin_wiki_troubleshooting_0",
    "title": "Wiki: Troubleshooting (1/3)",
    "tags": ["wiki","openpilot","comma","troubleshooting"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Troubleshooting
https://github.com/commaai/openpilot/wiki/Troubleshooting

◄ Home

List of On Screen Messages

  "Harness Malfunction", "Please Check Hardware"
    See Fixing a Connection Issue

Alerts

 Communication Issue between Processes

CAN Errors

 CAN Error: Check Connections
 Radar Communication Issue
 Harness Box Error

Communication Issue between Processes

This error can mean a number of things. Essentially, it means not all the right processes are broadcasting to the comma two.

Common Issues

frontFrame not broadcasting

Rarely, the driver facing camera connector will become loose. When this happens, frontFrame will stop broadcasting - causing the Communication Issue between Processes error. Check if your driver facing camera still works by going to Settings -> Device -> Driver Camera View.

Some process not running

If you are running anything but release2 on your device, it is likely the fork maintainer missed something - or has an error in their DBC file. A good way to check is to SSH into your device and type tmux a

CAN Error

There are some message that the device is not receiving properly. Usually this is resolved by fixing a loose connection.

See Fixing a Connection Issue

Radar Communication Issue

This means the CAN bus that the radar sits on is not being received properly, which often means there is a loose cable somewhere.

See Fixing a Connection Issue

Harness Box Error

Similar to a radar error, this means that a CAN bus is not being received by the device.

See Fixing a Connection Issue

Hardware

Fixing a Connection Issue

Disconnect and reconnect every connector from every plug. Ensure each plug is firmly seated in its respective connector. Do this for everything! The comma power v2, the harness box, and the OBD-C cable to the comma device.

If the error persists, try flipping the OBD-C connector 180º - Sometimes the device will only accept all data lines from a certain direction on OBD-C connector.

If this doesn't fix the issue, the next step in troubleshooting is to purchase replacement cables and A/B compare.

EON discharges during use, or charges slowly

Get a better USB cable: thicker gauge and shorter length. The panda outputs at 5 volts, but due to cable resistance, there is voltage drop to the""",
  },
  {
    "id": "builtin_wiki_troubleshooting_1",
    "title": "Wiki: Troubleshooting (2/3)",
    "tags": ["wiki","openpilot","comma","troubleshooting"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Troubleshooting
https://github.com/commaai/openpilot/wiki/Troubleshooting

point where the EON cannot charge effectively.

Errors Relating to CAN or Not Detecting Ignition

For a cable to work, it must have all pins present. The only specs that do are USB-C 3.1 Gen 2 or USB-C with Thunderbolt.
Cables below are recommended and confirmed to work. We ship with a 1.5ft cable for most harnesses, or a 3 meter cable on Nissan and OBD-II harnesses.
 Anker USB-C Cable - similar length to included cable
 Angled USB-C Cable - slightly shorter than included cable

Car Unrecognized (Issues with FW Query)

 7ft Ethernet Cable
 10ft Ethernet Cable

If none of this resolves the issue, it is most likely a bad harness box. Contact support for further assistance, listing the things you tried.

comma three "Fan Malfunction Likely Hardware Issue"

Update the software to version 0.8.16 or higher. comma threes made in 2022 and beyond may have a new fan control chip that requires 0.8.16+.

https://blog.comma.ai/0816release/#improved-fan-control

Rebooting Device / Stuck on comma logo

Very rarely, the comma device can get corrupted during an update or by being unplugged without proper shut down.

If these don't work, or if the device continues to reboot while in 'fastboot' mode, contact support with your troubleshooting steps.

comma two

This is usually fixed by reflashing the NEOS operating system back onto the device.

A guide on how to do this is here for Windows, Mac, or Linux. https://github.com/commaai/eon-neos#restoring-on-linuxos-x

comma three

The first thing to try is to disconnect the device from power for 30 minutes and seeing if the issue persists. Do not skimp on the 30 minutes.

If not, the issue may be fixed by reflashing the AGNOS operating system back onto the device.

A guide on how to do this is here for Windows, Mac, or Linux. https://github.com/commaai/agnos

'No panda' on comma two

This is caused by the UNO board failing to communicate with the phone inside the comma device. Note: this is always expected when the comma device is powered outside the car.

If the comma device is plugged into the car harness, please proceed.

1. Reboot the comma device a few times

> Sometimes the device needs to be rebooted a few times to flash the int""",
  },
  {
    "id": "builtin_wiki_troubleshooting_2",
    "title": "Wiki: Troubleshooting (3/3)",
    "tags": ["wiki","openpilot","comma","troubleshooting"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Troubleshooting
https://github.com/commaai/openpilot/wiki/Troubleshooting

ernal UNO board. Did this fix the issue?

If you're running on a fork, you may have to SSH into your comma two and run make recover in cd /data/openpilot/panda/board

2. Run SSH commands to reset the UNO board

> There is a guide on how to SSH here: https://github.com/commaai/openpilot/wiki/SSH If you are still stuck, you can ask for help on discord.comma.ai.

cd /data/openpilot

PYTHONPATH=/data/openpilot python -c 'from selfdrive.thermald.thermald import setupeonfan, seteonfan; setupeonfan(); seteonfan(3);'

> When these commands are run, this error is expected and can be ignored. 'sh: can't create /sys/module/dwc3msm/parameters/otgswitch: Permission denied'

PYTHONPATH=/data/openpilot python -c 'from selfdrive.thermald.thermald import setupeonfan, seteonfan; setupeonfan(); seteonfan(0);'

3. Email support

If those commands still don't solve the issue after a device reboot, email support@comma.ai with your order # and your troubleshooting steps.

EON Fan Constantly Running

SSH into your device, and attempt to manually control the fan using this command.

 /data/openpilot && PYTHONPATH=/data/openpilot python -c 'from selfdrive.thermald.thermald import setupeonfan, seteonfan; setupeonfan(); seteonfan(1);' 

The value in the seteonfan function is the fan speed, anywhere between 0 and 3 (zero being off and 3 being the highest). Start with setting 1 and then set 0. (You will get a message about permission denied but the command still runs)

If your fan turns off when setting it to 0, then it is working properly. If it remains on, then your fan module is stuck in a state. Find other cooling solutions in #hw-unofficial on discord.

Advanced Debugging

First SSH into your device.  Once you are ssh'd into the device, you can monitor openpilot outputs with tmux\\
tmux a to attach to tmux window\\
  + d to exit tmux window (this is changed from the default ctrl-b + d)""",
  },
  {
    "id": "builtin_wiki_ssh_0",
    "title": "Wiki: SSH (1/8)",
    "tags": ["wiki","openpilot","comma","ssh"],
    "refresh": False,
    "text": """Source: openpilot Wiki — SSH
https://github.com/commaai/openpilot/wiki/SSH

NOTE: 🚧 openpilot 0.8.3 mandates usage of keys from a personal GitHub account and changes the SSH port from 8022 to 22.

Before You Start

1. You need a GitHub account. Make one if you don't already have one.
2. Enable SSH on your comma device:
    Two: Settings -> Network -> Enable SSH
    Three: Settings -> Network -> Advanced -> Enable SSH

Once that's done, pick an entry below to follow.

Table of Contents
=================

    Beginner
       Option 1 - Putty SSH Client
       Option 2 - Preinstalled OpenSSH Client on Windows 10 and up
       Option 2.Mac - Preinstalled OpenSSH Client on macOS
       Option 3 - Github's official instructions
    Advanced
       OpenSSH or Similar Client
       Connecting to ssh.comma.ai
          Using OpenSSH
          Using Putty to Connect to ssh.comma.ai
    Mobile SSH Clients
    Troubleshoot SSH Issues
       I'm hotspotting my comma two/phone. What IP do I use?
       When SSH is automatically enabled/disabled
       Invalid Format when trying to connect
       No route to host
       Permission denied (publickey,keyboard-interactive)

Beginner

NOTE: If you're just doing this to try to install forks, tunes, or whatnot, you may be better served by Shane's Fork Installer especially as a beginner. Of course, deeper debugging and whatnot usually eventually requires SSH access setup which the fork installer won't help with.

Option 1 - Putty SSH Client

(✨ Instructions are updated for 0.8.3+)

Putty is a simple beginner friendly way to connect to a comma device via SSH.
1. Download and install Putty.
2. Use PuTTYgen (part of Putty) to generate a key. Save both public (for reference) and private key.
3. Copy the contents of the textbox (probably starts with ssh-rsa, this also in your public key file) and add it to https://github.com/settings/ssh/new
4. Get the IP address of your EON/C2 in settings under Settings > WiFi > Open WiFi Settings > More Options > Three Dots in Top Left > Advanced (Please make sure your EON and your computer connect to the same WiFi)
5. Go to Settings [⚙️ icon] > Network > SSH Keys and press Add. Enter your GitHub username and press "⏎". You should see the SSH Keys option change to include your""",
  },
  {
    "id": "builtin_wiki_ssh_1",
    "title": "Wiki: SSH (2/8)",
    "tags": ["wiki","openpilot","comma","ssh"],
    "refresh": False,
    "text": """Source: openpilot Wiki — SSH
https://github.com/commaai/openpilot/wiki/SSH

GitHub username with the Add button changed to Remove.
    If a GitHub username is already there, press Remove.
    If you change or add new SSH keys on GitHub, you should repeat this step to pull down and refresh the authorized SSH keys data on the device from GitHub.
6. Make sure Settings [⚙️ icon] > Network > Enable SSH is enabled. It should be green.
7. Open Putty, and enter the hostname as comma@<ipaddress>  where <ipaddress> is your device IP and leave the port to 22 (screenshot below showing port 8022 and the root user is from an older version):

8. Load the private key file in Connection > SSH > Auth > Private key for authentication:

9. Finally, click Open on the bottom of the program, and if all works correctly, an SSH connection will be created. You will see a prompt with "comma@localhost:/data/openpilot$"

Option 2 - Pre-installed OpenSSH client on Windows 10 and up

(✨ Instructions are updated for 0.8.3+)

Windows 10 and up already comes with a SSH client and has everything you need to SSH into an EON/C2/C3. No additional software download or installation required.

1. Open PowerShell. You can find PowerShell by pressing the Start Menu and typing "PowerShell".
    You can copy and paste commands from this document by copying, and then "right-clicking" on the PowerShell window to "paste". Try copying and running this command: echo hello. The PowerShell window should print out "hello".
    Command Prompt is not the same as PowerShell! Do not substitute Command Prompt in place of PowerShell.
2. You'll need to have an SSH key on your PC that is added to GitHub to proceed.  For instructions on how to create a key and upload it to GitHub, please follow these steps.  If you have already created a key and uploaded it to GitHub, skip to the next step.
   1. Run ssh-keygen -t ed25519 -f $HOME/.ssh/ided25519. When there is a prompt to "Enter passphrase (empty for no passphrase):", just press Enter for no passphrase.
          This will generate a private key and public key and store them in a ".ssh" folder in your home directory folder on your machine.
   2. Run Get-Content $HOME\\.ssh\\ided25519.pub | Set-Clipboard
          This will copy the contents of the""",
  },
  {
    "id": "builtin_wiki_ssh_2",
    "title": "Wiki: SSH (3/8)",
    "tags": ["wiki","openpilot","comma","ssh"],
    "refresh": False,
    "text": """Source: openpilot Wiki — SSH
https://github.com/commaai/openpilot/wiki/SSH

file ided25519.pub, the public key counterpart to the private key generated in the previous step, to your clipboard.
   3. Visit https://github.com/settings/ssh/new, paste the contents of your clipboard to "Key", give it a name of your choice in "Title", and press Add SSH Key.
3. Run ssh -T git@github.com to check if GitHub is able to successfully identify you with the private key on your local system.
    You should get "Hi \\<your github username here\\>! You've successfully authenticated, but GitHub does not provide shell access."
       If you do not get this message, do/redo the key creation and upload instructions in the previous step.
    If you get an "authenticity of host cannot be determined message", answer yes.
4. Make sure your EON/C2/C3 and your computer connect to the same WiFi or network.
5.
    Get the IP address of your EON/C2 in settings under Settings [⚙️ icon] > Network > WiFi Settings > Three Dots in Top Right > Advanced and scroll to the bottom.
    Get the IP address of your C3 in settings under Settings [⚙️ icon] > Network > Advanced
6. Go to Settings [⚙️ icon] > Network [ > Advanced, if C3] > SSH Keys and press Add. Enter your GitHub username and press "⏎". You should see the SSH Keys option change to include your GitHub username with the Add button changed to Remove.
    If a GitHub username is already there, press Remove to make Add reappear.
    If you change or add new SSH keys on GitHub, you should repeat this step to pull down and refresh the authorized SSH keys data on the device from GitHub.
7. Make sure Settings [⚙️ icon] > Network [ > Advanced, if C3] > Enable SSH is enabled. Newer OP has it under Settings [⚙️ icon] > Developer. It should be green.
8. Run the command ssh comma@555.555.555.555 after replacing 555.555.555.555 with the IP address you discovered in the settings earlier. You should see a blue-ish prompt with "/data/openpilot" which confirms you are connected.
    If you get an "authenticity of host cannot be determined message", answer yes.
    Older device/OS and "port 22: Connection Refused"?
    C3 is compatible with Visual Studio Code Remote - SSH. See page for details. 

Option 2.Mac - Pre-installed OpenSSH clie""",
  },
  {
    "id": "builtin_wiki_ssh_3",
    "title": "Wiki: SSH (4/8)",
    "tags": ["wiki","openpilot","comma","ssh"],
    "refresh": False,
    "text": """Source: openpilot Wiki — SSH
https://github.com/commaai/openpilot/wiki/SSH

nt on macOS

(✨ Instructions are updated for 0.8.3+)

macOS already comes with a SSH client and has everything you need to SSH into an EON/C2/C3. No additional software download or installation required.

1. Open Terminal. You can find Terminal by opening Spotlight in the top-right corner and typing "Terminal".
    You can copy and paste commands from this document by copying, and then pasting with paste from the Edit menu. Try copying and running this command: echo hello. The Terminal window should print out "hello".
2. You'll need to have an SSH key on your Mac that is added to GitHub to proceed.  For instructions on how to create a key and upload it to GitHub, please follow these steps.  If you have already created a key and uploaded it to GitHub, skip to the next step.
   1. Run ssh-keygen -t ed25519 -f $HOME/.ssh/ided25519. When there is a prompt to "Enter passphrase (empty for no passphrase):", just press Return for no passphrase.
        This will generate a private key and public key and store them in a ".ssh" folder in your home directory folder on your machine.
   2. Run cat $HOME/.ssh/ided25519.pub | pbcopy
        This will copy the contents of the file ided25519.pub, the public key counterpart to the private key generated in the previous step, to your clipboard.
   3. Visit https://github.com/settings/ssh/new, paste the contents of your clipboard to "Key", give it a name of your choice in "Title", and press Add SSH Key.
3. Run ssh -T git@github.com to check if GitHub is able to successfully identify you with the private key on your local system.
    You should get "Hi \\<your github username here\\>! You've successfully authenticated, but GitHub does not provide shell access."
       If you do not get this message, do/redo the key creation and upload instructions in the previous step.
    If you get an "authenticity of host cannot be determined message", answer yes.
4. Make sure your EON/C2/C3 and your computer connect to the same WiFi or network.
5.
    Get the IP address of your EON/C2 in settings under Settings [⚙️ icon] > Network > WiFi Settings > Three Dots in Top Right > Advanced and scroll to the bottom.
    Get the IP address of your C3 in set""",
  },
  {
    "id": "builtin_wiki_ssh_4",
    "title": "Wiki: SSH (5/8)",
    "tags": ["wiki","openpilot","comma","ssh"],
    "refresh": False,
    "text": """Source: openpilot Wiki — SSH
https://github.com/commaai/openpilot/wiki/SSH

tings under Settings [⚙️ icon] > Network > Advanced
6. Go to Settings [⚙️ icon] > Network [ > Advanced, if C3] > SSH Keys and press Add. Enter your GitHub username and press "⏎". You should see the SSH Keys option change to include your GitHub username with the Add button changed to Remove.
    If a GitHub username is already there, press Remove to make Add reappear.
    If you change or add new SSH keys on GitHub, you should repeat this step to pull down and refresh the authorized SSH keys data on the device from GitHub.
7. Make sure Settings [⚙️ icon] > Network [ > Advanced, if C3] > Enable SSH is enabled. Newer OP has it under Settings [⚙️ icon] > Developer. It should be green.
8. Run the command ssh comma@555.555.555.555 after replacing 555.555.555.555 with the IP address you discovered in the settings earlier. You should see a blue-ish prompt with "/data/openpilot" which confirms you are connected.
    If you get an "authenticity of host cannot be determined message", answer yes.
    Older device/OS and "port 22: Connection Refused"?
    C3 is compatible with Visual Studio Code Remote - SSH. See page for details. 

Option 3 - Github's official instructions

If nothing above works, perhaps instructions based more from GitHub's official documentation may work. They certainly got paid a lot more than the person(s) writing this page.

1. Follow the steps here: to create and test your GitHub SSH keys.
4. Enter a GitHub username for SSH: Settings -> Network -> SSH Keys (hit Remove and then Add if needed).  This enables SSH to the comma two via a private key corresponding to any public key saved in your GitHub settings.

Advanced
This section assumes that you have used SSH before.  If you want to use Putty, use the instructions above.

OpenSSH or Similar Client

(⚠ Instructions are not updated for 0.8.3+)

1. Download the private key from the openpilot repo.. Save the key file as a text file and name it something like key.pem.
2. Open a terminal
3. Run C$ chmod 600 key.pem (otherwise, the system will think the text file is not safe).
4. Get the IP address of your comma two from Settings > WiFi > Open WiFi Settings > More Options > Options (top right icon) > Advanc""",
  },
  {
    "id": "builtin_wiki_ssh_5",
    "title": "Wiki: SSH (6/8)",
    "tags": ["wiki","openpilot","comma","ssh"],
    "refresh": False,
    "text": """Source: openpilot Wiki — SSH
https://github.com/commaai/openpilot/wiki/SSH

ed (please make sure your comma two and your computer connect to the same WiFi).
5. Ping the device address from your computer to make sure it is reachable.
6. Under a Unix/Linux, macOS terminal or Windows 10 with OpenSSH, use the command:

$ssh comma@<IP address of comma two> -p 8022 -i key.pem

Example:
$ ssh comma@192.168.1.100 -p 8022 -i key.pem

Connecting to ssh.comma.ai
Using OpenSSH
The instructions on ssh.comma.ai for a saved connection are slightly wrong.  If you want to connect to your comma device by typing ssh comma-{dongleid} your ~/.ssh/config file should read as follows (Note the ${%h} entries in the ProxyCommand):

Host comma-
  Port 22
  User comma
  IdentityFile ~/.ssh/mygithubkey
  ProxyCommand ssh ${%h}@ssh.comma.ai -W ${%h}:%p

Host ssh.comma.ai
  Hostname ssh.comma.ai
  Port 22
  IdentityFile ~/.ssh/mygithubkey

Better yet, if you just want to connect directly to your vehicle without memorizing your DongleID you can do as follows (replacing <DongleID> with, you know the ID.  You can change the hostname <comma-rav4> to anything) then you can use ssh comma-rav4:

Host comma-rav4
  Port 22
  User comma
  IdentityFile ~/.ssh/mygithubkey
  ProxyCommand ssh <DongleID>@ssh.comma.ai -W <DongleID>:%p

Host ssh.comma.ai
  Port 22
  IdentityFile ~/.ssh/mygithubkey
  Hostname ssh.comma.ai

The one time connection listed on ssh.comma.ai works just fine.

Using Putty to Connect to ssh.comma.ai
Using Putty to connect to ssh.comma.ai is a bit involved.  First, it assumes you have already gotten the direct SSH connection using Putty to work as described above.

1. Start the pageant program (it is found in the same folder as Putty).
2. Pageant will load in your taskbar .  Right click the icon and select View Keys

3. Click Add Key

4. Locate and select your private key idrsa.ppk
5. After opening the key, you should see it in the key list

6. You can click Close (pageant will keep running)
7. Open Putty
8. In the Host Name enter comma@<dongleid> where <dongleid> is your dongle id and Port 22

9. Under Connection > Proxy enter the following:
- Proxy type Local
- Proxy hostname ssh.comma.ai
- Port 22
- Telnet command or local proxy command plink.exe -v %host@%""",
  },
  {
    "id": "builtin_wiki_ssh_6",
    "title": "Wiki: SSH (7/8)",
    "tags": ["wiki","openpilot","comma","ssh"],
    "refresh": False,
    "text": """Source: openpilot Wiki — SSH
https://github.com/commaai/openpilot/wiki/SSH

proxyhost -nc %host:%port

10. Go back to Session
11. Type a name in Saved Session

12. Click Save
13. Click Open
14. You may get a few prompts to accept the server fingerprints.

You should now be connected to your device.  If you made any mistakes, you can load the saved session and fix the errors, but be sure to click Save after making any changes, or they will not be permanent.

Pageant will keep running until you log off your computer.  You can also exit pageant by right-clicking the taskbar icon and selecting Exit.

Mobile SSH Clients

 Android
   ConnectBot
   Termius
    - Supports Putty .ppk key.
   JuiceSSH

 iOS
   Termius

Troubleshoot SSH Issues

I'm hotspotting my comma two/phone. What IP do I use?
If your Android phone is connected to comma two: comma two should be 192.168.43.1

If your comma two is connected to your Android phone: comma two should be 192.168.43.2

If you're connecting your comma two to an iPhone: comma two should be 172.20.10.2

When SSH is automatically enabled/disabled
WiFi\\
SSH is automatically enabled with a clean comma two factory reset. It is disabled once you start installing dashcam or custom software. You then will need to enable SSH through the phone's UI settings if you want to SSH after install. SSH'ing into the phone before installing software (and typing tmux a) is helpful in understanding what is going on if you are having trouble performing your install.\\
\\
LTE\\
You can always SSH via the LTE connection. Follow the guide here: ssh.comma.ai

Invalid Format when trying to connect
Something is wrong with your private key.  Again, Putty and OpenSSH private keys are in different formats, make sure you are using the correct one.

No route to host
The IP address to your device is wrong in some way.  Are both your computer and device on the same network, is the IP address typed correctly?

Permission denied (publickey,keyboard-interactive)
This is a generic authentication error and could mean many things.  Did you enable SSH on the device?  If you entered a GitHub Username, did you use a private key that matches one in your GitHub account? Did you correctly download and save the private key file?  Does the private key hav""",
  },
  {
    "id": "builtin_wiki_ssh_7",
    "title": "Wiki: SSH (8/8)",
    "tags": ["wiki","openpilot","comma","ssh"],
    "refresh": False,
    "text": """Source: openpilot Wiki — SSH
https://github.com/commaai/openpilot/wiki/SSH

e the correct permissions?

With the 0.8.3 update, the SSH requirements have changed. If you have previously SSH'd into your device, you may need to delete the old key from from the '/user/.ssh' folder. Remove the key from 'knownhosts' as well as the key file, especially if you have used workbench in the past.

port 22: Connection refused

Older devices and OSes only listened on port 8022 in the past. Use port 8022 instead.

Incoming packet was garbled on decryption

When using putty with ssh.comma.ai for the first time, plink may not properly handle accepting the host keys. To fix this, configure a SSH session to ssh.comma.ai to manually accept the host key and then the proxy session should go through properly.

Connecting VSCode to the comma three

It is possible to use VSCode Remote to remotely edit on a comma three device as the system is a glibc-based Linux system. There are some caveats though as the home directory is small. To make VSCode work, SSH in and do mkdir -p /data/vscode-server && ln -s /data/vscode-server ~/.vscode-server. After that, setup VSCode Remote to login to the comma three as the comma user and it will install its dependencies remotely.""",
  },
  {
    "id": "builtin_wiki_tuning_0",
    "title": "Wiki: Tuning (1/9)",
    "tags": ["wiki","openpilot","comma","tuning"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Tuning
https://github.com/commaai/openpilot/wiki/Tuning

◄ Home

Using PlotJuggler
Using PlotJuggler helps objectively determine if you are tuning in the "right direction" A quick tutorial for openpilot can be found here.

Breakpoint (BP) and Value (V) Lists
When you see xBP and xV, that means that the speeds defined in the breakpoint list (xBP) correspond to the values in the value (xV) list.

For example, take xBP = [0., 5., 35.] (in m/s) and xV = [1.0, 1.5, 2.0]

If code is easier to read than English, np.interp(20, [0., 5., 35.], [1.0, 1.5, 2.0]) = 1.75

When you are traveling 5 m/s, 1.5 is the value that openpilot uses, for 35 m/s, 2.0 is the corresponding value. Speeds in between the defined speeds in xBP are linearly interpolated, so if you're halfway between 5 and 35 m/s the output will be halfway between 1.5 and 2.0.

Use the speed conversion table for quick conversions.

Lateral Tuning
Tuning is done mainly in tunes.py OR interface.py. Tunes are in different places for different OEMs.

PI Tuning Strategy

PI tuning is done mainly in tunes.py OR interface.py, depends on OEM.

These are the relevant CarParams values that need adjustment:

selfdrive/car/<make>/interface.py OR selfdrive/car/<make>/tunes.py

ret.steerRatio = 16.8
ret.steerRateCost = 0.5
ret.steerActuatorDelay = 0.
ret.lateralTuning.pid.kpBP = [10., 41.0]
ret.lateralTuning.pid.kpV = [0.18, 0.275]
ret.lateralTuning.pid.kiBP = [10., 41.0]
ret.lateralTuning.pid.kiV = [0.01, 0.021]
ret.lateralTuning.pid.kf = 0.0002

Note that steerRatio is part of liveParams automatically calculated, but doesn't seem to be used yet, so the value in interface.py can have a large impact.

steerActuatorDelay is vital (as it is INDI), and should be adjusted first. This can be relatively easily calculated in PlotJuggler by overlaying the desired torque with the actual torque graphs for even a short drive. Even very small adjustments can have a huge impact on cornering.

The PI controller has 3 sets of settings. Proportional, Integral, and Feedforward. Reviewing the Wikipedia article on PID controllers to get a basic understanding of the purpose of these.

kpBP and kiBP are generally identical. The breakpoint units are meters/s and apply to the vehicle speed. Most cars only""",
  },
  {
    "id": "builtin_wiki_tuning_1",
    "title": "Wiki: Tuning (2/9)",
    "tags": ["wiki","openpilot","comma","tuning"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Tuning
https://github.com/commaai/openpilot/wiki/Tuning

have two BPs - a low speed and a high speed (41 m/s is about 90 mph for example). The purpose of these tuning arrays is to tweak the proportional and integral gain based on vehicle speed.

kpV and kiV are gain applied to the output of the I and P calculation, which is a scale of 0 to +-1, 0 being no torque, +-1 being 100% of available torque in either direction. This is a gross simplification, but should help get the rough idea.

Conceptual descriptions of the PIDF components:
 Feedforward is the part of the steering controller that only cares about the desired steering angle (how sharp the curve is). So feedforward only comes into play in curves when the desired steering angle is non-zero, and the greater the angle, the greater the feedforward response, which is scaled by kf. To tune kf, you observe if OpenPilot enters curves too early/late and rides curves too far inside/outside. If it enters too early (late) and/or rides too far inside (outside), then kf is too high (low) and should be lowered (raised) in 10% increments until it enters correctly and rides center. 
 Proportional gain responds proportionally to the instantaneous error being controlled. The greater the error, the greater the corrective response, linearly, and scaled according to kp. In this case, where we're controlling the steering angle, the proportional gain alone cannot completely correct for error, becuase when the error is close to zero, so is the proportional response. The best way to tune kp is then using nudgeless lane change on straight roads (no feedforward response), which creates a sudden (so doesn't trigger the integral response) change in course that results in a reproducible error source that triggers the proportional and derivative responses. Set kd to zero to best assess kp. If the lane change feels too assertive or jerky, lower kp. If too weak, increase kp. 
 Integral gain responds based on the accumulated error, so if you're missing the target continually, the integral response builds the longer you're off in the same direction. This corrects for things like persistent crosswinds, inconsistent tire pressures, or dramatic road roll that roll compensation fails to fully compen""",
  },
  {
    "id": "builtin_wiki_tuning_2",
    "title": "Wiki: Tuning (3/9)",
    "tags": ["wiki","openpilot","comma","tuning"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Tuning
https://github.com/commaai/openpilot/wiki/Tuning

sate for. The drawback is that integral gain can "wind up", overshooting the desired angle, causing lateral oscillations, ping-ponging back and forth about lane center.
 Derivative gain responds to the rate of change of error. The benefits are two-fold. First, note that the proportional and integral responses always push against the error until the error is zero (and due to integral wind-up, integral can push past zero even), which necessarily results in overshoot and oscillations. In such an overshooting case, when you're returning to lane center and the error (let's say positive) is decreasing, the error rate wil be negative even though the error is still positive, so the derivative response is pushing against the proportional and integral overshoot. Second, if you're quickly leaving lane center then the rate of change of error is positive along with the error, so the derivative here helps along with the proportional and integral responses to correct for the error. Too high of kd is indicated by a jerky initial correction when using nudgeles lane change on straight roads.
 Simple tuning strategy: Tune kf and kp with ki set to zero, then set ki to 1/10th the value of kp or less, and kd to 1/20th the value of kp or less. If lateral oscillations occur, lower ki in 10% increments until they are no longer observed. 

The following is a procedure based on suggestions from @clockenessmnstr:

Note: Tune kf and kp/ki separately.
1. With the kp & ki set at 0, look through the OP code for a similar vehicle's kf to use as a starting point.
Or start with 0.00001. kf only applies to curves, so when testing don't worry about straightaway behavior.
If you start with 0.00001, try 0.00003 and test again. Use your judgement on how much to increase each time
kf alone should make the steering angle close to target angle in a harder turn - but will not necessarily be properly aligned. This is ok.
Increase kf until the car almost makes turns, but doesn't over shoot / oversteer on it's own.
If kf is too high, it will turn too hard, pact the correct curvature, or at the end of a curve it will have trouble straightening out.
3. Sometimes actuator delay can be fine tuned a little once k""",
  },
  {
    "id": "builtin_wiki_tuning_3",
    "title": "Wiki: Tuning (4/9)",
    "tags": ["wiki","openpilot","comma","tuning"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Tuning
https://github.com/commaai/openpilot/wiki/Tuning

f is "going through" turns.
The only steering OP does at this point is for turns, so turn initiation timing should be obvious.
Pay close attention to when OP begins turning the wheel. If it seem too early or too late, adjust the actuator delay. TINY Adjustments!
   Lower delay "waits to turn longer", higher delay "starts the turn sooner"
4. Set kf to 0, and start tuning kp. Again, use an initial value of a similar car.
kp turns the wheel to get you back to center. As you increase it, the car will center better and better, then it will begin to oscillate (i.e. over shoot in one direction, then the other back and forth). Increase it till it centers well and starts to oscillate.
5. Then cut back kp so it doesn't oscillate anywhere (turns/straights/pulling the wheel for a second)
6. Leaving kp on, ki can then be introduced and raised to smooth out and hold center and hold turns. This is a very powerful setting, and as you add it, the car may begin to oscillate. If it does, nudge kp down a bit. ki applies to "persistent" errors - sidewinds, slanted roads, and centering in long curves. It has a smoothing impact. Increase it till it starts causing problems (too rigid maybe?)
7. Now reintroduce kf. Watch for oscillations again. If they are only showing up in curves, lower kf (small steps) and/or kp just a tiny bit at a time. Oscillations on straight sections just reduce kp. If it is overshooting curves, or seeming to "keep turning too long", "taking too long to straighten out", you may need to reduce ki (although I have found tiny reductions in kf to resolve this as well)
8. Once again, watch when it enters turns very closely, and if it's too early or too late adjust steer actuator delay accordingly.

This process can be very time consuming - there are several options out there with live tune adjusting abilities while riding as a passenger.

INDI Tuning Strategy
 - Search Discord / Github for prior INDI tuning efforts for your vehicle
 - Vary one parameter at a time, by less than 10%. Parameters affect each other.
 - Use a well known test route with excellent lane markings, long straights, varying curvature, varying speeds.
  - Don't confuse tuning with variable plannin""",
  },
  {
    "id": "builtin_wiki_tuning_4",
    "title": "Wiki: Tuning (5/9)",
    "tags": ["wiki","openpilot","comma","tuning"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Tuning
https://github.com/commaai/openpilot/wiki/Tuning

g from poor lane markings, or unexpected behavior from unknown roads.
 - Start with moderate values for outer (angle error) and inner (rate error) loops, e.g. Prius's outer 3, inner 4.
 - Avoid instability
  - Undertuned is sloppy, late, weave
  - Overtuned is jerky, too early, over-correcting, oscillating
  - Find the lower and upper edges of stability, then use a performant moderate value.
 - INDI tunes live in selfdrive/car/<make>/tunes.py

1. CRITICAL: Tune steerActuatorDelay first.
2. Tune actuator effectiveness. Lowest value without over-saturating (feels like bang-bang control). (May vary with speed?)
3. Tune time constant. Lowest value with smooth actuation. This is an exponential moving average of previous outputs.
4. Tune inner loop (rate error gain). Highest value that still gives smooth control. Effects turning into curves. This multiplies the outer loop, so increasing this may need to decrease the outer loop.
5. Tune outer loop (angle error gain). Highest value that still gives smooth control. Effects lane centering.

Notes on INDI tuning parameters
 steerActuatorDelay
   Plan(now + steerActuatorDelay) -> Vehicle Model -> Desired Steer Output
   Emits controls ahead on plan
   Crude
     If turning too early, decrease steerActuatorDelay
     If turning too late, increase steerActuatorDelay
     On straight section, vary in small steps +/- from best guess until the plan wobbles. Use mid-point.
   Fine
     Normalize steer torque command and lateral acceleration, which should be dependent but delayed
     Find median phase delay in frequency domain?
     Find maximum correlation when varying time delay?
 lateralTuning.indi.actuatorEffectiveness
   As effectiveness increases, actuation strength decreases
   Too high: weak, sloppy lane centering, slow oscillation, can't follow high curvature, high steering error causes snappy corrections
   Too low: overpower, saturation, jerky, fast oscillation, bang-bang control
   Just right: Highest value able to maintain good lane centering.
 lateralTuning.indi.timeConstant
   Exponential moving average of prior output steer
   Too high: sloppy lane centering
   Too low: noisy actuation, responds to every bump, may""",
  },
  {
    "id": "builtin_wiki_tuning_5",
    "title": "Wiki: Tuning (6/9)",
    "tags": ["wiki","openpilot","comma","tuning"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Tuning
https://github.com/commaai/openpilot/wiki/Tuning

be unable to maintain lane center due to rapid actuation
   Just right: above noisy actuation and lane centering instability
 lateralTuning.indi.innerLoopGain
   Steer rate error gain
   Too high: jerky oscillation in high curvature
   Too low: sloppy, cannot accomplish desired steer angle
   Just right: brief snap on entering high curvature
 lateralTuning.indi.outerLoopGain
   Steer error gain
   Too high: twitchy hyper lane centering, oversteering
   Too low: sloppy, long hugging in turns (not to be confused with over/understeering), all over lane (no tendency to approach the center)
   Just right: crisp lane centering

Longitudinal Tuning
Skip to tuning

Introduction

Understanding how openpilot decides what speed to travel
This will change when comma.ai moves to using the driving model for full longitudinal control.

openpilot uses your car's radar (which returns up to 16 to 18 detected objects) and the driving model to select a radar point using the camera. openpilot runs the selected radar point (called a lead) through a kalman filter to get a more accurate acceleration and speed of the lead. The lead's speed, acceleration, and distance is sent to a longitudinal MPC which after some complex math returns a desired speed to travel (along with desired acceleration) to longmpc.py. This speed (which we'll mostly focus on) is then used by longcontrol.py and a PI loop (not PID) which controls the gas and brakes.

TL;DR: Input the lead's speed, acceleration, and distance to the LongitudinalMpc, and a desired speed to travel is returned (along with extra values like future desired speed, acceleration, etc.).

Your vehicle's interface file
Now that you have some background on how openpilot's LongitudinalMpc works (it's not necessary to understand everything), we can move on to understanding how the PI loop controls your vehicle's gas and brakes and subsequently actually tuning your vehicle. Here are some of the parameters that longcontrol's PI loop uses to output a gas signal sent to the car.

selfdrive/car/toyota/tunes.py

tune.deadzoneBP = [0., 8.05]
tune.deadzoneV = [.0, .14]
tune.kpBP = [0., 5., 20.]
tune.kpV = [1.3, 1.0, 0.7]
tune.kiBP = [0., 5., 12., 20., 27.]""",
  },
  {
    "id": "builtin_wiki_tuning_6",
    "title": "Wiki: Tuning (7/9)",
    "tags": ["wiki","openpilot","comma","tuning"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Tuning
https://github.com/commaai/openpilot/wiki/Tuning

tune.kiV = [.35, .23, .20, .17, .1]

Understanding the PI controller
 Proportional (kpBP and kpV):
  - Again, kpBP is the breakpoint list and kpV is the values list that the PI loop uses in operation. kpV or kp stands for proportional gain, and it's the simplest part of the PI controller. If you just had a P controller the output would simply be defined as (desired speed - current speed)  proportional gain. The first section is also known as the error. In code (from pid.py), this would look like: error  self.kp. That proportional gain we're multiplying here changes based on your speed.

    Once you get the output, you would simply return the value and use it as the gas/brake value to send to the car.

 Integral (kiBP and kiV):
  - kiV or ki stands for integral gain. You can think of integral as the error (again, desired speed - current speed) that builds up over time. For a simple example, let's say that the error is 1 for one iteration (desired speed is 1 mph faster than our current speed). Then in the next iteration let's say we're still traveling at the same speed and we still want to go 1 mph faster.

    We now take the previous error and the current error, which both are 1 and sum them. Now our integral value is 2 (not gain, that's what is multiplied by 2 here to get the final output). This continues forever, so if the error is too small from proportional to bring us to our desired speed (think something like 50 mph - 49.5 mph), integral would build up over time and help us apply more gas to reach the desired speed.

    In a more concrete example, let's say we're approaching a steep hill and we want to maintain our speed of 50 mph. Of course the hill makes us lose some speed initially as the incline starts to increase, so proportional would kick in as our error increases. However, once we get close enough to the desired speed again, the output of proportional would fall to near 0, causing us to lose speed again. Here's where integral steps in. It can see the sum of the past errors, so integral would build up the longer we're lower than 50 mph, causing a higher gas output.

    In pseudo code, this looks like self.i = self.i + (error  integral gain). You""",
  },
  {
    "id": "builtin_wiki_tuning_7",
    "title": "Wiki: Tuning (8/9)",
    "tags": ["wiki","openpilot","comma","tuning"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Tuning
https://github.com/commaai/openpilot/wiki/Tuning

can see the two things that increase the output of the integral factor are error and time. If the error is large, integral increases. And if any error exists for some amount of time, integral increases.

 gasMaxBP and gasMaxV:
  - gasMaxV represents the maximum percentage of gas (0 being no gas and 1 being 100% gas) allowed to be output by the PI loop. Since gasMaxBP = [0.] and gasMaxV = [0.5], the maximum gas allowed by the PI loop is 50% which is used at all speeds.

The output of the PI loop (excluding feedforward) is essentially the sum of the output of the proportional factor and integral factor. control = self.p + self.i

Tuning the longitudinal PI controller
The two main factors you can tune to get a different response out of the long PI loop are of course proportional and integral. To make the tuning process less complex, it's said to set the integral gain to all 0's so the only thing that's interacting with the output is proportional at first.

- When to increase proportional:
  1. If your car doesn't give enough gas or brake to reach the set cruise speed in a timely manner.
  2. If your car doesn't brake enough when you approach a stopped lead.
- When to decrease proportional:
  1. If your car applies so much gas or brake trying to reach the desired speed that it doesn't feel smooth.
  2. If it doesn't feel smooth when reacting to a change in desired speed.

After you have it tuned so that it feels smooth enough either cruising without a lead, or with a lead that is always changing its speed, it's time to start tuning integral.

- When to increase integral:
  1. If when the lead is decelerating/accelerating over a few seconds and the car doesn't give enough gas or brake to maintain a safe/reasonable distance
  2. If you're traveling up or down a hill and the car doesn't give enough gas or brake to maintain your desired speed.
- When to decrease integral:
  1. If you start to experience overshoot (most easily identifiable on hills); ex. once you reach the crest of a hill and your car continues to apply gas when it should start to ease off.

Appendix

Speed Conversion Table
| m/s | mph | kph |
|-----|-----|-----|
| 5   | 11  | 18  |
| 10  | 22  | 36  |""",
  },
  {
    "id": "builtin_wiki_tuning_8",
    "title": "Wiki: Tuning (9/9)",
    "tags": ["wiki","openpilot","comma","tuning"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Tuning
https://github.com/commaai/openpilot/wiki/Tuning

| 15  | 34  | 54  |
| 20  | 45  | 72  |
| 25  | 56  | 90  |
| 30  | 67  | 108 |
| 35  | 78  | 126 |
| 40  | 89  | 144 |""",
  },
  {
    "id": "builtin_wiki_development_0",
    "title": "Wiki: Development",
    "tags": ["wiki","openpilot","comma","development"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Development
https://github.com/commaai/openpilot/wiki/Development

openpilot Development
Community guides that help you contribute to openpilot, or make your own modifications to the open source code. Especially for common procedures, please edit a page if the instructions don't seem to work. It is also recommended to join the comma Discord to get help from other users / developers in case you have any questions or want to share feedback. If you find bugs, it is probably better to report them as issues on Github than to post them on Discord.

Getting Started
 Introduction to openpilot
 openpilot Tools
 comma API
 Simulation

Common procedures
 SSH into your device
 Update/modify openpilot
 Fingerprint your car
 Using cabana

Advanced (Developers Only)

Software
 Custom forks
   How to pull branches from multiple forks
 Tuning

Hardware
 comma pedal
 Smart DSU
 Webcam on PC
 Zorro Steering Sensor
 Unofficial Hardware
 Retired Hardware
  ## Flashing
   panda Flashing
   Flashing AGNOS
   Flashing NEOS

Other
 Building and deploying a release branch
 Requirements
 OP Customizations""",
  },
  {
    "id": "builtin_wiki_installing_openpilot_0",
    "title": "Wiki: Installing openpilot (1/2)",
    "tags": ["wiki","openpilot","comma","installing"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Installing openpilot
https://github.com/commaai/openpilot/wiki/Installing-openpilot

◄ Home

On comma two or three

Prerequisite
Your comma device must be setup in your car prior to installing openpilot. Please follow the official setup procedures at comma.ai/setup or the device installation guide.

Upon first boot of the comma device, do not tap "Dashcam software" and instead proceed to the installation paragraph below. If you already have, read the paragraph on removing the Dashcam software.

Note: The comma device is intended to be setup in your car. If you attempt to power up the comma device outside of your vehicle, you need to use a USB-A to USB-C adapter with a high output wall charger (min 2A output suggested).

Install openpilot

Note: only follow this if you have not selected "Dashcam software" on the first boot of the comma device.

Video walkthrough.

1. When your device boots up for the first time, you'll have the choice of either installing "Dashcam software" or "Custom Software (Advanced)." Let's go through this process to install openpilot instead of the Dashcam software (which does not pilot the car).
2. Ensure you're connected either to a WiFi hotspot, or that you can "Skip" the WiFi hotspot selection (that means the SIM card is connected to a network).
3. Select "Custom Software (Advanced)."
4. Enter openpilot.comma.ai and click "Install Software."
5. Your device will then download the software, and install it. Note that when using the SIM card for this, you may need to retry once or twice depending on the quality of the connection. When using a wall charger at your desk, make sure it can output 2-3A (installation draws just a little above 1.0A)
6. Closely follow the training guide.
7. Train (calibrate) the system on your car by manually driving faster than 15 mph (~ 25 km/h) for a few minutes. The screen will show what the camera sees after the training is complete.
8. You may now enable cruise control as per usual, and openpilot will take control after emitting a sound.

Remove Dashcam software

If you selected the "Dashcam" software during setup you should uninstall with the following steps

1. Click on the settings icon (the gear in the top left of the homescreen)
2. Click "Developer" on the right (will say "Dashcam vX.X.X""",
  },
  {
    "id": "builtin_wiki_installing_openpilot_1",
    "title": "Wiki: Installing openpilot (2/2)",
    "tags": ["wiki","openpilot","comma","installing"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Installing openpilot
https://github.com/commaai/openpilot/wiki/Installing-openpilot

)
3. Scroll down to "Uninstall Dashcam"
    If the option is grayed out or unavailable, shut off your car.
4. When prompted with a confirmation of uninstalling click, "Uninstall"
5. The device will reboot and uninstall the dashcam software.
6. Once finished it will return to the device's initial state. You can now install other software through the setup.""",
  },
  {
    "id": "builtin_wiki_installation_guides_0",
    "title": "Wiki: Installation Guides (1/3)",
    "tags": ["wiki","openpilot","comma","installation"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Installation Guides
https://github.com/commaai/openpilot/wiki/Installation-Guides

◄ Home

Introduction
This page is a repository of the numerous existing installation guides as well as a supplement for additional information. If you read through this entire page and relevant links before starting your installation, you are less likely to have installation issues. Note: it is recommended that you install the device in your car before loading openpilot onto the device.

Once you have the device installed, you can proceed to Install openpilot.

Table of Contents
=================

    Installation Videos
    Installation Instructions
    Additional Installation Suggestions
       Aligning and Placing Components
       Encouraging a Strong Adhesive Bond
       Attaching Cables
       Custom Options
    Installation Troubleshooting
       My mount fell off
       How do I Remove the Residue on the Windshield after removing the Mount
       Community Troubleshooting Video

Installation Videos
It is recommended that you fully watch an installation video before undertaking your installation. A number of good installation videos exist:

Official Installation Guide
| Video         | Car           | Creator          |
|:-------------:|:-------------:|:----------------:|
| [](//www.youtube.com/watch?v=lcjqxCymins) | Honda Civic 2017 | comma |

Community Guides
| Video           | Car           | Creator        |
|:-------------:|:-------------:|:----------------:|
| [](//www.youtube.com/watch?v=zmuWNfJ-wDQ) | Toyota Corolla 2020 | Logan LeGrand |
| [](//www.youtube.com/watch?v=Pel4LKiNiY0) | GMC Sierra/Chevy Silverado 1500 2020 | Morris Lee |

Installation Instructions

 See the comma FAQ particularly the section titled How do I mount the comma two?
 comma has also provided a pictorial walk through of the steps.

Additional Installation Suggestions

The comma community has developed the following additional suggestions that may improve your installation process:

Aligning and Placing Components
 It is best to test fit the various components before permanently affixing them. Check to make sure that all cords will reach and that covers can be replaced. Ensure there is enough space between the mount and the mirror that you will be able to remove the device""",
  },
  {
    "id": "builtin_wiki_installation_guides_1",
    "title": "Wiki: Installation Guides (2/3)",
    "tags": ["wiki","openpilot","comma","installation"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Installation Guides
https://github.com/commaai/openpilot/wiki/Installation-Guides

from the mount. Also make sure the mount will not interfere with the removal of any cover around your rear-view mirror.
 The main comma mount should be affixed in the center of the windshield below the rear-view mirror attachment even though this will cause the road facing camera to be slightly off center. openpilot has a calibration process that will adjust for this slight shift. Mounting the camera on the center line of the car will help to prevent issues with the driver facing camera properly seeing the driver.
 Whiteboard markers can be used to mark your test fit location. Be sure none of the marker material will be covered by the adhesive.
 One suggestion has been to affix a string to the outside of the windshield to denote the center-line of the windshield.
 openpilot is tolerant of small abnormalities in the mounting. If you can hang a picture you can do this.

Encouraging a Strong Adhesive Bond
comma provides the following instructions in the package:

 Before adhering any components, it is recommended that you clean the area with isopropyl alcohol (often called IPA on Discord) to remove any oils or other contaminants from the surface. This is particularly important for the main comma mount. Contaminants may cause the adhesive hold to weaken, resulting in your device falling off your windshield.
 When affixing the main comma mount to the windshield, try to prevent air from being trapped under the adhesive. This can be done by adhering one edge of the mount to the windshield first and "rolling" the rest of the mount onto the windshield.
 Many people recommend leaving mount adhered to your windshield for 24-48 hours before attaching the device. It is also recommended that you keep the mount out of the sun for this "curing" time period. Attaching tape to the exterior of your windshield helps to provide shade while the adhesive sets if you can't keep it in the dark.
 Avoid installing the mount on very cold days. The adhesive may not form a strong bond under cold temperatures. Additionally, the condensation from your breath on the windshield could prevent a strong bond from forming. If necessary, install with with window defrost on to warm up the window and p""",
  },
  {
    "id": "builtin_wiki_installation_guides_2",
    "title": "Wiki: Installation Guides (3/3)",
    "tags": ["wiki","openpilot","comma","installation"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Installation Guides
https://github.com/commaai/openpilot/wiki/Installation-Guides

revent condensation.

Attaching Cables
 Be sure to attach all cables firmly. This is one of the main installation errors. The automotive cables should all click when fully seated. The RJ45 (flat Ethernet cable) should also nicely click into both connections.
 The USB-C connection should be pushed in with some force. Users with errors have frequently discovered that the USB-C connection on the back of the C2 is a tight fit make sure the connector is fully inserted.
 Try not to bend or pinch the USB-C cable. The wires and connectors, while covered in protective plastic, are sensitive and very thin internally.

Custom Options
 Transparent comma mount - A transparent mount instead of the black one that comes with the comma. This is handy if you drive around without the comma device mounted to your windshield.

Installation Troubleshooting
My mount fell off
If your mount falls off, discard at least the VHB (the adhesive) or the whole mount if you like. Any adhesive that has attempted to stick and failed is compromised and the same thing will happen if you attempt to reuse it. comma provides you with a second mount, so just use that. Another option is to order two new mounts from the shop. Be sure to go through all of the cleaning steps again, especially use of isopropyl alcohol. You can also purchase additional VHB adhesive from Amazon, the 3in squares work well.
How do I Remove the Residue on the Windshield after removing the Mount
IPA is usually all you need to do this (see above for what IPA is). If it is really bad, products like goo-gone can be used, but be sure to clean them off thoroughly before reinstalling a mount again.

Community Troubleshooting Video
If you are a visual learner, the community has also created some troubleshooting videos that may help you:
| Video           | Car           | Creator        |
|:-------------:|:-------------:|:----------------:|
| [](//www.youtube.com/watch?v=ZHtCYYLM4UM) | Toyota Corolla 2020 | Logan LeGrand |""",
  },
  {
    "id": "builtin_wiki_general_terms_0",
    "title": "Wiki: General Terms (1/5)",
    "tags": ["wiki","openpilot","comma","general"],
    "refresh": False,
    "text": """Source: openpilot Wiki — General Terms
https://github.com/commaai/openpilot/wiki/General-Terms

◄ Home

comma.ai terms

Term | Abbreviation | Definition
--- | --- | ---
comma.ai | | The company behind openpilot
comma API | | link to docs
comma connect | | An open source progressive web app used to view drives and interact with the device remotely
car harness | | A universal interface to your car. A unique harness exists for each of the supported makes and models of cars. This replaces the older giraffe Connector
comma pedal | | A device that provides stop-and-go capability on cars that don't currently support it. This device is not sold by comma.ai (not officially supported by them), but supported in openpilot.
comma points | | Awarded for various activities you perform on the platform. Good for bragging rights.
comma power | CPv1, CPv2 | Use your car's OBD-II port to power your Toyota, Bosch, or FCA giraffe. CPv1 was the initial version, for use w/ giraffes. CPv2 came out later, used with comma harness, and has an RJ45 jack.
comma prime | | A subscription service from comma.ai offering a specific list of benefits
comma three devkit | C3, comma three | The latest generation devkit from comma. Runs Ubuntu linux and suppors the latest openpilot releases. Has an integrated panda (dos). Supports using an external red panda to interface with CAN-FD vehicles.
comma two devkit | C2, comma two | A smartphone running a customized version of Android and a custom case with additional cooling. This device runs the openpilot software and has an integrated panda (uno)
EON devkit | EON, EON Gold, EON SE | The previous generation of the comma two devkit. It did not have an integrated panda
fingerprint | FPv1, FPv2 | A list of CAN bus signals unique to a particular vehicle. Allows openpilot to recognize which car it is connected to. CAN-based FPv1 is now deprecated; emphasis is now on firmware-based FPv2.
FrEON | | "Free EON"... an open source variant of the EON case. The repository contains files that can be used for 3D printing a case. Developed by @Chase#7213
giraffe connector | | An adapter board that lets you read buses that aren't exposed on the main OBD-II connector, with variants for different vehicle makes/models.
Lane Change Assist | LCA | Activate the turn signa""",
  },
  {
    "id": "builtin_wiki_general_terms_1",
    "title": "Wiki: General Terms (2/5)",
    "tags": ["wiki","openpilot","comma","general"],
    "refresh": False,
    "text": """Source: openpilot Wiki — General Terms
https://github.com/commaai/openpilot/wiki/General-Terms

l and gently nudge the wheel in the direction you wish to travel to when it's safe. Change lanes while always paying attention.
LeEco Le Pro 3 | LeEco, Lepro | The phone used in comma two and EON Gold devkits
LiveParameters | | A continually updated file (ie. "Live") that stores learned calibration data for the vehicle.
OnePlus 3T | op3t | One of the phones used in the previous generation EON devkits. It was discontinued due to a lack of supply. Known model numbers: A3000(US version) A3010(Asian version)
openpilot | op | An open source driver assistance system developed by comma.ai
panda | | CAN bus interface. Available in 3 variants: white (last supported 0.7.6.1) / grey (last supported 0.7.10) / black. Internal pandas are also found inside the
comma two (uno) and comma three (dos).
panda paw | | A device to help you unbrick a panda.

openpilot terms
Term | Abbreviation | Definition
--- | --- | ---
big model | | A new paradigm in model development that takes a bigger input frame. Full frame is 1164x874, little model is a 512x256 crop, big model is a 1024x512 crop, 4x bigger than little. Make box bigger, drive better. Useful for signs and lights.
Driving Model | model | The resulting neural network after Comma trains on driving data on their supercomputer.  This file lives on the device, and processes inputs to give outputs relevant to driving. Usually takes the form of an ONNX file, or a THNEED file after compilation on device. This file does not change or get trained on device, only processes inputs and outputs. See the list of driving models for names and details of models over time.
End to end | e2e| End to end means the model reacts like a human would. It assesses the whole picture and acts accordingly. Unlike other approaches where things must be labeled by hand, end to end learns all the nuances of driving. A model is basically trained on what human drivers would do in a certain situation and attempts to reproduce that behavior.
longitudinal | long | Refers to gas and brake control
lateral | lat | Refers to steering control
Model predictive control | mpc | An advanced method of process control that is used to control a process while satisfying a set of co""",
  },
  {
    "id": "builtin_wiki_general_terms_2",
    "title": "Wiki: General Terms (3/5)",
    "tags": ["wiki","openpilot","comma","general"],
    "refresh": False,
    "text": """Source: openpilot Wiki — General Terms
https://github.com/commaai/openpilot/wiki/General-Terms

nstraints. Used for longitudinal and lateral control.
lead | | Selected radar point from your car's radar by the driving model of openpilot using the camera. Used for longitudinal MPC. Usual attributes: distance, speed, and acceleration

driver-assistance terms

Make-specific terms should be added to their perspective wiki page.

Term | Abbreviation | Definition
--- | --- | ---
Adaptive Cruise Control | ACC | A cruise control system that automatically adjusts the vehicle speed to maintain a safe distance from vehicles ahead.
Advanced Driver-Assistance Systems | ADAS | Electronic systems that aid the driver.
(Automatic) Lane Centering | (A)LC | A system designed to keep a car centered in the lane, relieving the driver of the task of steering.
Collision Avoidance System | AEB, CMS, FCW(S), FCA, PCS | A system designed to prevent or reduce the severity of a collision.
Driver Monitoring (System) | DM(S), DAM | A system that uses infrared sensors and/or cameras to monitor driver attentiveness
Dynamic Range Cruise Control | DRCC | A cruise control system that automatically adjusts the vehicle speed to maintain a safe distance from vehicles ahead.
hugging | | An undesired behavior where the vehicle drives too closely to one side of the lane.
Lane Keep Assist (System) | LKA(S) | Lane keep assist is what comes with most cars sold today. It will assist the driver if they go over a lane line, but will not keep the car centered in the lane.
Lane Departure Warning (System) | LDW(S), LDA | Lane departure warning will beep when a car goes over a lane line.
Pedestrian Crash Avoidance Mitigation | PCAM | A system that uses computer and artificial intelligence technology to recognize pedestrians and bicycles in an automobile's path to take action for safety.
ping pong | | An undesired behavior where the vehicle sways from one side of the lane to the other repeatedly. The desired behavior is to stay in the center of the lane.
wobble | | Similar to ping pong, but where the vehicle drives mostly centered in the lane but sways slightly from side to side. Primarily due to improper tuning of the steering control system, influence from wind, or poor lane/path perception due to rain, dir""",
  },
  {
    "id": "builtin_wiki_general_terms_3",
    "title": "Wiki: General Terms (4/5)",
    "tags": ["wiki","openpilot","comma","general"],
    "refresh": False,
    "text": """Source: openpilot Wiki — General Terms
https://github.com/commaai/openpilot/wiki/General-Terms

t, and/or debris on the vehicles windshield.
Traffic-sign recognition | TSR | A system by which a vehicle is able to recognize the traffic signs put on the road e.g. "speed limit" or "children" or "turn ahead".
Stop and Go | SnG | The ability for the car to be brought to a standstill and then resume driving without needing to disengage or reengage openpilot.
Vision Only Adaptive Cruise Control | VOACC | The exclusive use of cameras instead of radar to provide adaptive cruise control functions.

automotive terms

Make-specific terms should be added to their perspective wiki page.

Term | Abbreviation | Definition
--- | --- | ---
Controller Area Network | CAN, CAN bus | A message-based protocol that provides a standardized way for ECUs to communicate with each other.
CAN-FD | | A newer version of CAN that supports higher data rates and longer messages. A red panda is required to interface with CAN-FD vehicles.
Electronic Control Unit | ECU | Any embedded system in automotive electronics that controls one or more of the electrical systems or subsystems in a vehicle.
Electric Power Steering | EPS | Uses an electric motor to assist the driver of a vehicle. Sensors detect the position and torque of the steering column, and a computer module applies assistive torque via the motor, which connects to either the steering gear or steering column.
On-Board Diagnostics Connector | OBD-II, OBD-II port | OBD systems give the vehicle owner or repair technician access to the status of the various vehicle sub-systems. The comma power v2 uses this port to provide constant power to the comma two as well as access the diagnostic bus for FW query.
Full Self Driving | FSD |

technical terms
Term | Abbreviation | Definition
--- | --- | ---
Proportional–integral–derivative | PID | A proportional–integral–derivative controller (PID controller or three-term controller) is a feedback-based control loop mechanism commonly used to manage machines and processes that require continuous control and automatic adjustment.
Incremental Non-Linear Dynamic Inversion | INDI | Incremental Nonlinear Dynamic Inversion (INDI) is a sensor-based control method that uses a small amount of model information t""",
  },
  {
    "id": "builtin_wiki_general_terms_4",
    "title": "Wiki: General Terms (5/5)",
    "tags": ["wiki","openpilot","comma","general"],
    "refresh": False,
    "text": """Source: openpilot Wiki — General Terms
https://github.com/commaai/openpilot/wiki/General-Terms

o achieve high performance.
System on Module | SoM | Integrates the core components of an embedded processing system, such as processor, memory, and peripherals, in one PCB
Feed-Forward | FF | Feedforward control uses measurement of a disturbance input to control a manipulated input. This differs from feedback, which uses measurement of any output to control a manipulated input.
Multilayer perceptron | MLP | modern feedforward neural network) consisting of fully connected neurons with nonlinear activation functions, organized in layers, notable for being able to distinguish data that is not linearly separable.

discord terms
Term | Abbreviation | Definition
--- | --- | ---
Direct Message | DM (PM preferred to avoid confusion with driver monitoring) | Private message to an individual on Discord
Private Message | PM | Private message to an individual on Discord
Want To Buy | WTB | You want to buy an item (on #for-sale channel)
For Sale | FS | You want to sell an item (on #for-sale channel)""",
  },
  {
    "id": "builtin_wiki_comma_three_0",
    "title": "Wiki: comma three",
    "tags": ["wiki","openpilot","comma","comma"],
    "refresh": False,
    "text": """Source: openpilot Wiki — comma three
https://github.com/commaai/openpilot/wiki/comma-three

Hardware specs
 845 SOM from https://www.thundercomm.com/appen/product/1529761023999618
 185 degree front and driver facing camera and 45 degree front facing camera with https://www.onsemi.com/products/sensors/image-sensors/ar0231at image sensors
 Dual IR front facing LEDs
 Samsung 980 Evo NVME SSD 256GB or 1TB
 2160x1080 OLED front display
 New integrated panda
 25-30C/45-55F/25-30K cooler temperatures than comma two
 Custom hardware design
 DisplayPort

Improved software
 Navigation: Use the device to show the shortest path
 Better model performance due to camera improvements
 1 month of free comma prime
 8 core CPU will enable more features in the future
 Runs on Ubuntu 20.04 making it a much better development environment, apt, sudo and other nice tools just work""",
  },
  {
    "id": "builtin_wiki_honda_acura_0",
    "title": "Wiki: Honda Acura (1/3)",
    "tags": ["wiki","openpilot","comma","honda"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Honda Acura
https://github.com/commaai/openpilot/wiki/Honda-Acura

◄ Home

Make-Specific Terms

For general terms, go here.

| Term              | Abbreviation | Definition                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
|-------------------|--------------|------------|
| Honda Sensing     | Sensing      | What Honda calls their ADAS system which provides things such as adaptive cruise control, lane keeping assist, road departure mitigation, and lane departure warning.
| Acura Watch       | Acura Watch  | What Acura calls their ADAS system which provides things such as adaptive cruise control, lane keeping assist, road departure mitigation, and lane departure warning.|
| Honda Bosch       | Bosch        | Bosch is a company Honda uses to provide their ADAS systems. Experimental mode, when enabled on the nightly-dev branch or some community forks, does support many Bosch cars. Release versions of openpilot do not support openpilot longitudinal, but can sometimes (depending on model) steer down to a lower mph than Honda Nidec vehicles. |
| Honda Nidec       | Nidec        | Nidec is a company Honda uses to provide their ADAS systems. Nidec cars support openpilot longitudinal in release versions of openpilot. Nidec hardware is being phased out company-wide in favor of the Bosch system.                                                                                                                                                                                                                                                        |
| Rewrite Honda EPS | RWD          | Part of the Honda Diagnostic System (HDS) software is a tool to flash firmware updates (J2534 Rewrite application) and a set of firmware update files. See https://github.com/gregjhogan/rwd-xray/blob/master/README.md              

openpilot Capabilities

L""",
  },
  {
    "id": "builtin_wiki_honda_acura_1",
    "title": "Wiki: Honda Acura (2/3)",
    "tags": ["wiki","openpilot","comma","honda"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Honda Acura
https://github.com/commaai/openpilot/wiki/Honda-Acura

ateral Control (Steering)

Torque
Honda vehicles suffer from a low amount of steering torque that can be applied by openpilot, although torque has improved in some recent model years. Hondas with openpilot are best suited to highways and generally straight roads. They can typically make gradual turns at high speeds but may require reduced speed to successfully navigate sharper turns.

Minimum Speeds
Depending on the vehicle model, openpilot cannot steer the car at speeds below 3mph or 15mph or 43mph. When traveling below the minimum steering speed, the driver must take control of the steering wheel.

Longitudinal Control (Gas and Brakes)

Honda Bosch
With alpha longitudinal mode enabled on the nightly-dev branch, acceleration and braking can be controlled on Bosch ADAS-based vehicles (excluding Bosch C).  This experience can be rather jerky (0.9.8), although community forks can resolve the jerkiness.

Release versions of openpilot don't yet control acceleration on Bosch ADAS-based vehicles. The radar accepts commands and visual information from the factory windshield-mounted camera assembly which then commands the vehicle's acceleration and braking accordingly. Openpilot controls steering.  The factory Bosch radar does not output object data like other makes/models (including Honda Nidec).

Manual transmission models support acceleration and braking control above 25mph, while the driver manually shifts gears.  With alpha longitudinal mode enabled on the nightly-dev branch, acceleration and braking can be controlled at all speeds.

Honda Nidec
Depending on the model, openpilot will not support stop and go (titled "Low-Speed Follow" by Honda). openpilot does not have direct control over forward acceleration like other models, so it instead uses the factory built-in control system by commanding the desired vehicle speed. If improved acceleration or acceleration control is desired, the community-only supported comma pedal interceptor is required (see below. Not sold or built by comma.ai). openpilot, however, does have full braking control on these cars.

Community Features

enhancements to steering and longitudinal control

Community forks often implement improvemen""",
  },
  {
    "id": "builtin_wiki_honda_acura_2",
    "title": "Wiki: Honda Acura (3/3)",
    "tags": ["wiki","openpilot","comma","honda"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Honda Acura
https://github.com/commaai/openpilot/wiki/Honda-Acura

ts to steering, gas, and brake control for Honda models.  In addition, community forks can enable experimental mode on Honda Bosch C cars.

Join the #honda-acura channel on discord with questions.

comma pedal

Allows Nidec Hondas without cruise control capable of Low-Speed Follow to gain stop-and-go functionality by using openpilot with a device plugged into the accelerator pedal.

Community-Supported Models

The #honda-acura channel on discord maintains a google sheets document with community supported cars.  Almost every car with Honda Sensing or AcuraWatch is community supported.

Comma.ai maintains a compatibility list of officially supported cars.

Honda Clarity and Acura RLX

The Honda Clarity and Acura RLX have one extra CAN bus at the camera connector. Due to this, they need custom hardware and a custom fork to run.

Join the #honda-acura channel on discord with questions.

Serial Steering

There are some Honda/Acura with Honda Sensing/AcuraWatch that are not currently supported due to using dedicated serial data lines for its steering control messages. These cars can work with openpilot using additional hardware and minor software modifications. Community Maintained forks are available.

Below is the list of 'serial steering' cars:
 2016/2017 Accord
 14-20 Acura MDX
 15-20 Acura TLX

Join the #topic-serial-steering channel on discord with questions.

Unsupported EV Models manufactured by GM

The Honda Prologue and 2024 Acura ZDX are manufactured by GM, using their Global B architecture.  These models are not supported due to the encryption in the Global B CAN bus.""",
  },
  {
    "id": "builtin_wiki_toyota_lexus_0",
    "title": "Wiki: Toyota Lexus (1/5)",
    "tags": ["wiki","openpilot","comma","toyota"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Toyota Lexus
https://github.com/commaai/openpilot/wiki/Toyota-Lexus

◄ Home

Table of Contents
=================

- Table of Contents
- Supported Toyota/Lexus Vehicles
  - Toyota Camry Support
  - 2021+ Toyota ECU Security Key Support (new STEERINGLKA + More)
- Toyota/Lexus Terms
  - Toyota Safety Sense (TSS) Versions
  - Terms and Abbreviations
- openpilot Capabilities
  - Lateral Control
    - Torque
    - Steering Sensor
    - openpilot Replaces LDA LTA
  - Longitudinal Control
    - TSS2 Vehicles
    - TSSP Vehicles
    - Stock vs openpilot Longitudinal Control Differences
- Community Features
  - comma pedal
  - SDSU (SmartDSU/SmartenedDSU)
  - Zorro Steering Sensor (ZSS)
  - Manual Transmission (6MT)
- Common Toyota/Lexus Questions:
  - How can I find out what version of Toyota Safety Sense (TSS) or other features my car has?
  - How do I remove the camera cover in my car?
- Links:

Supported Toyota/Lexus Vehicles

The most up-to-date list of supported vehicles is on the openpilot main page.  Please take careful note of the following columns and pay attention to and read any footnotes:
 <u>Supported Package</u> - Mandatory trim levels or options required for openpilot to work, if any.  All means all versions of this model work.
 <u>ACC</u> - What is in charge of longitudinal control. This can be either Stock (your vehicle's cruise control system) or openpilot.
   Footnote 3 applies to a number of Toyota vehicles.  See discussion of Disconnecting DSU.
 <u>No ACC accel below</u> - Cruise control will not work below these speeds.  0 mph means that the vehicle is capable of stop-and-go driving.
   Footnote 1, see the comma pedal.
   For footnote 4 see openpilot Camry Support.
 <u>No ALC below</u> - No lateral control, this doesn't apply to any supported Toyota/Lexus vehicles currently.

Toyota Camry Support
Toyota Camry / Camry Hybrid 2018-20 can only use Stock adaptive cruise control due to having the radar directly control gas and brakes, with no external DSU to unplug. (unplugging the radar = no radar tracks and no ACC)

For 2018-2020 Camry models which don't have Full-Speed Range Dynamic Radar Cruise Control <u>openpilot will not function below 25mph</u> this includes the 4CYL L, 4CYL LE and 4CYL SE non-hybrid models.  Ther""",
  },
  {
    "id": "builtin_wiki_toyota_lexus_1",
    "title": "Wiki: Toyota Lexus (2/5)",
    "tags": ["wiki","openpilot","comma","toyota"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Toyota Lexus
https://github.com/commaai/openpilot/wiki/Toyota-Lexus

e is no current solution for this, these vehicles cannot use a comma pedal to solve this issue.  This is because these models use a Continental radar not used on other vehicles and messages from the radar cut out completely below 25mph.

This limitation does not apply to Camry models with Full-Speed Range Dynamic Radar Cruise Control including the (2018-2020 XLE, XSE, LE HV, XLE HV, and SE HV)

2021+ Toyota ECU Security Key Support (new STEERINGLKA + More)

Please see https://github.com/optskug/docs

Toyota/Lexus Terms

The following terms are specific to Toyota and Lexus vehicles and are often used in discussions.

For general terms, go here.

Toyota Safety Sense (TSS) Versions

Term | Abbreviation | Definition
--- | --- | ---
Toyota Safety Sense 2.0 | TSS2 TSS 2.0| TSS2 builds on the previous TSS-C and TSS-P suites, and consists of six active safety and driver assistance systems: PCS, DRCC, LDA, AHB, RSA, and LTA. It has a better angle sensor, and supports full range ACC on all openpilot compatible models.
Toyota Safety Sense P | TSSP TSS-P| An advanced active safety package for mid-size and large vehicles, and consists of six active safety and driver assistance systems: PCS, LDA, and AHB. Includes a DSU which does ACC and AEB.
Toyota Safety Sense C | TSSC TSS-C| An advanced active safety package for compact vehicles, and consists of six active safety and driver assistance systems: PCS, DRCC, LDA, and AHB. It does not feature lane keep assist, thus is not compatible with openpilot.

Terms and Abbreviations
Term | Abbreviation | Definition
--- | --- | ---
Driver Support Unit | DSU | This embedded system implements cruise control and Automatic Emergency Braking in some Toyota cars.
Pre-Collision System | PCS | May also include pedestrian detection and be written as PCS w/PD.  This is the main AEB feature.
Dynamic Radar Cruise Control | DRCC | This is ACC, and may be full speed depending on the model
Lane Departure Alert | LDA | The audible alert when leaving a lane.  May also include Steering Assist and be listed as LDA w/SA
Auto High Beams | AHB | Pretty straight forward.
Road Sign Assist | RSA | The thing that displays speed limit and stop signs on your dash.""",
  },
  {
    "id": "builtin_wiki_toyota_lexus_2",
    "title": "Wiki: Toyota Lexus (3/5)",
    "tags": ["wiki","openpilot","comma","toyota"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Toyota Lexus
https://github.com/commaai/openpilot/wiki/Toyota-Lexus

Lane Tracing Assist | LTA | The stock feature that enables lane centering or lane keeping while using DRCC

 RSA Is not available on Canadian sold TSS2.0 or TSS2.5+ Models.

openpilot Capabilities

Lateral Control

Control over the steering wheel.  openpilot handles lateral control for all supported Toyota/Lexus vehicles.  However, some TSSP vehicles may have jerky non-precise steering as noted in Steering Sensor.

Torque

Toyotas have very good torque, and work well on local and highway roads.

Steering Sensor

TSS2 Toyotas have a great angle sensor, as well as select 2019+ TSSP Toyotas.
Most TSSP Toyotas have a bad angle sensor. This results in jerky, non-precise steering. The worst culprit of this is the Prius. This can be fixed on some models with a ZSS.

openpilot Replaces LDA LTA

As noted in the comma.ai FAQ, openpilot replaces the LDA and LTA features on Toyota and Lexus vehicles when openpilot is enabled.  LDA alerts will originate from openpilot when openpilot is enabled, even when the cruise control feature is not enabled.  You can disable LDA warnings inside the openpilot settings.  Sadly, if your vehicle is equiped with LDA w/SA, openpilot does not currently emulate the Steering Assist function when the cruise control is disabled.

Longitudinal Control

Control over the gas and brakes.

TSS2 Vehicles

openpilot handles longitudinal control for these vehicles without any additional modifications.  AEB and blindspot warning will continue to function as they did on the original vehicle.  There is no option on these vehicles to use Stock ACC while using openpilot.

TSSP Vehicles

The Driver Support Unit is what controls AEB and longitudinal on TSSP cars. This unit must be unplugged to give openpilot control, although this removes AEB.  Users are strongly discouraged from disconnecting their DSU and abandoning AEB.  Instead, a SDSU solves this problem, by passing through the correct AEB messages while allowing openpilot to control longitudinal.

TSSP vehicle owners have the benefit of choosing to use openpilot or stock ACC, this is not an option for TSS2 vehicle owners.  SmartenedDSU owners may also have the option to switch between stock and openpilot f""",
  },
  {
    "id": "builtin_wiki_toyota_lexus_3",
    "title": "Wiki: Toyota Lexus (4/5)",
    "tags": ["wiki","openpilot","comma","toyota"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Toyota Lexus
https://github.com/commaai/openpilot/wiki/Toyota-Lexus

or each drive.

It is possible to enable OP stop-and-go in TSSP vehicles with a non-zero value for "no ACC accel below" on the official supported cars list with an SDSU and comma pedal. Some models may have luck with only an SDSU and the 2-line "SnG hack". See the discord for more information.

Stock vs openpilot Longitudinal Control Differences

Both systems work well and there are numerous people who prefer one system over the other.  Generally, the stock ACC is slower to accelerate from a stop and will keep a larger following distance as low speed.  openpilot on the other hand accelerates more aggressively and maintains a closer distance at low speeds but a larger distance as high (freeway) speeds.  Some hybrid owners prefer the stock system because its gentler acceleration profile means less use of the internal combustion engine in traffic.

Community Features

comma pedal

A comma pedal allows Toyotas without full-range cruise control to gain stop-and-go using openpilot with a device plugged into the gas pedal.

SDSU (SmartDSU/SmartenedDSU)

Upgrades the Driver Support Unit to passthrough AEB and enable openpilot longitudinal control.  SDSU was first sold as an external, harness-style contraption, and later the SmartenedDSU (DSU modified by forwarding a severed CAN connection back into the network by way of an onboard, stripped down, reflashed panda) and became preferred, with quick creation/installation.

 Smart DSU

Zorro Steering Sensor (ZSS)

Upgrades TSSP cars with a better angle sensor which allows more accurate steering with openpilot.

Manual Transmission (6MT)

A prepatchd sunnypilot and openpilot is available at here: https://github.com/op201920226mtcorollaug/openpilot

Although not officially supported, a very small change is required to get openpilot functioning with a Toyota manual transmission. All that is necessary (other than fingerprinting) is to change LOWSPEEDLOCKOUT in /data/openpilot/opendbc/car/toyota/carstate.py from 2 to False, like in this commit.

This video describes how it operates. TL;DR in gears > 1st, and at > ~18mph. Below that, everything disengages (unless using sunnypilot, only ACC disengages).

This has been tested in TSS""",
  },
  {
    "id": "builtin_wiki_toyota_lexus_4",
    "title": "Wiki: Toyota Lexus (5/5)",
    "tags": ["wiki","openpilot","comma","toyota"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Toyota Lexus
https://github.com/commaai/openpilot/wiki/Toyota-Lexus

2 Corolla Hatchbacks from 2019 to 2022.

Common Toyota/Lexus Questions:

How can I find out what version of Toyota Safety Sense (TSS) or other features my car has?
> A couple of helpful links.  You can lookup you vehicle details using your VIN on the Toyota Vehicle Information Lookup.  You can also review this handy TSS Applicability Chart

How do I remove the camera cover in my car?

Links:

 2010-2015 Prius wiring drawing
 Toyota Wiring Harnesses""",
  },
  {
    "id": "builtin_wiki_ford_0",
    "title": "Wiki: Ford (1/11)",
    "tags": ["wiki","openpilot","comma","ford"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Ford
https://github.com/commaai/openpilot/wiki/Ford

◄ Home

Overview

A range of Ford vehicles are now supported in openpilot. Work is underway to expand official support for Ford/Lincoln vehicles, particularly those with CAN FD. Some community maintained forks provide support additional vehicles. Safety code is not always working properly and these forks should NOT be used without fully understanding the ramifications of such. Make sure to read [Safer Control of Steering]. If your car is not listed in the compatibility table, but has Lane Centering, it may be possible to add support.

-----

Table of Contents

- Overview
- Supported vehicles
  - Looking for testers
  - Footnotes
      - CAN FD Vehicles
  - Is my car compatible?
    - Likely unsupported vehicles
- Make-Specific Terms
- openpilot Capabilities
  - Lateral Control
    - Traffic Jam Assist (TJA) / Lane Centering Assist (LCA)
    - Lane Keep Assist (LKA)
  - Longitudinal Control
    - Older vehicles
- Harnesses
  - Old style (14-pin)
  - CGEA 1.2 Style (16-pin)
  - Ford Q3 / Lane Centering (12-pin)
  - Ford Q4 / BlueCruise / CAN FD (20-pin)
- Useful links

Supported vehicles

[ford-q3]: #ford-q3--lane-centering-12-pin
[ford-q4]: #ford-q4--bluecruise--can-fd

Lateral control is implemented using the TJA/LCA messages which enables steering with no timeout.

openpilot Longitudinal Control (Alpha) is available for Ford and can be enabled when running master-ci/nightly/devel or another development branch. Enable it to use Experimental Mode, which includes alpha features like stopping for red lights and stop signs.

- ✅ is supported.
- ⏰ is supported, but is in dashcam mode until a user supplies a route.
- 🧪 works on a development branch, but is not yet officially supported.
- 🔜 is thought to be compatible but needs a user to test. Take advantage of comma's 30 day money back trial.

If you have a Ford which you think may be compatible, and you're interested in helping us add support, join the [comma.ai discord server][discord]!

|Make|Model|Required Package|Harness|Supported?|Comment|
|:---|:---|:---|:---|---|:---|
|Ford|Bronco Sport 2021-24|Co-Pilot360 Assist+|Ford Q3|✅|
|Ford|Edge 2019-24|Co-Pilot360 Assist+|Ford Q3|🔜|In progress #30762|
|Ford|Escape 2""",
  },
  {
    "id": "builtin_wiki_ford_1",
    "title": "Wiki: Ford (2/11)",
    "tags": ["wiki","openpilot","comma","ford"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Ford
https://github.com/commaai/openpilot/wiki/Ford

020-22|Co-Pilot360 Assist+|Ford Q3|✅|
|Ford|Escape 2023-24|Co-Pilot360 Assist 2.0|Ford Q4[<sup><strong>[1]</strong></sup>](#footnotes)|🔜|Untested|
|Ford|Expedition 2022-24|Co-Pilot360 Assist 2.0|Ford Q4[<sup><strong>[1]</strong></sup>](#footnotes)|🔜|Untested|
|Ford|Explorer 2020-24|Co-Pilot360 Assist+|Ford Q3|✅|
|Ford|F-150 2021-23|Co-Pilot360 Assist 2.0|Ford Q4[<sup><strong>[1]</strong></sup>](#footnotes)|🧪|Join the Discord|
|Ford|F-150 Lightning 2022-23|Co-Pilot360 Assist 2.0|Ford Q4[<sup><strong>[1]</strong></sup>](#footnotes)|🧪|Join the Discord|
|Ford|Focus 2019-23[<sup><strong>[2]</strong></sup>](#footnotes)|Driver Assistance Pack[<sup><strong>[3]</strong></sup>](#footnotes)|Ford Q3|✅|
|Ford|Kuga 2019-22|Driver Assistance Pack[<sup><strong>[3]</strong></sup>](#footnotes)|Ford Q3|✅|
|Ford|Maverick 2022-24|Co-Pilot360 Assist|Ford Q3|✅|
|Ford|Mustang Mach-E 2021-23|Co-Pilot360 Assist 2.0|Ford Q4[<sup><strong>[1]</strong></sup>](#footnotes)|🧪|Join the Discord|
|Lincoln|Aviator 2020-24|Co-Pilot360 Plus|Ford Q3|✅|
|Lincoln|Corsair 2020-22|Co-Pilot360 1.5 Plus|Ford Q3|🔜|Untested|
|Lincoln|Corsair 2023-24|?|Ford Q4|🔜|Untested|
|Lincoln|Nautilus 2019-23|?|Ford Q3|🔜|Untested|
|Lincoln|Nautilus 2024|?|Ford Q4[<sup><strong>[1]</strong></sup>](#footnotes)|🔜|Untested|
|Lincoln|Navigator 2020-21|?|Ford Q3|🔜|Untested|
|Lincoln|Navigator 2022-24|?|Ford Q4[<sup><strong>[1]</strong></sup>](#footnotes)|🔜|Untested|

Newer model years within the same generation are usually compatible. Model refreshes may include a change in vehicle architecture (e.g. CAN -> CAN FD) and could mean adding support is not trivial.

Footnotes

1. Requires additional hardware when used with older devices. See CAN FD Vehicles.
2. Refers only to the fourth generation Focus (C519) available in Europe, China, Taiwan and Australasia.
3. Requires Adaptive Cruise Control (with Lane Centering & Stop and Go on Automatic Transmission only).

CAN FD Vehicles

These vehicles with the Mobileye Q4 chip (BlueCruise platform) use CAN FD, which is a newer standard for modules in the car to communicate. A red panda is required for openpilot running on a Comma 3 to be able to interact with a CAN FD bus.

The""",
  },
  {
    "id": "builtin_wiki_ford_2",
    "title": "Wiki: Ford (3/11)",
    "tags": ["wiki","openpilot","comma","ford"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Ford
https://github.com/commaai/openpilot/wiki/Ford

CAN FD panda kit can be purchased from the comma shop. You can choose to include it with a purchase of the comma three and Ford Q4 harness. Note that the Comma 3X has CAN FD support built-in, so a separate red panda is not required for CAN FD support.

Is my car compatible?

graph TD
    A([Start]) --> B("Do you have BlueCruise?")
    B -->|No| C("Do you have Co-Pilot360 Assist+ or Assist 2.0?")
    C -->|No| D("Do you have Lane Centering?")
    D -->|No| E("Do you have Traffic Jam Assist?")
    E -->|No| U("Does your model year have any of these packages as options?")
    U ---->|No| W["Likely not compatible 😔"]
    U -->|Yes| V("Do you have Adaptive Cruise Control?")
    V --->|No| X["Retrofit ACC 🔧"]
    V --->|Yes| Y["Potentially compatible with module programming 🪄"]
    B & C & D & E ----->|Yes| Z["Likely compatible 🎉"]

- Any vehicle with BlueCruise, Co-Pilot360 Assist+ or Assist 2.0, Lane Centering or Traffic Jam Assist is likely compatible. See Getting Started for next steps.

- Vehicles without one of these packages but where the package is an option on your model year could be supported:
  - If it has ACC, it is probably compatible, since there aren't hardware differences between the cars which chose the LKAS package and did not. The modules simply need reprogramming (this is not the same as firmware flashing). You can even do this to get stock lane centering on your car!

  - If it does not have ACC, we cannot support it yet. Consider retrofitting ACC (e.g. radar, brakes module) and reprogramming your modules.

    - You may find out your model already has the required hardware for ACC! If it has a brake booster designed for ACC, it may be supported with vision-only ACC in the future.

- Most cars ship with "Co-Pilot360" but this is not the same as "Co-Pilot360 Assist+" or "Co-Pilot360 Assist 2.0". The same applies to "Lane Keep Assist" on older vehicles, which is not the same as "Lane Centering" and "Traffic Jam Assist".

- Active Park Assist is not an indicator of compatibility. It cannot be used above 5mph. See [Safer Control of Steering] for more information.

- Lane Keep Assist is subject to a steering lockout in the EPS firmware and so this""",
  },
  {
    "id": "builtin_wiki_ford_3",
    "title": "Wiki: Ford (4/11)",
    "tags": ["wiki","openpilot","comma","ford"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Ford
https://github.com/commaai/openpilot/wiki/Ford

cannot be used for openpilot.

Likely unsupported vehicles

Co-Pilot360 Assist+ or an equivalent package is not available on these vehicles. Further investigation would require testing with the vehicle, or compatible package may be introduced in later model years. If the vehicle has a compatible PSCM, it may be possible to enable the LCA/TJA commands, but this can't be determined without attempting it.

- Ford Bronco
- Ford Ecosport
- Ford F-250/F-350/F-450
- Ford Fiesta
- Ford Fusion/Mondeo/Taurus
- Ford Mustang
- Ford Puma
- Ford Ranger
- Ford Transit

If you're up for a challenge and have some technical knowledge, you might be able to find a way to support one of these vehicles! Improve your chances by buying a vehicle with adaptive cruise control and by getting access to some diagnostic software such as Forscan. Alternatively, you could attempt to reverse engineer some module firmware if you have knowledge in that area. Perhaps you can find a way to bypass the LKA Lockout.

Make-Specific Terms

For general terms, go here.

Abbreviation | Term | Definition
--- | --- | ---
AHBC | Automatic High Beam Control |
APA | Active Park Assist | See [Safer Control of Steering]
APIM | Accessory Protocol Interface Module | SYNC Screen
BLIS | Blind Spot Information System |
CADS, CCM | Collision Avoidance Detection System / Cruise Control Module | Radar Module
CTA | Cross Traffic Alert |
DAS | Driver Alertness System |
DLC | Data Link Connector | OBD-II port
FDA | Forward Distance Alert | Follow distance warning if you are too close to the vehicle in front. Also known as Forward Alert (FA)
GWM | Gateway Module | Forwards messages between various CAN buses, provides OBD-II port diagnostic bus
HUD | Head Up Display | Used for the Collision Warning and Pre-Collision Assist
iACC | Intelligent Adaptive Cruise Control | Automatically adjust ACC speed using TSR and navigation data
IPC | Instrument Panel Cluster | aka instrument cluster, speedometer...
IPMA | Image Processing Module A | LKAS Camera (sends LKAS and ACC commands)
IPMB | Image Processing Module B | Reversing Camera
LCA | Lane Centering Assist |
PAM | Park Aid Module |
PCA | Pre-Collision Assist |
PSCM | Power Steeri""",
  },
  {
    "id": "builtin_wiki_ford_4",
    "title": "Wiki: Ford (5/11)",
    "tags": ["wiki","openpilot","comma","ford"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Ford
https://github.com/commaai/openpilot/wiki/Ford

ng Control Module |
SCCM | Steering Column Control Module | SWC Buttons
SODL, SODR | Side Obstacle Detection Left/Right | BLIS Left/Right Module
TCU | Telematics Control Unit | SYNC Connect LTE
TJA | Traffic Jam Assist | A term which describes the combined stop-and-go ACC and lane centering system on Ford vehicles

openpilot Capabilities

Operation of openpilot is tied to the stock cruise control being engaged/disengaged. Below is a table showing the range of speeds at which cruise control can be operated. With ACC SnG, openpilot can operate at the full range of speeds.

Transmission|Stop and Go|Min Engage Speed|Disengage Speed
---|---|---|---
Manual|-|20mph|12mph
Automatic|No|20mph|12mph
Automatic|Yes|0mph|-

(this may be out of date - there is no automatic without stop and go on modern platform)

Lateral Control

Control over the steering wheel.

Method|Min Steer Speed|Max Steer Speed|Notes
---|---|---|---
Traffic Jam Assist (TJA) / Lane Centering Assist (LCA)|0mph|-|Only some PSCMs are compatible. See flowchart.
Lane Keep Assist (LKA)|35mph|-|Lockout for 200-300ms every 10 seconds.
Active Park Assist (APA)|0mph|5mph|Cannot be used over 5mph. See [Safer Control of Steering].

Traffic Jam Assist (TJA) / Lane Centering Assist (LCA)

► Read More: LateralMotionControl

<table>
<tr>
<td><img src=https://user-images.githubusercontent.com/4038174/192129435-a78457a0-c576-4fce-ab1f-f87eb4f3427b.png height=250 /></td>
<td><img src=https://user-images.githubusercontent.com/4038174/192129480-7b6e1e53-8dbf-4b6a-a952-639e8441ec4c.png height=250 /></td>
</tr>
</table>

Traffic Jam Assist (TJA) is the driver assistance system on Ford vehicles which applies torque to the steering wheel to enable continuous lane centering. It is packaged as "Intelligent Adaptive Cruise Control (with Stop-and-Go and Lane Centering)" on many vehicles. TJA can describe the combination of both the stop-and-go ACC and lane centering systems.

In the stock system, the driver is required to keep their hands on the steering wheel during operation. If no driver input is detected after displaying warnings it may begin to slow the vehicle before coming to a stop.

The IPMA is responsible for calculating t""",
  },
  {
    "id": "builtin_wiki_ford_5",
    "title": "Wiki: Ford (6/11)",
    "tags": ["wiki","openpilot","comma","ford"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Ford
https://github.com/commaai/openpilot/wiki/Ford

he characteristics of the lane and sending this information to the PSCM. The PSCM then applies torque to the steering wheel to keep the vehicle centered in the lane.

The feature can be enabled on supported vehicles which did not come equipped with the required package from the factory by changing the TJA/LCA Enable bit in the PSCM as-built data using diagnostic tools such as Forscan.

There are some videos online of apparent "continuous lane centering" functionality on older vehicles ([[1]](//youtu.be/dz7sbCy344U), [[2]](//youtu.be/C3Np-7hl1E0)), which suggests that firmware may exist to support these features on the old platform.

Minimum speeds

Lateral Control with LCA is functional down to 0mph and is not linked to the cruise state. However, it cannot turn the wheel at standstill.

Lane Keep Assist (LKA)

Lane Keep Assist (LKA) is the driver assist system on Ford vehicles which applies torque to the wheel to nudge the car back into lane when a departure event is detected. This system is only designed to provide temporary steering assistance. It is subject to a steering lockout in the PSCM firmware and so this cannot be used for openpilot.

The lockout is triggered either after 10 seconds of operation, or immediately after operation ceases. Operation cannot be resumed for approximately 200-300ms. This makes steering control very uncomfortable, especially when approaching a curve or at highway speeds, and there is no workaround to allow for steering events which last more than 10 seconds.

Technical Details

- 10 second lockout (<code>LaActAvailDActl</code>)
  - <code>3 "LKALCALDWAvail" 2 "LCALKAAvailLDWSuppress" 1 "LCALKASuppressLDWAvail" 0 "LCALKALDWSuppress"</code>
  - <code>LaActAvailDActl</code> must be 2 or 3 to send command
  - If <code>LaActAvailDActl</code> is 0 or 1 then LKA is locked out, and sending a command will prevent the PSCM from leaving the lockout state
  - LKA is locked out immediately after you stop sending a command, too
  - <code>LaActAvailDActl</code> returns to 2 or 3 after not sending a command for approx 200ms
- min speed (10mph in F-150, 35mph in Focus Mk4)
- almost all PSCMs can be configured to accept this message

It may be pos""",
  },
  {
    "id": "builtin_wiki_ford_6",
    "title": "Wiki: Ford (7/11)",
    "tags": ["wiki","openpilot","comma","ford"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Ford
https://github.com/commaai/openpilot/wiki/Ford

sible to develop a workaround, either through CAN messages or by modifying the PSCM firmware. Prior work has determined the lockout applies regardless of driver input torque so wheel weights are not a solution.

Minimum speeds

On the vehicles tested so far, LKA is only functional at speeds above 35 mph.

Longitudinal Control

Control over the gas and brakes.

On newer vehicles, the IPMA sends longitudinal commands to the PCM. It uses information from its own camera sensor and point cloud data from the front radar (CCM) to calculate these. The CCM is connected to the IPMA on a private CAN bus. Since the messages are sent from the IPMA where we can intercept them, it will be possible to implement openpilot longitudinal for all supported vehicles in the future.

Older vehicles

Most older Ford/Lincoln vehicles do not support OP Longitudinal Control. The CCM on these vehicles (Non Stop/Go) interfaces directly with the HS2 CAN bus and cannot be intercepted (note: this might be possible with an extra harness?). These vehicles run in Lateral Only mode.

Stop and Go vehicles can be intercepted, but this has not been tested.

Harnesses

In order to intercept the CAN messages from the IPMA we need to use a harness. There are a few known variants of the IPMA as Ford introduced new features.

- Old style (14-pin)
- CGEA 1.2 Style (16-pin)
- Ford Q3 / Lane Centering (12-pin)
- Ford Q4 / BlueCruise / CAN FD (20-pin)

comma now sells [Ford Q3][ford-q3] and [Ford Q4][ford-q4] development harnesses at comma.ai/shop.

Alternatively, one could build their own harness by buying the "Developer Harness" from comma (with the comma power, harness box and fully-wired harness with no connectors). Building a harness requires the dev harness, connectors (female connector for car side, and male connector to the camera) and crimp pins for attaching the dev harness wires to the connectors. You can use the information below (pinouts, part lists) to help you source these parts. The pinout for the 26-pin harness wire can be found on GitHub.

The CAN bus from the car should be connected to panda CAN0, the CAN bus from the camera should be connected to panda CAN2, and if there is a radar present""",
  },
  {
    "id": "builtin_wiki_ford_7",
    "title": "Wiki: Ford (8/11)",
    "tags": ["wiki","openpilot","comma","ford"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Ford
https://github.com/commaai/openpilot/wiki/Ford

then its private CAN bus should be connected to panda CAN1.

Old style (14-pin)

This connector is present on the original IPMA which is not believed to support "Lane Centering".

It has a 14-pin connector from Western Diversified Plastics, who do not sell the part to individuals. However, STL files exist which can be used to 3D print the connectors. These have kindly been provided by Wahzoo#3094 on Discord. Download on Google Drive.

CGEA 1.2 Style (16-pin)

This connector is found on the 2013-2019 Ford Explorer, Ford Fusion, Ford Taurus, Lincoln MKS, or Lincoln MKT with Lane Keep Assist. Some models (mainly Fusion) received a refreshed camera past 2016 with a different pinout.

<details>
  <summary><strong>Click here to reveal pinout</strong></summary>

|Pin|Function|Colour|
|---|--------|------|
|1  |12V (IGNITION/ACCESSORY)|Violet-Brown|
|2  |-       |      |
|3  |-       |      |
|4  |-       |      |
|5  |-       |      |
|6  |ELECTROCHROMATIC DOOR MIRROR DRIVE|      |
|7  |ELECTROCHROMATIC DOOR MIRROR GROUND|      |
|8  |GROUND|Black|
|9  |-       |      |
|10 |ENABLE/DISABLE SWITCH|      |
|11 |-       |      |
|12 |CAMERA DEFROST HEATER +|      |
|13 |-       |      |
|14 |HS CAN+|White-Blue|
|15 |HS CAN-|White|
|16 |CAMERA DEFROST HEATER -|      |
</details>

Ford Q3 / Lane Centering (12-pin)

<details>
  <summary><strong>Click here to reveal images</strong></summary>
  <img src="https://user-images.githubusercontent.com/4038174/168285425-c7a49ad2-d33a-4bd4-949b-743b51b528a5.png" width=400>
  <img src="https://user-images.githubusercontent.com/4038174/168285314-8c0180ff-0621-4c8a-8321-910b07cbf2c7.png" width=400>
</details>

The newer IPMA contains the Mobileye Q3 chip and introduced the "Lane Centering" feature for vehicles with stop-and-go ACC.
It is found on the vehicles as early as 2017, such as the Ford Fiesta in Europe. All vehicles with this IPMA are potentially supportable by openpilot provided they have, or have retrofitted, Adaptive Cruise Control.

<details>
  <summary><strong>Click here to reveal image</strong></summary>
  <img src="https://user-images.githubusercontent.com/4038174/168283467-12cd4efb-c24e-4dfa-bcb3-b263f3d3302e.png" width=4""",
  },
  {
    "id": "builtin_wiki_ford_8",
    "title": "Wiki: Ford (9/11)",
    "tags": ["wiki","openpilot","comma","ford"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Ford
https://github.com/commaai/openpilot/wiki/Ford

00>
</details>

<details>
  <summary><strong>Click here to reveal pinout</strong></summary>

Connector C9224 (IPMA) Pinout

This is a Molex Mini50 Series 12-pin connector.

<img src="https://user-images.githubusercontent.com/4038174/168447280-1711786d-6a4c-45ec-8e88-c9a25e48302e.png" width=200>

|Pin|Function|Colour|
|---|--------|------|
|1  |LANE DEPARTURE WARNING HEATER FRONT WINDOW -|BU-WH|
|2  |-       |      |
|3  |RADAR CAN HIGH|BN-BU|
|4  |12V (IGNITION/ACCESSORY)|BU-BN|
|5  |GROUND  |BK-WH|
|6  |-       |      |
|7  |-       |      |
|8  |LANE DEPARTURE WARNING HEATER FRONT WINDOW +|BU-GY|
|9  |CAN BUS HIGH SPEED 2 LOW|GY-BU|
|10 |CAN BUS HIGH SPEED 2 HIGH|GN-OG|
|11 |RADAR CAN LOW|GY-BU|
|12 |-       |      |
</details>

<details>
  <summary><strong>Click here to reveal parts list</strong></summary>

|Name|Part|Manufacturer|Links|Notes|
|----|----|------------|-----|-----|
|MINI50 CONN RCPT 12CKT NB NP BLK|0348240124|Molex|WM10324-ND at DigiKey|Harness connector|
|CONN HEADER R/A 12POS 2MM|0348260124|Molex|WM10328-ND at DigiKey|Harness receptacle|
|CONN SOCKET 24AWG CRIMP TIN|5600230421|Molex|WM8745CT-ND at DigiKey|Pins for harness connector|
</details>

Ford Q4 / BlueCruise / CAN FD (20-pin)

The latest IPMA with Mobileye Q4 chip for BlueCruise on the CAN FD platform (extra hardware required). The only vehicles using this platform are the Ford Mustang Mach-E 2021+, Ford F-150 2021+ and the new Ford F-150 Lightning 2022+.

Not all of the connectors sources have been identified for this harness. If you are building it yourself, 3D printed parts are required. Otherwise, it can be purchased on the comma shop.

<details>
  <summary><strong>Click here to reveal pinouts</strong></summary>

Connector C4242A (IPMA) Pinout

Connector colour: Black

|Pin|Function|Colour|
|---|--------|------|
|1  |12V<strong></strong>|WH-OG |
|2  |-       |      |
|3  |-       |      |
|4  |PARKING AID SENSORS REAR -|GN-WH|
|5  |SENSOR PARKING AID REAR (RIGHT INNER)|YE-VT|
|6  |SENSOR PARKING AID REAR (RIGHT OUTER)|VT-OG|
|7  |SENSOR PARKING AID ACTIVE PARK ASSIST (AUTOPARK) FRONT LEFT SIDE|BU|
|8  |SENSOR PARKING AID ACTIVE PARK ASSIST (AUTOPARK) FRONT RIGHT SIDE|GY-VT|
|9  |SE""",
  },
  {
    "id": "builtin_wiki_ford_9",
    "title": "Wiki: Ford (10/11)",
    "tags": ["wiki","openpilot","comma","ford"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Ford
https://github.com/commaai/openpilot/wiki/Ford

NSOR PARKING AID FRONT (RIGHT INNER)|WH|
|10 |SENSOR PARKING AID FRONT (RIGHT OUTER)|BN-WH|
|11 |PARKING AID SENSORS FRONT -|YE-OG|
|12 |-       |      |
|13 |GROUND  |BK    |
|14 |-       |      |
|15 |PARKING AID SENSORS REAR +|BU-WH|
|16 |SENSORS PARKING AID REAR (LEFT INNER)|BU-GY|
|17 |SENSORS PARKING AID REAR (LEFT OUTER)|GY-BN|
|18 |SENSOR PARKING AID ACTIVE PARK ASSIST (AUTOPARK) REAR RIGHT SIDE|BU-BN|
|19 |SENSOR PARKING AID ACTIVE PARK ASSIST (AUTOPARK) REAR LEFT SIDE|BU-GN|
|20 |SENSOR PARKING AID FRONT (LEFT INNER)|VT-GN|
|21 |SENSOR PARKING AID FRONT (LEFT OUTER)|GN-OG|
|22 |PARKING AID SENSORS FRONT +|VT-GY|
|23 |-       |      |
|24 |SWITCH - PARKING AID|GN-BN|

: Unclear if this is constant battery 12V or only in accessory mode/ignition

Connector C4242B (IPMA) Pinout

Connector colour: Grey

|Pin|Function|Colour|
|---|--------|------|
|1  |-       |      |
|2  |RIGHT REAR RADAR GROUND|BU-BN|
|3  |-       |      |
|4  |-       |      |
|5  |LEFT REAR RADAR GROUND|VT-BN|
|6  |LANE DEPARTURE WARNING HEATER FRONT WINDOW -|BU-WH|
|7  |CAN BUS HIGH SPEED FD LOW|BU-OG|
|8  |CAN BUS HIGH SPEED FD HIGH|YE-OG|
|9  |FRONT RADAR GROUND|GN-WH|
|10 |-       |      |
|11 |RIGHT REAR RADAR POWER<strong></strong>|VT-GY|
|12 |REAR RADAR CAN BUS LOW|YE-BU|
|13 |REAR RADAR CAN BUS HIGH|GN-VT|
|14 |LEFT REAR RADAR POWER<strong></strong>|YE-GN|
|15 |REAR RADAR CAN BUS LOW|YE-BU|
|16 |REAR RADAR CAN BUS HIGH|GN-VT|
|17 |LANE DEPARTURE WARNING HEATER FRONT WINDOW +|BU-GY|
|18 |FRONT RADAR POWER<strong></strong>|GY|
|19 |FORWARD LOOKING RADAR CAN BUS LOW|GY-BU|
|20 |FORWARD LOOKING RADAR CAN BUS HIGH|BN-BU|

: Seems to be switched 12V power (only on accessory mode/ignition)

Connector C4242C (IPMA) Pinout

Connector colour: Black

|Pin|Function|Colour|
|---|--------|------|
|1  |-       |      |
|2  |RIGHT FRONT RADAR GROUND|GN-BU|
|3  |LEFT FRONT RADAR GROUND|BN-GN|
|4  |FRONT RADAR CAN BUS LOW|WH-OG|
|5  |FRONT RADAR CAN BUS HIGH|WH-VT|
|6  |-       |      |
|7  |-       |      |
|8  |-       |      |
|9  |-       |      |
|10 |-       |      |
|11 |RIGHT FRONT RADAR POWER|GN-BU|
|12 |FRONT RADAR CAN BUS LOW|WH-OG|
|13 |FRONT RADAR CAN BUS HIGH|WH-VT|
|14 |LEFT FRONT""",
  },
  {
    "id": "builtin_wiki_ford_10",
    "title": "Wiki: Ford (11/11)",
    "tags": ["wiki","openpilot","comma","ford"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Ford
https://github.com/commaai/openpilot/wiki/Ford

RADAR POWER|YE-OG|
|15 |-       |      |
|16 |-       |      |
|17 |-       |      |
|18 |-       |      |
|19 |-       |      |
|20 |-       |      |
</details>

<details>
  <summary><strong>Click here to reveal parts list</strong></summary>

Note: These parts haven't been tested/confirmed.

|Name|Part|Manufacturer|Links|Notes|
|----|----|------------|-----|-----|
|?|?|TE Connectivity||Need to source C4242A harness connector|
|Generation Y Connector, 20 Pos, 2.54mm|2288276-1|TE Connectivity|TE Connectivity|For C4242B and C4242C harness connectors?|
|?|?|TE Connectivity||Need to source harness receptacles|
</details>

Useful links

- [Safer Control of Steering]
- [Discord]

[Safer Control of Steering]: //medium.com/@commaai/safer-control-of-steering-362f3526c9ab
[Discord]: //discord.comma.ai""",
  },
  {
    "id": "builtin_wiki_gm_0",
    "title": "Wiki: GM (1/7)",
    "tags": ["wiki","openpilot","comma","gm"],
    "refresh": False,
    "text": """Source: openpilot Wiki — GM
https://github.com/commaai/openpilot/wiki/GM

◄ Home
Vehicle Requirements
Supported Vehicles
Note that this table may not be complete. Please ask in Discord if anything is unclear, and we will update it.
ALL 2024+ GM EVs are using Global B; Therefore, they're unsupported. (N/A†)

| Make      | Model       | Trim                         | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|-----------|-------------|------------------------------|------|------|------|------|------|------|------|------|------|------|
| Buick     | Envision    |                              |      |      |      |      |      | N/A† | N/A† | N/A† | N/A† | N/A† |
| Buick     | Regal       | Essence                      |      | ASCM | ASCM | ASCM |      |      |      |      |      |      |
| Buick     | Lacrosse    | w/ ACC                       |      | ASCM | ASCM | ASCM |      |      |      |      |      |      |
| Cadillac  | ATS         |                              |      |      |      |      |  --  |  --  |  --  |  --  |  --  |  --  |
| Cadillac  | ATS-V       |                              |      |      |      |      |  --  |  --  |  --  |  --  |  --  |  --  |
| Cadillac  | CTS         |                              |      |      |      |      |  --  |  --  |  --  |  --  |  --  |  --  |
| Cadillac  | CTS-V       |                              |      |      |      |      |  --  |  --  |  --  |  --  |  --  |  --  |
| Cadillac  | CT4         |                              |  --  |  --  |  --  |  --  |      | N/A† | N/A† | N/A† | N/A† | N/A† |
| Cadillac  | CT5         |                              |  --  |  --  |  --  |      |      | N/A† | N/A† | N/A† | N/A† | N/A† |
| Cadillac  | CT6         | w/ LKAS                      |      | GM | GM |      |      |      |      |      |      |      |
| Cadillac  | Escalade    | w/ ACC                       |      | ASCM | ASCM | ASCM | ASCM | N/A† | N/A† | N/A† | N/A† | N/A† |
| Cadillac  | Escalade ESV| w/ ACC                       | ASCM | ASCM | ASCM | ASCM | ASCM | N/A† | N/A† | N/A† | N/A† | N/A† |
| Cadillac  | XT4         | Driver Assist Package        |      |      |      |      |      |      |      | SDGM |      |      |
| Cadillac  | XT5         | w/ LKA""",
  },
  {
    "id": "builtin_wiki_gm_1",
    "title": "Wiki: GM (2/7)",
    "tags": ["wiki","openpilot","comma","gm"],
    "refresh": False,
    "text": """Source: openpilot Wiki — GM
https://github.com/commaai/openpilot/wiki/GM

S                      |      |      | GM |      |      |      |      |      |      |      |
| Cadillac  | XT6         |                              |      |      |      |      |      |      |      |      |      |      |
| Chevrolet | Blazer      | w/ ACC                       |      |      |      |      |      |      |      |      |      |      |
| Chevrolet | Blazer EV   |                              |      |      |      |      |      |      |      |      | N/A† | N/A† |
| Chevrolet | Bolt        | w/ SuperCruise               |      |      |      |      |      |      |      |      |      |      |
| Chevrolet | Bolt        | w/ ACC, w/o SuperCruise      |      |      |      |      |      |      | GM   | GM   |      |      |
| Chevrolet | Bolt        | w/ LKAS                      |      | GM | GM | GM | GM | GM | GM | GM |      |      |
| Chevrolet | Corvette    |                              |      |      |      |      |      | N/A† | N/A† | N/A† | N/A† | N/A† |
| Chevrolet | Equinox     | w/ ACC                       |      |      |      | GM   | GM   | GM   | GM   |      |      |      |
| Chevrolet | Equinox     | w/ LKAS                      |      |      |      | GM | GM | GM | GM |      |      |      |
| Chevrolet | Equinox EV  |                              |      |      |      |      |      |      |      |      | N/A† | N/A† |
| Chevrolet | Malibu      | w/ ACC                       |      | GM   | GM   | GM   | GM   | GM   | GM   | GM   |      |      |
| Chevrolet | Malibu      | w/ LKAS                      | GM | GM | GM | GM | GM | GM | GM | GM |      |      |
| Chevrolet | Silverado   | 1500 w/ ACC                  |      |      |      |      | GM   | GM   | N/A† | N/A† | N/A† | N/A† |
| Chevrolet | Silverado   | 2500                         |      |      |      |      | N/A‡ | N/A‡ | N/A† | N/A† | N/A† | N/A† |
| Chevrolet | Suburban    | w/ ACC                       | GM | GM | GM | GM | GM | N/A† | N/A† | N/A† | N/A† | N/A† |
| Chevrolet | Suburban    | w/ LKAS                      | GM | GM | GM | GM | GM | N/A† | N/A† | N/A† | N/A† | N/A† |
| Chevrolet | Tahoe       |                              |      |      |      |      |      | N/A† |""",
  },
  {
    "id": "builtin_wiki_gm_2",
    "title": "Wiki: GM (3/7)",
    "tags": ["wiki","openpilot","comma","gm"],
    "refresh": False,
    "text": """Source: openpilot Wiki — GM
https://github.com/commaai/openpilot/wiki/GM

N/A† | N/A† | N/A† | N/A† |
| Chevrolet | Trailblazer | w/ ACC                       |      |      |      |      |      | GM   | GM   |      |      |      |
| Chevrolet | Trailblazer | w/ LKAS                      |      |      |      |      |      | GM | GM |      |      |      |
| Chevrolet | Traverse    | RS/Premier/High Country Trim |      |      |      |      |      |      | SDGM | SDGM |      |      |
| Chevrolet | Volt        | w/ ACC                       |      | ASCM | ASCM | SDGM |      |      |      |      |      |      |
| Chevrolet | Volt        | w/ LKAS                      | OBD| OBD| OBD |      |      |      |      |      |      |      |
| Holden    | Astra       | w/ ACC                       |      | ASCM | ASCM | ASCM |      |      |      |      |      |      |
| GMC       | Acadia      | w/ ACC                       |      |      | GM   | GM   |      |      |      |      |      |      |
| GMC       | Sierra      | 1500 w/ ACC                  |      |      |      |      | GM   | GM   |      |      |      |      |
| GMC       | Yukon       | w/ LKAS and ACC              |      |      |      | GM   | GM   | N/A† | N/A† | N/A† | N/A† | N/A† |
- : This vehicle is not supported on stock openpilot and requires a fork such as OPGM.
- †: This vehicle is on GM's new Global B platform which has encrypted messaging. Currently there is no way around this.
- ‡: This vehicle does not have electric power steering so openpilot cannot steer the car.

Harnesses
- ASCM(new): A new ASCM harness that is more like the standard openpilot installation developed by thinkpad4by3 link to Discord, more details here ASCM doc, it no longer requires an additional OBD harness and can auto switch between stock and openpilot. 
- SDGM: SDGM harness is for newer GM hardware setup that uses an ASCM but also have the OBD-II port filtered. Developed by garrettpall link to Discord, more details here SDGM doc and SDGM github repo
- ASCM(old): This requires the OBD harness (sold by Comma) as well as a third-party harness known as the L&P harness. It can be purchased below. This hardware setup is deprecated and will be replaced at some point with a new all-in-one ASCM harness.
- OBD""",
  },
  {
    "id": "builtin_wiki_gm_3",
    "title": "Wiki: GM (4/7)",
    "tags": ["wiki","openpilot","comma","gm"],
    "refresh": False,
    "text": """Source: openpilot Wiki — GM
https://github.com/commaai/openpilot/wiki/GM

: This requires the OBD harness (sold by Comma). No L&P harness required. These cars may also work with the standard GM harness.

Unofficial Vehicles
Any GM vehicle 2016+, but before Global B (Encrypted Can Bus)
Need to have front camera and lane keeping. These will only control steering, not gas/brake. They will only work with custom forks, not with stock openpilot.

Volt '16, '17, and '18 without Adaptive Cruise Control
On Volt LT and Premier (No Radar and ACC), the car's firmware may be modified to enable full longitudinal control. Note that DIY firmware mods come at the risk of bricking your car.

Firmware modifications required for 2017 LT Volt Openpilot

There are also a few hardware modification necessary or optional depending on your car.
 Radar: Optional if you want to use Vision-Only ACC from OP
 Premier Steering Wheel Replacement: Required for LT, not for Premier with LKAS
 LKAS Camera Bypass Plug: Required for Premier with LKAS, not for LT

Hardware modifications required for 2017 LT Volt Openpilot

Cars with an ASCM and a SDGM
These cars are usually from 2019 to when the platform switched to Global B and have a front radar. A SDGM Harness is needed to connect to the comma and is located behind the OBD port.

Bolt
See the openpilot Bolt wiki.

Capabilities

Steering is unavailable under 6 MPH(10 KPH).

Model year differences

On Volt '17, initial engage with openpilot must be at a speed above 18 mph. Sometimes cruise faults at speeds below 18 mph. Auto-resume is supported, which means openpilot will resume following a stopped lead car when the lead car pulls away.

On Volt '18, initial engage starts at 1 mph. Auto-resume is not supported, so you need to either press RES button on control pad or the gas pedal to resume. Auto-resume using a comma pedal is currently WIP.

On Volt '19, control over steering may be accomplished with the SDGM Harness (instead of the OBD-II and ASCM harness combo listed below).

General experience

No steering under 6 MPH is barely noticeable unless you do a lot of gridlock traffic, since it is slow and does not take long to reach. Some curves are too tight to steer unless vision braking is enabled (see Twilsonco's fork). H""",
  },
  {
    "id": "builtin_wiki_gm_4",
    "title": "Wiki: GM (5/7)",
    "tags": ["wiki","openpilot","comma","gm"],
    "refresh": False,
    "text": """Source: openpilot Wiki — GM
https://github.com/commaai/openpilot/wiki/GM

ighway to highway merges are generally fine. Lane changing is fine. Once on highway it's smooth sailing, interventions generally come down to other people doing the wrong thing, or if you're in the right lane and you need to slow for someone to merge.

Hardware
1. Comma 3x with OBD-II car harness (The one with USB-C connector)

ASCM Bypass (For Volt Premier with Stock LKAS and ACC)
In Volt with stock LKAS and ACC, radar and camera data will be sent to ASCM to process. ASCM needs to be bypassed to allow normal operation of OP. 

2. ASCM wiring harness (DO NOT Buy if you have an LT or Premier WITHOUT ACC Radar)
<br><img src="https://127003977.cdn6.editmysite.com/uploads/1/2/7/0/127003977/s803498971386427909p20i6w1440.jpeg?width=2400&optimize=medium" width="600">

Other ASCM Bypass Harness Methods
 Bypass ASCM and power the radar, choose one of:
    1. GM giraffe - $300-$500
    <br><img src="https://github.com/commaai/openpilot/assets/76917194/b5f39ae7-ad4c-42fa-8b19-44103cfe3477" width="300">
    2. ASCM connector Amazon / Amazon alt - $7-10 + Cam molex connector digikey - $10
    3. 0.1" header homebrew harness

DIY ASCM Harness Examples

ASCM 14-pin stub

<img src="https://github.com/commaai/openpilot/assets/76917194/da255583-5742-446e-8283-e19683c555ff" width="300">
<img src="https://github.com/commaai/openpilot/assets/76917194/9856af43-879c-4b40-8a47-77e2b8c85854" width="300">
<img src="https://github.com/commaai/openpilot/assets/76917194/0d9e5df4-41e6-4e2e-b9ba-d865846e9993" width="300">

Camera stub

<img src="https://github.com/commaai/openpilot/assets/76917194/f5e7dc7a-7699-418d-9282-84eeb3c7f4b1" width="400">

Connect switched +12V (e.g. ignition on, rearview mirror connector or driver fusebox) to pin 9 (radar power) of cam connector. This will turn on the front radar when the car is powered on.

Original instructions from Zoneos

Homemade OBD-II to OBD-C Harness
  Map OBD-II to OBD-C female (at comma device) schematic

|   | OBD-II |   | OBD-C |
|---|---|---|---|
| 4 | GND | GND | |
| 6 | CAN1H | A2 | CAN0H |
| 14 | CAN1L | A3 | CAN0L |
| 3 | CAN2H | A11 | CAN1H |
| 11 | CAN2L | A10 | CAN1L |
| 12 | CAN3H | B2 | CAN2H
| 13 | CAN3L | B3 | CAN2L
| 16 | 12""",
  },
  {
    "id": "builtin_wiki_gm_5",
    "title": "Wiki: GM (6/7)",
    "tags": ["wiki","openpilot","comma","gm"],
    "refresh": False,
    "text": """Source: openpilot Wiki — GM
https://github.com/commaai/openpilot/wiki/GM

V | VBUS | |
| | | B8 | SBU2 1kΩ to GND |

Troubleshooting

CAN Error, OBD-C Connector Orientation

ODB-C cable orientation matters. If you receive a CAN Error, flip the OBD-C connector orientation 180º either at the male-to-male adapter or at the OBD-II car port.

Cruise Fault Warning on Volt (Brake Pedal Positioning)

An issue where ACC brake-pressed is not the same as openpilot brake-pressed. This causes a cruise fault or controls mismatched warning when engaging, tapping the brakes, or hitting bumps.

The pedal failure is addressed by service bulletin for 2016-2017 Volt Brake Pedal Push Rod Retainer (part 39081933), TSB 16-NA-147. If using the top of your foot to pull up on the brake pedal resolves the fault, this is likely the cause.

GM dealerships may fix this fault for free - just make sure to remove the OBD-II splitter and put the ASCM toggle switch in dealer mode before taking the Volt in for service.

This condition is often mis-diagnosed by service centers - their first diagnostic step is usually to re-flash the front camera and/or radar sensor. Politely referencing TSB 16-NA-147 should help guide the service department on the right path.

A loose brake pedal affected by this issue could theoretically be a huge issue. Imagine driving around a curve, and openpilot disengages randomly from this issue! Don't try to fix this issue in software, fix the hardware!!!

Forks that Play Nice with GM Vehicles

 OPGM (supports 3 and 3x)
 Twilsonco Volt GM Fork (supports 3, some branches supports 3x)
 FrogPilot (supports 3 and 3x)
 SunnyPilot (supports 3 and 3x)
 StarPilot (supports 3 and 3x)
Helpful Videos

 2017 Volt Install
 2018 Volt Install
 WatchJRGo Install and Demo Video

Terms
OpenPilot General Terms
See General-Terms.

GM Specific Terms
Term | Abbreviation | Definition
--- | --- | ---
Active Safety Control Module | ASCM | Car computer/module that does sensor fusion from Radar and Camera to create ACC and LKA messages to PCM (powertrain control module). Typically located in the trunk.
Calibration | n/a | Packaged adjustments to running parameters of firmware running on GM vehicles. Updates available from SPS within TIS2Web
Developmental Programming System""",
  },
  {
    "id": "builtin_wiki_gm_6",
    "title": "Wiki: GM (7/7)",
    "tags": ["wiki","openpilot","comma","gm"],
    "refresh": False,
    "text": """Source: openpilot Wiki — GM
https://github.com/commaai/openpilot/wiki/GM

| DPS | Software application that allows direct programming of vehicle modules without an online connection. This allows the possibility of custom programming not otherwise supported by GM.
Diagnosis Trouble Code | DTC | DTC, General Motors OBD-II Trouble Codes
Firmware | FW | Base operating system for various devices throughout the vehicle. Updates available from SPS within TIS2Web
Global Diagnostic System 2  | GDS2 | GM system for advanced diagnostics and firmware flashing
GM Local Area Network | GMLAN | Single wire propriety interface present on the CAN connector in GM vehicles.
Multiple Diagnostic Interface | MDI | GM service device connecting the vehicle to a computer. Lower price generics exist such as vxdiag.
Serial Data Gateway Module | SDGM | Functions as a gateway to isolate the secure networks on the vehicle from unsecured networks. Isolating primary networks helps ensure advanced driver assistance systems and active safety features, such as enhanced collision avoidance, can all operate in conjunction with each other.
Service Programming System | SPS | Firmware and calibrations within the TIS2Web application. Updates can be seen for vehicles by VIN without cost here.
Tech2 for Windows | Tech2Win | Emulated legacy diagnostic interfaces for Windows. Runs in an emulated terminal.
Techline Information System | TIS2Web | ACDelco site providing diagnostics and firmware for cars on a subscription basis. Interacts with vehicle via GM MDI. Java webstart application.
Vehicle Intelligence Platform | VIP | VIP, which has also been referred to as Global B, is a new electrical architecture that has a five-fold increase in system capacity and responsiveness over the current Global A system that can provide the required electrical bandwidth and data processing power to run advanced driver assistance systems (ADAS) and supports over-the-air updates for the vehicle’s operating system, infotainment and more. Cybersecurity is another key aspect of the Vehicle Intelligence Platform, protecting GM vehicles and their users from data hacking attempts and other cyberattacks.""",
  },
  {
    "id": "builtin_wiki_fca_0",
    "title": "Wiki: FCA (1/2)",
    "tags": ["wiki","openpilot","comma","fca"],
    "refresh": False,
    "text": """Source: openpilot Wiki — FCA
https://github.com/commaai/openpilot/wiki/FCA

◄ Home

Make-Specific Terms

For general terms, go here.

Term | Abbreviation | Definition
--- | --- | ---
LaneSense | LKAS | Stock lane keeping system (can turn the wheel, you need this.)
Adaptive Cruise Control | ACC | Stock cruise control system with radar that paces the vehicle in front of you (you need this.)
Fiat Chrysler of America | FCA | You'll see this term a lot.  It just groups Ram, Jeep, Chrysler, Dodge, Fiat, etc into one.

Current community supported vehicles: (must have ACC and LaneSense)
2017-2018 Jeep Grand Cherokee (all trims including SRT, Trackhawk)
2019+ Jeep Grand Cherokee (all trims including SRT, Trackhawk)  minimum steer speed 39 mph
2017-2018 Chrysler Pacifica (all trims and powertrains)
2019+ Chrysler Pacifica (all trims and powertrains)  minimum steer speed 39 mph
2019+ Jeep Cherokee (KL) (all trims)  minimum steer speed 32 mph (Confirmed in 2019 model with ACC and LaneSense)
To add openpilot to one of the above vehicles, a comma two (c2) or newer is required, and FCA Harness.  The official openpilot releases from comma work with the above vehicles except the Jeep Cherokee (KL) which is supported by a community-maintained fork.

openpilot Capabilities

Lateral Control

Control over the steering wheel.

Torque

Minimum Speeds

Chrysler Pacifica and Jeep Grand Cherokee models years 2017-2018 can steer down to 9 mph.

Jeep Cherokee model year 2019 can steer down to 32 mph.

Model years 2019 and later can start steering once reaching 39 mph, and then steer down to approximately 30 mph.

Longitudinal Control

Control over the gas and brakes.

Longitudinal control is provided by the stock system that came with the car.

2019+ Ram 1500 with ACC and LaneSense

Owners of Ram 1500's interested in making openpilot work with their trucks would need a comma two (c2) and Dev Harness, outfitted with connectors as found in this document: https://1drv.ms/b/s!AhlEjIwibjKfiZojQEU934HfcvMHA?e=mOVWBh.
Discord user Tunder has a working fork for Ram 1500's.  It is in active development, and does NOT conform to comma's safety standards.  It has working lateral control as of March 28, 2021.  Ram 1500 owners are encouraged to contribute to the development and""",
  },
  {
    "id": "builtin_wiki_fca_1",
    "title": "Wiki: FCA (2/2)",
    "tags": ["wiki","openpilot","comma","fca"],
    "refresh": False,
    "text": """Source: openpilot Wiki — FCA
https://github.com/commaai/openpilot/wiki/FCA

upstreaming of the Ram port to comma's openpilot repo as a community supported vehicle.  The software can be found here: https://github.com/Tundergit/waifupilot.git, branch 082-testing.  Use of this fork is entirely at your own risk, and nobody but you is responsible for anything that happens as a result of the use of any documents or software linked on this page.

Ram 2500 and 3500's equipped with Active LaneSense may also be eligible candidates, late models have an electric assist motor that may be actuable.

Ram models with the radar behind the mirror may be openpilot longitudinal support eligble, and is something that will be investigated in the future.

2014-2018 Chrysler 200, 2014-2019 Jeep Cherokee (KL), late model Jeep Renegade, late model Jeep Compass, 2014-2018 Dodge Chargers, 2014-2018 Chrysler 300 equipped with ACC and LaneSense

These vehicles work with openpilot via a fork maintained by Discord member, Tunder.  Those interested should contact Tunder directly, as the fork is highly experimental and in active development.  It can be found, and forked, from https://github.com/Tundergit/waifupilot.git, branch: 200-devel.   This implementation does NOT conform to safety standards enforced by comma.  Use of this fork is entirely at your own risk, and nobody but you is responsible for anything that happens as a result of the use of any documents or software linked on this page.

Owners of the above vehicles will need a comma two (c2) or newer and Dev Harness, outfitted with the connectors found in this document: https://1drv.ms/b/s!AhlEjIwibjKfiZoczAAEKfpPBOIE-w?e=SjJmJQ""",
  },
  {
    "id": "builtin_wiki_hyundai_kia_genesis_0",
    "title": "Wiki: Hyundai Kia Genesis (1/2)",
    "tags": ["wiki","openpilot","comma","hyundai"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Hyundai Kia Genesis
https://github.com/commaai/openpilot/wiki/Hyundai-Kia-Genesis

◄ Home

Harness Guide

Before purchasing a harness for an unsupported vehicle, make sure you are purchasing the correct type.
It's important to look where the notches are on your plug side, and ensure they match correctly.

You can find this connector plugged into your Lane-Keep camera which is located near your rear-view mirror. You will need to pull back some trim to expose the camera. Once you do, unplug the connector and compare it to the types below.

The harnesses are grouped by same notch types. One missing wire is fine.
The color of the connector may help when identifying harnesses.

---

non-HDA2 - wiring diagram 

HDA2 - Hyundai S does not exist yet, you'll need to flip Hyundai M in the meantime.

---

non-HDA2 - wiring diagram 

HDA2 - wiring diagram 

different wiring / non-HDA2 - wiring diagram 

different wiring / HDA2 - Hyundai T does not exist yet, you'll need to flip Hyundai N in the meantime.

---

non-HDA2 - wiring diagram 

HDA2 - wiring diagram 

different wiring / non-HDA2 - wiring diagram 

---

non-HDA2 - wiring diagram 

HDA2 - wiring diagram 

---

wiring diagram 

wiring diagram 

---

wiring diagram 

wiring diagram 

---

wiring diagram 

wiring diagram 

---

wiring diagram 

wiring diagram 

---

Same connector housing as a Toyota harness, but different wiring.
wiring diagram 

---

Make-Specific Terms

For general terms, go here.

Abbreviation | Term | Definition
--- | --- | ---
SCC | Smart Cruise Control | A fancy way to say ACC, or adaptive cruise control.
HDA | Highway Driver Assist | Combines LFA and SCC with map data to create a more comfortable level 2 experience.
LFA | Lane Follow Assist | A fancier LKAS that centers but nags

openpilot Capabilities

Lateral Control

Control over the steering wheel.

For HKG cars that have critical damping (ping pong, oscillation, ziggy zaggies) no matter your settings, PID tuning may not be right for your car.  You can try INDI tuning instead by adding these five lines to your relevant car in /car/hyundai/interface.py :

ret.lateralTuning.init('indi')
ret.lateralTuning.indi.innerLoopGain = 3.0
ret.lateralTuning.indi.outerLoopGain = 2.0
ret.lateralTuning.indi.timeConstant = 1.0
ret.lateralT""",
  },
  {
    "id": "builtin_wiki_hyundai_kia_genesis_1",
    "title": "Wiki: Hyundai Kia Genesis (2/2)",
    "tags": ["wiki","openpilot","comma","hyundai"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Hyundai Kia Genesis
https://github.com/commaai/openpilot/wiki/Hyundai-Kia-Genesis

uning.indi.actuatorEffectiveness = 1.0

Comment out the lines containing Kp, Ki and Kf with a # at the beginning of the line.

The above is only a start point, and needs tuning like any variable parameter.  Raise and lower the LoopGain's by 0.1 at a time, both up or down, until your condition improves.  For Stinger and Genesis, the actuatorEffectiveness start point should be 1.5.

Longitudinal Control

Control over the gas and brakes.

At the moment, longitudinal control is provided by the stock system that came with the car.
In the future, we will be able to control longitudinally via openpilot for any vehicle whose trims can support SCC, even if not equipped""",
  },
  {
    "id": "builtin_wiki_subaru_0",
    "title": "Wiki: Subaru (1/5)",
    "tags": ["wiki","openpilot","comma","subaru"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Subaru
https://github.com/commaai/openpilot/wiki/Subaru

◄ Home

Make-Specific terms

For general terms, go here.

Term | Abbreviation | Definition
--- | --- | ---
EyeSight | ES | Subaru's vision based adaptive cruise / emergency braking / lane keeping system
Global Platform | Global / gen1 | Subaru's current unified platform, allowing a consistent core between different models. Lowering cost, and improving ease of development. Models using Global Platform include 2017+ Impreza, 2018+ Crosstrek
gen2 | Global gen2 | 2020+ Legacy and 2020+ Outback. Same as global gen1, except moved some messages to bus1, especially ones required for long control. Requires EyeSight to be disabled to have long control (POC done).
Pre-Global Platform | Pre-Global | Refers to models with ES predating Global Platform, for example 2015-2019 Outback, 2015-2019 Legacy, 2017-2018 Forester
Modern Platform | Angle-based | 2023+ Global models using angle-based steering control and Subaru D harness

Supported Models

Global
| Make   | Model (US Market Reference) | Supported Package | ACC   | No ACC accel below | No ALC below | Harness |
|--------|-----------------------------|-------------------|-------|--------------------|--------------|---------|
| Subaru | Ascent 2019-21              | EyeSight          | Stock | 0mph               | 0mph         | A |
| Subaru | Crosstrek 2018-23           | EyeSight          | Stock | 0mph               | 0mph         | A |
| Subaru | XV 2018-23                  | EyeSight          | Stock | 0mph               | 0mph         | A |
| Subaru | Forester 2019-21            | EyeSight          | Stock | 0mph               | 0mph         | A |
| Subaru | Impreza 2017-22             | EyeSight          | Stock | 0mph               | 0mph         | A |
| Subaru | Legacy 2020-22              | EyeSight          | Stock | 0mph               | 0mph         | B |
| Subaru | Outback 2020-22             | EyeSight          | Stock | 0mph               | 0mph         | B |

Openpilot supported vehicles list https://comma.ai/vehicles#subaru

Modern (Angle-Based Steering)

All modern US-market Subarus are angle-based steering and use the Subaru D harness.

There is no indication that modern Subaru EyeSight systems are encrypte""",
  },
  {
    "id": "builtin_wiki_subaru_1",
    "title": "Wiki: Subaru (2/5)",
    "tags": ["wiki","openpilot","comma","subaru"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Subaru
https://github.com/commaai/openpilot/wiki/Subaru

d (Except the electric vehicles, as they are rebadged Toyotas).

Confirmed Working (Forced Fingerprint Branch)

The following models have been confirmed working using a forced fingerprint branch:

- Crosstrek 2024–2025
- Outback 2023–2025 (3 camera modules confirmed; 2 camera module validated on 2024 Outback)
- Outback 2022 (Australian Model - Different to USDM Outback 2022. See below for AU's Harness)
- Impreza 2025  
- Ascent 2023,2025
- Legacy 2022,2025(2 camera)
- Not supported, but forks have existed which worked for them:
  - Does not work, but is possible: Forester 2023 (Pre-global, but angle-based)
- Does not work, unconfirmed 2026 Crosstrek Hybrid
  - https://discord.com/channels/469524606043160576/525718620517564446/1475538719204315422

Installer branch:
https://installer.comma.ai/jacobwaller/master

Required PRs for Upstream Support

Modern Subaru support requires the following PRs:

- https://github.com/commaai/opendbc/pull/3103  
- https://github.com/commaai/opendbc/pull/2864  

Until merged upstream, modern Subaru support requires custom branches.

Hardware Requirements

- Comma 3X / 4
- Subaru D harness (US variants)  

Installation Notes

- Remove the EyeSight shroud by pushing it forward (parallel to the windshield) with moderate force. This is applicable to the Subarus I have dealt with directly, but some (2023 Outback/Ascent, for example) have screws. Do not break your shroud!
- The Subaru D connector is typically located on the left side of the EyeSight module.
- International (non-US) Models may be different. For example, the Australian 2022 Outback needs a slightly modified harness: https://discord.com/channels/469524606043160576/525718620517564446/1464828879129678069

Example Shroud

<img width="800" height="600" alt="image" src="https://github.com/user-attachments/assets/ff250a05-d998-4586-b963-bb491f6e5e37" />

The connector you want is behind "B". Push that shroud forward along the windshield

Pre-global
| Make   | Model (US Market Reference) | Supported Package | ACC   | No ACC accel below | No ALC below | Harness |
|--------|-----------------------------|-------------------|-------|--------------------|--------------|---------|
| Suba""",
  },
  {
    "id": "builtin_wiki_subaru_2",
    "title": "Wiki: Subaru (3/5)",
    "tags": ["wiki","openpilot","comma","subaru"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Subaru
https://github.com/commaai/openpilot/wiki/Subaru

ru | Forester 2017-18            | EyeSight          | Stock | 0mph               | 0mph         | A |
| Subaru | Legacy 2015-19              | EyeSight          | Stock | 0mph               | 0mph         | A |
| Subaru | Levorg 2016-20              | EyeSight          | Stock | 0mph               | 0mph         | A |
| Subaru | Outback 2015-19             | EyeSight          | Stock | 0mph               | 0mph         | A |
| Subaru | WRX 2016-2018               | EyeSight          | Stock | 0mph               | 0mph         | A |

Pre-global models are upstreamed but dashcam only  
https://github.com/commaai/opendbc/blob/master/opendbc/car/subaru/interface.py#L21

Work in progress
| Make   | Model (US Market Reference) | Supported Package | ACC         | No ACC accel below | No ALC below | Comments |
|--------|-----------------------------|-------------------|-------------|--------------------|--------------|----------|
| Subaru | Crosstrek 2020 Hybrid       | EyeSight          | Stock       | 0mph               | 0mph         | Subaru B harness, ACC disengage on gas press does not work |
| Subaru | Forester 2020 Hybrid        | EyeSight          | Stock       | 0mph               | 0mph         | upstream PR open, needs better CruiseActivated signal |
| Subaru | Forester 2022               | EyeSight          | Stock       | 0mph               | 0mph         | Subaru C harness, needs better CruiseActivated signal |
| Subaru | Ascent 2023                 | EyeSight          | Angle-based | 0mph               | 0mph         | Subaru D harness |
| Subaru | Outback 2023–2025           | EyeSight          | Angle-based | 0mph               | 0mph         | Subaru D harness, forced fingerprint branch functional |
| Subaru | Crosstrek 2024–2025         | EyeSight          | Angle-based | 0mph               | 0mph         | Subaru D harness, forced fingerprint branch functional |
| Subaru | Impreza 2025                | EyeSight          | Angle-based | 0mph               | 0mph         | Subaru D harness, forced fingerprint branch functional |
| Subaru | Solterra 2023               | Toyota TSS 3.0    | TBD         | TBD                | TBD          | Toyota B har""",
  },
  {
    "id": "builtin_wiki_subaru_3",
    "title": "Wiki: Subaru (4/5)",
    "tags": ["wiki","openpilot","comma","subaru"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Subaru
https://github.com/commaai/openpilot/wiki/Subaru

ness, CAN FD, SecOC signed |

WIP models support is incomplete and untested  
https://github.com/martinl/openpilot/tree/subaru-community  
https://github.com/martinl/openpilot/issues  

Not supported models

- BRZ - does not have LKAS  

openpilot capabilities

Lateral control

Control over the steering wheel.

Torque (Global / Pre-global)

Older Subarus use torque-based steering control.

Angle (Modern)

Modern Subarus (2023+) use angle-based steering control.

Minimum speeds

0 mph minimum speed for lateral control

Longitudinal control

Control over the gas and brakes.

Longitudinal control is provided by the stock system that came with the car.

Stop and go support

EyeSight ACC stops the car behind a lead vehicle.

On models with electric parking brake:
- ACC will engage hold mode for up to 2 minutes.
- After 2 minutes, the parking brake engages.
- Resume requires manual input.

On traditional handbrake models:
- ACC disengages ~3 seconds after stopping.

Automatic resume for stop and go is implemented in the community-supported branch:
https://github.com/martinl/openpilot/tree/subaru-community

Community videos

Subaru harness install
- 2018 Subaru Crosstrek (global): https://www.youtube.com/watch?v=LD7qiOcPFtU
- 2018 Subaru Legacy (pre-global): https://www.youtube.com/watch?v=-1Snpp3cQEg

Drives
- 2018 Subaru Crosstrek City Drive Timelapse: https://www.youtube.com/watch?v=1iNOc3cq8cs
- 2018 Subaru Impreza City Drive Timelapse: https://www.youtube.com/watch?v=LMCTiQEAdo

Harness pinouts

- Subaru A: https://github.com/commaai/neo/blob/master/carharness/v3/SubaruAHarness.pdf  
- Subaru B: https://github.com/commaai/neo/blob/master/carharness/v3/SubaruBHarness.pdf  
- Subaru C: https://github.com/commaai/neo/blob/master/carharness/v3/SubaruCHarness.pdf  
- Subaru D: https://github.com/commaai/neo/blob/master/carharness/v3/SubaruDHarness.pdf  
- Toyota B: https://github.com/commaai/neo/blob/master/carharness/v3/ToyotaBHarness.pdf  

Subaru A to Subaru B car harness conversion

<img width="408" alt="subaru-outback-2020-pin-swap" src="https://user-images.githubusercontent.com/148686/115105836-19046400-9f6a-11eb-9bbd-3d14309861d2.png">

- 4 <> 8, Can0 High with""",
  },
  {
    "id": "builtin_wiki_subaru_4",
    "title": "Wiki: Subaru (5/5)",
    "tags": ["wiki","openpilot","comma","subaru"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Subaru
https://github.com/commaai/openpilot/wiki/Subaru

Can1 High  
- 6 <> 10, Can0 Low with Can1 Low  
- 18 <> 22, Can1 High with Can2 High  
- 20 <> 24, Can1 Low with Can2 Low""",
  },
  {
    "id": "builtin_wiki_mazda_0",
    "title": "Wiki: Mazda (1/3)",
    "tags": ["wiki","openpilot","comma","mazda"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Mazda
https://github.com/commaai/openpilot/wiki/Mazda

◄ Home

Setup Notes

The Mazda harness sold by Comma requires the use of the included Comma Power.

Make-Specific Terms

For general terms, go here.

Mazda I-ACTIVSENSE is an umbrella term that Mazda uses to describe a series of advanced safety and driver assistance technologies such as ACC, LKAS, Blind-spot monitoring, Smart City brakes and so on. Most models/trims from 2017 and newer come with ACC and LKAS as standard options.

Term | Abbreviation | Definition
--- | --- | ---
Mazda Radar Cruise Control  | MRCC | Mazda Adaptive Cruise Control - ACC
Lane-Keep Assist System | LAS | Mazda LKAS

Supported models
Officially Supported Models
 2021+ CX-9 (good torque, steer down to 28mph)
 2022+ CX-5  (best torque, steer down to zero)

Community Supported Models with Limitation
 2017-2020 CX-9 (2019 and 2020 models have twice the torque compared to earlier years)
 2017-2021 Mazda 6, and CX-5
 2017-2018 Mazda 3
 2017-2020 CX-3 (needs confirmation)
 2019-2023 Mazda 3 / CX-30 / CX-50 and newer use a new driver assistance system and is not yet supported, comma connector is not correct but the community has created a developer harness (see below to make your own).
 2024+ Mazda 3 / CX-30 / CX-50 and newer is not yet supported and no harness is available at this time.

Changing source code, using weighted lockout mitigation or changing EPS is all done at your own risk.

Out of the box, only CX-5 2022 and CX-9 2021 is officially supported. For all other models openpilot is only available in dashcam mode due to a steering lockout that occurs when driver does not touch the steering wheel for more than 5 seconds. Using Stock openpilot with Mazda models that have limitations requires source code changes, and always keeping your hands on the wheel or use of a weighted steering lockout mitigation or changing Electronic Power Steering motor (EPS) to 2021 CX-9 where compatible. Failure to overcome the steering lockout results in the car not responding to steer commands from openpilot.

To change source code from dashcam only mode, change the line in selfdrive/car/mazda/interface.py [[here]](//github.com/commaai/openpilot/blob/master/selfdrive/car/mazda/interface.py#L25)
from:
ret.das""",
  },
  {
    "id": "builtin_wiki_mazda_1",
    "title": "Wiki: Mazda (2/3)",
    "tags": ["wiki","openpilot","comma","mazda"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Mazda
https://github.com/commaai/openpilot/wiki/Mazda

hcamOnly = candidate not in [CAR.CX92021]

to
ret.dashcamOnly = False

If you don't want to make source code change, you can use Mazda community fork, see the link at the bottom of this page.

Note: Some earlier year models 2016-2017 models that are equipped with LKAS are known to work with the Community fork but may require a different connector than the Mazda development connector sold at comma shop.

Mazda openpilot Capabilities

Lateral Control

For the CX-9, Mazda LKAS is not available on low speeds. In particular, LKAS is not available until the car drives above 32mph/52kph. LKAS gets disabled when the speed goes below 28mpg/45kph. When OP is engaged but stock LKAS is not available, OP continues to be engaged but will not steer and will display a warning about steering being unavailable.

22+ CX-5 is able to steer down to zero.

Torque
CX-9 2019-2023 and CX-5 22+ offer the best torque among Mazda cars. They offer twice the torque compared to other models/years allowing them to make tighter turns even on city streets. For other cars the available steering torque is adequate for most highway driving conditions. City driving requires driver intervention on sharp turns.

Minimum Speeds

The following applies to CX-9, but NOT 22+ CX-5. The CX-5 is able to steer down to zero.

 LKAS is allowed when the car drives above 32mph
 LKAS is not allowed when the speed dips below 28mph

Longitudinal Control

Longitudinal control is not supported by OP with Mazda. OP relies on the stock MRCC to control speed. MRCC support follow-to-stop to 0mph and automatic resume if the stop is less than three seconds. OP improve on that by allowing the car to resume without driver intervention after longer delays. Even though MRCC works down to 0mph, the lowest allowed set speed is 19mph.

Custom solutions:
 
Harness Connector parts:
 Classic OP connector
 Camera side
 Car Side
 car connector crimps
 Classic OP connector crimps

Harness wiring:
  
  
  
  Note: Power is supplied to the Comma device via the OBD port from the Comma Power and RJ45 cable.

Mazda 3, CX-30, CX-50 wiring harness (2019 - 2023):

Steering Lockout Mitigation
 Steering Cover
 Weight

Developer TODOs
 Steer down t""",
  },
  {
    "id": "builtin_wiki_mazda_2",
    "title": "Wiki: Mazda (3/3)",
    "tags": ["wiki","openpilot","comma","mazda"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Mazda
https://github.com/commaai/openpilot/wiki/Mazda

o zero
 Steer without lockout
 openpilot longitudinal control (without intercepting the front radar CANBUS)

See Also

 https://medium.com/@to.jafar/how-to-setup-openpilot-on-mazda-3eb54c62fdc5""",
  },
  {
    "id": "builtin_wiki_volvo_0",
    "title": "Wiki: Volvo",
    "tags": ["wiki","openpilot","comma","volvo"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Volvo
https://github.com/commaai/openpilot/wiki/Volvo

There is a work in progress port for the EUCD architecture vehicles (V60 / S60 / XC60 up to 2018, "P3" platform).

https://github.com/incognitojam/openpilot/commits/volvo-v60

Join the #volvo channel on the comma discord.""",
  },
  {
    "id": "builtin_wiki_rivian_0",
    "title": "Wiki: Rivian",
    "tags": ["wiki","openpilot","comma","rivian"],
    "refresh": False,
    "text": """Source: openpilot Wiki — Rivian
https://github.com/commaai/openpilot/wiki/Rivian

- Installation Tips & Tricks

- Optimizing Tire Choice for the Best Openpilot Autosteering Performance on Rivian R1S and R1T""",
  },
]
