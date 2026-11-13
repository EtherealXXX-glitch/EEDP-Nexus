"""Component contracts, resource ownership, and persistent activity records."""
from __future__ import annotations

import base64
from collections import deque
from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import threading
import copy
import sqlite3
import uuid
from log_store import LogStore, archive_rows


class ArchivedRotatingHandler(RotatingFileHandler):
    def doRollover(self):
        oldest = Path(self.baseFilename + "." + str(self.backupCount))
        if oldest.exists():
            destination = oldest.parent / "archives/text"
            destination.mkdir(parents=True, exist_ok=True)
            oldest.rename(destination / (datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8] + ".jsonl"))
        super().doRollover()


class Resources:
    def __init__(self):
        self.lock = threading.RLock()
        self.owners = {}

    def acquire(self, resource, owner):
        resource = resource.upper()
        with self.lock:
            if resource in self.owners:
                raise ValueError(f"{resource} 正由 {self.owners[resource]} 占用，请先释放")
            self.owners[resource] = owner

    def release(self, resource, owner):
        with self.lock:
            key = resource.upper()
            if self.owners.get(key) == owner:
                del self.owners[key]

    def status(self):
        with self.lock:
            return dict(self.owners)


class Activity:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.lock = threading.RLock()
        self.items = deque(maxlen=4000)
        self.sequence = 0
        self.session = uuid.uuid4().hex
        self.database = sqlite3.connect(directory / "activity.sqlite3", check_same_thread=False)
        self.database.execute("PRAGMA journal_mode=WAL")
        self.database.execute("PRAGMA synchronous=NORMAL")
        self.database.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, component TEXT, payload TEXT)")
        self.database.execute("CREATE INDEX IF NOT EXISTS events_component ON events(component,id)")
        self.sequence = self.database.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]
        previous = self.database.execute("SELECT seq FROM sqlite_sequence WHERE name='events'").fetchone()
        if previous: self.sequence = max(self.sequence, previous[0])
        legacy = directory / "activity.jsonl"
        if not self.sequence and legacy.exists():
            for line in legacy.read_text(encoding="utf-8").splitlines():
                try:
                    item = json.loads(line)
                    if not all(k in item for k in ("component", "kind", "time", "text")): continue
                    self.sequence += 1
                    item["id"] = self.sequence
                    item.setdefault("session", "legacy")
                    self.database.execute("INSERT INTO events(id,component,payload) VALUES(?,?,?)",
                        (self.sequence, item["component"], json.dumps(item, ensure_ascii=False)))
                except (ValueError, TypeError): continue
        self.database.commit()
        self.logger = logging.getLogger(f"activity.{id(self)}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        handler = ArchivedRotatingHandler(directory / "activity.jsonl", maxBytes=10_000_000,
                                      backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(handler)

    def emit(self, component, kind, text="", data=None, client=None):
        with self.lock:
            self.sequence += 1
            item = dict(id=self.sequence, time=datetime.now().astimezone().isoformat(timespec="milliseconds"),
                        component=component, kind=kind, text=text)
            item["session"] = self.session
            if client: item["client"] = client
            if data is not None:
                item["base64"] = base64.b64encode(data).decode("ascii")
            self.items.append(item)
            self.database.execute("INSERT INTO events(id,component,payload) VALUES(?,?,?)",
                                  (self.sequence, component, json.dumps(item, ensure_ascii=False)))
            if self.sequence % 1000 == 0:
                archive_rows(self, "id <= ?", [self.sequence - 100_000])
            self.database.commit()
            self.logger.info(json.dumps(item, ensure_ascii=False))
            return item

    def read(self, after=0, component="", limit=300):
        with self.lock:
            reset = int(after) > self.sequence
            after = 0 if reset else max(0, int(after))
            minimum = self.database.execute("SELECT MIN(id) FROM events").fetchone()[0]
            query, params = "SELECT payload FROM events WHERE id > ?", [after]
            if component:
                query += " AND component = ?"
                params.append(component)
            query += " ORDER BY id LIMIT ?"
            params.append(max(1, min(int(limit), 1000)))
            page = [json.loads(row[0]) for row in self.database.execute(query, params)]
            return dict(events=page, cursor=page[-1]["id"] if page else max(after, self.sequence),
                        dropped=bool(minimum and after and after < minimum - 1), reset=reset,
                        session=self.session)

    def close(self):
        with self.lock:
            self.database.close()
            for handler in self.logger.handlers[:]:
                handler.close()
                self.logger.removeHandler(handler)


def field(name, label, default="", choices=None, kind="str", remember=True):
    value = dict(name=name, label=label, default=default, type=kind)
    if choices:
        value["choices"] = choices
    if not remember: value["remember"] = False
    return value


class Registry:
    """Transport and GUI see this contract; components do not depend on each other."""
    def __init__(self, activity, resources, settings=None):
        self.activity, self.resources = activity, resources
        self.components = {}
        self.settings = settings
        self.lock = threading.RLock()
        self.plugin_manager = None
        self.call_locks = {}
        self.in_flight = {}
        self.closing = False
        self.logs = LogStore(activity, settings,
            lambda: [c.status().get("id") for c in self.components.values() if c.status().get("id")],
            lambda: [c.status().get("id") for c in self.components.values() if c.status().get("state")=="running" and c.status().get("id")])

    def register(self, component):
        self.components[component.id] = component
        self.call_locks[component.id] = threading.RLock()
        self.in_flight[component.id] = 0

    def describe(self):
        with self.lock:
            result = []
            for component in self.components.values():
                actions = copy.deepcopy(component.actions)
                saved = self.settings.get("component." + component.id) if self.settings else {}
                for name, schema in actions.items():
                    for parameter in schema.get("fields", []):
                        parameter["default"] = saved.get(name, {}).get(parameter["name"], parameter["default"])
                result.append(dict(id=component.id, name=component.name, description=component.description, actions=actions,
                                   ui=getattr(component,"ui",{"view":"generic"}),version=getattr(component,"plugin_version","unknown")))
            return result

    def invoke(self, target, arguments, client=None):
        identifier = target.partition(".")[0]
        with self.lock:
            if self.closing: raise ValueError("后台服务正在关闭")
            if identifier not in self.components: raise ValueError("未知组件："+identifier)
            call_lock = self.call_locks[identifier]
            self.in_flight[identifier] += 1
        try:
            with call_lock: return self._invoke(target, arguments, client)
        finally:
            with self.lock: self.in_flight[identifier] -= 1

    def _invoke(self, target, arguments, client):
        component_id, _, action = target.partition(".")
        component = self.components.get(component_id)
        if component is None or action not in component.actions:
            raise ValueError(f"未知动作：{target}")
        allowed = {x["name"] for x in component.actions[action].get("fields", [])}
        if set(arguments) - allowed:
            raise ValueError(f"未知参数：{sorted(set(arguments) - allowed)}")
        arguments = dict(arguments)
        saved = self.settings.get("component." + component_id).get(action, {}) if self.settings else {}
        for parameter in component.actions[action].get("fields", []):
            name = parameter["name"]
            value = arguments.get(name, saved.get(name, parameter["default"]))
            kind = parameter["type"]
            if kind == "bool" and not isinstance(value, bool):
                raise ValueError(f"{name} 必须是 JSON 布尔值")
            if kind == "str" and not isinstance(value, str):
                raise ValueError(f"{name} 必须是字符串")
            if kind in ("int", "float"):
                if isinstance(value, bool): raise ValueError(f"{name} 必须是数字")
                if kind == "int" and float(value) != int(value): raise ValueError(f"{name} 必须是整数")
                value = int(value) if kind == "int" else float(value)
            if "choices" in parameter and value not in parameter["choices"]:
                raise ValueError(f"{name} 的取值不在允许范围内")
            arguments[name] = value
        self.activity.emit(component_id, "call", f"调用 {target}", client=client)
        try:
            result = getattr(component, action)(**arguments)
            if self.settings and arguments:
                ephemeral = {p["name"] for p in component.actions[action].get("fields", []) if not p.get("remember", True)}
                remembered = {k: v for k, v in arguments.items() if k != "text" and k not in ephemeral and
                              not (isinstance(v, str) and ".state" in v and "requests" in v)}
                self.settings.update("component." + component_id, {action: remembered})
            text = json.dumps(result, ensure_ascii=False)
            if component.actions[action].get("log_result") == "summary" and len(text)>8192:
                text = text[:8192]+"…（视窗结果摘要，完整数据保存在原始波形中）"
            self.activity.emit(component_id, "result", f"{target}: {text}", client=client)
            return result
        except Exception as exc:
            self.activity.emit(component_id, "error", f"{target}: {exc}", client=client)
            raise

    def close(self):
        self.closing = True
        for component in self.components.values():
            component.close()
        self.activity.close()
