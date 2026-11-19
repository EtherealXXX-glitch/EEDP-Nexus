import tempfile
from pathlib import Path
import tkinter as tk
import unittest
from unittest.mock import patch
from nexus_ui import desktop

class ComponentMenuTest(unittest.TestCase):
    def test_menu_opens_component_settings_and_uses_plugin_lifecycle(self):
        original=tk.Tk;calls=[];failures=[]
        def request(method,args=None):
            args=args or {};calls.append((method,args))
            if method=='settings.get':return {}
            if method=='tools':return []
            if method=='events':return {'events':[],'cursor':0,'dropped':False}
            if method=='status':return {'version':'test','resources':{},'components':{'serial':{'connected':False},'beken':{'state':'idle'}}}
            if method=='plugins.set':return []
            if method=='settings.update':return args['values']
            if method=='call':return []
            raise ValueError(method)
        def walk(widget):
            yield widget
            for child in widget.winfo_children():yield from walk(child)
        class Root(original):
            def __init__(self):
                super().__init__();self.after(600,self.check);self.after(4000,self.destroy)
            def check(self):
                try:
                    menus=[w._nexus_context_menu for w in walk(self) if hasattr(w,'_nexus_context_menu')]
                    assert menus and menus[0].entrycget(0,'label')=='组件设置'
                    menus[0].invoke(0)
                    menus[0].invoke(1)
                    assert menus[0].entrycget(2,'label')=='高级操作'
                    menus[0].invoke(2)
                    self.after(400,self.destroy)
                except Exception as exc:failures.append(exc);self.destroy()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent/'build') as tmp:
            with patch('nexus_ui.desktop.tk.Tk',Root):desktop.launch(request,lambda:None,Path(tmp))
        if failures:raise failures[0]
        self.assertTrue(any(m=='settings.get' and a.get('scope')=='component.serial' for m,a in calls))
        self.assertTrue(any(m=='plugins.set' and a=={'id':'serial','enabled':False} for m,a in calls))
