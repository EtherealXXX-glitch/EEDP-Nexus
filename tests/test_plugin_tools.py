"""Generic action form exercises use only fake calls and never acquire hardware."""
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from nexus_ui.plugin_tools import open_plugin_tools


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class PluginToolsTest(unittest.TestCase):
    def test_video_source_can_be_browsed_and_submitted(self):
        root = tk.Tk(); root.withdraw(); calls = []
        def frame(parent, **kwargs): return tk.Frame(parent, **kwargs)
        def label(parent, text='', **kwargs):
            kwargs.pop('muted', None); return tk.Label(parent, text=text, **kwargs)
        def button(parent, text, command, **kwargs):
            kwargs.pop('small', None); kwargs.pop('primary', None); return tk.Button(parent, text=text, command=command, **kwargs)
        def request(method, arguments, success=None, failure=None):
            calls.append((method, arguments))
            result = [{'id':'netvideo', 'description':'video', 'actions':{
                'prepare':{'label':'准备', 'destructive':False, 'fields':[
                    {'name':'source', 'label':'素材', 'type':'str', 'default':''}]}}}] if method == 'tools' else {}
            if success: success(result)
        try:
            view = open_plugin_tools(root, 'netvideo', request, frame, label, button, embedded=True)
            view.pack(); root.update_idletasks()
            self.assertTrue(any(isinstance(w, tk.Canvas) for w in descendants(view)))
            browse = next(w for w in descendants(view) if isinstance(w, tk.Button) and w.cget('text') == '浏览')
            with patch('nexus_ui.plugin_tools.filedialog.askopenfilename', return_value='C:/clip.mjpeg'):
                browse.invoke()
            next(w for w in descendants(view) if isinstance(w, tk.Button) and w.cget('text') == '执行').invoke()
            action = next(args for method, args in calls if method == 'call')
            self.assertEqual(action['target'], 'netvideo.prepare')
            self.assertEqual(action['arguments']['source'], 'C:/clip.mjpeg')
        finally:
            root.destroy()


if __name__ == '__main__': unittest.main()
