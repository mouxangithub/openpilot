# Publish a release

Updating an installed server: [updates and rollback](releasing.md). This page:
publishing a release.

A pushed `v*` tag runs the Release workflow: the macOS app and the Linux server
for Jetsons and PCs.

Cut one when something under `JetlinkKit`, `macos`, `ios`, `android`,
`install.sh` or the wire (`jetlink/protocol.py`, `jetlink/transport`,
`jetlink/spec.py`, `jetlink/registry`) changed. A change on the comma's side
alone ships as a zoompilot pin of the `main` commit (driven on
`danger-unstable` first) and waits for the next release's notes: a tag builds
and publishes every app, and the installer moves every Jetson and PC to it.

1. Set `__version__` in `jetlink/__init__.py` (`pyproject.toml` reads it), run
   `.venv/bin/python JetlinkKit/Scripts/make_pins.py` so `Pinned.swift` carries
   the new version, add a `Jetlink vX.Y.Z` section at the top of
   `CHANGELOG.md`, and commit.
   - The tag must match `__version__`; `macos/scripts/check-version.sh` checks
     before the build.
   - The section becomes the release notes: write what installers will notice,
     not how it was done. Without one, GitHub generates the notes. Include
     what changed on the comma since the last release, and say whether the
     protocol version moved; if it did, the comma and the server update
     together.
2. Tag and push (replace `0.7.0`):

```bash
git tag v0.7.0
git push origin v0.7.0
```

3. Watch **Actions > Release**. The macOS job builds, smoke-tests and notarizes
   the app; each Linux server builds on a native runner for its architecture
   with `scripts/build-linux.sh`.
4. Check the release page: `Jetlink-0.7.0-macOS.dmg`, `SHA256SUMS`,
   `jetlink-server-0.7.0-linux-aarch64.tar.gz` and `-linux-x86_64.tar.gz`
   with their `.sha256`, and notes made of the changelog section and the
   install commands.

- The release waits for both Linux servers: the installer takes the newest
  release, so one without them would stop every install and update.
- Each push to `main` refreshes the `edge` prerelease with
  `jetlink-server-edge-linux-aarch64.tar.gz` and `-x86_64`, which the installer
  takes with `--ref main`. A push that changes only the comma's side (the
  `changes` job in `.github/workflows/ci.yml` lists the paths) builds nothing:
  the comma takes jetlink as a git pin, and edge keeps the server it has.
- Prereleases: a hyphen (`v0.7.0-rc1`) or a PEP 440 suffix (`v0.7.0a1`,
  `v0.7.0b2`, `v0.7.0rc1`) publishes as a prerelease. Use the same version in
  `jetlink/__init__.py` and the tag, minus the leading `v`.

## Installing the app

Open the DMG and drag Jetlink to Applications. Verify against `SHA256SUMS`:

```bash
shasum -a 256 -c SHA256SUMS
```

## Signing secrets

Releases are signed with a Developer ID and notarized. A fork without these
secrets gets an ad hoc signed ZIP and no DMG; the workflow step "Report the
signing mode" says which mode ran.

| Secret | What |
| --- | --- |
| `MACOS_CERTIFICATE_P12_BASE64` | the Developer ID Application certificate with its private key, exported from Keychain Access as a .p12 and base64 encoded |
| `MACOS_CERTIFICATE_PASSWORD` | the .p12 password |
| `KEYCHAIN_PASSWORD` | any random string; it locks the temporary keychain the runner builds in |
| `NOTARY_KEY_ID` | the App Store Connect API key id |
| `NOTARY_ISSUER_ID` | the issuer id of that key |
| `NOTARY_PRIVATE_KEY_P8_BASE64` | the key's .p8 file, base64 encoded |

- Notary key: a Team key with the Developer role, made under **Users and
  Access > Integrations** in App Store Connect.
- Encode a certificate with `base64 -i cert.p12 | pbcopy`; for
  `NOTARY_PRIVATE_KEY_P8_BASE64` encode the `.p8` file instead.

<a id="the-container-images"></a>
