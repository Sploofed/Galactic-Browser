#!/usr/bin/env python3
"""
Galactic Browser - Setup Wizard  (this one file is the whole product)

Double-click this file (or run  python setup_wizard.py).  Nothing else is needed: the browser itself,
its icon, the shortcuts and the uninstaller are all created by the wizard.

What it does
  1. Asks which search engine you prefer (DuckDuckGo, Brave, Google, Bing, Startpage, Ecosia,
     Yahoo, Qwant, or your own address) and where to install
  2. Creates the install folder (default: %LOCALAPPDATA%\\Programs\\Galactic Browser) and writes the browser into it
  3. Creates a private Python environment there and installs the browser engine (PySide6 + WebEngine)
  4. Creates the planet icon and the Desktop / Start Menu shortcuts
  5. Registers an uninstaller (Settings > Apps > Galactic Browser, and a Start Menu entry)

Requirements: Python 3.9+ (python.org installer, with "tcl/tk" and "Add python.exe to PATH" ticked).

Command line
  python setup_wizard.py                       open the wizard
  python setup_wizard.py --silent              install with defaults, no window
      --dir PATH  --engine NAME  --custom-url URL  --no-desktop  --no-startmenu  --launch
      NAME: duckduckgo brave google bing startpage ecosia yahoo qwant
      URL:  your own search address, with %s where the search words go
  python setup_wizard.py --uninstall           open the uninstaller
  python setup_wizard.py --uninstall --silent  uninstall without asking (add --remove-data to wipe saved data)

Troubleshooting
  Setup log:      %TEMP%\\galactic_setup.log
  Browser errors: %LOCALAPPDATA%\\GalacticBrowser\\error.log
"""

import sys

if sys.version_info < (3, 9):
    sys.exit("Galactic Browser needs Python 3.9 or newer (https://www.python.org/downloads/).")

import argparse
import base64
import json
import os
import platform
import queue
import shutil
import subprocess
import tempfile
import threading
import traceback
import types
import zlib
from pathlib import Path

APP_NAME = "Galactic Browser"
VERSION = "1.0.0"
PUBLISHER = "Galactic"
SYSTEM = platform.system()
SRC = Path(__file__).resolve().parent
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\GalacticBrowser"
SETUP_LOG = Path(tempfile.gettempdir()) / "galactic_setup.log"

NO_WINDOW = 0x08000000          # CREATE_NO_WINDOW
DETACHED = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def default_dir():
    if SYSTEM == "Windows":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "Programs" / APP_NAME
    return Path.home() / ".local" / "share" / "galactic-browser-app"


_APP = None


def app_source():
    """The browser's source code, unpacked from the payload embedded at the bottom of this file."""
    return zlib.decompress(base64.b64decode("".join(_PAYLOAD.split()))).decode("utf-8")


def load_app():
    """Load the embedded browser as a module (gives us the icon art, engine list and config helpers)."""
    global _APP
    if _APP is None:
        mod = types.ModuleType("galactic_browser")
        mod.__file__ = str(SRC / "galactic_browser.py")
        exec(compile(app_source(), mod.__file__, "exec"), mod.__dict__)
        sys.modules["galactic_browser"] = mod
        _APP = mod
    return _APP


def base_python():
    """A console python.exe to build the venv with (never pythonw)."""
    exe = Path(sys.executable)
    if SYSTEM == "Windows" and exe.name.lower() == "pythonw.exe":
        cand = exe.with_name("python.exe")
        if cand.exists():
            return str(cand)
    return str(exe)


def venv_python(d, windowed=False):
    if SYSTEM == "Windows":
        return d / "venv" / "Scripts" / ("pythonw.exe" if windowed else "python.exe")
    return d / "venv" / "bin" / "python"


def run_cmd(cmd, log, cwd=None):
    """Run a command, streaming its output lines to log(). Returns the exit code."""
    p = subprocess.Popen([str(c) for c in cmd], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                         cwd=cwd, creationflags=NO_WINDOW if SYSTEM == "Windows" else 0)
    for line in p.stdout:
        line = line.rstrip()
        if line:
            log(line)
    return p.wait()


