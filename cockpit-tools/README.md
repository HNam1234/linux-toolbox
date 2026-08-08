# Cockpit Tools Codex patch installer

This installer builds and installs the Linux Codex patch from:

<https://github.com/HNam1234/cockpit-tools-linux-codex>

It is also available inside the Linux Toolbox GUI under **Cockpit Fork**.

```bash
./install.sh install --stop-running
```

The installer fetches the upstream Cockpit Tools source, applies the Linux
Codex Desktop switching patch from the fork's
`linux-codex-desktop-support` branch, and validates the `.deb` before touching an existing
`cockpit-tools` package. If the official package is installed, it removes only
the package and installs the patched build; it does not purge Cockpit
account/config data. The installer writes a marker under
`~/.local/share/linux-toolbox/cockpit-tools-fork.json` so Linux Toolbox can
distinguish its managed fork from an official or manually installed package.

Useful commands:

```bash
./install.sh status
./install.sh repair --stop-running
./install.sh uninstall --stop-running
```

From the Linux Toolbox repository root, the shorter command below is also
supported and dispatches to this installer:

```bash
./install.sh patch --stop-running
```

Use `repair` (or its `patch` alias) when an official Cockpit update has
replaced the patched package. It reapplies the Codex patch to the current
upstream source and only replaces the installed package after the build
succeeds. If an upstream source change no longer matches the patch anchors,
the operation stops without changing the currently installed package.

`uninstall` removes only a fork previously marked as managed by Linux Toolbox.
It refuses to remove an official/unknown installation. The source build needs
Node.js 18+, npm 9+, Rust/Cargo, Git, and Ubuntu/Debian build libraries.
The installer downloads a checksum-verified private Go 1.26.5 toolchain into
its cache when the system Go is too old (x86_64 and arm64); it does not replace
the system Go installation. Missing Ubuntu packages are installed through `pkexec` unless
`COCKPIT_FORK_SKIP_APT=1` is set.
