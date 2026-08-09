# Cockpit Tools Codex fork installer

Linux Toolbox installs the prebuilt Debian package from:

<https://github.com/HNam1234/cockpit-tools-linux-codex/releases>

It does not build Rust, Go, Node.js, or Tauri on the client machine.

```bash
./install.sh install --stop-running
```

The installer downloads `cockpit-tools-linux-amd64.deb` and its release
checksum, verifies both the checksum and Debian metadata, then removes any
installed `cockpit-tools` package without purging user data and installs the
fork. Cockpit account/config data is kept.

Useful commands:

```bash
./install.sh status
./install.sh repair --stop-running
./install.sh uninstall --stop-running
```

From the Linux Toolbox repository root, this also installs or updates the
fork:

```bash
./install.sh patch --stop-running
```

`uninstall` removes only a fork marked as installed by Linux Toolbox. It
refuses to remove an official or unknown Cockpit Tools package.
