"""Network-video workspace: prepare and control each stream independently."""
import tkinter as tk
from tkinter import filedialog, ttk
import os
import re
import time


def mjpeg_variant_path(source, limit):
    """Find a sibling prepared rendition without assuming a machine-specific path."""
    if limit not in (30, 35, 40, 45, 50, 55, 60):
        raise ValueError('不支持的档位')
    result, count = re.subn(r'(?i)(-mjpeg-)(?:30|35|40|45|50|55|60)(k-1024x608-12fps\.mjpeg)$',
                            lambda match: match.group(1) + str(limit) + match.group(2), source)
    if not count:
        raise ValueError('请先选择同一组预生成的 MJPEG 档位文件')
    return result


def open_netvideo_view(parent, request, frame, label, button):
    view = frame(parent)
    view.columnconfigure(0, weight=1)
    view.rowconfigure(1, weight=1)
    host = tk.StringVar()
    engine = tk.StringVar()
    duration = tk.StringVar(value='300')
    loop = tk.BooleanVar(value=True)
    exclusive = tk.BooleanVar(value=False)
    state = tk.StringVar(value='选择视频后，先准备，再开始发送。')
    sources = {k: tk.StringVar() for k in ('mjpeg', 'h264')}
    ports = {'mjpeg': tk.StringVar(value='5001'), 'h264': tk.StringVar(value='5002')}
    quality = tk.StringVar(value='0')
    jpeg_limit = tk.StringVar(value='50')
    mjpeg_fps = tk.StringVar(value='12')
    display_hz = tk.StringVar(value='30')
    display_hz_status = tk.StringVar(value='自研板：请选择目标刷新率；实际值以板卡为准。')
    variant_status = tk.StringVar(value='未选择档位')
    mjpeg_pacing = tk.StringVar(value='0')
    preset = tk.StringVar(value='medium')
    h264_auto = tk.BooleanVar(value=True)
    h264_passthrough = tk.BooleanVar(value=False)
    passthrough = tk.BooleanVar(value=False)
    summaries = {k: tk.StringVar(value='未准备') for k in sources}
    details = {k: tk.StringVar(value='请选择视频并准备') for k in sources}
    prepared = {}
    initialised = set()
    preview_active = False
    preview_generation = 0
    preview_window = None
    quick_busy = False
    previous = {}
    jobs = {}

    header = frame(view)
    header.grid(row=0, column=0, sticky='ew', padx=12, pady=(8, 4))
    header.columnconfigure(2, weight=1)
    label(header, '视频传输').grid(row=0, column=0, sticky='w', padx=(0, 10))
    label(header, '板卡 IP').grid(row=0, column=1, sticky='w')
    ttk.Entry(header, style='Nexus.TEntry', textvariable=host, width=18).grid(row=0, column=2, sticky='w', padx=6)
    main_actions = frame(header); main_actions.grid(row=1, column=0, columnspan=4, sticky='w', pady=(5, 0))
    button(main_actions, '播放两路', lambda: play_both(), primary=True, small=True).grid(row=0, column=0, padx=(0, 4))
    button(main_actions, '全部停止', lambda: stop_all(), small=True).grid(row=0, column=1, padx=4)
    advanced = frame(view)
    advanced.grid(row=3, column=0, sticky='ew', padx=12, pady=4)
    advanced.columnconfigure(1, weight=1)
    label(advanced, 'FFmpeg').grid(row=0, column=0, sticky='w')
    ttk.Entry(advanced, style='Nexus.TEntry', textvariable=engine).grid(row=0, column=1, sticky='ew', padx=6)
    def browse_engine():
        path = filedialog.askopenfilename(parent=view, filetypes=[('FFmpeg', '*.exe'), ('全部文件', '*.*')])
        if path:
            engine.set(path)
            request('settings.update', {'scope':'component.netvideo-ui', 'values':{'last_engine':path}}, lambda _: None, lambda _: None)
    button(advanced, '选择', browse_engine, small=True).grid(row=0, column=2, sticky='w')
    label(advanced, '准备时长（秒，1～300）', muted=True).grid(row=1, column=0, sticky='w', pady=(5, 0))
    ttk.Entry(advanced, style='Nexus.TEntry', textvariable=duration, width=8).grid(row=1, column=1, sticky='w', padx=6, pady=(5, 0))
    toggles = frame(advanced)
    toggles.grid(row=1, column=1, sticky='e', padx=4, pady=(5, 0))
    ttk.Checkbutton(toggles, style='Nexus.TCheckbutton', text='循环', variable=loop).pack(side='left')
    ttk.Checkbutton(toggles, style='Nexus.TCheckbutton', text='两路互斥', variable=exclusive).pack(side='left', padx=4)

    advanced.grid_remove()
    def toggle_advanced():
        if advanced.winfo_ismapped(): advanced.grid_remove()
        else: advanced.grid()
    button(header, '高级设置', toggle_advanced, small=True).grid(row=0, column=3, padx=4)

    dashboard = frame(view)
    dashboard.grid(row=1, column=0, sticky='nsew', padx=12, pady=4)
    dashboard.columnconfigure(0, weight=1)
    dashboard.rowconfigure(0, weight=1)
    notebook = ttk.Notebook(dashboard, style='NexusVideo.TNotebook')
    notebook.grid(row=0, column=0, sticky='nsew')
    panels = {}
    for column, (lane, title) in enumerate((('mjpeg', '本地 · 板卡屏幕'), ('h264', '远程 · 手机视频'))):
        box = frame(notebook)
        notebook.add(box, text=title)
        box.columnconfigure(0, weight=1)
        panels[lane] = box
        spec = '输出 1024×608 / 可选 12 或 15 帧每秒' if lane == 'mjpeg' else '输出 640×360 / 12 帧每秒，视频数据不超过 60 KiB/秒'
        label(box, title).grid(row=0, column=0, sticky='w', padx=8, pady=(8, 2))
        spec_label = label(box, spec, muted=True); spec_label.configure(wraplength=260, justify='left')
        spec_label.grid(row=1, column=0, sticky='w', padx=8, pady=2)
        item = label(box, '', muted=True); item.configure(textvariable=summaries[lane], anchor='w', wraplength=0, justify='left')
        item.grid(row=2, column=0, sticky='ew', padx=8, pady=4)
        file_row = frame(box); file_row.grid(row=3, column=0, sticky='ew', padx=8, pady=3); file_row.columnconfigure(0, weight=1)
        ttk.Entry(file_row, style='Nexus.TEntry', textvariable=sources[lane], width=12).grid(row=0, column=0, sticky='ew', padx=(0, 4))
        def browse(which=lane):
            path = filedialog.askopenfilename(parent=view, filetypes=[('视频文件', '*.avi *.mp4 *.mov *.mkv *.h264 *.mjpeg'), ('全部文件', '*.*')])
            if path:
                sources[which].set(path)
                request('settings.update', {'scope':'component.netvideo-ui', 'values':{'default_' + which + '_source':path}},
                        lambda _: None, lambda error: state.set('素材路径未能保存：' + str(error)) if view.winfo_exists() else None)
        button(file_row, '选择视频', browse, small=True).grid(row=0, column=1, padx=2)

        settings = frame(advanced)
        settings.grid(row=2 + column, column=0, columnspan=3, sticky='ew', padx=8, pady=(4, 0))
        settings.columnconfigure(1, weight=1)
        label(settings, '板卡端口', muted=True).grid(row=0, column=0, sticky='w')
        ttk.Entry(settings, style='Nexus.TEntry', textvariable=ports[lane], width=7).grid(row=0, column=1, sticky='w', padx=5)
        if lane == 'mjpeg':
            label(settings, '单帧上限 KiB', muted=True).grid(row=1, column=0, sticky='w', pady=2)
            ttk.Entry(settings, style='Nexus.TEntry', textvariable=jpeg_limit, width=6).grid(row=1, column=1, sticky='w', padx=5, pady=2)
            label(settings, 'JPEG 质量（0 为自动）', muted=True).grid(row=2, column=0, sticky='w', pady=2)
            ttk.Entry(settings, style='Nexus.TEntry', textvariable=quality, width=7).grid(row=2, column=1, sticky='w', padx=5, pady=2)
            ttk.Checkbutton(settings, style='Nexus.TCheckbutton', text='符合规格的 MJPEG 直发', variable=passthrough).grid(row=3, column=0, columnspan=2, sticky='w', pady=2)
            label(settings, '分块发送时间（毫秒）', muted=True).grid(row=4, column=0, sticky='w', pady=2)
            ttk.Entry(settings, style='Nexus.TEntry', textvariable=mjpeg_pacing, width=7).grid(row=4, column=1, sticky='w', padx=5, pady=2)
        else:
            ttk.Checkbutton(settings, style='Nexus.TCheckbutton', text='自动优化画质', variable=h264_auto).grid(row=2, column=0, sticky='w', pady=2)
            ttk.Combobox(settings, textvariable=preset, values=['veryfast', 'medium', 'slow'], state='readonly', width=8).grid(row=2, column=1, sticky='w', padx=5, pady=2)
            ttk.Checkbutton(settings, style='Nexus.TCheckbutton', text='H.264 直发（实验）', variable=h264_passthrough).grid(row=3, column=0, columnspan=2, sticky='w', pady=2)

        actions = frame(box); actions.grid(row=4, column=0, sticky='w', padx=8, pady=5)
        button(actions, '播放', lambda k=lane: play(k), primary=True, small=True).grid(row=0, column=0, padx=(0, 4), pady=2)
        button(actions, '暂停', lambda k=lane: action(k, 'pause'), small=True).grid(row=0, column=1, padx=4, pady=2)
        button(actions, '停止', lambda k=lane: action(k, 'stop'), small=True).grid(row=0, column=2, padx=4, pady=2)
        button(actions, '预览', lambda k=lane: preview(k), small=True).grid(row=0, column=3, padx=4, pady=2)
        button(settings, '准备视频', lambda k=lane: action(k, 'prepare'), small=True).grid(row=6, column=0, sticky='w')
        if lane == 'mjpeg':
            variant_title = label(box, '', muted=True); variant_title.configure(textvariable=variant_status)
            variant_title.grid(row=5, column=0, sticky='w', padx=8, pady=(6, 0))
            quick = frame(box); quick.grid(row=6, column=0, sticky='w', padx=8, pady=4)
            for n, limit in enumerate((30, 35, 40, 45, 50, 55, 60)):
                button(quick, str(limit), lambda n=limit: quick_switch(n), small=True).grid(row=n//3, column=n%3, padx=3, pady=2)
            fps_row = frame(box); fps_row.grid(row=7, column=0, sticky='w', padx=8, pady=4)
            label(fps_row, '本地帧率（帧/秒）', muted=True).grid(row=0, column=0, sticky='w')
            ttk.Combobox(fps_row, textvariable=mjpeg_fps, values=['12', '15'], state='readonly', width=5).grid(row=0, column=1, padx=6)
            button(fps_row, '应用帧率', lambda: play('mjpeg', force_reencode=True), small=True).grid(row=0, column=2)
            display_row = frame(box); display_row.grid(row=9, column=0, sticky='w', padx=8, pady=(8, 2))
            label(display_row, '屏幕刷新率（Hz）', muted=True).grid(row=0, column=0, sticky='w')
            ttk.Combobox(display_row, textvariable=display_hz, values=['30', '36', '45', '48', '60'], state='readonly', width=5).grid(row=0, column=1, padx=6)
            button(display_row, '应用刷新率', lambda: apply_display_hz(), small=True).grid(row=0, column=2)
            display_hint = label(box, '', muted=True)
            display_hint.configure(textvariable=display_hz_status, justify='left', anchor='w', wraplength=500)
            display_hint.grid(row=10, column=0, sticky='ew', padx=8, pady=(0, 4))
        else:
            rate_row = frame(box); rate_row.grid(row=5, column=0, sticky='w', padx=8, pady=(8, 3))
            label(rate_row, '手机视频上限（KB/秒）', muted=True).grid(row=0, column=0, sticky='w')
            label(rate_row, '固定 60 KB/秒', muted=True).grid(row=0, column=1, padx=8)
            label(box, '手机视频载荷上限 60 KB/秒（不含网络协议开销）。', muted=True).grid(row=6, column=0, sticky='w', padx=8, pady=4)
        description = label(box, '', muted=True)
        description.configure(textvariable=details[lane], justify='left', anchor='w', wraplength=260)
        description.grid(row=8, column=0, sticky='ew', padx=8, pady=4)
        box.bind('<Configure>', lambda event, widget=description: widget.configure(wraplength=max(200, event.width - 30)), add='+')
    feedback = label(view, '', muted=True)
    feedback.configure(textvariable=state, anchor='w')
    feedback.grid(row=4, column=0, sticky='ew', padx=12, pady=(2, 8))

    def apply_display_hz():
        hz = display_hz.get()
        if hz not in ('30', '36', '45', '48', '60'):
            display_hz_status.set('不支持该刷新率。'); return
        def failed(error):
            if view.winfo_exists(): display_hz_status.set('刷新率命令未发送：' + str(error))
        def checked(result):
            if not view.winfo_exists(): return
            if not result.get('connected'):
                display_hz_status.set('串口未连接：请先在串口监控中连接板卡。'); return
            display_hz_status.set(f'正在发送 {hz} Hz 切换命令…')
            request('call', {'target':'serial.send', 'arguments':{
                'text':f'app display refresh {hz}', 'newline':'CRLF', 'hex_mode':False}},
                lambda _: display_hz_status.set(f'已发送 {hz} Hz 请求；请查看板卡串口反馈。') if view.winfo_exists() else None,
                failed)
        request('call', {'target':'serial.status', 'arguments':{}}, checked, failed)

    def quick_switch(limit):
        nonlocal quick_busy
        if quick_busy:
            state.set('正在切换，请稍候。'); return
        try:
            current = sources['mjpeg'].get().strip() or str(prepared.get('mjpeg', {}).get('source') or '')
            target = mjpeg_variant_path(current, limit)
            if int(mjpeg_fps.get()) != 12:
                jpeg_limit.set(str(limit)); play('mjpeg', force_reencode=True); return
            if not os.path.isfile(target):
                jpeg_limit.set(str(limit)); play('mjpeg', force_reencode=True); return
            if not host.get().strip(): raise ValueError('请先填写板卡 IP。')
            args = dict(lane='mjpeg', source=target, engine=engine.get().strip(),
                        duration_s=int(duration.get()), mjpeg_passthrough=True, jpeg_limit_kib=limit, mjpeg_fps=int(mjpeg_fps.get()))
            start_args = dict(lane='mjpeg', host=host.get().strip(), port=int(ports['mjpeg'].get()),
                              loop=loop.get(), exclusive=exclusive.get(), mjpeg_pacing_ms=int(mjpeg_pacing.get()))
        except ValueError as error:
            if str(error) == '请先选择同一组预生成的 MJPEG 档位文件':
                jpeg_limit.set(str(limit)); play('mjpeg', force_reencode=True); return
            state.set(str(error)); return
        request('settings.update', {'scope':'component.netvideo-ui', 'values':{'default_mjpeg_fps':int(mjpeg_fps.get()), 'default_mjpeg_limit_kib':limit}}, lambda _: None, lambda _: None)
        quick_busy = True
        deadline = time.monotonic() + 45
        state.set(f'正在切换到 {limit} KiB，手机视频保持运行。')
        def fail(error):
            nonlocal quick_busy
            quick_busy = False
            if view.winfo_exists(): state.set('切换失败：' + str(error))
        def poll(phase):
            if not view.winfo_exists(): return
            if time.monotonic() > deadline: fail('等待超时，请检查发送状态'); return
            def checked(result):
                if not view.winfo_exists(): return
                job = (result.get('lanes') or {}).get('mjpeg', {})
                if job.get('state') == 'running':
                    view.after(250, lambda: poll(phase)); return
                if phase == 'stop':
                    request('call', {'target':'netvideo.prepare', 'arguments':args},
                            lambda _: view.after(250, lambda: poll('prepare')), fail)
                elif job.get('state') != 'succeeded' or job.get('operation') != 'prepare':
                    fail(job.get('error') or '素材准备未成功')
                else:
                    sources['mjpeg'].set(target); jpeg_limit.set(str(limit)); passthrough.set(True)
                    def started(result):
                        nonlocal quick_busy
                        quick_busy = False; consume(result)
                        if view.winfo_exists():
                            state.set(f'已启动 {limit} KiB/帧发送任务，请查看连接状态。')
                            request('settings.update', {'scope':'component.netvideo-ui', 'values':{
                                'last_host':start_args['host'], 'default_mjpeg_source':target}}, lambda _: None,
                                lambda error: state.set('发送任务已启动，但地址或素材未能保存：' + str(error)) if view.winfo_exists() else None)
                    request('call', {'target':'netvideo.start', 'arguments':start_args}, started, fail)
            request('call', {'target':'netvideo.status', 'arguments':{}}, checked, fail)
        request('call', {'target':'netvideo.stop', 'arguments':{'lane':'mjpeg'}},
                lambda _: view.after(250, lambda: poll('stop')), fail)

    def stop_all():
        state.set('正在停止两路发送。')
        request('call', {'target':'netvideo.stop', 'arguments':{'lane':'all'}}, consume,
                lambda error: state.set(str(error)) if view.winfo_exists() else None)

    def play_both():
        if exclusive.get():
            advanced.grid(); state.set('两路互斥已开启，请先在高级设置中关闭。'); return
        play('mjpeg', lambda: play('h264'))

    def play(which, after=None, force_reencode=False):
        nonlocal quick_busy
        if quick_busy:
            state.set('正在准备视频，请稍候。'); return
        source = sources[which].get().strip()
        if not source:
            source = filedialog.askopenfilename(parent=view, filetypes=[('视频文件', '*.avi *.mp4 *.mov *.mkv *.h264 *.mjpeg'), ('全部文件', '*.*')])
            if not source: return
            sources[which].set(source)
        if not os.path.isfile(source): state.set('视频文件不存在，请重新选择。'); return
        if not host.get().strip(): state.set('请先填写板卡 IP。'); return
        info = prepared.get(which, {})
        same = os.path.normcase(os.path.normpath(source)) == os.path.normcase(os.path.normpath(str(info.get('source') or '')))
        job = jobs.get(which, {})
        if same and not force_reencode and job.get('state') == 'running' and job.get('operation') == 'send':
            if job.get('stage') in ('已暂停', '正在暂停'):
                action(which, 'resume')
                if after: after()
                return
            state.set(('板卡' if which == 'mjpeg' else '手机') + '视频正在发送；更改板卡地址后请先停止再播放。')
            if after: after()
            return
        try:
            start_args = dict(lane=which, host=host.get().strip(), port=int(ports[which].get()), loop=loop.get(),
                              exclusive=exclusive.get(), mjpeg_pacing_ms=int(mjpeg_pacing.get()) if which == 'mjpeg' else 0)
            raw = which == 'mjpeg' and source.lower().endswith('.mjpeg')
            match = re.search(r'(?i)-mjpeg-(30|35|40|45|50|55|60)k-1024x608-12fps\.mjpeg$', source) if raw else None
            if match and not force_reencode: jpeg_limit.set(match.group(1))
            if (not same or force_reencode) and (not raw or force_reencode) and not os.path.isfile(engine.get().strip()):
                advanced.grid(); state.set('此素材需要 FFmpeg：请在高级设置中选择后再播放。'); return
            args = dict(lane=which, source=source, engine=engine.get().strip(), duration_s=int(duration.get()),
                        mjpeg_passthrough=which == 'mjpeg' and not force_reencode and (raw or passthrough.get()),
                        mjpeg_fps=int(mjpeg_fps.get()),
                        jpeg_quality=int(quality.get()), jpeg_limit_kib=int(jpeg_limit.get()),
                        h264_auto=True if force_reencode else h264_auto.get(), h264_kbps=480, h264_preset=preset.get(),
                        h264_passthrough=which == 'h264' and not force_reencode and (h264_passthrough.get() or source.lower().endswith('.h264')))
        except ValueError:
            state.set('请检查高级设置中的数字。'); return
        if which == 'mjpeg':
            request('settings.update', {'scope':'component.netvideo-ui', 'values':{'default_mjpeg_fps':int(mjpeg_fps.get()), 'default_mjpeg_limit_kib':int(jpeg_limit.get())}}, lambda _: None, lambda _: None)
        quick_busy = True; deadline = time.monotonic() + 300
        def fail(error):
            nonlocal quick_busy
            quick_busy = False
            if view.winfo_exists(): state.set('播放失败：' + str(error))
        def start():
            def started(result):
                nonlocal quick_busy
                quick_busy = False; consume(result)
                if view.winfo_exists():
                    state.set(('板卡' if which == 'mjpeg' else '手机') + '发送任务已启动，请查看连接状态。')
                    request('settings.update', {'scope':'component.netvideo-ui', 'values':{
                        'last_host':start_args['host'], 'default_' + which + '_source':source}},
                        lambda _: None,
                        lambda error: state.set('发送任务已启动，但地址或素材未能保存：' + str(error)) if view.winfo_exists() else None)
                if after: after()
            request('call', {'target':'netvideo.start', 'arguments':start_args}, started, fail)
        if same and not force_reencode:
            start(); return
        state.set(('板卡' if which == 'mjpeg' else '手机') + '视频正在准备，请稍候。')
        def poll(phase):
            if not view.winfo_exists(): return
            if time.monotonic() > deadline: fail('准备超时'); return
            def checked(result):
                job = (result.get('lanes') or {}).get(which, {})
                if job.get('state') == 'running': view.after(250, lambda: poll(phase)); return
                if phase == 'stop':
                    request('call', {'target':'netvideo.prepare', 'arguments':args},
                            lambda _: view.after(250, lambda: poll('prepare')), fail)
                elif job.get('state') == 'succeeded' and job.get('operation') == 'prepare': start()
                else: fail(job.get('error') or '素材准备未成功')
            request('call', {'target':'netvideo.status', 'arguments':{}}, checked, fail)
        request('call', {'target':'netvideo.stop', 'arguments':{'lane':which}},
                lambda _: view.after(250, lambda: poll('stop')), fail)

    def action(which, operation):
        try:
            if operation == 'prepare':
                args = dict(lane=which, source=sources[which].get().strip(), engine=engine.get().strip(),
                            duration_s=int(duration.get()), mjpeg_passthrough=passthrough.get() if which == 'mjpeg' else False,
                            jpeg_quality=int(quality.get()), jpeg_limit_kib=int(jpeg_limit.get()), mjpeg_fps=int(mjpeg_fps.get()), h264_auto=h264_auto.get(),
                            h264_kbps=480, h264_preset=preset.get(), h264_passthrough=h264_passthrough.get() if which == 'h264' else False)
                raw_mjpeg = which == 'mjpeg' and args['mjpeg_passthrough'] and args['source'].lower().endswith('.mjpeg')
                if not args['source'] or (not raw_mjpeg and not args['engine']):
                    state.set('请先选择视频文件和 FFmpeg。'); return
            elif operation == 'start':
                args = dict(lane=which, host=host.get().strip(), port=int(ports[which].get()), loop=loop.get(), exclusive=exclusive.get(),
                            mjpeg_pacing_ms=int(mjpeg_pacing.get()) if which == 'mjpeg' else 0)
                if not args['host']:
                    state.set('请先填写板卡 IP。'); return
                info = prepared.get(which)
                if not info:
                    state.set('请先准备该路视频，再开始发送。'); return
                chosen = sources[which].get().strip().replace('/', '\\').casefold()
                loaded = str(info.get('source') or '').replace('/', '\\').casefold()
                if chosen and loaded and chosen != loaded:
                    state.set('视频文件已改变，请先重新准备，再开始发送。'); return
            else:
                args = dict(lane=which)
        except ValueError:
            state.set('请检查时长、端口、质量和码率是否为数字。'); return
        state.set(('板卡画面' if which == 'mjpeg' else '手机画面') + '：' + {'prepare':'正在准备', 'start':'正在启动', 'pause':'正在暂停', 'resume':'正在继续', 'stop':'正在停止'}[operation])
        def succeeded(result):
            consume(result)
            if operation == 'start' and view.winfo_exists():
                request('settings.update', {'scope':'component.netvideo-ui', 'values':{'last_host':args['host']}},
                        lambda _: None, lambda _: None)
                state.set('已启动发送；板卡 IP 已保存，网络更换时请核对。')
        request('call', {'target':'netvideo.'+operation, 'arguments':args},
                succeeded, lambda error: state.set(str(error)) if view.winfo_exists() else None)

    def stop_preview():
        nonlocal preview_active, preview_generation, preview_window
        preview_generation += 1
        if preview_window is not None:
            preview_window.destroy()
            preview_window = None
        if preview_active:
            preview_active = False
            request('call', {'target':'netvideo.preview_stop', 'arguments':{}}, lambda _: None, lambda _: None)

    def preview(lane):
        nonlocal preview_active, preview_generation, preview_window
        info = prepared.get(lane, {})
        selected = sources[lane].get().strip()
        loaded = str(info.get('source') or '')
        same_source = bool(loaded and selected and os.path.normcase(os.path.normpath(loaded)) == os.path.normcase(os.path.normpath(selected)))
        use_prepared = bool(info.get('preview_path') and (same_source or not selected))
        path = info['preview_path'] if use_prepared else selected
        if not path:
            state.set('请先选择视频文件。'); return
        fmt = lane if path.lower().endswith(('.mjpeg', '.h264')) else 'auto'
        if preview_window is not None:
            preview_window.destroy()
        preview_window = tk.Toplevel(view)
        preview_window.title(('本地 MJPEG' if lane == 'mjpeg' else '远程 H.264') + ' · 发送素材预览')
        preview_window.geometry('960x650')
        preview_window.minsize(400, 300)
        preview_window.protocol('WM_DELETE_WINDOW', stop_preview)
        surface = tk.Frame(preview_window, bg='black', highlightthickness=0)
        surface._nexus_preview = True  # Keep the video canvas black across light and dark themes.
        surface.pack(fill='both', expand=True)
        preview_window.update_idletasks()
        preview_generation += 1
        generation = preview_generation
        def failed(error):
            if view.winfo_exists() and generation == preview_generation:
                stop_preview()
                state.set('预览失败：'+str(error))
        def play(_):
            nonlocal preview_active
            if not view.winfo_exists() or generation != preview_generation: return
            preview_active = True
            fps = float(info.get('fps', 12)) if use_prepared else float(mjpeg_fps.get() if lane == 'mjpeg' else 12)
            request('call', {'target':'netvideo.preview_play', 'arguments':{'source':path, 'format':fmt, 'fps':fps}},
                    lambda _: state.set(('正在预览处理后的 ' if use_prepared else '正在预览新源文件（尚未准备）：') + lane) if view.winfo_exists() else None, failed)
        def attach(_):
            if view.winfo_exists() and generation == preview_generation:
                request('call', {'target':'netvideo.preview_attach', 'arguments':{'window_id':surface.winfo_id()}}, play, failed)
        request('call', {'target':'netvideo.preview_stop', 'arguments':{}}, attach, failed)

    def consume(result):
        if not view.winfo_exists() or not isinstance(result, dict): return
        incoming = result.get('prepared') or {}
        # Follow an externally switched source only if the field still shows
        # the old prepared source; preserve paths the user has typed instead.
        for lane in sources:
            old_source = str(prepared.get(lane, {}).get('source') or '')
            new_source = str(incoming.get(lane, {}).get('source') or '')
            current = sources[lane].get().strip()
            def norm(path): return os.path.normcase(os.path.normpath(path)) if path else ''
            if old_source and new_source and norm(current) == norm(old_source) and norm(old_source) != norm(new_source):
                sources[lane].set(new_source)
        prepared.clear(); prepared.update(incoming)
        jobs.clear(); jobs.update(result.get('lanes') or {})
        for lane in sources:
            job = (result.get('lanes') or {}).get(lane, {})
            info = prepared.get(lane, {})
            job_state = job.get('state')
            status = ('已停止' if job_state == 'cancelled' else '失败' if job_state == 'failed' else
                      '已准备' if job_state == 'succeeded' and job.get('operation') == 'prepare' else
                      job.get('stage') or ('已准备' if info else '未准备'))
            error = (job.get('error') or '') if job_state == 'failed' or job.get('stage') == '等待重连' else ''
            active = job_state == 'running' and job.get('operation') == 'send'
            now = time.monotonic(); old = previous.get(lane)
            current = (job.get('id'), now, job.get('frames', 0), job.get('payload_bytes', 0))
            rate = fps = 0.0
            if active and old and old[0] == current[0] and current[1] > old[1]:
                elapsed = current[1] - old[1]
                fps = max(0, current[2] - old[2]) / elapsed
                rate = max(0, current[3] - old[3]) / elapsed
            elif active:
                fps = job.get('average_fps', 0) or 0; rate = job.get('average_payload_bytes_s', 0) or 0
            previous[lane] = current
            summaries[lane].set(f"{status} · {fps:.1f} 帧/秒 · {rate / 1000:.1f} KB/秒\n重连 {job.get('reconnects', 0)} 次" + (f' · {error}' if error else ''))
            if not info:
                details[lane].set('请选择视频并准备'); continue
            source = info.get('source') or '未知'
            if not sources[lane].get() and info.get('source'): sources[lane].set(info['source'])
            if lane not in initialised:
                if lane == 'mjpeg' and info.get('jpeg_limit_kib'): jpeg_limit.set(str(info['jpeg_limit_kib']))
                if lane == 'mjpeg' and info.get('fps') in (12, 15): mjpeg_fps.set(str(info['fps']))
                initialised.add(lane)
            max_kib = (info.get('max_frame_bytes') or 0) / 1024
            if lane == 'mjpeg':
                variant_status.set(f"本地单帧上限：{info.get('jpeg_limit_kib', '?')} KiB")
                settings_text = f"最大帧 {max_kib:.1f} KiB · 上限 {info.get('jpeg_limit_kib', '?')} KiB · 重压缩 {info.get('recompressed_frames', 0)} 帧"
            else:
                crf = info.get('chosen_crf'); peak = info.get('peak_1s_bytes')
                mode = '原码流直发' if info.get('h264_passthrough') else f"CRF {crf if crf is not None else '未统计'}"
                target = info.get('h264_kbps')
                limit_text = f'{target / 8:.0f} KB/秒' if target and not info.get('h264_passthrough') else '直发码流'
                settings_text = f"{mode} · 设定 {limit_text} · 最大帧 {max_kib:.1f} KiB · 一秒峰值 {f'{peak / 1000:.1f} KB' if peak is not None else '未统计'}"
            details[lane].set(f"当前素材：{source}\n{settings_text} · 共 {info.get('frames', 0)} 帧")
    view.consume_status = consume
    view.stop_preview = stop_preview
    def load_preferences(value):
        if view.winfo_exists() and isinstance(value, dict):
            if not host.get() and value.get('last_host'):
                host.set(value['last_host'])
                state.set('已填入上次的板卡 IP；切换网络后请核对。')
            if not engine.get() and value.get('last_engine'): engine.set(value['last_engine'])
            for lane in sources:
                saved = value.get('default_' + lane + '_source')
                if not sources[lane].get() and isinstance(saved, str): sources[lane].set(saved)
            if value.get('default_mjpeg_limit_kib') in (30, 35, 40, 45, 50, 55, 60):
                jpeg_limit.set(str(value['default_mjpeg_limit_kib']))
            if value.get('default_mjpeg_fps') in (12, 15):
                mjpeg_fps.set(str(value['default_mjpeg_fps']))
            if isinstance(value.get('default_h264_passthrough'), bool): h264_passthrough.set(value['default_h264_passthrough'])
            if isinstance(value.get('default_loop'), bool): loop.set(value['default_loop'])
            if isinstance(value.get('default_exclusive'), bool): exclusive.set(value['default_exclusive'])
    request('settings.get', {'scope':'component.netvideo-ui'}, load_preferences, lambda _: None)
    return view
