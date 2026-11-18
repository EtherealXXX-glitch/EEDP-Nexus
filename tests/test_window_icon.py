"""Exercise the native wrapper mapping sequence that used to restore Tk's feather."""
import ctypes
from ctypes import wintypes
import tkinter as tk
import unittest
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
from nexus_core.app_paths import RESOURCES
from nexus_ui.window_icon import WindowIcon
from nexus_ui.windows_identity import PropertyStore,APP_ID,PRODUCTION_APP_ID,set_shortcut_identity


class WindowIconTests(unittest.TestCase):
    def test_shortcut_receives_packaged_app_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"icon-test.lnk"
            script="$s=New-Object -ComObject WScript.Shell; $l=$s.CreateShortcut($env:EEDP_TEST_SHORTCUT); $l.TargetPath=$env:EEDP_TEST_TARGET; $l.Save()"
            subprocess.run(["powershell","-NoProfile","-Command",script],check=True,
                           env={**os.environ,"EEDP_TEST_SHORTCUT":str(path),"EEDP_TEST_TARGET":str(Path(os.environ["WINDIR"])/"notepad.exe")},
                           creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),capture_output=True)
            set_shortcut_identity(path)
            store=PropertyStore(shortcut=path)
            try:self.assertEqual(store.get(5),PRODUCTION_APP_ID)
            finally:store.close()

    def test_first_map_and_remap_keep_native_icons(self):
        root=tk.Tk()
        root.withdraw()
        user=ctypes.WinDLL("user32")
        user.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        user.SendMessageW.restype=wintypes.LPARAM
        from nexus_ui.windows_identity import set_window_identity
        def publish(handle,path):
            self.assertNotEqual(user.SendMessageW(handle,0x7f,0,0),0,'Small icon must precede Shell registration')
            self.assertNotEqual(user.SendMessageW(handle,0x7f,1,0),0,'Big icon must precede Shell registration')
            set_window_identity(handle,path)
        with patch('nexus_ui.windows_identity.set_window_identity',publish):
            icon=WindowIcon(root,RESOURCES/"assets/nexus-hub.ico")
        try:
            store=PropertyStore(window=icon.handle)
            try:
                self.assertEqual(store.get(5),APP_ID)
                self.assertIsNone(store.get(3))
                self.assertIsNone(store.get(2))
                self.assertEqual(APP_ID,'EEDP.Nexus.Development')
            finally:store.close()
            for _ in range(2):
                # Reproduce Tk replacing an icon at unchanged DPI.
                user.SendMessageW(icon.handle,0x80,1,0)
                root.deiconify()
                root.update()
                self.assertIn(user.SendMessageW(icon.handle,0x7f,1,0),icon.icons.values())
                self.assertIn(user.SendMessageW(icon.handle,0x7f,0,0),icon.icons.values())
                user.SendMessageW(icon.handle,0x80,1,0)
                icon.refresh()
                self.assertIn(user.SendMessageW(icon.handle,0x7f,1,0),icon.icons.values())
                root.withdraw()
                root.update()
        finally:
            root.destroy()
