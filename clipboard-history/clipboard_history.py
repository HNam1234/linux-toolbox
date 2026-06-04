#!/usr/bin/env python3
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402


APP_ID = "local.clipboard-history"
DATA_DIR = Path.home() / ".local/share/clipboard-history"
HISTORY_FILE = DATA_DIR / "history.json"
MAX_ITEMS = 80
POLL_MS = 700


def load_history():
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [item for item in data if isinstance(item, str) and item.strip()]


def save_history(items):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(items[:MAX_ITEMS], ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_text(text):
    if text is None:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return text


def add_history_item(text):
    text = normalize_text(text)
    if not text:
        return False

    items = load_history()
    items = [item for item in items if item != text]
    items.insert(0, text)
    save_history(items)
    return True


def set_clipboard_text(text):
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    clipboard.set_text(text, -1)
    clipboard.store()


def daemon_running():
    current_pid = os.getpid()
    try:
        output = subprocess.run(
            ["pgrep", "-af", "clipboard_history.py --daemon|clipboard-history --daemon"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ).stdout
    except Exception:
        return False

    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            pid = int(line.split(maxsplit=1)[0])
        except ValueError:
            continue
        if pid != current_pid:
            return True
    return False


def ensure_daemon():
    if daemon_running():
        return

    launcher = Path.home() / ".local/bin/clipboard-history"
    command = [str(launcher), "--daemon"] if launcher.exists() else [str(Path(__file__).resolve()), "--daemon"]
    subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    time.sleep(0.15)


def run_daemon():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    state = {"last": ""}

    def poll_clipboard():
        try:
            text = normalize_text(clipboard.wait_for_text())
        except Exception:
            return GLib.SOURCE_CONTINUE

        if text and text != state["last"]:
            state["last"] = text
            add_history_item(text)
        return GLib.SOURCE_CONTINUE

    GLib.timeout_add(POLL_MS, poll_clipboard)
    poll_clipboard()

    loop = GLib.MainLoop()

    def stop(_signum, _frame):
        loop.quit()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    loop.run()


class HistoryPopup(Gtk.Window):
    def __init__(self):
        super().__init__(title="Clipboard History")
        self.set_default_size(560, 460)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_keep_above(True)
        self.set_border_width(12)
        self.connect("key-press-event", self.on_key_press)
        self.connect("destroy", Gtk.main_quit)

        self.items = load_history()
        self.filtered_items = list(self.items)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(root)

        title = Gtk.Label()
        title.set_markup("<span size='large'><b>Clipboard History</b></span>")
        title.set_xalign(0)
        root.pack_start(title, False, False, 0)

        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Search copied text")
        self.search.connect("search-changed", self.on_search_changed)
        self.search.connect("activate", self.on_activate)
        root.pack_start(self.search, False, False, 0)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-activated", self.on_row_activated)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(self.listbox)
        root.pack_start(scroller, True, True, 0)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        root.pack_start(button_box, False, False, 0)

        paste_button = Gtk.Button(label="Copy Selected")
        paste_button.connect("clicked", lambda _button: self.copy_selected())
        button_box.pack_start(paste_button, True, True, 0)

        clear_button = Gtk.Button(label="Clear History")
        clear_button.connect("clicked", self.on_clear)
        button_box.pack_start(clear_button, True, True, 0)

        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda _button: self.close())
        button_box.pack_start(close_button, True, True, 0)

        hint = Gtk.Label(label="Enter copies selected text. Esc closes.")
        hint.set_xalign(0)
        root.pack_start(hint, False, False, 0)

        self.refresh_list()
        self.search.grab_focus()

    def refresh_list(self):
        for child in self.listbox.get_children():
            self.listbox.remove(child)

        if not self.filtered_items:
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label="No clipboard history yet. Copy some text first.")
            label.set_xalign(0)
            label.set_margin_top(10)
            label.set_margin_bottom(10)
            row.add(label)
            self.listbox.add(row)
        else:
            for item in self.filtered_items:
                row = Gtk.ListBoxRow()
                preview = item.replace("\n", " ")
                if len(preview) > 160:
                    preview = preview[:157] + "..."
                label = Gtk.Label(label=preview)
                label.set_xalign(0)
                label.set_line_wrap(True)
                label.set_margin_top(8)
                label.set_margin_bottom(8)
                label.set_margin_start(8)
                label.set_margin_end(8)
                row.add(label)
                self.listbox.add(row)

        self.listbox.show_all()
        first = self.listbox.get_row_at_index(0)
        if first and self.filtered_items:
            self.listbox.select_row(first)

    def on_search_changed(self, entry):
        query = entry.get_text().strip().lower()
        if not query:
            self.filtered_items = list(self.items)
        else:
            self.filtered_items = [item for item in self.items if query in item.lower()]
        self.refresh_list()

    def on_activate(self, _entry):
        self.copy_selected()

    def on_row_activated(self, _listbox, row):
        self.copy_row(row)

    def on_key_press(self, _window, event):
        if event.keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def selected_index(self):
        row = self.listbox.get_selected_row()
        if not row:
            return None
        index = row.get_index()
        if index < 0 or index >= len(self.filtered_items):
            return None
        return index

    def copy_selected(self):
        index = self.selected_index()
        if index is None:
            return
        text = self.filtered_items[index]
        set_clipboard_text(text)
        add_history_item(text)
        self.close()

    def copy_row(self, row):
        index = row.get_index()
        if index < 0 or index >= len(self.filtered_items):
            return
        text = self.filtered_items[index]
        set_clipboard_text(text)
        add_history_item(text)
        self.close()

    def on_clear(self, _button):
        save_history([])
        self.items = []
        self.filtered_items = []
        self.refresh_list()


