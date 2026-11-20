import ctypes
import sys

from gui.app import AppWindow


def main():
    try:  # Windows 高分屏下避免界面模糊
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = AppWindow()
    app.mainloop()


if __name__ == "__main__":
    sys.exit(main())
