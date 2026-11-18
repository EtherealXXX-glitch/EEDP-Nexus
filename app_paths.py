"""Runtime paths shared by source and portable executable builds."""
import os
from pathlib import Path
import sys

FROZEN = bool(getattr(sys, "frozen", False))
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
RESOURCES = Path(getattr(sys, "_MEIPASS", ROOT))
STATE = Path(os.environ.get("EEDP_STATE_DIR", str(ROOT / ".state")))
APP_NAME = "EEDP Nexus"
GUI_EXE = "EEDP Nexus.exe"
CLI_EXE = "EEDP-Agent.exe"


def service_command():
    if FROZEN:
        return [str(ROOT / GUI_EXE), "serve"]
    executable = Path(sys.executable)
    pythonw = executable.with_name("pythonw.exe")
    return [str(pythonw if pythonw.exists() else executable), str(ROOT / "run-workbench.py"), "serve"]
