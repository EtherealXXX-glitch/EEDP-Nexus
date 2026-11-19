import importlib.util
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from core import Activity,Resources

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('netvideo_test',ROOT/'plugins/netvideo/component.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class NetworkVideoTests(unittest.TestCase):
    def test_raw_mjpeg_switch_needs_no_ffmpeg_but_still_validates_frames(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            activity=Activity(Path(tmp)/'logs');component=module.NetworkVideo(activity,Resources())
            # Minimal JPEG marker sequence for the format validator.
            frame=bytes.fromhex('ffd8 ffc0 0011 08 0260 0400 03 012100 021100 031100 ffd9')
            source=Path(tmp)/'sample.mjpeg';source.write_bytes(frame*13)
            try:
                component.prepare('mjpeg',str(source),'',1,mjpeg_passthrough=True,jpeg_limit_kib=40)
                until=time.monotonic()+5
                while component.status()['state']=='running' and time.monotonic()<until:time.sleep(.01)
                result=component.status()
                self.assertEqual(result['lanes']['mjpeg']['state'],'succeeded',result)
                self.assertEqual(result['prepared']['mjpeg']['frames'],12)
                preview=Path(result['prepared']['mjpeg']['preview_path'])
                self.assertTrue(preview.is_file(), 'raw MJPEG preview must survive snapshot cleanup')
                self.assertEqual(preview.read_bytes(),frame*12)
                bad=Path(tmp)/'bad.mjpeg';bad.write_bytes(b'\xff\xd8invalid\xff\xd9')
                component.prepare('mjpeg',str(bad),'',1,mjpeg_passthrough=True)
                until=time.monotonic()+5
                while component.status()['state']=='running' and time.monotonic()<until:time.sleep(.01)
                self.assertEqual(component.status()['lanes']['mjpeg']['state'],'failed')
            finally:component.close();activity.close()

    def test_raw_mjpeg_explicit_15_fps_preserves_duration(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            activity=Activity(Path(tmp)/'logs');component=module.NetworkVideo(activity,Resources())
            frame=bytes.fromhex('ffd8 ffc0 0011 08 0260 0400 03 012100 021100 031100 ffd9')
            source=Path(tmp)/'sample.mjpeg';source.write_bytes(frame*16)
            try:
                component.prepare('mjpeg',str(source),'',1,mjpeg_passthrough=True,mjpeg_fps=15)
                until=time.monotonic()+5
                while component.status()['state']=='running' and time.monotonic()<until:time.sleep(.01)
                result=component.status()
                self.assertEqual(result['lanes']['mjpeg']['state'],'succeeded',result)
                self.assertEqual(result['prepared']['mjpeg']['fps'],15)
                self.assertEqual(result['prepared']['mjpeg']['frames'],15)
                self.assertEqual(Path(result['prepared']['mjpeg']['preview_path']).read_bytes(),frame*15)
            finally:component.close();activity.close()

    def test_paced_packet_preserves_bytes_and_honours_stop(self):
        class FakeSocket:
            def __init__(self): self.parts=[]
            def sendall(self,data): self.parts.append(bytes(data))
        packet=b'header'+bytes(range(256))*80
        sock=FakeSocket();stop=threading.Event();started=time.monotonic()
        blocked=module.send_paced(sock,packet,stop,12)
        self.assertEqual(b''.join(sock.parts),packet)
        self.assertGreater(len(sock.parts),1)
        self.assertIsNotNone(blocked)
        self.assertGreater(time.monotonic()-started,0.005)
        stop.set();self.assertIsNone(module.send_paced(FakeSocket(),packet,stop,12))

    def test_exclusive_send_blocks_other_lane_until_stopped(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            activity=Activity(Path(tmp)/'logs');component=module.NetworkVideo(activity,Resources())
            activity.emit=lambda *args:None
            try:
                component._launch('mjpeg','sending',lambda stop:stop.wait(5),operation='send',exclusive=True)
                with self.assertRaisesRegex(ValueError,'互斥'):
                    component._launch('h264','sending',lambda stop:None,operation='send',exclusive=False)
                component.stop('mjpeg')
                until=time.monotonic()+2
                while component.status()['state']=='running' and time.monotonic()<until:time.sleep(.01)
                component._launch('h264','sending',lambda stop:None,operation='send',exclusive=True)
            finally:component.close();activity.close()

    def test_peak_payload_includes_loop_boundary(self):
        frames=[b'x'*n for n in (9000,100,100,100,100,100,100,100,100,100,100,9000,9000)]
        self.assertEqual(module.peak_loop_payload(frames), 27900)
        self.assertEqual(module.peak_loop_payload([b'x'*100]),1200)

    def test_h264_passthrough_requires_h264_lane(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            activity=Activity(Path(tmp)/'logs');component=module.NetworkVideo(activity,Resources())
            try:
                with self.assertRaisesRegex(ValueError,'requires h264 lane'):
                    component.prepare(lane='mjpeg',h264_passthrough=True)
            finally:component.close();activity.close()

    def test_deadline_excludes_send_time_and_resets_after_delay(self):
        self.assertAlmostEqual(module.next_deadline(10.0,10.03),10.0+1/12)
        self.assertAlmostEqual(module.next_deadline(10.0,10.20),10.20+1/12)

    def test_h264_sliding_budget_loopback(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            activity=Activity(Path(tmp)/'logs');component=module.NetworkVideo(activity,Resources())
            frame=b'\0\0\1\x09a\0\0\1\x67a\0\0\1\x68a\0\0\1\x65'+b'X'*20000
            path=Path(tmp)/'frames';path.write_bytes((struct.pack('>I',len(frame))+frame)*4)
            component.ready['h264']=dict(path=str(path))
            server=socket.socket();server.bind(('127.0.0.1',0));server.listen();server.settimeout(5)
            arrivals=[]
            def receive():
                conn,_=server.accept()
                with conn:
                    data=b''
                    while chunk:=conn.recv(65536):
                        data+=chunk
                        while len(data)>=24:
                            n=struct.unpack('>4sIIIQ',data[:24])[1]
                            if len(data)<24+n:break
                            arrivals.append(time.monotonic());data=data[24+n:]
            thread=threading.Thread(target=receive);thread.start()
            try:
                component.start('h264','127.0.0.1',server.getsockname()[1],False)
                thread.join(5)
                self.assertEqual(len(arrivals),4)
                self.assertGreaterEqual(arrivals[3]-arrivals[0],1.0)
            finally:component.stop();server.close();activity.close()

    def test_offline_conversion_both_lanes(self):
        engine=ROOT/'build/ffmpeg.exe'
        if not engine.exists():self.skipTest('Local offline FFmpeg not installed')
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            source=Path(tmp)/'test.avi'
            subprocess.run([str(engine),'-loglevel','error','-f','lavfi','-i','testsrc2=size=64x48:rate=12',
                            '-t','1','-c:v','mpeg4',str(source)],check=True,timeout=20,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            activity=Activity(Path(tmp)/'logs');component=module.NetworkVideo(activity,Resources())
            try:
                for lane in ('mjpeg','h264'):
                    component.prepare(lane,str(source),str(engine),1,jpeg_limit_kib=40,h264_kbps=320)
                    until=time.monotonic()+30
                    while component.status()['state']=='running' and time.monotonic()<until:time.sleep(.05)
                    status=component.status()
                    self.assertEqual(status['lanes'][lane]['state'],'succeeded',status)
                    self.assertEqual(status['prepared'][lane]['frames'],12)
                    self.assertLessEqual(status['prepared'][lane]['max_frame_bytes'],61440)
                    if lane=='mjpeg':
                        self.assertLessEqual(status['prepared'][lane]['max_frame_bytes'],40*1024)
                        with open(status['prepared'][lane]['path'],'rb') as stream:
                            for _ in range(12):
                                size=struct.unpack('>I',stream.read(4))[0]
                                self.assertEqual(module.jpeg_format(stream.read(size)),(1024,608,(0x21,0x11,0x11)))
                    else:
                        self.assertLessEqual(status['prepared'][lane]['peak_1s_bytes'],40000)
                        self.assertEqual(status['prepared'][lane]['h264_kbps'],320)
            finally:component.close();activity.close()

    def test_pause_and_resume_mjpeg_preserves_position_without_catchup(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            activity=Activity(Path(tmp)/'logs');component=module.NetworkVideo(activity,Resources())
            path=Path(tmp)/'frames'
            frames=[b'frame'+bytes([i]) for i in range(40)]
            path.write_bytes(b''.join(struct.pack('>I',len(x))+x for x in frames))
            component.ready['mjpeg']=dict(path=str(path),fps=12)
            server=socket.socket();server.bind(('127.0.0.1',0));server.listen();server.settimeout(.2)
            received=[];done=threading.Event()
            def receive():
                while not done.is_set():
                    try:conn,_=server.accept()
                    except socket.timeout:continue
                    except OSError:return
                    with conn:
                        conn.settimeout(.2);buf=b''
                        while not done.is_set():
                            try:chunk=conn.recv(4096)
                            except socket.timeout:continue
                            except OSError:break
                            if not chunk:break
                            buf+=chunk
                            while len(buf)>=16:
                                size=struct.unpack('>4sIII',buf[:16])[1]
                                if len(buf)<16+size:break
                                received.append(buf[16:16+size][-1]);buf=buf[16+size:]
            thread=threading.Thread(target=receive,daemon=True);thread.start()
            try:
                component.start('mjpeg','127.0.0.1',server.getsockname()[1],False)
                until=time.monotonic()+3
                while len(received)<5 and time.monotonic()<until:time.sleep(.01)
                self.assertGreaterEqual(len(received),5)
                component.pause('mjpeg')
                until=time.monotonic()+3
                while component.status()['lanes']['mjpeg']['stage']!='已暂停' and time.monotonic()<until:time.sleep(.01)
                self.assertEqual(component.status()['lanes']['mjpeg']['stage'],'已暂停')
                time.sleep(.2);count=len(received);last=received[-1];time.sleep(.25)
                self.assertEqual(len(received),count)
                component.resume('mjpeg')
                until=time.monotonic()+3
                while len(received)==count and time.monotonic()<until:time.sleep(.01)
                self.assertGreater(len(received),count)
                self.assertEqual(received[count],last+1)
            finally:
                component.stop();done.set();server.close();thread.join(1);activity.close()

    def test_resume_h264_starts_with_previous_keyframe(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            activity=Activity(Path(tmp)/'logs');component=module.NetworkVideo(activity,Resources())
            path=Path(tmp)/'frames';key=b'\x00\x00\x01\x67s\x00\x00\x01\x68p\x00\x00\x01\x65'
            normal=b'\x00\x00\x01\x41'
            frames=[(key if i%4==0 else normal)+bytes([i]) for i in range(24)]
            path.write_bytes(b''.join(struct.pack('>I',len(x))+x for x in frames))
            component.ready['h264']=dict(path=str(path),h264_kbps=480)
            server=socket.socket();server.bind(('127.0.0.1',0));server.listen();server.settimeout(.2)
            connections=[];done=threading.Event()
            def receive():
                while not done.is_set():
                    try:conn,_=server.accept()
                    except socket.timeout:continue
                    except OSError:return
                    items=[];connections.append(items)
                    with conn:
                        conn.settimeout(.2);buf=b''
                        while not done.is_set():
                            try:chunk=conn.recv(4096)
                            except socket.timeout:continue
                            except OSError:break
                            if not chunk:break
                            buf+=chunk
                            while len(buf)>=24:
                                size=struct.unpack('>4sIIIQ',buf[:24])[1]
                                if len(buf)<24+size:break
                                items.append(buf[24:24+size]);buf=buf[24+size:]
            thread=threading.Thread(target=receive,daemon=True);thread.start()
            try:
                component.start('h264','127.0.0.1',server.getsockname()[1],False)
                until=time.monotonic()+3
                while (not connections or len(connections[0])<6) and time.monotonic()<until:time.sleep(.01)
                self.assertGreaterEqual(len(connections[0]),6)
                component.pause('h264')
                until=time.monotonic()+3
                while component.status()['lanes']['h264']['stage']!='已暂停' and time.monotonic()<until:time.sleep(.01)
                self.assertEqual(component.status()['lanes']['h264']['stage'],'已暂停')
                last=connections[0][-1][-1]
                component.resume('h264')
                until=time.monotonic()+3
                while (len(connections)<2 or not connections[1]) and time.monotonic()<until:time.sleep(.01)
                self.assertGreaterEqual(len(connections),2)
                self.assertTrue(module.keyframe(connections[1][0]))
                self.assertEqual(connections[1][0][-1],last//4*4)
            finally:
                component.stop();done.set();server.close();thread.join(1);activity.close()

    def test_loopback_two_frames_and_resource_release(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            activity=Activity(Path(tmp)/'logs');resources=Resources()
            component=module.NetworkVideo(activity,resources)
            frame=b'\xff\xd8example\xff\xd9'
            data=Path(tmp)/'prepared.frames';data.write_bytes((struct.pack('>I',len(frame))+frame)*2)
            component.ready['mjpeg']=dict(path=str(data))
            server=socket.socket();server.bind(('127.0.0.1',0));server.listen();server.settimeout(5)
            received=[]
            def receive():
                conn,_=server.accept()
                with conn:
                    while chunk:=conn.recv(65536):received.append(chunk)
            thread=threading.Thread(target=receive);thread.start()
            try:
                component.start('mjpeg','127.0.0.1',server.getsockname()[1],False)
                until=time.monotonic()+5
                while component.status()['state']=='running' and time.monotonic()<until:time.sleep(.02)
                thread.join(3)
                raw=b''.join(received)
                self.assertEqual(struct.unpack('>4sIII',raw[:16]),(b'MJPG',len(frame),1,0))
                self.assertEqual(len(raw),2*(16+len(frame)))
                self.assertEqual(component.status()['lanes']['mjpeg']['state'],'succeeded')
                self.assertEqual(resources.status(),{})
            finally:component.close();server.close();activity.close()

    def test_prepare_requires_explicit_engine_and_does_not_connect(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            activity=Activity(Path(tmp)/'logs');component=module.NetworkVideo(activity,Resources())
            try:
                with self.assertRaises(ValueError):component.prepare()
                self.assertEqual(component.status()['state'],'idle')
            finally:component.close();activity.close()
