# Galactic Browser

A fast, custom web browser written in Python, with a space theme, tabs, bookmarks and history.
Pick your favorite search engine during setup. Everything you do is saved automatically.

The whole project is a single file: **`setup_wizard.py`**. It contains the browser and creates everything
else when you run it.

## Install

**Requirements:** Windows with [Python 3.9 or newer](https://www.python.org/downloads/). During the
Python install, tick **Add python.exe to PATH** and keep **tcl/tk and IDLE** selected (both are on by default).

1. Download **`setup_wizard.py`** (open the file on GitHub and click **Download raw file**).
2. Double-click it.
3. Follow the wizard: choose your **search engine**, choose where to install, click **Install**.

The wizard writes the browser into the install folder, installs the browser engine into a private
environment, creates the planet icon, adds Desktop and Start Menu shortcuts, and registers an uninstaller
(Settings > Apps > Galactic Browser). The first install downloads a few hundred MB, so it needs an
internet connection and can take a few minutes.

## Search engines

The wizard asks which search engine you prefer:

DuckDuckGo, Brave Search, Google, Bing, Startpage, Ecosia, Yahoo, Qwant, or **your own address**.

For a custom engine, enter its search URL with `%s` where the search words go, for example
`https://example.com/search?q=%s`. You can switch engines at any time from the toolbar.

## Silent install

```
python setup_wizard.py --silent --engine google
python setup_wizard.py --silent --custom-url "https://example.com/search?q=%s"
```

| Option | Meaning |
| --- | --- |
| `--engine NAME` | `duckduckgo`, `brave`, `google`, `bing`, `startpage`, `ecosia`, `yahoo`, `qwant` |
| `--custom-url URL` | Your own search address, with `%s` for the search words |
| `--dir PATH` | Install folder |
| `--no-desktop` | Skip the Desktop shortcut |
| `--no-startmenu` | Skip the Start Menu shortcuts |
| `--launch` | Start the browser when the install finishes |

## Uninstall

Settings > Apps > Galactic Browser > Uninstall, or the **Uninstall Galactic Browser** Start Menu entry, or:

```
python setup_wizard.py --uninstall
```

You'll be asked whether to also delete your saved data (bookmarks, history, logins). Add `--silent` to skip the
prompts, and `--remove-data` to wipe the saved data.

## Features

- Tabs, smart address bar, back / forward / reload / home
- Your choice of search engine, switchable from the toolbar
- Animated space start page
- Bookmarks (Ctrl+D) and history (Ctrl+H)
- Autosaves tabs, window position, per-site zoom, cookies and logins every few seconds
- Closing the last tab opens the home page
- Fullscreen video, and downloads go to your Downloads folder
- Background tabs are frozen after 5 minutes to save memory

| Shortcut | Action |
| --- | --- |
| Ctrl+T / Ctrl+W | New tab / close tab |
| Ctrl+Shift+T | Reopen closed tab |
| Ctrl+L | Focus address bar |
| Ctrl+D / Ctrl+H | Bookmark page / bookmarks & history |
| Ctrl +, -, 0 | Zoom in, out, reset |
| F11 | Fullscreen |

## Custom icon

Put your own `app_icon.ico` in the same folder as `setup_wizard.py` before running it.

## Troubleshooting

- **The wizard doesn't open:** your Python is missing Tk. Reinstall Python from python.org with
  **tcl/tk and IDLE** ticked, or install without a window using `--silent`.
- **Setup log:** `%TEMP%\galactic_setup.log`
- **Browser crash details:** `%LOCALAPPDATA%\GalacticBrowser\error.log`
- **Desktop icon looks wrong:** Windows caches icons. Sign out and back in, or delete and recreate the shortcut.

## Notes

The rendering engine is Chromium (via PySide6 / Qt WebEngine). The browser has no password manager;
you stay signed in to sites through saved cookies.