def show_popup():
    ensure_daemon()
    window = HistoryPopup()
    window.show_all()
    Gtk.main()


def install():
    app_dir = Path.home() / ".local/share/clipboard-history"
    bin_dir = Path.home() / ".local/bin"
    autostart_dir = Path.home() / ".config/autostart"
    desktop_dir = Path.home() / ".local/share/applications"
    source = Path(__file__).resolve()
    target = app_dir / "clipboard_history.py"

    app_dir.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    autostart_dir.mkdir(parents=True, exist_ok=True)
    desktop_dir.mkdir(parents=True, exist_ok=True)

    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    target.chmod(0o755)

    launcher = bin_dir / "clipboard-history"
    launcher.write_text(f"#!/usr/bin/env bash\nexec {target} \"$@\"\n", encoding="utf-8")
    launcher.chmod(0o755)

    autostart = autostart_dir / "clipboard-history-daemon.desktop"
    autostart.write_text(
        f"""[Desktop Entry]
Type=Application
Name=Clipboard History
Comment=Record clipboard text history
Exec={launcher} --daemon
Terminal=false
X-GNOME-Autostart-enabled=true
""",
        encoding="utf-8",
    )

    desktop = desktop_dir / "clipboard-history.desktop"
    desktop.write_text(
        f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Clipboard History
Comment=Show clipboard text history
Exec={launcher} --popup
Terminal=false
Categories=Utility;
Icon=edit-paste
""",
        encoding="utf-8",
    )

    subprocess.run(["update-desktop-database", str(desktop_dir)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    configure_shortcut(str(launcher))
    start_daemon(str(launcher))


def configure_shortcut(launcher):
    base = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
    path = f"{base}/clipboard-history/"
    current = subprocess.run(
        ["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ).stdout.strip()

    entries = []
    if current.startswith("["):
        entries = [part.strip().strip("'") for part in current.strip("[]").split(",") if part.strip()]
    if path not in entries:
        entries.append(path)

    value = "[" + ", ".join(f"'{entry}'" for entry in entries) + "]"
    subprocess.run(["gsettings", "set", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings", value])
    schema = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
    subprocess.run(["gsettings", "set", schema + f":{path}", "name", "Clipboard History"])
    subprocess.run(["gsettings", "set", schema + f":{path}", "command", f"{launcher} --popup"])
    subprocess.run(["gsettings", "set", schema + f":{path}", "binding", "<Super>v"])


def start_daemon(launcher):
    subprocess.Popen(
        [launcher, "--daemon"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def main():
    parser = argparse.ArgumentParser(description="Small GTK clipboard history utility.")
    parser.add_argument("--daemon", action="store_true", help="Run clipboard monitor daemon")
    parser.add_argument("--popup", action="store_true", help="Show clipboard history popup")
    parser.add_argument("--install", action="store_true", help="Install autostart entry and Super+V shortcut")
    args = parser.parse_args()

    if args.daemon:
        run_daemon()
    elif args.install:
        install()
    else:
        show_popup()


if __name__ == "__main__":
    raise SystemExit(main())
