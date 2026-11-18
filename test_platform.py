import json
from pathlib import Path
import tempfile
import unittest
import threading
import time

from core import Activity, Registry, Resources
from settings import Settings
from plugin_manager import Plugins
from api import dispatch
from mcp_adapter import MCP
from plugins.serial.component import SerialMonitor


class PlatformTest(unittest.TestCase):
    def test_slow_component_does_not_block_other_components_or_allow_unload(self):
        entered,release=threading.Event(),threading.Event()
        probe=self.registry.components["probe"]
        original=probe.echo
        def slow(text=""):
            entered.set()
            release.wait(3)
            return original(text)
        probe.echo=slow
        self.registry.register(SerialMonitor(self.registry.activity,self.registry.resources))
        thread=threading.Thread(target=lambda:self.registry.invoke("probe.echo",{"text":"slow"}))
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            started=time.perf_counter()
            self.registry.invoke("serial.status",{})
            self.assertLess(time.perf_counter()-started,.2)
            with self.assertRaises(ValueError):self.plugins.set_enabled("probe",False)
        finally:
            release.set()
            thread.join(3)
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        plugin = self.root / "plugins/probe"
        plugin.mkdir(parents=True)
        (plugin / "plugin.json").write_text(json.dumps(dict(api_version=1,id="probe",name="Probe",version="1.0.0",entrypoint="entry.py:Probe")),encoding="utf-8")
        (plugin / "entry.py").write_text('''from core import field
class Probe:
    id="probe"
    name="Probe"
    description="Test capability"
    actions={"echo":{"label":"Echo","fields":[field("text","Text","")]}}
    def __init__(self,activity,resources): pass
    def echo(self,text=""): return {"text":text}
    def status(self): return {"state":"idle"}
    def close(self): pass
''',encoding="utf-8")
        self.open()

    def open(self):
        self.registry = Registry(Activity(self.root / "logs"), Resources(), Settings(self.root / "settings.json"))
        self.plugins = Plugins(self.root / "plugins", self.registry)
        self.plugins.rescan()

    def tearDown(self):
        self.registry.close()
        self.temp.cleanup()

    def test_plugin_lifecycle_is_discoverable_and_persistent(self):
        self.assertEqual(self.registry.describe()[0]["id"], "probe")
        self.plugins.set_enabled("probe", False)
        self.assertEqual(self.registry.describe(), [])
        self.registry.close()
        self.open()
        self.assertFalse(self.plugins.list()[0]["enabled"])
        self.plugins.set_enabled("probe", True)
        self.assertEqual(self.registry.invoke("probe.echo", {"text":"works"}), {"text":"works"})

    def test_active_plugin_cannot_be_disabled(self):
        self.registry.resources.acquire("COM99", "probe")
        with self.assertRaises(ValueError): self.plugins.set_enabled("probe", False)
        self.assertTrue(self.plugins.list()[0]["enabled"])
        self.registry.resources.release("COM99", "probe")

    def test_removing_idle_plugin_needs_no_core_changes(self):
        (self.root / "plugins/probe").rename(self.root / "removed-probe")
        self.plugins.rescan()
        self.assertEqual(self.plugins.list(), [])
        self.assertEqual(self.registry.describe(), [])

    def test_settings_and_history_survive_restart(self):
        dispatch(self.registry,"settings.update",dict(scope="ui",values={"geometry":"1280x800"}),"windows-test")
        self.registry.invoke("probe.echo", {"text":"shared"}, client="wsl-test")
        first = self.registry.activity.read()
        cursor = first["cursor"]
        self.registry.close()
        self.open()
        self.assertEqual(dispatch(self.registry,"settings.get"),{"geometry":"1280x800"})
        history = self.registry.activity.read()["events"]
        self.assertTrue(any(x.get("client")=="wsl-test" for x in history))
        new = self.registry.activity.emit("probe", "rx", "after restart")
        self.assertGreater(new["id"], cursor)
        self.assertEqual(self.registry.activity.read(after=cursor)["events"][-1]["text"], "after restart")

    def test_component_preferences_do_not_auto_connect(self):
        self.registry.register(SerialMonitor(self.registry.activity, self.registry.resources))
        self.registry.invoke("serial.connect", dict(port="loop://", baudrate=921600))
        self.registry.invoke("serial.disconnect", {})
        self.registry.close()
        self.open()
        component = SerialMonitor(self.registry.activity, self.registry.resources)
        self.registry.register(component)
        self.assertFalse(component.status()["connected"])
        tool = next(x for x in self.registry.describe() if x["id"]=="serial")
        baud = next(x for x in tool["actions"]["connect"]["fields"] if x["name"]=="baudrate")
        self.assertEqual(baud["default"],921600)

    def test_custom_baudrates_are_not_restricted_to_presets(self):
        from desktop import SERIAL_BAUDRATES
        self.assertEqual(len(SERIAL_BAUDRATES),35)
        self.assertEqual(tuple(sorted(set(SERIAL_BAUDRATES))),SERIAL_BAUDRATES)
        self.assertIn(96000,SERIAL_BAUDRATES)
        component=SerialMonitor(self.registry.activity,self.registry.resources)
        try:
            for baud in (110,96000,123457):
                result=component.connect(port="loop://",baudrate=baud)
                self.assertEqual(result["baudrate"],baud)
                component.disconnect()
        finally:component.close()

    def test_mcp_schema_call_and_disabled_tool_removal(self):
        server = MCP(lambda method,args=None:dispatch(self.registry,method,args,"mcp-test"))
        def send(method,params=None):return server.handle(dict(jsonrpc="2.0",id=1,method=method,params=params or {}))
        self.assertEqual(send("initialize",{"protocolVersion":"2025-11-25"})["result"]["protocolVersion"],"2025-11-25")
        tool = next(x for x in send("tools/list")["result"]["tools"] if x["name"]=="probe__echo")
        self.assertEqual(tool["inputSchema"]["properties"]["text"]["type"],"string")
        answer = send("tools/call",{"name":"probe__echo","arguments":{"text":"shared"}})
        self.assertEqual(answer["result"]["structuredContent"],{"text":"shared"})
        send("tools/call",{"name":"workbench_set_plugin","arguments":{"id":"probe","enabled":False}})
        self.assertNotIn("probe__echo",[x["name"] for x in send("tools/list")["result"]["tools"]])
        self.assertIn("error",send("tools/call",{"name":"probe__echo"}))


if __name__ == "__main__": unittest.main()
