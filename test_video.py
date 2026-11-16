"""Offline tests: no windows, physical devices, or external network streams."""
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import time
import unittest
import uuid
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("video_component_test", ROOT / "plugins/video/component.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VideoTests(unittest.TestCase):
    def setUp(self):
        self.video = module.VideoPlayer(Mock(), Mock())

    def tearDown(self):
        self.video.close()

    @unittest.skipUnless(os.name == "nt", "Windows window handles")
    def test_raw_video_arguments_and_owned_process(self):
        self.video.engine = ROOT / "plugins/video/bin/mpv.exe"
        if not self.video.engine.is_file(): self.skipTest("local mpv engine not installed")
        self.video.window_id = 123
        process = Mock()
        process.poll.return_value = None
        with patch.object(module.ctypes.windll.user32, "IsWindow", return_value=1), patch.object(module.subprocess, "Popen", return_value=process) as launch:
            result = self.video.play("udp://127.0.0.1:12345", format="rawvideo", width=64, height=48, pixel_format="nv12", fps=30)
            self.assertTrue(result["playing"])
            args = launch.call_args.args[0]
            self.assertIn("--demuxer-rawvideo-w=64", args)
            self.assertIn("--demuxer-rawvideo-mp-format=nv12", args)
            self.assertEqual(args[-2:], ["--", "udp://127.0.0.1:12345"])
            self.video.stop()
            process.terminate.assert_called_once()

    def test_invalid_inputs_are_rejected_without_starting(self):
        self.video.engine = ROOT / "plugins/video/bin/mpv.exe"
        if not self.video.engine.is_file(): self.skipTest("local mpv engine not installed")
        with self.assertRaisesRegex(ValueError, "帧率"):
            self.video.play("udp://127.0.0.1:12345", format="rawvideo", fps=0)
        with self.assertRaisesRegex(ValueError, "账号密码"):
            self.video.play("https://name:password@example.com/video")

    def test_decode_samples_without_window(self):
        engine = ROOT / "plugins/video/bin/mpv.exe"
        if not engine.is_file(): self.skipTest("local mpv engine not installed")
        samples = [
            ("video-test.h264", ["--demuxer-lavf-format=h264"]),
            ("video-test.mjpeg", ["--demuxer-lavf-format=mjpeg"]),
            ("video-test.ts", ["--demuxer-lavf-format=mpegts"]),
            ("video-test.yuv", ["--demuxer=rawvideo", "--demuxer-rawvideo-w=64", "--demuxer-rawvideo-h=48", "--demuxer-rawvideo-mp-format=yuv420p", "--demuxer-rawvideo-fps=5"]),
        ]
        if not all((ROOT / "build" / name).is_file() for name, _ in samples): self.skipTest("offline samples not generated")
        for name, options in samples:
            with self.subTest(name=name):
                p = subprocess.run([str(engine), "--no-config", "--vo=null", "--ao=null", "--frames=1", *options, str(ROOT / "build" / name)],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.assertEqual(p.returncode, 0, p.stdout.decode("utf-8", "replace"))

    @unittest.skipUnless(os.name == "nt", "Windows named pipes")
    def test_player_ipc_without_window(self):
        if not self.video.engine.is_file(): self.skipTest("local mpv engine not installed")
        self.video.pipe = r"\\.\pipe\eedp-test-" + uuid.uuid4().hex
        self.video.process = subprocess.Popen([str(self.video.engine), "--no-config", "--no-terminal", "--vo=null", "--ao=null", "--idle=yes", "--input-ipc-server=" + self.video.pipe],
                                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                              creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(30):
            try:
                self.video.volume(50)
                break
            except ValueError:
                time.sleep(.1)
        else: self.fail("player IPC did not become ready")
        self.assertTrue(self.video.pause()["paused"])

    @unittest.skipUnless(os.name == "nt", "Windows subprocess flags")
    def test_h264_udp_loopback_without_window(self):
        engine = self.video.engine
        ffmpeg = ROOT / "build/ffmpeg.exe"
        if not engine.is_file() or not ffmpeg.is_file(): self.skipTest("offline engines not installed")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        url = f"udp://127.0.0.1:{port}"
        receiver = subprocess.Popen([str(engine), "--no-config", "--vo=null", "--ao=null", "--frames=3", "--demuxer-lavf-format=h264", url],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        time.sleep(.3)
        sender = subprocess.Popen([str(ffmpeg), "-loglevel", "error", "-re", "-f", "lavfi", "-i", "testsrc2=size=64x48:rate=5", "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-g", "5", "-f", "h264", url],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            output, _ = receiver.communicate(timeout=20)
            self.assertEqual(receiver.returncode, 0, output.decode("utf-8", "replace"))
        finally:
            for process in (sender, receiver):
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
