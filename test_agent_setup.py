import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from agent_setup import configure


class AgentSetupTests(unittest.TestCase):
    def test_portable_packaged_setup_preserves_other_config_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"Nexus 空 格"
            home=Path(tmp)/"new-user"
            (root/"skills/use-agent-workbench").mkdir(parents=True)
            (root/"skills/use-agent-workbench/SKILL.md").write_text("test")
            (root/"EEDP-Agent.exe").touch()
            config=home/".codex/config.toml"
            config.parent.mkdir(parents=True)
            config.write_text('model="keep"\n[mcp_servers.other]\ncommand="keep.exe"\n[mcp_servers.agent-workbench]\ncommand="old.exe"\n[mcp_servers.agent-workbench.env]\nOLD="remove"\n',encoding="utf-8")
            for _ in range(2):configure(root,home)
            values=tomllib.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(values["model"],"keep")
            self.assertEqual(values["mcp_servers"]["other"]["command"],"keep.exe")
            server=values["mcp_servers"]["agent-workbench"]
            self.assertEqual(server["command"],str(root/"EEDP-Agent.exe"))
            self.assertEqual(server["args"],["mcp"])
            self.assertNotIn("env",server)
            self.assertEqual(len(list(config.parent.glob("*.pre-nexus-*"))),1)
            self.assertTrue((home/".agents/skills/use-agent-workbench/SKILL.md").exists())
            self.assertEqual(json.loads((home/".eedp-agent.json").read_text(encoding="utf-8"))["root"],str(root))

    def test_wsl_source_config_and_invalid_toml_no_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"checkout"
            home=Path(tmp)/"home"
            (root/"skills/use-agent-workbench").mkdir(parents=True)
            (root/"skills/use-agent-workbench/SKILL.md").write_text("test")
            (root/"run-workbench.py").touch()
            configure(root,home,wsl=True)
            server=tomllib.loads((home/".codex/config.toml").read_text())["mcp_servers"]["agent-workbench"]
            self.assertEqual(server["command"],"python3")
            self.assertEqual(server["args"],[str(root/"mcp-bridge.py")])
            (home/".codex/config.toml").write_text("invalid = [")
            pointer=(home/".eedp-agent.json").read_bytes()
            with self.assertRaises(tomllib.TOMLDecodeError):configure(root,home,wsl=True)
            self.assertEqual((home/".eedp-agent.json").read_bytes(),pointer)
