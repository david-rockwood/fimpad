import platform
import tkinter as tk
from importlib import resources


def set_app_icon(root: tk.Tk) -> None:
    """
    Set the FIMpad window/taskbar icon.

    FIMpad ships both PNG (cross-platform Tk iconphoto) and ICO (Windows taskbar/EXE)
    assets so the UI and bundled executables look correct on every OS.
    """

    try:
        with resources.path("fimpad.resources", "fimpad.png") as png_path:
            root._fimpad_icon_png = tk.PhotoImage(file=png_path)
            root.iconphoto(True, root._fimpad_icon_png)
    except Exception:
        # Fail silently; FIMpad should still run without an icon
        pass

    if platform.system() == "Windows":
        try:
            with resources.path("fimpad.resources", "fimpad.ico") as ico_path:
                root.iconbitmap(default=str(ico_path))
        except Exception:
            pass
