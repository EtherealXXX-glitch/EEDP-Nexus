import gc
import tkinter as tk
import unittest

from themes import ThemeManager, THEMES, contrast, color


class ThemesTest(unittest.TestCase):
    def tearDown(self):gc.collect()

    def test_high_contrast_text_buttons_edges_and_waveforms(self):
        p=THEMES["contrast"]
        for foreground in ("text","muted"):
            for background in ("bg","panel","terminal","field"):
                self.assertGreaterEqual(contrast(p[foreground],p[background]),7)
        self.assertGreaterEqual(contrast(p["primary_text"],p["primary"]),7)
        for background in ("bg","panel","field"):
            self.assertGreaterEqual(contrast(p["border"],p[background]),3)
        for wave in p["waves"]:self.assertGreaterEqual(contrast(wave,p["plot"]),4.5)

    def test_switches_retheme_existing_and_new_widgets_and_preserve_button_names(self):
        root=tk.Tk()
        root.withdraw()
        manager=ThemeManager(root,{})
        field=tk.Entry(root,bg="#30343e",fg="#e3e6ed")
        action=tk.Button(root,text="▶  开始采集",bg="#23576b",fg="#e3e6ed")
        action._nexus_primary=True
        try:
            for theme in ("mocha","paper","contrast","nord","nexus"):
                manager.select(theme)
                self.assertEqual(field.cget("background"),THEMES[theme]["field"])
                self.assertEqual(field.cget("foreground"),THEMES[theme]["text"])
                self.assertEqual(action.cget("foreground"),THEMES[theme]["primary_text"])
            manager.typography.update(icons=False,size=12,bold=True)
            manager.apply()
            self.assertEqual(action.cget("text"),"开始采集")
            action.configure(text="➤  发送")
            self.assertEqual(action.cget("text"),"发送")
            manager.select("paper")
            new=tk.Text(root,bg="#23252b",fg="#e3e6ed")
            manager.apply()
            self.assertEqual(new.cget("background"),THEMES["paper"]["terminal"])
            manager.typography["icons"]=True
            manager.apply()
            self.assertEqual(action.cget("text"),"➤  发送")
            self.assertEqual(manager.settings()["button_size"],12)
        finally:root.destroy()

    def test_canvas_redraw_uses_current_palette(self):
        root=tk.Tk()
        root.withdraw()
        manager=ThemeManager(root,{})
        canvas=tk.Canvas(root,bg="#171c25")
        try:
            manager.select("paper")
            item=canvas.create_line(0,0,10,10,fill="#63dcf2")
            self.assertEqual(canvas.itemcget(item,"fill"),THEMES["paper"]["waves"][0])
            self.assertEqual(color("#929aaa"),THEMES["paper"]["muted"])
        finally:root.destroy()
