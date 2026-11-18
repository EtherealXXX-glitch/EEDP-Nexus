"""Hardware-free behavioral checks for the component boundary and task lifecycle."""
import base64
import hashlib
from pathlib import Path
import tempfile
import time
import subprocess
import sys
import unittest
from unittest.mock import patch

from core import Activity, Registry, Resources
from components.serial_monitor import SerialMonitor
from components.beken_flash import BekenFlash, OutputLines


class ComponentsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.activity = Activity(self.directory / "logs")
        self.resources = Resources()
        self.monitor = SerialMonitor(self.activity, self.resources)
        self.flash = BekenFlash(self.activity, self.resources)
        self.registry = Registry(self.activity, self.resources)
        self.registry.register(self.monitor)
        self.registry.register(self.flash)

    def tearDown(self):
        self.registry.close()
        for handler in self.activity.logger.handlers[:]:
            handler.close()
            self.activity.logger.removeHandler(handler)
        # Windows can briefly retain a finished child's working-directory handle.
        for attempt in range(20):
            try:
                self.temp.cleanup()
                break
            except PermissionError:
                if attempt == 19: raise
                time.sleep(.1)

    def eventually(self, predicate):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if predicate(): return
            time.sleep(0.02)
        self.fail("timed out waiting for component")

    def firmware(self):
        binary, engine = self.directory / "input.bin", self.directory / "bk_loader.exe"
        binary.write_bytes(b"\x01\x02" * 257)
        engine.write_bytes(b"fake engine, never executed")
        return dict(firmware=str(binary), engine=str(engine), port="COM14", address="0x0")

    def test_serial_loopback_text_and_hex_and_release(self):
        self.registry.invoke("serial.connect", dict(port="loop://", baudrate=1500000))
        self.registry.invoke("serial.send", dict(text="测试", newline="LF"))
        self.registry.invoke("serial.send", dict(text="00 ff 10", hex_mode=True))
        self.eventually(lambda: self.monitor.status()["rx_bytes"] == len("测试\n".encode()) + 3)
        data = b"".join(base64.b64decode(x["base64"]) for x in self.activity.read()["events"] if x["kind"] == "rx")
        self.assertEqual(data, "测试\n".encode() + b"\x00\xff\x10")
        self.monitor.disconnect()
        self.assertEqual(self.resources.status(), {})

    def test_serial_text_endings_and_hex_are_exact(self):
        self.monitor.connect(port="loop://")
        for ending in ("CRLF", "CR", "LF", "NONE"):
            self.monitor.send(text="X", newline=ending)
        self.monitor.send(text="41", hex_mode=True, newline="CRLF")
        expected = b"X\r\nX\rX\nXA"
        self.eventually(lambda: self.monitor.status()["rx_bytes"] == len(expected))
        data = b"".join(base64.b64decode(x["base64"]) for x in self.activity.read()["events"] if x["kind"] == "rx")
        self.assertEqual(data, expected)

    def test_incremental_decode(self):
        self.monitor.connect(port="loop://")
        self.monitor.send(text="e4", hex_mode=True)
        time.sleep(0.15)
        self.monitor.send(text="b8 ad", hex_mode=True)
        self.eventually(lambda: self.monitor.status()["rx_bytes"] == 3)
        text = "".join(x["text"] for x in self.activity.read()["events"] if x["kind"] == "rx")
        self.assertEqual(text, "中")

    def test_resource_conflict_does_not_disconnect_other_component(self):
        self.resources.acquire("COM14", "serial")
        with self.assertRaisesRegex(ValueError, "serial"):
            self.flash.start(**self.firmware())
        self.assertEqual(self.resources.status(), {"COM14": "serial"})

    def test_discovery_and_bad_arguments(self):
        tools = self.registry.describe()
        self.assertEqual({t["id"] for t in tools}, {"serial", "beken"})
        self.assertTrue(tools[1]["actions"]["start"]["destructive"])
        with self.assertRaises(ValueError):
            self.registry.invoke("serial.connect", dict(unexpected="x"))
        with self.assertRaises(ValueError):
            self.registry.invoke("nonexistent.start", {})

    def fake_process(self, success, exitcode=0):
        class FinishedProcess:
            returncode = exitcode
            def poll(self): return 0
        def launch(command, **kwargs):
            self.command = command
            kwargs["stdout"].write(b"Begin write to flash...\n" + (b"WriteFlash ->pass\nWriting Flash OK\n{All Finished Successfully}\n" if success else b"ERROR\n"))
            kwargs["stdout"].flush()
            return FinishedProcess()
        return launch

    def test_flash_snapshot_command_and_success(self):
        arguments = self.firmware()
        plan = self.flash.inspect(**arguments)
        self.assertEqual(plan["transfer_length"], 768)
        with patch("components.beken_flash.subprocess.Popen", side_effect=self.fake_process(True)):
            self.flash.start(**arguments)
            self.eventually(lambda: self.flash.status()["state"] != "running")
        self.assertEqual(self.flash.status()["state"], "succeeded")
        self.assertEqual(self.resources.status(), {})
        self.assertIn("firmware.bin@0x0-0x300", self.command[9])
        snapshot = Path(self.flash.status()["log"]).parent / "firmware.bin"
        self.assertEqual(hashlib.sha256(snapshot.read_bytes()).hexdigest(), plan["sha256"])

    def test_zero_exit_without_success_is_failure(self):
        with patch("components.beken_flash.subprocess.Popen", side_effect=self.fake_process(False)):
            self.flash.start(**self.firmware())
            self.eventually(lambda: self.flash.status()["state"] != "running")
        self.assertEqual(self.flash.status()["state"], "failed")
        self.assertEqual(self.resources.status(), {})

    def test_vendor_success_exitcode_one(self):
        with patch("components.beken_flash.subprocess.Popen", side_effect=self.fake_process(True, 1)):
            self.flash.start(**self.firmware())
            self.eventually(lambda: self.flash.status()["state"] != "running")
        self.assertEqual(self.flash.status()["state"], "succeeded")
        self.assertEqual(self.flash.status()["engine_exitcode"], 1)

    def test_actual_engine_progress_and_persistent_result(self):
        self.flash._output("Erasing Flash ... 79%")
        self.assertEqual(self.flash.status()["stage"], "擦除目标区域")
        self.assertEqual(self.flash.status()["phase_progress"], 79)
        self.flash._output("Writing Flash ... 31%")
        self.assertEqual(self.flash.status()["stage"], "写入固件")
        self.assertEqual(self.flash.status()["phase_progress"], 31)
        self.flash.job.update(state="succeeded", stage="烧录成功")
        self.flash._save_state()
        restored = BekenFlash(self.activity, self.resources)
        self.assertEqual(restored.status()["state"], "succeeded")

    def test_carriage_return_progress_is_processed_before_newline(self):
        splitter = OutputLines()
        first = splitter.feed(b"Writing Flash ... 0%\rWriting Flash ... 1%\rWriting Fla")
        self.assertEqual(first, ["Writing Flash ... 0%", "Writing Flash ... 1%"])
        for line in first: self.flash._output(line)
        self.assertEqual(self.flash.status()["phase_progress"], 1)
        second = splitter.feed(b"sh ... 2%\r\nWriting Flash ... 3%\r")
        self.assertEqual(second, ["Writing Flash ... 2%", "Writing Flash ... 3%"])
        for line in second: self.flash._output(line)
        self.assertEqual(self.flash.status()["phase_progress"], 3)
        self.assertEqual(splitter.feed(b"done", final=True), ["done"])

    def test_progress_arrives_while_child_process_is_still_running(self):
        actual_popen = subprocess.Popen
        script = ("import sys,time\n"
                  "for n in [0, 10, 20, 30]:\n"
                  " sys.stdout.write('Writing Flash ... %d%%\\r'%n);sys.stdout.flush();time.sleep(.25)\n"
                  "print('WriteFlash ->pass\\nWriting Flash OK\\nAll Finished Successfully');sys.exit(1)\n")
        def launch(command, **kwargs):
            return actual_popen([sys.executable, "-u", "-c", script], **kwargs)
        seen = []
        with patch("components.beken_flash.subprocess.Popen", side_effect=launch):
            self.flash.start(**self.firmware())
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = self.flash.status()
                if state["state"] != "running": break
                seen.append(state.get("phase_progress"))
                time.sleep(.03)
        self.assertTrue(any(x in (10, 20, 30) for x in seen), seen)
        self.assertEqual(self.flash.status()["state"], "succeeded")

    def test_events_cursor_does_not_repeat_filtered_events(self):
        self.activity.emit("serial", "rx", "a")
        self.activity.emit("beken", "output", "b")
        first = self.activity.read(component="serial")
        self.assertEqual(len(first["events"]), 1)
        self.assertEqual(self.activity.read(after=first["cursor"], component="serial")["events"], [])


if __name__ == "__main__":
    unittest.main()
