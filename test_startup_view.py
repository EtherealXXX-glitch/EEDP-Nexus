import tkinter as tk
import unittest
from startup_view import StartupReveal


class StartupTests(unittest.TestCase):
    def test_reveal_is_nonblocking_skippable_and_cancels_timer(self):
        root=tk.Tk()
        try:
            reveal=StartupReveal(root)
            self.assertEqual(reveal.duration,1.0)
            root.after(45,root.quit)
            root.mainloop()
            self.assertTrue(reveal.canvas.winfo_exists())
            self.assertGreater(len(reveal.canvas.find_all()),0)
            reveal.canvas.event_generate("<Button-1>")
            root.update()
            self.assertTrue(reveal.closed)
            self.assertFalse(reveal.canvas.winfo_exists())
            reveal.close()
            timed=StartupReveal(root,duration=0)
            self.assertTrue(timed.closed)
        finally:root.destroy()
