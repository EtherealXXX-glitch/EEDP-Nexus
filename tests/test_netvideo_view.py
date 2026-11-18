"""GUI checks use fake component calls; no network or physical device is touched."""
import tkinter as tk
import unittest
from unittest.mock import patch
import time
from tkinter import ttk
from nexus_ui.netvideo_view import open_netvideo_view


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class NetVideoViewTest(unittest.TestCase):
    def test_display_refresh_requires_serial_and_sends_selected_command(self):
        root=tk.Tk(); root.withdraw(); calls=[]; connected=False
        def frame(parent,*a,**k): return tk.Frame(parent)
        def label(parent,text='',**k): k.pop('muted',None); return tk.Label(parent,text=text,**k)
        def button(parent,text,command,**k):
            k.pop('small',None); k.pop('primary',None); return tk.Button(parent,text=text,command=command,**k)
        def request(method,args,ok=None,fail=None):
            calls.append((method,args))
            result={'connected':connected} if args.get('target')=='serial.status' else {}
            if ok: ok(result)
        try:
            view=open_netvideo_view(root,request,frame,label,button);view.pack();root.update_idletasks()
            choices=next(w for w in descendants(view) if isinstance(w,ttk.Combobox) and tuple(w.cget('values'))==('30','36','45','48','60'))
            apply=next(w for w in descendants(view) if isinstance(w,tk.Button) and w.cget('text')=='应用刷新率')
            calls.clear(); choices.set('48'); apply.invoke()
            self.assertEqual([args.get('target') for _,args in calls], ['serial.status'])
            connected=True; calls.clear(); apply.invoke()
            self.assertEqual([args.get('target') for _,args in calls], ['serial.status','serial.send'])
            self.assertEqual(calls[-1][1]['arguments'], {'text':'app display refresh 48','newline':'CRLF','hex_mode':False})
        finally: root.destroy()

    def test_mjpeg_fps_and_frame_limit_controls(self):
        root=tk.Tk();root.withdraw();calls=[];preparing=False
        def frame(parent,*a,**k):return tk.Frame(parent)
        def label(parent,text='',**k):k.pop('muted',None);return tk.Label(parent,text=text,**k)
        def button(parent,text,command,**k):
            k.pop('small',None);k.pop('primary',None);return tk.Button(parent,text=text,command=command,**k)
        def request(method,args,ok=None,fail=None):
            nonlocal preparing
            calls.append((method,args));target=args.get('target')
            if method=='settings.get':result={'last_host':'10.0.0.1','last_engine':'ffmpeg.exe'}
            elif target=='netvideo.prepare':preparing=True;result={}
            elif target=='netvideo.status':result={'lanes':{'mjpeg':{'state':'succeeded' if preparing else 'cancelled','operation':'prepare' if preparing else 'send'}}}
            else:result={}
            if ok:ok(result)
        try:
            with patch('nexus_ui.netvideo_view.os.path.isfile',return_value=True):
                view=open_netvideo_view(root,request,frame,label,button);view.pack();root.update_idletasks()
                view.consume_status({'prepared':{'mjpeg':{'source':r'C:\clip.mp4','fps':12,'jpeg_limit_kib':50}},'lanes':{}})
                choices=next(w for w in descendants(view) if isinstance(w,ttk.Combobox) and tuple(w.cget('values'))==('12','15'))
                choices.set('15')
                names=[w.cget('text') for w in descendants(view) if isinstance(w,tk.Button)]
                for size in ('30','35','40','45','50','55','60'):self.assertIn(size,names)
                calls.clear();next(w for w in descendants(view) if isinstance(w,tk.Button) and w.cget('text')=='应用帧率').invoke()
                deadline=time.monotonic()+3
                while time.monotonic()<deadline and not any(a.get('target')=='netvideo.start' for _,a in calls):root.update();time.sleep(.01)
                args=next(a['arguments'] for method,a in calls if method=='call' and a.get('target')=='netvideo.prepare')
                self.assertEqual(args['mjpeg_fps'],15);self.assertEqual(args['jpeg_limit_kib'],50)
        finally:root.destroy()

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
            with patch('nexus_ui.netvideo_view.os.path.isfile', return_value=True):
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
            with patch('nexus_ui.netvideo_view.os.path.isfile', return_value=True):
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

    def test_phone_bitrate_reencodes_only_h264(self):
        root=tk.Tk(); root.withdraw(); calls=[]; prepared=False
        def frame(parent,*a,**k): return tk.Frame(parent)
        def label(parent,text='',**k): k.pop('muted',None); return tk.Label(parent,text=text,**k)
        def button(parent,text,command,**k):
            k.pop('small',None); k.pop('primary',None); return tk.Button(parent,text=text,command=command,**k)
        def request(method,args,ok=None,fail=None):
            nonlocal prepared
            calls.append((method,args)); target=args.get('target')
            if method == 'settings.get': result={'last_host':'10.0.0.1','last_engine':'ffmpeg.exe'}
            elif target == 'netvideo.prepare': prepared=True; result={}
            elif target == 'netvideo.status':
                result={'capabilities': {'h264_selected_peak_limit': True}, 'lanes': {'h264': {'state':'succeeded' if prepared else 'cancelled',
                                          'operation':'prepare' if prepared else 'send'}}}
            else: result={}
            if ok: ok(result)
        try:
            with patch('nexus_ui.netvideo_view.os.path.isfile', return_value=True):
                view=open_netvideo_view(root,request,frame,label,button); view.pack();root.update_idletasks()
                view.consume_status({'prepared': {'h264': {'source':r'C:\face.h264'}},
                                     'lanes': {'h264': {'state':'running','operation':'send'}}})
                self.assertFalse(any(isinstance(w,ttk.Combobox) and tuple(w.cget('values'))==('30','40','45','50','55','60') for w in descendants(view)))
                calls.clear()
                buttons=[w for w in descendants(view) if isinstance(w,tk.Button) and w.cget('text')=='准备视频']
                buttons[1].invoke()
                operations=[a for method,a in calls if method=='call']
                self.assertEqual(operations[-1]['target'],'netvideo.prepare')
                self.assertEqual(operations[-1]['arguments']['lane'],'h264')
                self.assertEqual(operations[-1]['arguments']['h264_kbps'],480)
        finally: root.destroy()

    def test_saved_defaults_survive_backend_restart_and_use_h264_passthrough(self):
        root=tk.Tk();root.withdraw();calls=[]
        def frame(parent,*a,**k):return tk.Frame(parent)
        def label(parent,text='',**k):k.pop('muted',None);return tk.Label(parent,text=text,**k)
        def button(parent,text,command,**k):
            k.pop('small',None);k.pop('primary',None);return tk.Button(parent,text=text,command=command,**k)
        def request(method,args,ok=None,fail=None):
            calls.append((method,args))
            if method=='settings.get':result={'last_host':'10.0.0.1','last_engine':'ffmpeg.exe',
                'default_mjpeg_source':'C:/fresh-mjpeg-60k-1024x608-12fps.mjpeg',
                'default_h264_source':'C:/face.avi','default_mjpeg_limit_kib':60,
                'default_h264_limit_kbps':480,'default_h264_passthrough':True,
                'default_loop':True,'default_exclusive':False}
            elif args.get('target')=='netvideo.status':result={'lanes':{'h264':{'state':'cancelled'}}}
            else:result={}
            if ok:ok(result)
        try:
            with patch('nexus_ui.netvideo_view.os.path.isfile',return_value=True):
                view=open_netvideo_view(root,request,frame,label,button);view.pack();root.update_idletasks()
                entries=[w.get() for w in descendants(view) if isinstance(w,ttk.Entry) and not isinstance(w,ttk.Combobox)]
                self.assertIn('C:/fresh-mjpeg-60k-1024x608-12fps.mjpeg',entries)
                self.assertIn('C:/face.avi',entries)
                calls.clear();controls=[w for w in descendants(view) if isinstance(w,tk.Button) and w.cget('text')=='播放']
                controls[1].invoke();deadline=time.monotonic()+2
                while time.monotonic()<deadline and not any(a.get('target')=='netvideo.prepare' for _,a in calls):root.update();time.sleep(.01)
                prepare=next(a['arguments'] for _,a in calls if a.get('target')=='netvideo.prepare')
                self.assertTrue(prepare['h264_passthrough']);self.assertEqual(prepare['source'],'C:/face.avi')
        finally:root.destroy()

    def test_external_source_switch_updates_unedited_path(self):
        root=tk.Tk();root.withdraw()
        def frame(parent,*a,**k):return tk.Frame(parent)
        def label(parent,text='',**k):k.pop('muted',None);return tk.Label(parent,text=text,**k)
        def button(parent,text,command,**k):
            k.pop('small',None);k.pop('primary',None);return tk.Button(parent,text=text,command=command,**k)
        def request(method,args,ok=None,fail=None):
            if ok:ok({})
        try:
            view=open_netvideo_view(root,request,frame,label,button);view.pack();root.update_idletasks()
            view.consume_status({'prepared':{'mjpeg':{'source':'C:/old.mjpeg'}},'lanes':{}})
            entry=next(w for w in descendants(view) if isinstance(w,ttk.Entry) and not isinstance(w,ttk.Combobox) and w.get()=='C:/old.mjpeg')
            view.consume_status({'prepared':{'mjpeg':{'source':'C:/new.mjpeg'}},'lanes':{}})
            self.assertEqual(entry.get(),'C:/new.mjpeg')
            entry.delete(0,'end');entry.insert(0,'C:/manual.mjpeg')
            view.consume_status({'prepared':{'mjpeg':{'source':'C:/third.mjpeg'}},'lanes':{}})
            self.assertEqual(entry.get(),'C:/manual.mjpeg')
        finally:root.destroy()

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
            with patch('nexus_ui.netvideo_view.os.path.isfile', return_value=True):
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
            notebook = next(w for w in descendants(view) if isinstance(w, ttk.Notebook))
            self.assertEqual([notebook.tab(tab, 'text') for tab in notebook.tabs()], ['本地 · 板卡屏幕', '远程 · 手机视频'])
            self.assertEqual(notebook.cget('style'), 'NexusVideo.TNotebook')
            self.assertTrue(all(w.cget('style') == 'Nexus.TEntry' for w in descendants(view) if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox)))
            self.assertTrue(all(w.cget('style') == 'Nexus.TCheckbutton' for w in descendants(view) if isinstance(w, ttk.Checkbutton)))
            controls = [w for w in descendants(view) if isinstance(w, tk.Button)]
            self.assertEqual(sum(w.cget('text') == '准备视频' for w in controls), 2)
            self.assertEqual(sum(w.cget('text') == '播放' for w in controls), 2)
            self.assertEqual(sum(w.cget('text') == '播放两路' for w in controls), 1)
            preview = next(w for w in controls if w.cget('text') == '预览')
            preview.invoke()
            self.assertFalse(calls, 'preview must not start before prepare')
            view.consume_status({'prepared': {'mjpeg': {'preview_path': 'test.mjpeg'}}, 'lanes': {}})
            preview.invoke()
            self.assertEqual([a['target'] for _, a in calls], ['netvideo.preview_stop', 'netvideo.preview_attach', 'netvideo.preview_play'])
            self.assertEqual(calls[-1][1]['arguments']['format'], 'mjpeg')
            view.stop_preview()
            self.assertEqual(calls[-1][1]['target'], 'netvideo.preview_stop')
        finally:
            root.destroy()

if __name__ == '__main__': unittest.main()
