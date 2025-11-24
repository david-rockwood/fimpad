# Notes

## Icons and desktop integration

- `fimpad/resources/fimpad.png` is the primary cross-platform icon used by Tkinter and Linux desktop files.
- `fimpad/resources/fimpad.ico` provides the Windows EXE/taskbar icon and is also set on the Tk root window when available.
- For Linux desktop files, ensure the PNG is installed into an icon theme path under the `fimpad` name so `Icon=fimpad` resolves correctly.

Example `fimpad.desktop` (commented for reference):

```
# Example desktop entry (install to ~/.local/share/applications or /usr/share/applications)
[Desktop Entry]
Type=Application
Name=FIMpad
Comment=FIM-oriented text editor for local LLMs
Exec=python -m fimpad
Icon=fimpad  # expects fimpad.png to be installed in the system icon theme
Terminal=false
Categories=Development;Utility;
```