def _ps(x):
    return str(x).replace("'", "''")   # escape for PowerShell single-quoted strings


# --------------------------------------------------------------------------- #
# Install
# --------------------------------------------------------------------------- #
def create_shortcuts(d, ico, want_desktop, want_start, log):
    script = d / "galactic_browser.py"
    runner = venv_python(d, windowed=True)
    if not runner.exists():
        runner = Path(sys.executable)
    created = []

    if SYSTEM == "Windows":
        items = []
        run_args = f'"{script}" --foreground'
        if want_desktop:
            items.append(("Desktop", APP_NAME, runner, run_args, APP_NAME))
        if want_start:
            items.append(("Programs", APP_NAME, runner, run_args, APP_NAME))
            items.append(("Programs", f"Uninstall {APP_NAME}", runner,
                          f'"{d / "setup_wizard.py"}" --uninstall', f"Uninstall {APP_NAME}"))
        ps = "$ws = New-Object -ComObject WScript.Shell\n"
        for folder, name, target, args, desc in items:
            ps += (
                f"$p = Join-Path ([Environment]::GetFolderPath('{folder}')) '{_ps(name)}.lnk'\n"
                "$s = $ws.CreateShortcut($p)\n"
                f"$s.TargetPath = '{_ps(target)}'\n"
                f"$s.Arguments = '{_ps(args)}'\n"
                f"$s.WorkingDirectory = '{_ps(d)}'\n"
                f"$s.IconLocation = '{_ps(ico)},0'\n"
                f"$s.Description = '{_ps(desc)}'\n"
                "$s.Save()\n"
                "Write-Output $p\n"
            )
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                           capture_output=True, text=True, creationflags=NO_WINDOW,
                           stdin=subprocess.DEVNULL)
        created = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        if r.returncode != 0 or (items and not created):
            raise RuntimeError("Could not create shortcuts: " + (r.stderr.strip() or "PowerShell returned nothing"))
        for c in created:
            log(f"Shortcut created: {c}")
        refresh_icons()
    elif SYSTEM == "Linux":
        entry = (f"[Desktop Entry]\nType=Application\nName={APP_NAME}\nComment=Python web browser\n"
                 f"Exec=\"{runner}\" \"{script}\" --foreground\nIcon={d / 'app_icon.png'}\n"
                 "Terminal=false\nCategories=Network;WebBrowser;\n")
        targets = []
        if want_start:
            targets.append(Path.home() / ".local" / "share" / "applications")
        if want_desktop:
            targets.append(Path.home() / "Desktop")
        for t in targets:
            t.mkdir(parents=True, exist_ok=True)
            f = t / "galactic-browser.desktop"
            f.write_text(entry)
            f.chmod(0o755)
            created.append(str(f))
            log(f"Shortcut created: {f}")
    try:   # keep shortcuts from an earlier install so the uninstaller can still remove them
        created += [f for f in json.loads((d / "shortcuts.json").read_text(encoding="utf-8")) if f not in created]
    except Exception:
        pass
    (d / "shortcuts.json").write_text(json.dumps(created), encoding="utf-8")
    return created


def refresh_icons():
    """Make Windows redraw icons so the new shortcut icon appears immediately."""
    if SYSTEM != "Windows":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED
    except Exception:
        pass
    try:
        subprocess.run(["ie4uinit.exe", "-show"], capture_output=True, timeout=15,
                       creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
    except Exception:
        pass


def register_uninstall(d, ico):
    if SYSTEM != "Windows":
        return
    import winreg
    runner = venv_python(d, windowed=True)
    if not runner.exists():
        runner = Path(sys.executable)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, VERSION)
        winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
        winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, str(d))
        winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ, str(ico))
        winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ,
                          f'"{runner}" "{d / "setup_wizard.py"}" --uninstall')
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)


