# XFCE Utility

A desktop utility for browsing and applying installed GTK, XFWM4, icon, and cursor themes from a single interface. XFCE Utility is built with Python and CustomTkinter and uses the desktop's existing theme settings rather than downloading or installing theme collections.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux)
![Desktop: XFCE](https://img.shields.io/badge/desktop-XFCE-2284F2)
![Status: In development](https://img.shields.io/badge/status-in%20development-orange)

> **GitHub status:** This workspace does not include a GitHub repository URL or Actions workflow, so repository-specific badges (such as live build, release, or star counts) are not available yet.

## Features

- **GTK themes:** Discover installed GTK themes, show their installation paths and GTK 2/3/4 and XFWM4 support, and apply a selected theme. Related icon, cursor, or window themes declared by the GTK theme are applied when available.
- **Window themes:** Browse and apply installed XFWM4 window-decoration themes.
- **Icon themes:** Browse installed icon themes and view a preview composed from sample icons when the theme provides them.
- **Cursor themes:** Browse installed Xcursor themes, including themes that inherit cursor assets from another theme, and display a cursor preview when an image is available.
- **All-user configuration:** GTK, window, icon, and cursor tabs provide an opt-in to apply settings to accounts under `/home`. Existing configuration files are backed up before they are changed.
- **Desktop settings integration:** Apply themes through XFCE settings and, when available, GNOME `gsettings` keys.
- **Theme details and feedback:** View theme names and paths, see which theme is active when it can be detected, and receive status or error messages while loading or applying settings.

The **KDE Theme** tab is currently a placeholder; KDE theme management is not implemented yet.

## Requirements

- Linux with XFCE settings tools available (`xfconf-query`); `gsettings` is used when available.
- Python 3.10 or newer.
- Python packages listed in [`requirements.txt`](requirements.txt).
- On Ubuntu, the Tk, Cairo, Xcursor, and Polkit packages listed below. An XFCE Polkit authentication agent must be running for all-user changes.

## Build and system-wide installation

The steps below build a wheel and install it with `pipx` in its isolated global environment. The `xfce-util` command is placed in `/usr/local/bin`, and the desktop entry adds XFCE Utility to the applications menu.

On Ubuntu, install the runtime and build tools:

```bash
sudo apt update
sudo apt install python3 python3-venv pipx python3-tk libcairo2 libxcursor1 xfconf libglib2.0-bin policykit-1 xfce-polkit
```

Build the wheel from the project directory:

```bash
python3 -m venv .build-venv
source .build-venv/bin/activate
python -m pip install --upgrade build
python -m build
deactivate
```

Install the wheel and desktop launcher for all users:

```bash
sudo pipx install --global dist/xfce_util-0.1.0-py3-none-any.whl
sudo install -Dm644 xfce-util.desktop /usr/local/share/applications/xfce-util.desktop
```

Log out and back in, or refresh the desktop's application menu if the launcher does not appear immediately. You can also start the application from a terminal with `xfce-util`.

To uninstall:

```bash
sudo pipx uninstall --global xfce-util
sudo rm /usr/local/share/applications/xfce-util.desktop
```

For development without a global install, activate a virtual environment, install dependencies with `python -m pip install -r requirements.txt`, and run `python main.py`.

## Using the application

1. Open a tab for the theme type you want to manage.
2. Choose an installed theme from the list. The details area shows its name and path; icon and cursor themes may also have a preview.
3. Select **Apply** to update the current desktop settings.
4. To update configuration for other accounts, enable the all-user option before applying. XFCE Utility stays in your desktop session and requests authentication through the native Polkit dialog only for this operation.

All-user changes target home directories under `/home`. Settings changed through a live desktop session affect the current session; other users' running sessions are not changed live. GTK themes selected for all-user use must be installed in `/usr/share/themes` or `/usr/local/share/themes`. All-user operations require the system-wide pipx installation described above; do not launch the whole GUI as root.

## Development

Run the test suite from the project directory:

```bash
python -m unittest discover -v
```

## License

This project is distributed under the [MIT License](LICENSE).
