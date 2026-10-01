# Jetlink documentation

New? Start with the [quick start](../README.md#quick-start).

## Setup and daily use

| I want to... | Read |
| --- | --- |
| Set up a Jetson (JetPack, power) | [Jetson setup](jetson.md) |
| Install and use the Mac app | [Jetlink for Mac](macos-app.md) |
| Try the iPhone and iPad app (experimental) | [Jetlink for iPhone and iPad](iphone-app.md) |
| Try the Android app (experimental) | [Jetlink for Android](android-app.md) |
| Set up a Linux PC, WSL2, or a source install | [Platform setup](platforms.md) |
| Understand icons, startup, and model switching | [Using Jetlink](using-jetlink.md) |
| Watch a Jetson or PC from a phone | [Status page](using-jetlink.md#status-page) |
| Choose a model or prepare one ahead of time | [Model management](models.md) |
| Update or roll back | [Updates and rollback](releasing.md) |
| Choose a cable, or set up power and sleep | [Cables, networking, and power](transport.md) |
| Check performance and limits | [Performance and limits](status.md) |

Problems: start with the [common checks](../README.md#if-something-is-wrong),
then your platform guide's troubleshooting.

## Development and reference

| Task | Reference |
| --- | --- |
| Install manually or customize USB | [Installation reference](installation-reference.md) |
| Run `jetlink-server` by hand: commands, options, `server.env` | [The server command](installation-reference.md#the-server-command) |
| Use the model CLI | [Commands, identifiers, and cache files](model-cli.md) |
| Understand how the comma and the server talk | [Link protocol](transport.md#link-protocol) |
| Understand how the apps and the status page talk to the server | [Control protocol](control-protocol.md) |
| Choose or investigate an inference backend | [Backends and measurements](backends.md) |
| Mac benchmarks and implementation | [Mac performance](mac-performance.md) |
| Test a server without a comma | [Benchmark setup](platforms.md#test-without-a-comma) |
| Build the Mac app | [Mac development](../macos/README.md) |
| Build the iPhone and iPad app | [iPhone development](../ios/README.md) |
| Build the Android app | [Android development](../android/README.md) |
| Keep the server in step with the comma's package | [Conformance](conformance.md) |
| Publish releases | [Publishing](publishing.md) |