def install(opts, log, step):
    """opts: dir, engine, desktop, startmenu, deps.  log(str), step(percent, label)."""
    d = Path(opts["dir"]).expanduser()
    gb = load_app()
    engine = opts.get("engine", "duckduckgo")
    if engine == "custom" and not gb.valid_template(opts.get("custom_url")):
        raise RuntimeError("The custom search address must start with http:// or https:// and contain %s once.")
    if engine != "custom" and engine not in gb.ENGINES:
        raise RuntimeError(f"Unknown search engine: {engine}")

    step(3, "Creating install folder")
    d.mkdir(parents=True, exist_ok=True)

    step(8, "Writing the browser")
    (d / "galactic_browser.py").write_text(app_source(), encoding="utf-8")
    if SRC.resolve() != d.resolve():
        shutil.copy2(Path(__file__).resolve(), d / "setup_wizard.py")   # used by the uninstaller
    (d / "installed.flag").write_text(VERSION, encoding="utf-8")
    log(f"Installed files to {d}")

    step(15, "Creating the Galactic icon")
    ico = d / "app_icon.ico"
    custom = SRC / "app_icon.ico"
    if custom.exists() and custom.resolve() != ico.resolve():
        shutil.copy2(custom, ico)
    elif not ico.exists():
        ico.write_bytes(gb.make_ico())
    (d / "app_icon.png").write_bytes(gb.make_icon_png(256))

    if opts.get("deps", True):
        step(22, "Creating a private Python environment")
        vpy = venv_python(d)
        if not vpy.exists():
            rc = run_cmd([base_python(), "-m", "venv", d / "venv"], log)
            if rc != 0 or not vpy.exists():
                raise RuntimeError("Could not create the Python environment (is Python 3.9+ installed with 'venv'?)")
        step(35, "Installing the browser engine - this can take a few minutes")
        rc = run_cmd([vpy, "-m", "pip", "install", "--disable-pip-version-check",
                      "PySide6", "PySide6-WebEngine"], log)
        if rc != 0:
            raise RuntimeError("pip could not install PySide6 / PySide6-WebEngine. Check your internet connection and try again.")

    step(80, "Saving your settings")
    cfg = gb.load_config()
    if engine == "custom":
        cfg["custom_url"] = opts["custom_url"]
    cfg["engine"] = engine
    gb.save_config(cfg)
    log(f"Search engine: {engine}")

    step(86, "Creating shortcuts")
    create_shortcuts(d, ico, opts.get("desktop", True), opts.get("startmenu", True), log)

    step(95, "Registering the uninstaller")
    register_uninstall(d, ico)
    step(100, "Done")


def launch_app(d):
    script = Path(d) / "galactic_browser.py"
    runner = venv_python(Path(d), windowed=True)
    if not runner.exists():
        runner = Path(sys.executable)
    kw = {"creationflags": DETACHED} if SYSTEM == "Windows" else {"start_new_session": True}
    subprocess.Popen([str(runner), str(script), "--foreground"], cwd=str(d), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kw)


# --------------------------------------------------------------------------- #
# Uninstall
# --------------------------------------------------------------------------- #
def find_install_dir():
    if (SRC / "installed.flag").exists():
        return SRC
    return default_dir()


