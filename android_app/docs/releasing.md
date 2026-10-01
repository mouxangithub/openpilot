# Updates and rollback

The comma and the server have to speak the same protocol version. A release
that changes it says so in its notes, and across it the two update together: a
comma on the older protocol stays on its small model. Every other release, and
every comma update, can be taken on its own. Update offroad, with both devices
powered and online.

## Updating

1. Update the comma in **Settings > Software** and let it reboot.
2. Update the server:

   - Jetson or Linux PC (installer): run `jetlink update`. It moves to the
     newest release, keeps your settings, and restores the previous server if
     the update fails. An install from 0.6.0 or earlier also moves out of
     Docker, keeping its models and prepared engines.
   - Mac app: quit Jetlink, replace it with the new release, and reopen it.
   - iPhone app: run `git pull` in the checkout, then click **Run** in Xcode.
   - Android app: run `git pull` in the checkout, then build and install it
     again ([Android development](../android/README.md#build)).
   - Mac terminal: run `git pull`, then build `jetlink-server` again
     ([from a terminal](platforms.md#from-a-terminal)).

3. Connect the comma offroad and wait for green. A new Jetlink or model may
   prepare the engine again.

## Rolling back

* Stop using Jetlink now: set **Settings > Models > Accelerator Link** to **Off**.
* Across a protocol change, roll back the comma build and server together;
  one alone leaves them incompatible. Keep the model cache.
* Installer: `jetlink update --ref v0.7.0` (replace with the release to go
  back to). It stays there until `jetlink update --ref latest`.
* Going back to 0.6.0 puts the Docker server back. To come forward from it,
  use the installer, since 0.6.0's `jetlink update` cannot:

```bash
curl -fsSL https://raw.githubusercontent.com/zoompilot/jetlink/main/install.sh | bash -s -- --update --ref latest
```

Manual rollback: [installation reference](installation-reference.md#versions-and-manual-rollback).

<a id="which-jetlink-to-run"></a>

## Maintainer reference

The comma takes Jetlink as a git pin: zoompilot's `develop`,
`danger-unstable` and `jetson-trt` pin a commit on `main`, driven on
`danger-unstable` first, and it may lie between releases. A `v*` release is
cut when the apps, the server or the wire changed, not for the comma's side
alone; its notes list what changed on the comma since the last release too.

Releasing: [publishing guide](publishing.md). A version bump in
`jetlink/__init__.py` means running `JetlinkKit/Scripts/make_pins.py` again;
each release attaches the Linux server tarballs the installer downloads.

<a id="installing-the-app"></a>
<a id="the-container-images"></a>
<a id="signing-secrets"></a>
