#!/usr/bin/env python3
"""Call the Windows workbench from either Windows Python or WSL Python."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

def windows_path(value):
    if os.name == "nt" or not value.startswith("/"):
        return value
    return subprocess.check_output(["wslpath", "-w", value], text=True).strip()


def installation_root(is_windows):
    def local(value):
        if not is_windows and len(value) > 1 and value[1] == ":":
            value = subprocess.check_output(["wslpath", "-u", value], text=True).strip()
        return Path(value)
    override = os.environ.get("AGENT_WORKBENCH_ROOT")
    if override: return local(override)
    pointers = [Path.home() / ".eedp-agent.json"]
    if not is_windows:
        try:
            profile=subprocess.check_output(["powershell.exe","-NoProfile","-Command","$env:USERPROFILE"],text=True,timeout=10).strip()
            pointers.append(local(profile)/".eedp-agent.json")
        except (OSError,subprocess.SubprocessError):pass
    for pointer in pointers:
        if pointer.is_file():
            candidate = local(json.loads(pointer.read_text(encoding="utf-8-sig"))["root"])
            if (candidate / "EEDP-Agent.exe").is_file() or (candidate/"run-workbench.py").is_file(): return candidate
    adjacent = Path(__file__).resolve().parents[3]
    if (adjacent / "EEDP-Agent.exe").is_file() or (adjacent/"run-workbench.py").is_file(): return adjacent
    raise RuntimeError("EEDP Nexus is not registered. Run install-agent.cmd on Windows (add -Wsl for WSL), or set AGENT_WORKBENCH_ROOT.")


def main():
    arguments = sys.argv[1:] or ["status"]
    is_windows = os.name == "nt"
    if not is_windows and not shutil.which("wslpath"):
        raise RuntimeError("This helper supports Windows and WSL, not a separate Linux host")
    root = installation_root(is_windows)
    executable = root / "EEDP-Agent.exe"
    packaged = executable.is_file()
    if not packaged: executable = root / ".venv/Scripts/python.exe"
    entry = root / "run-workbench.py"
    if not executable.is_file() or (not packaged and not entry.is_file()):
        raise RuntimeError(f"Workbench installation not found at {root}; set AGENT_WORKBENCH_ROOT to its local path")
    temporary = None
    staged = None
    try:
        if arguments[0] == "call":
            payload = None
            for option in ("--args-file", "--args"):
                if option in arguments:
                    index = arguments.index(option)
                    if index + 1 >= len(arguments):
                        raise ValueError(f"{option} requires a value")
                    value = arguments[index + 1]
                    payload = json.loads(Path(value).read_text(encoding="utf-8-sig") if option == "--args-file" else value)
                    arguments = arguments[:index] + arguments[index + 2:]
                    break
            if payload is not None:
                if not isinstance(payload, dict):
                    raise ValueError("Arguments must be a JSON object")
                directory = root / ".state/requests"
                directory.mkdir(parents=True, exist_ok=True)
                for key in ("firmware", "engine", "input"):
                    if key in payload:
                        original = payload[key]
                        converted = windows_path(original)
                        if not is_windows and original.startswith("/") and converted.startswith("\\\\"):
                            if key == "engine":
                                raise ValueError("The Windows loader engine must be on a Windows drive, e.g. /mnt/c/...")
                            source = Path(original)
                            before = source.stat()
                            staged = tempfile.TemporaryDirectory(prefix="firmware-", dir=directory)
                            target = Path(staged.name) / source.name
                            shutil.copyfile(source, target)
                            after = source.stat()
                            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                                raise ValueError("Input file changed while being staged; retry after it is complete")
                            converted = windows_path(str(target))
                        payload[key] = converted
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", dir=directory, delete=False) as stream:
                    json.dump(payload, stream, ensure_ascii=False)
                    temporary = Path(stream.name)
                arguments += ["--args-file", windows_path(str(temporary))]
        arguments += ["--client", "windows-skill" if is_windows else "wsl-skill"]
        # WSL's Windows-interop relay must not consume the caller's script stdin.
        prefix = [str(executable)] if packaged else [str(executable), windows_path(str(entry))]
        process = subprocess.Popen([*prefix, *arguments], stdin=subprocess.DEVNULL)
        try:
            return process.wait()
        except KeyboardInterrupt:
            process.terminate()
            process.wait()
            return 130
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
        if staged:
            staged.cleanup()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"workbench-client: {exc}", file=sys.stderr)
        sys.exit(1)