def uninstall(d, remove_data, log):
    d = Path(d)
    # shortcuts
    listed = []
    try:
        listed = json.loads((d / "shortcuts.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    for f in listed:
        try:
            Path(f).unlink()
            log(f"Removed {f}")
        except OSError:
            pass
    if SYSTEM == "Windows":
        try:
            import winreg
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY)
        except OSError:
            pass
        refresh_icons()

    if remove_data:
        try:
            gb = load_app()
            shutil.rmtree(gb.BASE, ignore_errors=True)
            log("Removed saved data (bookmarks, history, logins, settings)")
        except Exception:
            pass

    # The install folder holds this very script and the python running it, so delete it after we exit.
    inside = False
    try:
        Path(__file__).resolve().relative_to(d.resolve())
        inside = True
    except ValueError:
        pass
    if inside and SYSTEM == "Windows":
        subprocess.Popen(f'cmd /c ping -n 4 127.0.0.1 >nul & rmdir /s /q "{d}"', shell=True,
                         creationflags=DETACHED | NO_WINDOW, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log("Install folder will be removed in a few seconds")
    else:
        shutil.rmtree(d, ignore_errors=True)
        log(f"Removed {d}")


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #
BG, SIDE, PANEL = "#07061a", "#05040f", "#0d0a26"
FG, DIM, ACC, ACC2, LINE = "#e9e6ff", "#8c85c9", "#a24fff", "#4b3fd1", "#2b2478"


def run_wizard(args):
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        msg = ("This Python has no Tk window toolkit, so the wizard can't open.\n\n"
               "Reinstall Python from python.org (keep 'tcl/tk and IDLE' ticked), or install without a window:\n"
               "    python setup_wizard.py --silent --engine google")
        print(msg, file=sys.stderr)
        if SYSTEM == "Windows":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, msg, APP_NAME, 0x10)
            except Exception:
                pass
        return 1

    gb = load_app()

    class Wizard(tk.Tk):
        STEPS = ["Welcome", "Search engine", "Options", "Install", "Finish"]

        def __init__(self):
            super().__init__()
            self.title(f"{APP_NAME} Setup")
            self.geometry("720x520")
            self.resizable(False, False)
            self.configure(bg=BG)
            self.logo = None
            try:
                self.logo = tk.PhotoImage(data=base64.b64encode(gb.make_icon_png(128)).decode())
                self.iconphoto(True, self.logo)
            except Exception:
                pass
            self.dir_var = tk.StringVar(value=str(args.dir or default_dir()))
            saved = gb.load_config()          # keep the old choice when reinstalling
            self.engines = [(k, v[0]) for k, v in gb.ENGINES.items() if k != "custom"]
            self.engine_var = tk.StringVar(value=("custom" if args.custom_url else args.engine) or saved["engine"])
            self.custom_var = tk.StringVar(value=args.custom_url or saved.get("custom_url", ""))
            self.desktop_var = tk.BooleanVar(value=not args.no_desktop)
            self.start_var = tk.BooleanVar(value=not args.no_startmenu)
            self.launch_var = tk.BooleanVar(value=True)
            self.q = queue.Queue()
            self.page = 0
            self.installing = False
            self.error = None
            self.deps = not args.no_deps

            style = ttk.Style(self)
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass
            style.configure("G.Horizontal.TProgressbar", troughcolor=PANEL, background=ACC,
                            bordercolor=LINE, lightcolor=ACC, darkcolor=ACC2)

            self.side = tk.Frame(self, bg=SIDE, width=210)
            self.side.pack(side="left", fill="y")
            self.side.pack_propagate(False)
            if self.logo:
                tk.Label(self.side, image=self.logo, bg=SIDE).pack(pady=(34, 6))
            tk.Label(self.side, text="GALACTIC", bg=SIDE, fg=FG, font=("Segoe UI", 15, "bold")).pack()
            tk.Label(self.side, text="BROWSER", bg=SIDE, fg=DIM, font=("Segoe UI", 9)).pack(pady=(0, 26))
            self.step_labels = []
            for name in self.STEPS:
                lb = tk.Label(self.side, text=f"   {name}", bg=SIDE, fg=DIM, anchor="w",
                              font=("Segoe UI", 11))
                lb.pack(fill="x", padx=20, pady=4)
                self.step_labels.append(lb)

            right = tk.Frame(self, bg=BG)
            right.pack(side="right", fill="both", expand=True)
            self.content = tk.Frame(right, bg=BG)
            self.content.pack(fill="both", expand=True, padx=30, pady=(28, 6))
            bar = tk.Frame(right, bg=BG)
            bar.pack(fill="x", padx=30, pady=(0, 22))
            self.btn_cancel = self.button(bar, "Cancel", self.on_cancel)
            self.btn_cancel.pack(side="left")
            self.btn_next = self.button(bar, "Next  \u203A", self.on_next, primary=True)
            self.btn_next.pack(side="right")
            self.btn_back = self.button(bar, "\u2039  Back", self.on_back)
            self.btn_back.pack(side="right", padx=8)
            self.protocol("WM_DELETE_WINDOW", self.on_cancel)
            self.show(0)

        # ---- widgets ------------------------------------------------------
        def button(self, parent, text, cmd, primary=False):
            return tk.Button(parent, text=text, command=cmd, relief="flat", bd=0, padx=20, pady=8,
                             bg=ACC2 if primary else PANEL, fg=FG, activebackground=ACC,
                             activeforeground="white", disabledforeground="#4a4580",
                             font=("Segoe UI", 10), cursor="hand2")

        def heading(self, text, sub=None):
            tk.Label(self.content, text=text, bg=BG, fg=FG, font=("Segoe UI", 18, "bold"),
                     anchor="w").pack(fill="x")
            if sub:
                tk.Label(self.content, text=sub, bg=BG, fg=DIM, font=("Segoe UI", 10), anchor="w",
                         justify="left", wraplength=440).pack(fill="x", pady=(4, 16))

        def check(self, text, var):
            return tk.Checkbutton(self.content, text=text, variable=var, bg=BG, fg=FG, selectcolor=PANEL,
                                  activebackground=BG, activeforeground=FG, anchor="w",
                                  font=("Segoe UI", 10), highlightthickness=0, bd=0)

        # ---- pages --------------------------------------------------------
        def show(self, i):
            self.page = i
            for w in self.content.winfo_children():
                w.destroy()
            for n, lb in enumerate(self.step_labels):
                on = n == i
                lb.config(fg=FG if on else DIM, font=("Segoe UI", 11, "bold" if on else "normal"),
                          text=("\u25CF  " if on else "   ") + self.STEPS[n])
            [self.page_welcome, self.page_search, self.page_options, self.page_install, self.page_finish][i]()

        def page_welcome(self):
            self.heading("Welcome to Galactic Browser",
                         "This wizard installs everything for you - no manual setup needed.")
            for line in ("\u2726  A fast, private browser with a custom space theme",
                         "\u2726  Tabs, bookmarks, history and logins that are always saved",
                         "\u2726  Your choice of search engine: DuckDuckGo, Brave, Google, Bing and more",
                         "\u2726  Desktop and Start Menu shortcuts with the Galactic icon"):
                tk.Label(self.content, text=line, bg=BG, fg=FG, font=("Segoe UI", 11), anchor="w").pack(
                    fill="x", pady=3)
            tk.Label(self.content, text="Click Next to continue.", bg=BG, fg=DIM,
                     font=("Segoe UI", 10)).pack(side="bottom", anchor="w")
            self.set_buttons(back=False, next_text="Next  \u203A")

        def page_search(self):
            self.heading("Choose your search engine",
                         "The address bar and start page will search with this. "
                         "You can switch any time from the toolbar.")
            grid = tk.Frame(self.content, bg=BG)
            grid.pack(fill="x")
            for i, (key, name) in enumerate(self.engines):
                self.radio(grid, name, key).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 40), pady=4)
            rows = (len(self.engines) + 1) // 2
            self.radio(grid, "Custom address...", "custom").grid(row=rows, column=0, sticky="w", pady=(10, 2))
            self.custom_entry = tk.Entry(self.content, textvariable=self.custom_var, bg=PANEL, fg=FG,
                                         insertbackground=FG, relief="flat", font=("Segoe UI", 10),
                                         highlightthickness=1, highlightbackground=LINE, highlightcolor=ACC,
                                         disabledbackground=BG, disabledforeground=DIM)
            self.custom_entry.pack(fill="x", ipady=6, pady=(2, 4))
            tk.Label(self.content, text="Put %s where the search words go, e.g. https://example.com/search?q=%s",
                     bg=BG, fg=DIM, font=("Segoe UI", 9), anchor="w").pack(fill="x")
            self.engine_changed()
            self.set_buttons(back=True, next_text="Next  \u203A")

        def radio(self, parent, text, value):
            return tk.Radiobutton(parent, text=text, value=value, variable=self.engine_var,
                                  command=self.engine_changed, bg=BG, fg=FG, selectcolor=PANEL,
                                  activebackground=BG, activeforeground=FG, font=("Segoe UI", 11),
                                  highlightthickness=0, bd=0)

        def engine_changed(self):
            custom = self.engine_var.get() == "custom"
            self.custom_entry.config(state="normal" if custom else "disabled")
            if custom:
                self.custom_entry.focus_set()

        def engine_name(self):
            key = self.engine_var.get()
            return "Custom address" if key == "custom" else dict(self.engines).get(key, key)

        def page_options(self):
            self.heading("Choose your options")
            tk.Label(self.content, text="Install location", bg=BG, fg=DIM, anchor="w",
                     font=("Segoe UI", 10)).pack(fill="x")
            row = tk.Frame(self.content, bg=BG)
            row.pack(fill="x", pady=(2, 14))
            tk.Entry(row, textvariable=self.dir_var, bg=PANEL, fg=FG, insertbackground=FG, relief="flat",
                     font=("Segoe UI", 10), highlightthickness=1, highlightbackground=LINE,
                     highlightcolor=ACC).pack(side="left", fill="x", expand=True, ipady=6)
            self.button(row, "Browse...", self.browse).pack(side="left", padx=(8, 0))

            tk.Label(self.content, text=f"Search engine: {self.engine_name()}", bg=BG, fg=DIM, anchor="w",
                     font=("Segoe UI", 10)).pack(fill="x", pady=(0, 14))

            self.check("Create a Desktop shortcut", self.desktop_var).pack(fill="x", pady=2)
            self.check("Create a Start Menu shortcut (and uninstaller entry)", self.start_var).pack(fill="x", pady=2)
            self.check("Launch Galactic Browser when setup finishes", self.launch_var).pack(fill="x", pady=2)
            self.set_buttons(back=True, next_text="Install")

        def page_install(self):
            self.heading("Installing", "Please wait - this window will update as each step finishes.")
            self.step_text = tk.Label(self.content, text="Starting...", bg=BG, fg=FG, anchor="w",
                                      font=("Segoe UI", 11))
            self.step_text.pack(fill="x")
            self.bar = ttk.Progressbar(self.content, style="G.Horizontal.TProgressbar", maximum=100)
            self.bar.pack(fill="x", pady=(6, 12), ipady=3)
            self.logbox = tk.Text(self.content, height=11, bg=PANEL, fg=DIM, relief="flat", wrap="word",
                                  font=("Consolas", 9), highlightthickness=1, highlightbackground=LINE)
            self.logbox.pack(fill="both", expand=True)
            self.logbox.config(state="disabled")
            self.set_buttons(back=False, next_text="Next  \u203A", next_enabled=False, cancel=False)
            self.start_install()

        def page_finish(self):
            if self.error:
                self.heading("Setup couldn't finish", "Something went wrong. Details:")
                box = tk.Text(self.content, height=10, bg=PANEL, fg="#ffb4b4", relief="flat", wrap="word",
                              font=("Consolas", 9))
                box.pack(fill="both", expand=True)
                box.insert("1.0", self.error + f"\n\nFull log: {SETUP_LOG}")
                box.config(state="disabled")
                self.set_buttons(back=True, next_text="Close")
                return
            self.heading("All set!", "Galactic Browser is installed and ready.")
            for line in ("\u2726  Your shortcut is on the Desktop with the planet icon"
                         if self.desktop_var.get() else "\u2726  Installed successfully",
                         f"\u2726  Search engine: {self.engine_name()}",
                         "\u2726  Everything you do is saved automatically",
                         "\u2726  Uninstall any time from Settings > Apps"):
                tk.Label(self.content, text=line, bg=BG, fg=FG, font=("Segoe UI", 11), anchor="w").pack(
                    fill="x", pady=3)
            self.check("Launch Galactic Browser now", self.launch_var).pack(side="bottom", anchor="w")
            self.set_buttons(back=False, next_text="Finish", cancel=False)

        # ---- buttons / navigation ----------------------------------------
        def set_buttons(self, back=True, next_text="Next", next_enabled=True, cancel=True):
            self.btn_back.config(state="normal" if back else "disabled")
            self.btn_next.config(text=next_text, state="normal" if next_enabled else "disabled")
            self.btn_cancel.config(state="normal" if cancel else "disabled")

        def browse(self):
            p = filedialog.askdirectory(initialdir=self.dir_var.get() or None)
            if p:
                self.dir_var.set(str(Path(p) / APP_NAME) if Path(p).name != APP_NAME else p)

        def on_back(self):
            if self.page == 4 and self.error:
                self.error = None
                self.show(2)
            elif self.page > 0 and not self.installing:
                self.show(self.page - 1)

        def on_next(self):
            if self.page == 0:
                self.show(1)
            elif self.page == 1:
                if self.engine_var.get() == "custom" and not gb.valid_template(self.custom_var.get().strip()):
                    messagebox.showwarning(
                        APP_NAME, "Enter a search address that starts with http:// or https:// and contains "
                                  "%s once, where the search words go.\n\nExample: https://example.com/search?q=%s")
                    return
                self.show(2)
            elif self.page == 2:
                if not self.dir_var.get().strip():
                    messagebox.showwarning(APP_NAME, "Please choose an install location.")
                    return
                self.show(3)
            elif self.page == 4:
                if not self.error and self.launch_var.get():
                    try:
                        launch_app(self.dir_var.get())
                    except Exception as e:
                        messagebox.showerror(APP_NAME, f"Couldn't launch the browser:\n{e}")
                self.destroy()

        def on_cancel(self):
            if self.installing:
                if not messagebox.askyesno(APP_NAME, "Installation is still running. Stop and close setup?"):
                    return
            elif self.page < 4 and not messagebox.askyesno(APP_NAME, "Exit Galactic Browser setup?"):
                return
            self.destroy()

        # ---- install worker ----------------------------------------------
        def start_install(self):
            self.installing = True
            self.error = None
            opts = {"dir": self.dir_var.get().strip(), "engine": self.engine_var.get(),
                    "custom_url": self.custom_var.get().strip(),
                    "desktop": self.desktop_var.get(), "startmenu": self.start_var.get(), "deps": self.deps}

            def work():
                try:
                    SETUP_LOG.write_text("", encoding="utf-8")
                except OSError:
                    pass

                def log(msg):
                    self.q.put(("log", msg))

                def step(pct, label):
                    self.q.put(("step", pct, label))
                try:
                    install(opts, log, step)
                    self.q.put(("done",))
                except Exception:
                    self.q.put(("error", traceback.format_exc()))

            threading.Thread(target=work, daemon=True).start()
            self.after(80, self.poll)

        def poll(self):
            try:
                while True:
                    m = self.q.get_nowait()
                    if m[0] == "log":
                        self.append_log(m[1])
                    elif m[0] == "step":
                        self.bar["value"] = m[1]
                        self.step_text.config(text=m[2])
                        self.append_log(f"\u25B8 {m[2]}")
                    elif m[0] == "done":
                        self.installing = False
                        self.show(4)
                        return
                    elif m[0] == "error":
                        self.installing = False
                        self.error = m[1].strip().splitlines()[-1] if m[1].strip() else "Unknown error"
                        self.append_log(m[1])
                        self.error = m[1].strip()[-1500:]
                        self.show(4)
                        return
            except queue.Empty:
                pass
            if self.installing:
                self.after(80, self.poll)

        def append_log(self, text):
            try:
                with open(SETUP_LOG, "a", encoding="utf-8") as f:
                    f.write(text + "\n")
            except OSError:
                pass
            if self.page == 3 and self.logbox.winfo_exists():
                self.logbox.config(state="normal")
                self.logbox.insert("end", text + "\n")
                self.logbox.see("end")
                self.logbox.config(state="disabled")

    Wizard().mainloop()
    return 0


