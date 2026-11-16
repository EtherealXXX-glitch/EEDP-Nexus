"""Network-video workspace: prepare and control each stream independently."""
import tkinter as tk
from tkinter import filedialog, ttk
import os
import re
import time


def mjpeg_variant_path(source, limit):
    """Find a sibling prepared rendition without assuming a machine-specific path."""
    if limit not in (30, 40, 45, 50, 55, 60):
        raise ValueError('不支持的档位')
    result, count = re.subn(r'(?i)(-mjpeg-)(?:30|40|45|50|55|60)(k-1024x608-12fps\.mjpeg)$',
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
    jpeg_limit = tk.StringVar(value='37')
    variant_status = tk.StringVar(value='未选择档位')
    mjpeg_pacing = tk.StringVar(value='0')
    bitrate = tk.StringVar(value='480')
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
    quick_busy = False
    previous = {}
    jobs = {}

    header = frame(view)
    header.grid(row=0, column=0, sticky='ew', padx=12, pady=(8, 4))
    header.columnconfigure(2, weight=1)
    label(header, '视频传输').grid(row=0, column=0, sticky='w', padx=(0, 10))
    label(header, '板卡 IP').grid(row=0, column=1, sticky='w')
    ttk.Entry(header, textvariable=host, width=18).grid(row=0, column=2, sticky='w', padx=6)
    main_actions = frame(header); main_actions.grid(row=1, column=0, columnspan=4, sticky='w', pady=(5, 0))
    button(main_actions, '播放两路', lambda: play_both(), primary=True, small=True).grid(row=0, column=0, padx=(0, 4))
    button(main_actions, '全部停止', lambda: stop_all(), small=True).grid(row=0, column=1, padx=4)
    advanced = frame(view)
    advanced.grid(row=3, column=0, sticky='ew', padx=12, pady=4)
    advanced.columnconfigure(1, weight=1)
    label(advanced, 'FFmpeg').grid(row=0, column=0, sticky='w')
    ttk.Entry(advanced, textvariable=engine).grid(row=0, column=1, sticky='ew', padx=6)
    def browse_engine():
        path = filedialog.askopenfilename(parent=view, filetypes=[('FFmpeg', '*.exe'), ('全部文件', '*.*')])
        if path:
            engine.set(path)
            request('settings.update', {'scope':'component.netvideo-ui', 'values':{'last_engine':path}}, lambda _: None, lambda _: None)
    button(advanced, '选择', browse_engine, small=True).grid(row=0, column=2, sticky='w')
    label(advanced, '准备时长（秒，1～300）', muted=True).grid(row=1, column=0, sticky='w', pady=(5, 0))
    ttk.Entry(advanced, textvariable=duration, width=8).grid(row=1, column=1, sticky='w', padx=6, pady=(5, 0))
    toggles = frame(advanced)
    toggles.grid(row=1, column=1, sticky='e', padx=4, pady=(5, 0))
    ttk.Checkbutton(toggles, text='循环', variable=loop).pack(side='left')
    ttk.Checkbutton(toggles, text='两路互斥', variable=exclusive).pack(side='left', padx=4)

    advanced.grid_remove()
    def toggle_advanced():
        if advanced.winfo_ismapped(): advanced.grid_remove()
        else: advanced.grid()
    button(header, '高级设置', toggle_advanced, small=True).grid(row=0, column=3, padx=4)

    dashboard = frame(view)
    dashboard.grid(row=1, column=0, sticky='nsew', padx=12, pady=4)
    dashboard.columnconfigure(0, weight=1, uniform='video')
    dashboard.columnconfigure(1, weight=1, uniform='video')
    panels = {}
    for column, (lane, title) in enumerate((('mjpeg', '本地 · 板卡屏幕'), ('h264', '远程 · 手机视频'))):
        box = frame(dashboard)
        box.grid(row=0, column=column, sticky='nsew', padx=(0, 5) if column == 0 else (5, 0), pady=3)
        box.columnconfigure(0, weight=1)
        panels[lane] = box
        spec = '输出 1024×608 / 12 帧每秒' if lane == 'mjpeg' else '输出 640×360 / 12 帧每秒，视频数据不超过 60 KiB/秒'
        label(box, title).grid(row=0, column=0, sticky='w', padx=8, pady=(8, 2))
        spec_label = label(box, spec, muted=True); spec_label.configure(wraplength=260, justify='left')
        spec_label.grid(row=1, column=0, sticky='w', padx=8, pady=2)
        item = label(box, '', muted=True); item.configure(textvariable=summaries[lane], anchor='w', wraplength=260, justify='left')
        item.grid(row=2, column=0, sticky='ew', padx=8, pady=4)
        file_row = frame(box); file_row.grid(row=3, column=0, sticky='ew', padx=8, pady=3); file_row.columnconfigure(0, weight=1)
        ttk.Entry(file_row, textvariable=sources[lane], width=12).grid(row=0, column=0, sticky='ew', padx=(0, 4))
        def browse(which=lane):
            path = filedialog.askopenfilename(parent=view, filetypes=[('视频文件', '*.avi *.mp4 *.mov *.mkv *.h264 *.mjpeg'), ('全部文件', '*.*')])
            if path: sources[which].set(path)
        button(file_row, '选择视频', browse, small=True).grid(row=0, column=1, padx=2)

        settings = frame(advanced)
        settings.grid(row=2 + column, column=0, columnspan=3, sticky='ew', padx=8, pady=(4, 0))
        settings.columnconfigure(1, weight=1)
        label(settings, '板卡端口', muted=True).grid(row=0, column=0, sticky='w')
        ttk.Entry(settings, textvariable=ports[lane], width=7).grid(row=0, column=1, sticky='w', padx=5)
        if lane == 'mjpeg':
            label(settings, '单帧上限 KiB', muted=True).grid(row=1, column=0, sticky='w', pady=2)
            ttk.Entry(settings, textvariable=jpeg_limit, width=6).grid(row=1, column=1, sticky='w', padx=5, pady=2)
            label(settings, 'JPEG 质量（0 为自动）', muted=True).grid(row=2, column=0, sticky='w', pady=2)
            ttk.Entry(settings, textvariable=quality, width=7).grid(row=2, column=1, sticky='w', padx=5, pady=2)
            ttk.Checkbutton(settings, text='符合规格的 MJPEG 直发', variable=passthrough).grid(row=3, column=0, columnspan=2, sticky='w', pady=2)
            label(settings, '分块发送时间（毫秒）', muted=True).grid(row=4, column=0, sticky='w', pady=2)
            ttk.Entry(settings, textvariable=mjpeg_pacing, width=7).grid(row=4, column=1, sticky='w', padx=5, pady=2)
        else:
            label(settings, '目标码率 kbps', muted=True).grid(row=1, column=0, sticky='w', pady=2)
            ttk.Entry(settings, textvariable=bitrate, width=7).grid(row=1, column=1, sticky='w', padx=5, pady=2)
            ttk.Checkbutton(settings, text='自动优化画质', variable=h264_auto).grid(row=2, column=0, sticky='w', pady=2)
            ttk.Combobox(settings, textvariable=preset, values=['veryfast', 'medium', 'slow'], state='readonly', width=8).grid(row=2, column=1, sticky='w', padx=5, pady=2)
            ttk.Checkbutton(settings, text='H.264 直发（实验）', variable=h264_passthrough).grid(row=3, column=0, columnspan=2, sticky='w', pady=2)

        actions = frame(box); actions.grid(row=4, column=0, sticky='w', padx=8, pady=5)
        button(actions, '播放', lambda k=lane: play(k), primary=True, small=True).grid(row=0, column=0, padx=(0, 4), pady=2)
        button(actions, '停止', lambda k=lane: action(k, 'stop'), small=True).grid(row=0, column=1, padx=4, pady=2)
        button(actions, '预览', lambda k=lane: preview(k), small=True).grid(row=0, column=2, padx=4, pady=2)
        button(settings, '准备视频', lambda k=lane: action(k, 'prepare'), small=True).grid(row=6, column=0, sticky='w')
        if lane == 'mjpeg':
            variant_title = label(box, '', muted=True); variant_title.configure(textvariable=variant_status)
            variant_title.grid(row=5, column=0, sticky='w', padx=8, pady=(6, 0))
            quick = frame(box); quick.grid(row=6, column=0, sticky='w', padx=8, pady=4)
            for n, limit in enumerate((30, 40, 45, 50, 55, 60)):
                button(quick, str(limit), lambda n=limit: quick_switch(n), small=True).grid(row=n//3, column=n%3, padx=3, pady=2)
            label(box, '30～40 通常更流畅；高档位可能卡顿', muted=True).grid(row=7, column=0, sticky='w', padx=8)
        description = label(box, '', muted=True)
        description.configure(textvariable=details[lane], justify='left', anchor='w', wraplength=260)
        description.grid(row=8, column=0, sticky='ew', padx=8, pady=4)
        box.bind('<Configure>', lambda event, widget=description: widget.configure(wraplength=max(200, event.width - 30)), add='+')
    preview_tab = frame(view); preview_tab.grid(row=2, column=0, sticky='ew', padx=12, pady=4)
    preview_tab.columnconfigure(0, weight=1)
    label(preview_tab, '电脑端素材预览（实际播放以设备为准）', muted=True).grid(row=0, column=0, sticky='w', padx=8, pady=4)
    surface = tk.Frame(preview_tab, bg='black', highlightthickness=0)
    surface.configure(height=180); surface.grid(row=1, column=0, sticky='ew', padx=8, pady=4)
    button(preview_tab, '停止预览', lambda: stop_preview(), small=True).grid(row=2, column=0, sticky='e', padx=8, pady=4)
    feedback = label(view, '', muted=True)
    feedback.configure(textvariable=state, anchor='w')
    preview_tab.grid_remove()
    feedback.grid(row=4, column=0, sticky='ew', padx=12, pady=(2, 8))

    def quick_switch(limit):
        nonlocal quick_busy
        if quick_busy:
            state.set('正在切换，请稍候。'); return
        try:
            current = sources['mjpeg'].get().strip() or str(prepared.get('mjpeg', {}).get('source') or '')
            target = mjpeg_variant_path(current, limit)
            if not os.path.isfile(target): raise ValueError('找不到对应档位文件：' + target)
            if not host.get().strip(): raise ValueError('请先填写板卡 IP。')
            args = dict(lane='mjpeg', source=target, engine=engine.get().strip(),
                        duration_s=int(duration.get()), mjpeg_passthrough=True, jpeg_limit_kib=limit)
            start_args = dict(lane='mjpeg', host=host.get().strip(), port=int(ports['mjpeg'].get()),
                              loop=loop.get(), exclusive=exclusive.get(), mjpeg_pacing_ms=int(mjpeg_pacing.get()))
        except ValueError as error:
            state.set(str(error)); return
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
                        if view.winfo_exists(): state.set(f'已切换到 {limit} KiB/帧。')
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

    def play(which, after=None):
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
        if same and job.get('state') == 'running' and job.get('operation') == 'send':
            state.set(('板卡' if which == 'mjpeg' else '手机') + '视频正在发送。')
            if after: after()
            return
        try:
            start_args = dict(lane=which, host=host.get().strip(), port=int(ports[which].get()), loop=loop.get(),
                              exclusive=exclusive.get(), mjpeg_pacing_ms=int(mjpeg_pacing.get()) if which == 'mjpeg' else 0)
            raw = which == 'mjpeg' and source.lower().endswith('.mjpeg')
            match = re.search(r'(?i)-mjpeg-(30|40|45|50|55|60)k-1024x608-12fps\.mjpeg$', source) if raw else None
            if match: jpeg_limit.set(match.group(1))
            if not same and not raw and not os.path.isfile(engine.get().strip()):
                advanced.grid(); state.set('此素材需要 FFmpeg：请在高级设置中选择后再播放。'); return
            args = dict(lane=which, source=source, engine=engine.get().strip(), duration_s=int(duration.get()),
                        mjpeg_passthrough=raw or (which == 'mjpeg' and passthrough.get()),
                        jpeg_quality=int(quality.get()), jpeg_limit_kib=int(jpeg_limit.get()),
                        h264_auto=h264_auto.get(), h264_kbps=int(bitrate.get()), h264_preset=preset.get(),
                        h264_passthrough=which == 'h264' and (h264_passthrough.get() or source.lower().endswith('.h264')))
        except ValueError:
            state.set('请检查高级设置中的数字。'); return
        quick_busy = True; deadline = time.monotonic() + 300
        def fail(error):
            nonlocal quick_busy
            quick_busy = False
            if view.winfo_exists(): state.set('播放失败：' + str(error))
        def start():
            def started(result):
                nonlocal quick_busy
                quick_busy = False; consume(result)
                if view.winfo_exists(): state.set(('板卡' if which == 'mjpeg' else '手机') + '视频已开始发送。')
                if after: after()
            request('call', {'target':'netvideo.start', 'arguments':start_args}, started, fail)
        if same:
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
                            jpeg_quality=int(quality.get()), jpeg_limit_kib=int(jpeg_limit.get()), h264_auto=h264_auto.get(),
                            h264_kbps=int(bitrate.get()), h264_preset=preset.get(), h264_passthrough=h264_passthrough.get() if which == 'h264' else False)
                if not args['source'] or not args['engine']:
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
        state.set(('板卡画面' if which == 'mjpeg' else '手机画面') + '：' + {'prepare':'正在准备', 'start':'正在启动', 'stop':'正在停止'}[operation])
        def succeeded(result):
            consume(result)
            if operation == 'start' and view.winfo_exists():
                request('settings.update', {'scope':'component.netvideo-ui', 'values':{'last_host':args['host']}},
                        lambda _: None, lambda _: None)
                state.set('已启动发送；板卡 IP 已保存，网络更换时请核对。')
        request('call', {'target':'netvideo.'+operation, 'arguments':args},
                succeeded, lambda error: state.set(str(error)) if view.winfo_exists() else None)

    def stop_preview():
        nonlocal preview_active, preview_generation
        preview_generation += 1
        preview_tab.grid_remove()
        if preview_active:
            preview_active = False
            request('call', {'target':'video.stop', 'arguments':{}}, lambda _: None, lambda _: None)

    def preview(lane):
        nonlocal preview_active, preview_generation
        path = prepared.get(lane, {}).get('preview_path') or sources[lane].get().strip()
        if not path:
            state.set('请先选择视频文件。'); return
        fmt = lane if path.lower().endswith(('.mjpeg', '.h264')) else 'auto'
        preview_tab.grid()
        preview_generation += 1
        generation = preview_generation
        def failed(error):
            if view.winfo_exists(): state.set('预览失败：'+str(error))
        def play(_):
            nonlocal preview_active
            if not view.winfo_exists() or generation != preview_generation: return
            preview_active = True
            request('call', {'target':'video.play', 'arguments':{'source':path, 'format':fmt, 'fps':12.0}},
                    lambda _: state.set('正在预览处理后的 '+lane) if view.winfo_exists() else None, failed)
        def attach(_):
            if view.winfo_exists() and generation == preview_generation:
                request('call', {'target':'video.attach', 'arguments':{'window_id':surface.winfo_id()}}, play, failed)
        request('call', {'target':'video.stop', 'arguments':{}}, attach, failed)

    def consume(result):
        if not view.winfo_exists() or not isinstance(result, dict): return
        prepared.clear(); prepared.update(result.get('prepared') or {})
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
            if not sources[lane].get(): sources[lane].set(source)
            if lane not in initialised:
                if lane == 'mjpeg' and info.get('jpeg_limit_kib'): jpeg_limit.set(str(info['jpeg_limit_kib']))
                initialised.add(lane)
            max_kib = (info.get('max_frame_bytes') or 0) / 1024
            if lane == 'mjpeg':
                variant_status.set(f"本地单帧上限：{info.get('jpeg_limit_kib', '?')} KiB")
                settings_text = f"最大帧 {max_kib:.1f} KiB · 上限 {info.get('jpeg_limit_kib', '?')} KiB · 重压缩 {info.get('recompressed_frames', 0)} 帧"
            else:
                crf = info.get('chosen_crf'); peak = info.get('peak_1s_bytes')
                mode = '原码流直发' if info.get('h264_passthrough') else f"CRF {crf if crf is not None else '未统计'}"
                settings_text = f"{mode} · 最大帧 {max_kib:.1f} KiB · 一秒峰值 {f'{peak / 1024:.1f} KiB' if peak is not None else '未统计'}"
            details[lane].set(f"当前素材：{source}\n{settings_text} · 共 {info.get('frames', 0)} 帧")
    view.consume_status = consume
    view.stop_preview = stop_preview
    def load_preferences(value):
        if view.winfo_exists() and isinstance(value, dict):
            if not host.get() and value.get('last_host'):
                host.set(value['last_host'])
                state.set('已填入上次的板卡 IP；切换网络后请核对。')
            if not engine.get() and value.get('last_engine'): engine.set(value['last_engine'])
    request('settings.get', {'scope':'component.netvideo-ui'}, load_preferences, lambda _: None)
    return view
