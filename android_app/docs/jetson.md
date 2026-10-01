# Set up Jetlink on a Jetson

About an hour the first time, mostly downloads. Set up in or out of the car,
offroad. Keep the Jetson and comma powered and online.

## What you need

- A **Jetson Orin Nano Super Developer Kit (8 GB)**.
- A **64 GB or larger microSD card**, or an NVMe SSD.
- A **comma 3X or comma 4** and a **USB 3 A-to-C data cable**.
- Separate power for the Jetson and comma (the comma cannot power the Jetson).

## 1. Choose your power setup

**Recommended: always-on 12 V power with deep sleep.** Use a straight
12 V-to-DC adapter with a **5.5 mm outer / 2.5 mm inner, center-positive**
plug, rated for at least 25 W (supply and cable).
[Adapter example](transport.md#recommended-jetson-power-setup).

Pick the installer option for your car's power socket:

| Socket powered with the ignition off? | Choose | Ignition off | Car started |
| --- | --- | --- | --- |
| Yes | **Always on** (recommended) | Jetson sleeps after a few minutes, using about **0.3 W** on 12 V. | The comma wakes it. |
| No | **Switched** | Jetson loses power. | It boots, with the model ready about 30 seconds after power-on. |

Socket turns off a few minutes after parking? Choose **Switched**.

**Battery protection** (installer question):

- **Yes:** the comma shuts the Jetson down for low battery or a long park. To
  restart it, press its power button or reconnect its power. Starting the car
  won't.
- **No:** the Jetson stays in deep sleep while parked, with no
  battery-protection shutdown.

<a id="1-put-jetpack-on-the-jetson"></a>
<a id="2-run-the-installer"></a>

## 2. Install Jetlink

Needs **JetPack 7.2.1** (tested) or **6.2** (untested with this release).
JetPack 7.0 and 7.1 do not work.

<details>
<summary>New Jetson? Install JetPack first</summary>

You need another computer, a 16 GB or larger USB stick, a DisplayPort monitor,
and a keyboard. **This erases the selected Jetson drive.**

1. Download the Jetson ISO from [NVIDIA](https://developer.nvidia.com/embedded/jetpack)
   and write it to the USB stick with [balenaEtcher](https://etcher.balena.io/).
2. Connect the monitor, keyboard, storage, and USB stick to the Jetson.
   Power it on, press **Esc**, and select the USB stick in **Boot Manager**.
3. If offered a firmware update, **press Y within 30 seconds**.
4. Choose **Install Jetson ISO** and your target drive. Then remove the USB
   stick and finish the on-screen setup.

Older firmware or problems: [NVIDIA's setup guide](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/quick_start.html).

</details>

On the Jetson, open **Terminal** and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/zoompilot/jetlink/main/install.sh | bash
```

It installs the latest release, and JetPack's TensorRT if it is missing (a
2.3 GB download). Answer the power questions as above. Takes 10–30 minutes;
leave it running. An install from Jetlink 0.6.0 or earlier moves out of Docker
on its next `jetlink update`, keeping its answers, models and prepared engines.

## 3. Connect the comma

1. **Install zoompilot.** After resetting the comma, enter
   **`zoompilot/jetson-trt`** as the install URL. Already on zoompilot? Select
   **jetson-trt** in **Settings > Software > Target Branch >
   Non-Prebuilt Branches**. Wait for installation and any reboot.
2. **Enable Jetlink.** Set **Settings > Models > Accelerator Link** to **USB**.
   Leave **Big Model** at its default.
3. **Connect the cable.** Jetson **USB-A** → comma **USB-C**.
4. **Wait for the green icon.** The model downloads itself; the first prepare
   takes about 3 minutes.

Always-on power: leave both cables connected. The Jetson sleeps when parked and
wakes when you start the car.

Read [daily use](using-jetlink.md) before driving. A phone on the same
network can watch the server on its [status page](using-jetlink.md#status-page);
`jetlink status` prints the address. Frame times per model on a Jetson:
[performance](status.md#measured-performance).

<a id="troubleshooting"></a>

## Need help?

| Problem | Try this |
| --- | --- |
| Installer stopped | Run the install command again. |
| Icon never turns green | Run `jetlink status`. Use the Jetson's USB-A port; try another USB 3 data cable. |
| Jetson will not wake | After a full shutdown, press its power button or reconnect power. Otherwise check **Always on** with `jetlink setup`. |
| Jetson sleeps while you work on it over SSH | Run `jetlink caffeinate` and keep it running. |
| Model fails to prepare or keeps disconnecting | Run `jetlink logs`. Check storage space, power, cable, and cooling. |
| Comma stays on its small model after an update | [Update both the comma and Jetlink](releasing.md). |

<details>
<summary>Commands and reporting a problem</summary>

<a id="everyday-use"></a>
<a id="reporting-a-problem"></a>

```bash
jetlink status      # check Jetlink, the comma connection, the status page address
jetlink logs        # view errors; Ctrl-C to stop watching
jetlink restart     # restart Jetlink
jetlink update      # update to the newest release, keeping your settings
jetlink setup       # change power settings or the status page port
jetlink models      # list, download or prepare models (jetlink models --help)
jetlink caffeinate  # keep it awake until Ctrl-C (-t SECONDS, or while a command runs)
jetlink uninstall   # remove Jetlink
```

Asking for help? Include `jetlink status` output, the model name, the exact
alert, and when it happened. Installer log: `/var/log/jetlink-install.log`.
Server log:

```bash
sudo journalctl -u jetlink-server -b --no-pager > jetson.log
```

</details>

<a id="choosing-a-model"></a>
<a id="downloading-a-model-on-the-jetson"></a>
<a id="what-the-installer-changes"></a>
<a id="installing-by-hand"></a>

[Daily use](using-jetlink.md) · [Model choices](models.md) ·
[Manual installation](installation-reference.md)
