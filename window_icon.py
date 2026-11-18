"""Load window icons at the actual Windows DPI instead of scaling a generic size."""
import ctypes
from ctypes import wintypes


class WindowIcon:
    def __init__(self, root, path):
        self.root, self.path = root, str(path)
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user.GetAncestor.restype = wintypes.HWND
        self.user.GetDpiForWindow.argtypes = [wintypes.HWND]
        self.user.GetDpiForWindow.restype = wintypes.UINT
        self.user.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
        self.user.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                       ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self.user.LoadImageW.restype = wintypes.HANDLE
        self.user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user.SendMessageW.restype = wintypes.LPARAM
        self.user.DestroyIcon.argtypes = [wintypes.HICON]
        self.handle = self.user.GetAncestor(root.winfo_id(), 2)
        self.shell_handle=None
        self.icons = {}
        self.current_dpi = None
        self.refresh()
        root.bind("<Configure>", self.configured, add="+")
        # Tk installs its wrapper-window icon while mapping. Reapply after that
        # native operation even when the monitor DPI has not changed.
        root.bind("<Map>", self.mapped, add="+")
        root.bind("<Destroy>", lambda event:self.close() if event.widget==root else None, add="+")

    def configured(self, event):
        if event.widget == self.root:
            self.refresh()

    def mapped(self,event):
        if event.widget==self.root:
            self.root.after_idle(self.reapply)

    def reapply(self):
        if self.root.winfo_exists():self.refresh(force=True)

    def refresh(self,force=False):
        handle=self.user.GetAncestor(self.root.winfo_id(),2)
        if handle!=self.handle:
            self.handle=handle
            force=True
        dpi = self.user.GetDpiForWindow(self.handle) or 96
        sizes=[self.user.GetSystemMetricsForDpi(metric,dpi) for metric in (49,11)]
        if dpi==self.current_dpi and not force and all(
            self.user.SendMessageW(self.handle,0x7f,kind,0)==self.icons.get(size)
            for kind,size in enumerate(sizes)):return
        for kind, metric in ((0, 49), (1, 11)):
            size = self.user.GetSystemMetricsForDpi(metric, dpi)
            if size not in self.icons:
                icon = self.user.LoadImageW(None, self.path, 1, size, size, 0x10)
                if not icon: raise ctypes.WinError(ctypes.get_last_error())
                self.icons[size] = icon
            self.user.SendMessageW(self.handle, 0x80, kind, self.icons[size])
        # Source windows get a development ID; packaged windows retain native
        # executable grouping, without publishing a custom production group.
        if self.shell_handle!=self.handle:
            from windows_identity import set_window_identity
            set_window_identity(self.handle,self.path)
            self.shell_handle=self.handle
        self.current_dpi = dpi
        self.apply_theme()

    def apply_theme(self, palette=None):
        if palette is None:
            from themes import palette as current_palette
            palette=current_palette()
        dwm = ctypes.WinDLL("dwmapi")
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
        dark = wintypes.DWORD(1 if palette["dark"] else 0)
        dwm.DwmSetWindowAttribute(self.handle,20,ctypes.byref(dark),ctypes.sizeof(dark))
        def rgb(value):
            return int(value[5:7]+value[3:5]+value[1:3],16)
        for attribute,color in ((34,rgb(palette["border"])),(35,rgb(palette["top"])),(36,rgb(palette["text"]))):
            value = wintypes.DWORD(color)
            dwm.DwmSetWindowAttribute(self.handle,attribute,ctypes.byref(value),ctypes.sizeof(value))

    def close(self):
        if self.shell_handle:
            from windows_identity import clear_window_identity
            try:clear_window_identity(self.shell_handle)
            except OSError:pass
            self.shell_handle=None
        for icon in self.icons.values(): self.user.DestroyIcon(icon)
        self.icons.clear()
