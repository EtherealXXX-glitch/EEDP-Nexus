import json
from pathlib import Path
import tempfile
import time
import sys
import unittest
from unittest.mock import patch
import zipfile

from core import Activity, Resources
from plugins.slogic.component import SLogic, DRIVER


class SLogicTest(unittest.TestCase):
    def setUp(self):
        directory=Path(__file__).parent/"build/test-artifacts"
        directory.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=directory)
        self.root=Path(self.temp.name)
        self.activity=Activity(self.root/"logs")
        self.resources=Resources()
        self.component=SLogic(self.activity,self.resources)

    def tearDown(self):
        self.component.close()
        self.activity.close()
        self.temp.cleanup()

    def fixture(self):
        target=self.root/"fixture.sr"
        metadata="[global]\nsigrok version=0.6.0\n[device 1]\nsamplerate=1 MHz\nunitsize=1\nprobe1=D0\nprobe2=D1\n"
        with zipfile.ZipFile(target,"w") as archive:
            archive.writestr("metadata",metadata)
            archive.writestr("version","2")
            archive.writestr("logic-1-1",bytes([0,0,1,1,2,2]))
            archive.writestr("logic-1-2",bytes([3,3,0,0]))
        return target

    def test_waveform_windows_across_chunks_are_exact_and_offline(self):
        path=self.fixture()
        with patch.object(self.component,"_run_query",side_effect=AssertionError("USB/CLI must not be used")):
            result=self.component.waveform(str(path),start_sample=4,sample_count=5,pixels=64)
        self.assertEqual(result["total_samples"],10)
        self.assertTrue(result["exact"])
        self.assertEqual(result["channels"][0]["ranges"],[[0,0],[0,0],[1,1],[1,1],[0,0]])
        self.assertEqual(result["channels"][1]["ranges"],[[1,1],[1,1],[1,1],[1,1],[0,0]])

    def test_dense_overview_keeps_activity_instead_of_skipping_edges(self):
        path=self.fixture()
        with zipfile.ZipFile(path,"a") as archive: archive.writestr("logic-1-3",bytes([0,1])*1000)
        result=self.component.waveform(str(path),pixels=64)
        self.assertFalse(result["exact"])
        self.assertTrue(any(x==[0,1] for x in result["channels"][0]["ranges"]))
        self.assertLessEqual(len(result["channels"][0]["ranges"]),64)

    def test_inspect_is_bounded_and_never_spawns_capture(self):
        with patch.object(self.component,"devices",return_value={"devices":[{"spec":DRIVER}]}), patch.object(
            self.component,"capabilities",return_value={"channels":["D0"],"samplerates":[10000000]}), patch.object(
            self.component,"_spawn",side_effect=AssertionError("must not capture")):
            result=self.component.inspect()
            self.assertIn("--time",result["args"])
            self.assertNotIn("--continuous",result["args"])
            with self.assertRaises(ValueError): self.component.inspect(duration_ms=0)
            with self.assertRaises(ValueError): self.component.inspect(channels="D8")
            with self.assertRaises(ValueError): self.component.inspect(trigger="D1=r")
            with self.assertRaises(ValueError): self.component.inspect(timeout_s=1)

    def test_decode_requires_explicit_channel_mapping(self):
        with self.assertRaises(ValueError): self.component.decode(input=str(self.fixture()),decoder="uart:baudrate=115200")

    def test_start_requires_fresh_voltage_and_ground_confirmation(self):
        with patch.object(self.component,"inspect",side_effect=AssertionError("must reject before opening USB")):
            with self.assertRaises(ValueError):self.component.start()
            with self.assertRaises(ValueError):self.component.start(signal_voltage=5,common_ground=True)
            with self.assertRaises(ValueError):self.component.start(signal_voltage=3.3,common_ground=False)

    def test_cancellation_stops_owned_process_and_releases_resource(self):
        script=self.root/"sleep.py"
        script.write_text("import time\ntime.sleep(30)\n")
        plan=dict(kind="capture",args=[],timeout_s=20)
        with patch.object(self.component,"_command",return_value=[sys.executable,str(script)]):
            self.component._spawn(plan,"capture.sr",hardware=True)
            self.assertEqual(self.resources.status(),{"USB:SLOGIC":"slogic"})
            self.component.cancel()
            self.component.worker.join(10)
        self.assertEqual(self.component.status()["state"],"cancelled")
        self.assertEqual(self.resources.status(),{})
        self.assertTrue(Path(self.component.status()["log"]).exists())


if __name__=="__main__": unittest.main()
