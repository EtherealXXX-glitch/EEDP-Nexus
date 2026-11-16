"""Independent TCP video sender. Construction never opens a socket."""
import collections
import copy
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import threading
import time
import uuid
from core import field

LIMIT=61440


def send_paced(conn, packet, stop, pacing_ms):
    if not pacing_ms:
        start=time.monotonic();conn.sendall(packet)
        return time.monotonic()-start
    started=time.monotonic();blocked=0.0;size=len(packet)
    for offset in range(0,size,8192):
        if stop.is_set():return None
        if offset and stop.wait(max(0.0, started + pacing_ms/1000 * offset/size - time.monotonic())):
            return None
        before=time.monotonic();conn.sendall(packet[offset:offset+8192]);blocked+=time.monotonic()-before
    return blocked


def next_deadline(previous, now, interval=1/12):
    candidate=previous+interval
    return candidate if candidate>now else now+interval


def jpeg_format(data):
    if not data.startswith(b'\xff\xd8'):raise ValueError('Not a JPEG')
    pos=2
    while pos+4<=len(data):
        if data[pos]!=0xff:raise ValueError('Invalid JPEG marker')
        while pos<len(data) and data[pos]==0xff:pos+=1
        marker=data[pos];pos+=1
        if marker in (0xd8,0xd9,0x01) or 0xd0<=marker<=0xd7:continue
        if pos+2>len(data):break
        size=int.from_bytes(data[pos:pos+2],'big')
        if size<2 or pos+size>len(data):raise ValueError('Invalid JPEG segment')
        if marker in (0xc0,0xc1,0xc2):
            segment=data[pos+2:pos+size]
            if len(segment)<15 or segment[5]!=3:raise ValueError('Unsupported JPEG components')
            return (int.from_bytes(segment[3:5],'big'),int.from_bytes(segment[1:3],'big'),tuple(segment[7+i*3] for i in range(3)))
        if marker==0xda:break
        pos+=size
    raise ValueError('JPEG frame header missing')


def units(data, codec):
    if codec=='mjpeg':
        start=0
        while start<len(data):
            end=data.find(b'\xff\xd9',start)
            if end<0 or data[start:start+2]!=b'\xff\xd8':raise ValueError('Invalid JPEG stream')
            yield data[start:end+2]
            start=end+2
    else:
        offsets=[m.start() for m in re.finditer(b'\x00\x00(?:\x00)?\x01\x09',data)]
        if not offsets or offsets[0]!=0:raise ValueError('H264 requires AUD-delimited access units')
        for i,start in enumerate(offsets):yield data[start:offsets[i+1] if i+1<len(offsets) else len(data)]


def keyframe(data):
    types=[m[1][0]&31 for m in re.finditer(b'\x00\x00(?:\x00)?\x01(.)',data,re.S)]
    return {7,8,5}.issubset(types)


