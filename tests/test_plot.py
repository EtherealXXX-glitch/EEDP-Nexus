import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/"plugins/plot/component.py"
spec=importlib.util.spec_from_file_location("plot_component",path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PlotTest(unittest.TestCase):
    def test_fragmented_lines_and_unrelated_logs(self):
        plot=module.Plot(None,None)
        plot.feed("ordinary log\n@plot voltage=3.")
        result=plot.feed("3,temp=-2\r\n@plot x=nan\n@plot x=4\n")
        self.assertEqual(result["accepted"],2)
        self.assertEqual(result["rejected"],1)
        self.assertEqual(plot.samples()["points"][0]["values"],{"voltage":3.3,"temp":-2.0})
    def test_limits_and_stream_reset(self):
        plot=module.Plot(None,None)
        plot.feed("@plot x=99")
        plot.feed("@plot y=2\n",reset_stream=True)
        self.assertEqual(plot.samples()["points"][-1]["values"],{"y":2.0})
        for _ in range(11):plot.feed("@plot x=1\n"*500)
        self.assertEqual(plot.status()["points"],5000)
        with self.assertRaises(ValueError):plot.samples(5001)
        self.assertEqual(plot.clear()["points"],0)
    def test_invalid_and_nonfinite_values(self):
        for line in ("@plot 1name=2","@plot x=inf","@plot x=1,x=2","@plot x=bad"):
            with self.assertRaises(ValueError):module.parse_line(line)
        self.assertIsNone(module.parse_line("system booted"))

    def test_channel_limit_applies_across_lines(self):
        plot=module.Plot(None,None)
        for index in range(16):plot.feed(f"@plot ch{index}=1\n")
        self.assertEqual(plot.feed("@plot extra=2\n")["accepted"],0)
        plot.clear()
        self.assertEqual(plot.feed("@plot extra=2\n")["accepted"],1)

    def test_sample_result_does_not_duplicate_data_in_activity_log(self):
        import tempfile
        from core import Activity,Registry,Resources
        from nexus_core.settings import Settings
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            activity=Activity(root/"logs")
            registry=Registry(activity,Resources(),Settings(root/"settings.json"))
            registry.register(module.Plot(activity,registry.resources))
            try:
                registry.invoke("plot.feed",{"text":"@plot distinctive=12345\n"})
                result=registry.invoke("plot.samples",{"limit":50})
                self.assertEqual(result["points"][0]["values"]["distinctive"],12345)
                logged=activity.read(component="plot")["events"][-1]["text"]
                self.assertNotIn("distinctive",logged)
                self.assertIn("已返回数据",logged)
            finally:registry.close()
