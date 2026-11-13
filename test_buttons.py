import gc
import tkinter as tk
import unittest
from buttons import ActionButton
from themes import ThemeManager


class ButtonTests(unittest.TestCase):
    def test_geometry_states_and_native_invocation(self):
        root=tk.Tk()
        root.geometry("420x180+0+0")
        manager=ThemeManager(root,{})
        calls=[]
        button=ActionButton(root,text="打开端口",primary=True,command=lambda:calls.append(1))
        button.pack(fill="x")
        manager.apply()
        root.update()
        try:
            self.assertGreaterEqual(button.winfo_height(),40)
            self.assertLess(button.winfo_height(),60)
            initial=button._frame
            button.event_generate("<Enter>");root.update()
            self.assertIsNot(button._frame,initial)
            hover=button._frame
            button._state(pressed=True)
            self.assertIsNot(button._frame,hover)
            button._state(pressed=False,hovered=False)
            button.invoke()
            self.assertEqual(len(calls),1)
            button.configure(state="disabled");button.invoke()
            self.assertEqual(len(calls),1)
            button.configure(state="normal")
            root.geometry("260x180");root.update()
            self.assertLess(button.winfo_width(),300)
            manager.typography.update(size=14,shape="square",density="compact")
            manager.apply();root.update()
            self.assertEqual(button.shape,"square")
            self.assertGreaterEqual(button.winfo_height(),button._font.metrics("linespace")+10)
            self.assertLessEqual(len(root._nexus_button_frames),96)
            self.assertEqual(manager.settings()["button_density"],"compact")
        finally:
            root.destroy()
            gc.collect()