def peak_loop_payload(frames, fps=12):
    """Worst 1-second payload for a repeating constant-fps sequence."""
    sizes=[len(frame) for frame in frames]
    if not sizes:return 0
    extended=(sizes*((len(sizes)+fps-2)//len(sizes)+1))[:len(sizes)+fps-1]
    return max(sum(extended[i:i+fps]) for i in range(len(sizes)))


def arguments():
    return [field('lane','视频通道','mjpeg',['mjpeg','h264']),
            field('source','素材文件绝对路径','',remember=False),
            field('engine','FFmpeg 可执行文件绝对路径','',remember=False),
            field('duration_s','预处理长度秒（最多300）',30,kind='int'),
            field('mjpeg_passthrough','直发已符合规格的 MJPEG',False,kind='bool',remember=False),
            field('h264_passthrough','直发已符合规格的 H.264',False,kind='bool',remember=False),
            field('jpeg_quality','JPEG 质量（0 自动，10–95 手动）',0,kind='int'),
            field('jpeg_limit_kib','JPEG 单帧上限（10–60 KiB）',60,kind='int'),
            field('h264_auto','自动优化 H.264 画质',True,kind='bool'),
            field('h264_kbps','H.264 编码上限（32–480 kbps）',480,kind='int'),
            field('h264_preset','H.264 编码速度','medium',['veryfast','medium','slow'])]


class NetworkVideo:
    id='netvideo'
    name='双路视频发送'
    description='独立TCP MJPEG/H.264发送；先预处理素材，再显式启动。板卡须实现对应服务。'
    actions={
        'status':dict(label='状态和统计',read_only=True,destructive=False,fields=[]),
        'prepare':dict(label='预处理素材（不联网）',read_only=False,destructive=False,fields=arguments()),
        'start':dict(label='开始发送',read_only=False,destructive=True,fields=[
            field('lane','视频通道','mjpeg',['mjpeg','h264']),field('host','板卡IP','',remember=False),
            field('port','端口（0=默认5001/5002）',0,kind='int'),field('loop','循环发送',True,kind='bool'),
            field('exclusive','两路互斥',True,kind='bool'),
            field('mjpeg_pacing_ms','MJPEG 分块发送时间（0–70 毫秒）',0,kind='int')]),
        'stop':dict(label='停止通道',read_only=False,destructive=True,fields=[field('lane','通道','all',['all','mjpeg','h264'])])}

    def __init__(self,activity,resources):
        self.activity,self.resources=activity,resources
        self.lock=threading.RLock()
        self.jobs={}
        self.controls={}
        self.ready={}
        self.cache=activity.directory.parent/'runtime/netvideo'

    def status(self):
        with self.lock:
            lanes=copy.deepcopy(self.jobs)
            for job in lanes.values():
                elapsed=max(.001,job.get('finished',time.time())-job['started'])
                job['average_fps']=round(job['frames']/elapsed,2)
                job['average_payload_bytes_s']=round(job['payload_bytes']/elapsed,2)
            return dict(state='running' if any(j['state']=='running' for j in self.jobs.values()) else 'idle',
                        lanes=lanes,prepared=copy.deepcopy(self.ready))

    def _launch(self,lane,stage,worker,operation='prepare',exclusive=False):
        if lane not in ('mjpeg','h264'):raise ValueError('Unknown lane')
        with self.lock:
            if self.jobs.get(lane,{}).get('state')=='running':raise ValueError('Lane is busy')
            if operation=='send':
                for other,job in self.jobs.items():
                    if other != lane and job.get('state')=='running' and job.get('operation')=='send' and (exclusive or job.get('exclusive')):
                        raise ValueError('两路互斥：请先停止另一通道并等待结束')
            stop=threading.Event()
            self.controls[lane]=stop
            self.jobs[lane]=dict(id=uuid.uuid4().hex,state='running',stage=stage,operation=operation,exclusive=exclusive,started=time.time(),frames=0,payload_bytes=0,reconnects=0,error='')
            def run():
                try:
                    worker(stop)
                    with self.lock:self.jobs[lane].update(state='cancelled' if stop.is_set() else 'succeeded',stage='完成')
                except Exception as exc:
                    with self.lock:self.jobs[lane].update(state='cancelled' if stop.is_set() else 'failed',error=str(exc),stage='已停止')
                finally:
                    with self.lock:self.jobs[lane]['finished']=time.time()
                    self.activity.emit(self.id,'finished',json.dumps(self.status(),ensure_ascii=False))
            thread=threading.Thread(target=run,daemon=True)
            thread.start()
        return self.status()

    def prepare(self,lane='mjpeg',source='',engine='',duration_s=30,mjpeg_passthrough=False,jpeg_quality=0,jpeg_limit_kib=60,h264_auto=True,h264_kbps=480,h264_preset='medium',h264_passthrough=False):
        if lane not in ('mjpeg','h264') or not 1<=duration_s<=300:raise ValueError('Invalid lane or duration')
        if mjpeg_passthrough and lane!='mjpeg':raise ValueError('MJPEG passthrough requires mjpeg lane')
        if h264_passthrough and lane!='h264':raise ValueError('H264 passthrough requires h264 lane')
        if jpeg_quality != 0 and not 10 <= jpeg_quality <= 95:raise ValueError('JPEG quality must be 0 or 10–95')
        if not 10 <= jpeg_limit_kib <= 60:raise ValueError('JPEG frame limit must be 10–60 KiB')
        if not 32 <= h264_kbps <= 480:raise ValueError('H264 bitrate must be 32–480 kbps')
        if h264_preset not in ('veryfast','medium','slow'):raise ValueError('Unsupported H264 preset')
        source=Path(source)
        raw_mjpeg = lane == 'mjpeg' and mjpeg_passthrough and source.suffix.lower() == '.mjpeg'
        engine=Path(engine) if engine else None
        if not source.is_file() or (not raw_mjpeg and (engine is None or not engine.is_file())):
            raise ValueError('Provide existing media and trusted FFmpeg executable')
        def work(stop):
            self.cache.mkdir(parents=True,exist_ok=True)
            token=uuid.uuid4().hex
            raw=self.cache/(token+'.raw')
            normalized=self.cache/(token+'.jpeg')
            prepared=self.cache/(token+'.frames')
            preview=self.cache/(token+('.mjpeg' if lane=='mjpeg' else '.h264'))
            snapshot=self.cache/(token+source.suffix)
            if source.stat().st_size>256*1024**2:raise ValueError('Source exceeds 256 MiB preparation limit')
            digest=hashlib.sha256()
            with source.open('rb') as stream, snapshot.open('xb') as saved:
                while chunk:=stream.read(1024*1024):
                    if stop.is_set():
                        saved.close();snapshot.unlink(missing_ok=True);return
                    saved.write(chunk)
                    if saved.tell()>256*1024**2:
                        saved.close();snapshot.unlink(missing_ok=True);raise ValueError('Growing source exceeds size limit')
                    digest.update(chunk)
            try:
                # MJPEG copy mode accepts existing JPEG only after per-frame validation below.
                codec_args=(['-vf','scale=1024:608,fps=12','-c:v','mjpeg','-pix_fmt','yuvj422p','-q:v','2','-f','mjpeg']
                            if lane=='mjpeg' and not mjpeg_passthrough else ['-c:v','copy','-f','mjpeg']
                            if lane=='mjpeg' else ['-vf','scale=640:360,fps=12','-c:v','libx264','-pix_fmt','yuv420p','-profile:v','baseline',
                            '-preset',h264_preset,'-tune','zerolatency','-bf','0','-g','12','-keyint_min','12',
                            '-b:v',f'{h264_kbps}k','-maxrate',f'{min(480, h264_kbps*5//4)}k','-bufsize','24k','-x264-params','aud=1:repeat-headers=1:scenecut=0','-f','h264'])
                def encode(options):
                    command=[str(engine.resolve()),'-nostdin','-hide_banner','-loglevel','error','-y','-i',str(snapshot),
                             '-t',str(duration_s),'-an','-threads','1',*options,str(raw)]
                    with self.lock:self.jobs[lane]['command']=command
                    with subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as process:
                        deadline=time.monotonic()+300
                        while process.poll() is None:
                            if stop.wait(.1) or time.monotonic()>deadline or (raw.exists() and raw.stat().st_size>256*1024**2):
                                process.kill();process.wait();raise ValueError('Preparation cancelled, timed out or exceeded size bound')
                        if process.returncode:raise ValueError('FFmpeg conversion failed; check source and encoder support')
                chosen_crf=None
                peak_bytes=None
                if lane=='h264' and h264_passthrough:
                    probe=subprocess.run([str(engine.resolve()),'-hide_banner','-i',str(snapshot)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).stderr.decode('utf-8','replace')
                    if not re.search(r'Video: h264 \((?:Constrained )?Baseline\).*?640x360.*?12 fps',probe):
                        raise ValueError('H264 passthrough requires verified 640x360 Baseline 12 fps input')
                    encode(['-c:v','copy','-bsf:v','h264_mp4toannexb','-f','h264'])
                    data=raw.read_bytes()
                    first=re.search(b'\x00\x00(?:\x00)?\x01\x09',data)
                    if not first:raise ValueError('H264 requires AUD-delimited access units')
                    if first.start():
                        data=data[first.start():first.end()]+data[:first.start()]+data[first.end():]
                    frames=list(units(data,'h264'))
                    keys=[i for i,frame in enumerate(frames) if keyframe(frame)]
                    if not keys or keys[0]!=0 or any(b-a>12 for a,b in zip(keys,keys[1:])) or len(frames)-keys[-1]>12:
                        raise ValueError('H264 requires repeated SPS/PPS and an IDR at least every 12 frames')
                    peak_bytes=peak_loop_payload(frames)
                    if peak_bytes>LIMIT or max(map(len,frames))>LIMIT:raise ValueError('H264 passthrough exceeds 60 KiB per second or frame')
                    raw.write_bytes(data)
                elif lane=='h264' and h264_auto:
                    lo,hi,best=12,45,None
                    while lo<=hi:
                        crf=(lo+hi)//2
                        with self.lock:self.jobs[lane]['stage']=f'自动码率：测试 CRF {crf}'
                        options=['-vf','scale=640:360,fps=12','-c:v','libx264','-pix_fmt','yuv420p','-profile:v','baseline',
                                 '-preset',h264_preset,'-tune','zerolatency','-bf','0','-g','12','-keyint_min','12',
                                 '-crf',str(crf),'-maxrate',f'{h264_kbps}k','-bufsize',f'{h264_kbps}k',
                                 '-x264-params','aud=1:repeat-headers=1:scenecut=0','-f','h264']
                        encode(options)
                        candidate=raw.read_bytes()
                        frames=list(units(candidate,'h264'))
                        peak=peak_loop_payload(frames)
                        if frames and peak<=LIMIT and max(map(len,frames))<=LIMIT:
                            best=(candidate,crf,peak);hi=crf-1
                        else:lo=crf+1
                    if best is None:raise ValueError('Cannot encode H264 within 60 KiB/s; use a simpler source')
                    raw.write_bytes(best[0]);chosen_crf=best[1];peak_bytes=best[2]
                elif raw_mjpeg:
                    # Raw MJPEG contains complete JPEG units; validation below is still mandatory.
                    # Avoid launching FFmpeg for every pre-generated quality switch.
                    shutil.copyfile(snapshot, raw)
                else:
                    encode(codec_args)
                if raw.stat().st_size>256*1024**2:raise ValueError('Output too large')
                recompressed=0
                if lane=='mjpeg' and not mjpeg_passthrough:
                    helper=Path(__file__).resolve().parent/'bin/eedp-jpeg/eedp-jpeg.exe'
                    if not helper.is_file():raise ValueError('Missing JPEG 4:2:2 encoder helper')
                    with subprocess.Popen([str(helper),str(raw),str(normalized),str(jpeg_quality),str(jpeg_limit_kib)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as process:
                        deadline=time.monotonic()+300
                        while process.poll() is None:
                            if stop.wait(.1) or time.monotonic()>deadline:
                                process.kill();process.wait();raise ValueError('JPEG conversion stopped or timed out')
                        output,error=process.communicate()
                        if process.returncode:raise ValueError('JPEG conversion failed: '+error.decode('utf-8','replace')[-500:])
                        recompressed=json.loads(output)['recompressed_frames']
                    if normalized.stat().st_size>256*1024**2:raise ValueError('Output too large')
                data=(normalized if lane=='mjpeg' and not mjpeg_passthrough else raw).read_bytes()
                if raw_mjpeg:
                    # Raw MJPEG has no container timestamps: its frame sequence is
                    # explicitly 12 fps, so limit the prepared duration by count.
                    end = 0
                    for index, frame in enumerate(units(data, lane)):
                        if index >= duration_s * 12: break
                        end += len(frame)
                    data = data[:end]
                count=0;largest=0
                with prepared.open('xb') as stream:
                    for frame in units(data,lane):
                        if stop.is_set():raise ValueError('Preparation cancelled')
                        if lane=='mjpeg' and jpeg_format(frame)!=(1024,608,(0x21,0x11,0x11)):
                            raise ValueError('JPEG must be 1024x608 with sampling 21/11/11')
                        if lane=='mjpeg' and len(frame)>jpeg_limit_kib*1024:
                            raise ValueError('JPEG frame exceeds selected limit')
                        if not 1<=len(frame)<=LIMIT:raise ValueError('Encoded frame exceeds 60 KiB; use a simpler/lower-rate source')
                        if lane=='h264' and count==0 and not keyframe(frame):raise ValueError('Missing initial SPS/PPS/IDR')
                        stream.write(struct.pack('>I',len(frame)));stream.write(frame)
                        count+=1;largest=max(largest,len(frame))
                if not count:raise ValueError('No video frames')
                preview.write_bytes(data)
                with self.lock:
                    old=self.ready.get(lane)
                    self.ready[lane]=dict(path=str(prepared),preview_path=str(preview),frames=count,max_frame_bytes=largest,recompressed_frames=recompressed,source=str(source.resolve()),sha256=digest.hexdigest(),fps=12,chosen_crf=chosen_crf,peak_1s_bytes=peak_bytes,jpeg_limit_kib=jpeg_limit_kib if lane=='mjpeg' else None,h264_passthrough=h264_passthrough if lane=='h264' else False)
                if old:
                    for previous in (old['path'], old.get('preview_path')):
                        if previous:
                            try:Path(previous).unlink(missing_ok=True)
                            except OSError:pass  # Windows 播放器可能仍在读取旧预览
            except BaseException:
                prepared.unlink(missing_ok=True)
                preview.unlink(missing_ok=True)
                raise
            finally:
                raw.unlink(missing_ok=True)
                normalized.unlink(missing_ok=True)
                snapshot.unlink(missing_ok=True)
        return self._launch(lane,'预处理',work)

    def start(self,lane='mjpeg',host='',port=0,loop=True,exclusive=True,mjpeg_pacing_ms=0):
        if lane not in ('mjpeg','h264'):raise ValueError('Unknown lane')
        if not isinstance(exclusive,bool):raise ValueError('exclusive must be boolean')
        if not isinstance(mjpeg_pacing_ms,int) or not 0<=mjpeg_pacing_ms<=70:raise ValueError('MJPEG pacing must be 0–70 ms')
        host=str(ipaddress.ip_address(host))
        port=port or (5001 if lane=='mjpeg' else 5002)
        if not 1<=port<=65535:raise ValueError('Invalid port')
        with self.lock:prepared=copy.deepcopy(self.ready.get(lane))
        if not prepared:raise ValueError('Prepare the lane first')
        def work(stop):
            resource=f'TCP:{host}:{port}'
            self.resources.acquire(resource,self.id)
            budget=collections.deque()
            frame_budget=collections.deque()
            try:
                while not stop.is_set():
                    try:
                        with socket.create_connection((host,port),timeout=2) as conn:
                            conn.settimeout(2)
                            sequence=1;timestamp=0;due=time.monotonic()
                            while not stop.is_set():
                                with open(prepared['path'],'rb') as stream:
                                    while length:=stream.read(4):
                                        size=struct.unpack('>I',length)[0]
                                        if not 1<=size<=LIMIT:raise ValueError('Corrupt prepared frame')
                                        frame=stream.read(size)
                                        if len(frame)!=size:raise ValueError('Truncated prepared frame')
                                        if stop.wait(max(0,due-time.monotonic())):return
                                        # Keep at most 12 frame starts in any rolling second.
                                        while True:
                                            now=time.monotonic()
                                            while frame_budget and now-frame_budget[0]>=1.0:frame_budget.popleft()
                                            if len(frame_budget)<12:break
                                            if stop.wait(max(0.001,1.0-(now-frame_budget[0]))):return
                                        if lane=='h264':
                                            while True:
                                                now=time.monotonic()
                                                while budget and now-budget[0][0]>1.001:budget.popleft()
                                                if sum(n for _,n in budget)+size<=LIMIT:break
                                                if stop.wait(.01):return
                                        if sequence>0xffffffff:raise OSError('Sequence rollover; reconnect')
                                        header=(struct.pack('>4sIII',b'MJPG',size,sequence,0) if lane=='mjpeg' else
                                                struct.pack('>4sIIIQ',b'H264',size,sequence,int(keyframe(frame)),timestamp))
                                        send_started=time.monotonic()
                                        frame_budget.append(send_started)
                                        budget.append((send_started,size))
                                        try:
                                            blocked=send_paced(conn,header+frame,stop,mjpeg_pacing_ms if lane=='mjpeg' else 0)
                                        finally:budget[-1]=(time.monotonic(),size)
                                        if blocked is None:return
                                        now=time.monotonic()
                                        while budget and now-budget[0][0]>1.001:budget.popleft()
                                        next_due=due+1/12
                                        due=now+1/12 if now-next_due>=1/12 else next_due
                                        sequence+=1;timestamp+=83334
                                        with self.lock:
                                            job=self.jobs[lane];job['frames']+=1;job['payload_bytes']+=size
                                            job.update(stage='发送中',last_sequence=sequence-1,window_payload_bytes=sum(n for _,n in budget),
                                                       send_max_ms=max(job.get('send_max_ms',0),round((now-send_started)*1000,2)),
                                                       send_block_max_ms=max(job.get('send_block_max_ms',0),round(blocked*1000,2)),
                                                       mjpeg_pacing_ms=mjpeg_pacing_ms if lane=='mjpeg' else 0)
                                if not loop:return
                    except OSError as exc:
                        with self.lock:self.jobs[lane].update(stage='等待重连',error=str(exc));self.jobs[lane]['reconnects']+=1
                        if stop.wait(2):return
            finally:self.resources.release(resource,self.id)
        return self._launch(lane,'连接中',work,operation='send',exclusive=exclusive)

    def stop(self,lane='all'):
        if lane not in ('all','mjpeg','h264'):raise ValueError('Unknown lane')
        with self.lock:
            for key,event in self.controls.items():
                if lane in ('all',key):event.set()
        return self.status()

    def close(self):self.stop()
