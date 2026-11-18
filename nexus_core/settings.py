"""Atomic, server-owned settings shared by all clients."""
import copy
import json
from pathlib import Path
import re
import threading


class Settings:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.values = {}
        if self.path.exists():
            self.values = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(self.values, dict): raise ValueError("Settings must be an object")

    def get(self, scope="ui"):
        with self.lock:
            return copy.deepcopy(self.values.get(scope, {}))

    def update(self, scope, values):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", scope) or not isinstance(values, dict):
            raise ValueError("Invalid settings scope or values")
        if len(json.dumps(values).encode()) > 100_000: raise ValueError("Settings too large")
        with self.lock:
            updated = {**self.values.get(scope, {}), **values}
            document = {**self.values, scope: updated}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
            self.values = document
            return copy.deepcopy(updated)
