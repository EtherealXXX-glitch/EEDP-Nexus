"""Compatibility entry point for existing source-mode Agent configurations."""
from pathlib import Path
import runpy
import sys

bridge = Path(__file__).resolve().parent / "agent_bridge"
sys.path.insert(0, str(bridge))
runpy.run_path(str(bridge / "mcp-bridge.py"), run_name="__main__")
