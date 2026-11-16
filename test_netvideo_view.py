"""GUI checks use fake component calls; no network or physical device is touched."""
import tkinter as tk
import unittest
from unittest.mock import patch
import time
from tkinter import ttk
from netvideo_view import open_netvideo_view


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class NetVideoViewTest(unittest.TestCase):
    def test_play_both_reuses_prepared_streams_without_repreparing(self):
        root = tk.Tk(); root.withdraw(); calls = []
        def frame(parent, *args, **kwargs): return tk.Frame(parent)
        def label(parent, text='', **kwargs):
            kwargs.pop('muted', None); return tk.Label(parent, text=text, **kwargs)
        def button(parent, text, command, **kwargs):
            kwargs.pop('small', None); kwargs.pop('primary', None); return tk.Button(parent, text=text, command=command, **kwargs)
        ready={'mjpeg': {'source':r'C:\mjpeg.mjpeg'}, 'h264': {'source':r'C:\remote.h264'}}
        lanes={'mjpeg': {'state':'cancelled','operation':'send'}, 'h264': {'state':'cancelled','operation':'send'}}
        def request(method,args,ok=None,fail=None):
            calls.append((method,args)); target=args.get('target')
            if method == 'settings.get': result={'last_host':'10.0.0.1'}
            else:
                if target == 'netvideo.start': lanes[args['arguments']['lane']]={'state':'running','operation':'send'}
                result={'prepared':ready,'lanes':lanes}
            if ok: ok(result)
        try:
            with patch('netvideo_view.os.path.isfile', return_value=True):
                view=open_netvideo_view(root,request,frame,label,button);view.pack();root.update_idletasks()
                view.consume_status({'prepared':ready,'lanes':lanes});calls.clear()
                next(w for w in descendants(view) if isinstance(w,tk.Button) and w.cget('text')=='播放两路').invoke()
                starts=[a['arguments']['lane'] for method,a in calls if method=='call' and a.get('target')=='netvideo.start']
                self.assertEqual(starts,['mjpeg','h264'])
                self.assertFalse(any(a.get('target')=='netvideo.prepare' for _,a in calls))
        finally: root.destroy()

    def test_quick_switch_only_restarts_mjpeg(self):
        root = tk.Tk(); root.withdraw(); calls = []; prepared = False
        def frame(parent, *args, **kwargs): return tk.Frame(parent)
        def label(parent, text='', **kwargs):
            kwargs.pop('muted', None); return tk.Label(parent, text=text, **kwargs)
        def button(parent, text, command, **kwargs):
            kwargs.pop('small', None); kwargs.pop('primary', None); return tk.Button(parent, text=text, command=command, **kwargs)
        def request(method, args, ok=None, fail=None):
            nonlocal prepared
            calls.append((method, args))
            target = args.get('target')
            if method == 'settings.get': result = {'last_host':'10.0.0.1'}
            elif target == 'netvideo.prepare': prepared = True; result = {}
            elif target == 'netvideo.status':
                result = {'lanes': {'mjpeg': {'state':'succeeded' if prepared else 'cancelled',
                                               'operation':'prepare' if prepared else 'send'}}}
            else: result = {}
            if ok: ok(result)
        try:
            with patch('netvideo_view.os.path.isfile', return_value=True):
                view = open_netvideo_view(root, request, frame, label, button)
                view.pack(); root.update_idletasks()
                entries = [w for w in descendants(view) if isinstance(w, ttk.Entry)]
                entries[1].insert(0, 'ffmpeg.exe')
                view.consume_status({'prepared': {'mjpeg': {'source':r'C:\media\address-mjpeg-40k-1024x608-12fps.mjpeg'}}, 'lanes': {}})
                next(w for w in descendants(view) if isinstance(w, tk.Button) and w.cget('text') == '45').invoke()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and not any(a.get('target') == 'netvideo.start' for _, a in calls):
                    root.update(); time.sleep(.01)
                operations = [a for method, a in calls if method == 'call']
                self.assertEqual([x['target'] for x in operations],
                                 ['netvideo.stop', 'netvideo.status', 'netvideo.prepare', 'netvideo.status', 'netvideo.start'])
                self.assertTrue(all(x['arguments'].get('lane', 'mjpeg') == 'mjpeg' for x in operations))
                self.assertEqual(operations[2]['arguments']['jpeg_limit_kib'], 45)
                self.assertEqual(operations[-1]['arguments']['host'], '10.0.0.1')
        finally: root.destroy()

    def test_stopped_stream_can_restart_with_saved_ip(self):
        root = tk.Tk(); root.withdraw(); calls = []
        def frame(parent, *args, **kwargs): return tk.Frame(parent)
        def label(parent, text='', **kwargs):
            kwargs.pop('muted', None); return tk.Label(parent, text=text, **kwargs)
        def button(parent, text, command, **kwargs):
            kwargs.pop('small', None); kwargs.pop('primary', None); return tk.Button(parent, text=text, command=command, **kwargs)
        def request(method, args, ok=None, fail=None):
            calls.append((method, args))
            if ok: ok({'last_host':'192.168.1.5'} if method == 'settings.get' else {})
        try:
            view = open_netvideo_view(root, request, frame, label, button)
            view.pack(); root.update_idletasks()
            view.consume_status({'prepared': {'mjpeg': {'source':'C:\\video.mjpeg', 'frames':12}},
                                 'lanes': {'mjpeg': {'state':'cancelled', 'stage':'完成', 'average_fps':12}}})
            labels=[w for w in descendants(view) if isinstance(w,tk.Label) and w.cget('textvariable')]
            texts=[root.getvar(w.cget('textvariable')) for w in labels]
            self.assertTrue(any('已停止' in text and '0.0 帧/秒' in text for text in texts),texts)
            with patch('netvideo_view.os.path.isfile', return_value=True):
                next(w for w in descendants(view) if isinstance(w,tk.Button) and w.cget('text')=='播放').invoke()
            starts=[args['arguments'] for method,args in calls if method=='call' and args.get('target')=='netvideo.start']
            self.assertEqual(len(starts),1)
            self.assertEqual(starts[0]['host'],'192.168.1.5')
            self.assertEqual(starts[0]['lane'],'mjpeg')
            self.assertFalse(starts[0]['exclusive'])
        finally: root.destroy()

    def test_controls_and_prepared_preview(self):
        root = tk.Tk()
        root.withdraw()
        calls = []
        def frame(parent, *args, **kwargs): return tk.Frame(parent)
        def label(parent, text='', **kwargs):
            kwargs.pop('muted', None)
            return tk.Label(parent, text=text, **kwargs)
        def button(parent, text, command, **kwargs):
            kwargs.pop('small', None); kwargs.pop('primary', None)
            return tk.Button(parent, text=text, command=command, **kwargs)
        def request(method, args, ok=None, fail=None):
            calls.append((method, args))
            if ok: ok({})
        try:
            view = open_netvideo_view(root, request, frame, label, button)
            view.pack();root.update_idletasks()
            calls.clear()  # opening the page loads saved UI preferences
            controls = [w for w in descendants(view) if isinstance(w, tk.Button)]
            self.assertEqual(sum(w.cget('text') == '准备视频' for w in controls), 2)
            self.assertEqual(sum(w.cget('text') == '播放' for w in controls), 2)
            self.assertEqual(sum(w.cget('text') == '播放两路' for w in controls), 1)
            preview = next(w for w in controls if w.cget('text') == '预览')
            preview.invoke()
            self.assertFalse(calls, 'preview must not start before prepare')
            view.consume_status({'prepared': {'mjpeg': {'preview_path': 'test.mjpeg'}}, 'lanes': {}})
            preview.invoke()
            self.assertEqual([a['target'] for _, a in calls], ['video.stop', 'video.attach', 'video.play'])
            self.assertEqual(calls[-1][1]['arguments']['format'], 'mjpeg')
            view.stop_preview()
            self.assertEqual(calls[-1][1]['target'], 'video.stop')
        finally:
            root.destroy()

if __name__ == '__main__': unittest.main()
