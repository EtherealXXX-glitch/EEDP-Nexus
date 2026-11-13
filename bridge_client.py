"""Portable client: WSL uses Windows interop, never a second hardware daemon."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
if ROOT.name == "agent_bridge": ROOT = ROOT.parent


def windows_path(value):
    if os.name == "nt" or not value.startswith("/"): return value
    return subprocess.check_output(["wslpath", "-w", value], text=True).strip()


@contextlib.contextmanager
def prepared_arguments(method, arguments):
    arguments = json.loads(json.dumps(arguments or {}))
    staged = None
    try:
        if os.name != "nt" and method == "call" and arguments.get("target", "").startswith(("beken.","slogic.")):
            payload = arguments.setdefault("arguments", {})
            for key in ("firmware", "engine", "input"):
                original = payload.get(key)
                if not isinstance(original, str) or not original.startswith("/"): continue
                converted = windows_path(original)
                if converted.startswith("\\\\"):
                    if key == "engine": raise ValueError("Vendor engine must be on a Windows drive")
                    directory = ROOT / ".state/requests"
                    directory.mkdir(parents=True, exist_ok=True)
                    staged = tempfile.TemporaryDirectory(prefix="firmware-", dir=directory)
                    source = Path(original)
                    before = source.stat()
                    target = Path(staged.name) / source.name
                    shutil.copyfile(source, target)
                    after = source.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise ValueError("Input file changed during handoff")
                    converted = windows_path(str(target))
                payload[key] = converted
        yield arguments
    finally:
        if staged: staged.cleanup()


class Client:
    def __init__(self, name="agent"):
        self.name = name
        self.runtime = None
        if os.name == "nt" and not (ROOT / "EEDP-Agent.exe").exists():
            spec = importlib.util.spec_from_file_location("workbench_client_runtime", ROOT / "run-workbench.py")
            self.runtime = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.runtime)

    def request(self, method, arguments=None):
        with prepared_arguments(method, arguments) as params:
            if self.runtime:
                self.runtime.ensure_started()
                return self.runtime.request(method, params, client=self.name)
            if os.name != "nt" and not shutil.which("wslpath"): raise ValueError("This bridge requires WSL Windows interop")
            directory = ROOT / ".state/requests"
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, suffix=".json", delete=False) as stream:
                json.dump(params, stream, ensure_ascii=False)
                temporary = Path(stream.name)
            try:
                env = {**os.environ, "AGENT_WORKBENCH_CLIENT": self.name}
                executable = ROOT / "EEDP-Agent.exe"
                prefix = [str(executable)] if executable.exists() else [str(ROOT / ".venv/Scripts/python.exe"), windows_path(str(ROOT / "run-workbench.py"))]
                response = subprocess.run([*prefix, "rpc", method, "--args-file", windows_path(str(temporary)), "--client", self.name],
                    stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", env=env, timeout=20)
                if response.returncode: raise RuntimeError(response.stderr.strip() or response.stdout.strip())
                return json.loads(response.stdout)
            finally:
                temporary.unlink(missing_ok=True)