def run_uninstall_gui(args):
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    d = find_install_dir()
    if not messagebox.askyesno(f"Uninstall {APP_NAME}", f"Remove {APP_NAME} from this computer?\n\n{d}"):
        return 0
    wipe = messagebox.askyesno(
        f"Uninstall {APP_NAME}",
        "Also delete your saved browser data?\n\n"
        "This removes bookmarks, history, logins and settings. Choose No to keep them\n"
        "in case you reinstall later.")
    try:
        uninstall(d, wipe, lambda m: None)
    except Exception as e:
        messagebox.showerror(APP_NAME, f"Uninstall problem:\n{e}")
        return 1
    messagebox.showinfo(APP_NAME, f"{APP_NAME} has been removed.")
    return 0


# --------------------------------------------------------------------------- #
def relaunch_without_console():
    """Double-clicking a .py on Windows opens python.exe with a black console; reopen under pythonw."""
    if SYSTEM != "Windows":
        return False
    exe = Path(sys.executable)
    if exe.name.lower() != "python.exe" or not exe.with_name("pythonw.exe").exists():
        return False
    try:
        subprocess.Popen([str(exe.with_name("pythonw.exe")), str(Path(__file__).resolve())] + sys.argv[1:],
                         creationflags=DETACHED, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True)
        return True
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser(description=f"{APP_NAME} setup wizard")
    ap.add_argument("--silent", action="store_true", help="no window, use defaults / the flags below")
    ap.add_argument("--uninstall", action="store_true", help="uninstall Galactic Browser")
    ap.add_argument("--remove-data", action="store_true", help="with --uninstall --silent: also delete saved data")
    ap.add_argument("--dir", help="install folder")
    ap.add_argument("--engine", choices=sorted(k for k in load_app().ENGINES if k != "custom"),
                    help="default search engine")
    ap.add_argument("--custom-url", help="your own search address, with %%s where the search words go")
    ap.add_argument("--no-desktop", action="store_true", help="skip the Desktop shortcut")
    ap.add_argument("--no-startmenu", action="store_true", help="skip the Start Menu shortcuts")
    ap.add_argument("--no-deps", action="store_true", help=argparse.SUPPRESS)  # dev/testing: skip venv + pip
    ap.add_argument("--launch", action="store_true", help="with --silent: start the browser afterwards")
    ap.add_argument("--console", action="store_true", help=argparse.SUPPRESS)  # keep the console attached
    args = ap.parse_args()
    if args.custom_url and not load_app().valid_template(args.custom_url):
        ap.error("--custom-url must start with http:// or https:// and contain %s once")

    if not args.silent and not args.console and relaunch_without_console():
        return 0

    if args.uninstall:
        if args.silent:
            uninstall(find_install_dir(), args.remove_data, print)
            return 0
        return run_uninstall_gui(args)

    if args.silent:
        opts = {"dir": str(args.dir or default_dir()),
                "engine": "custom" if args.custom_url else (args.engine or "duckduckgo"),
                "custom_url": args.custom_url,
                "desktop": not args.no_desktop, "startmenu": not args.no_startmenu, "deps": not args.no_deps}
        install(opts, print, lambda pct, label: print(f"[{pct:3d}%] {label}"))
        if args.launch:
            launch_app(opts["dir"])
        return 0
    return run_wizard(args)


# --------------------------------------------------------------------------- #
# The browser itself (galactic_browser.py), compressed. The wizard writes it into the install folder.
# --------------------------------------------------------------------------- #
_PAYLOAD = """
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
"""


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        tb = traceback.format_exc()
        try:
            SETUP_LOG.write_text(tb, encoding="utf-8")
        except OSError:
            pass
        print(tb, file=sys.stderr)
        if SYSTEM == "Windows":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, f"Setup crashed.\n\n{tb[-900:]}", APP_NAME, 0x10)
            except Exception:
                pass
        sys.exit(1)
