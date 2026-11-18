"""Shared history queries, consistent exports and conservative retention."""
from datetime import datetime, timedelta
import gzip
import json
from pathlib import Path
import threading
import time
import uuid
import zipfile
import shutil

DEFAULT_POLICY = dict(history_days=30, archive_days=90, max_mb=512,
                      protect_history=True, protect_firmware=True)


def archive_rows(activity, where, parameters):
    """Called under the activity lock: commit archive before removing indexed rows."""
    count = activity.database.execute("SELECT COUNT(*) FROM events WHERE " + where, parameters).fetchone()[0]
    if not count: return 0
    directory = activity.directory / "archives/events"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8] + ".jsonl.gz")
    temporary = target.with_suffix(".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as stream:
        for row in activity.database.execute("SELECT payload FROM events WHERE " + where + " ORDER BY id", parameters):
            stream.write(row[0] + "\n")
    temporary.replace(target)
    activity.database.execute("DELETE FROM events WHERE " + where, parameters)
    return count


def diagnostic_path(state, name):
    directory = Path(state) / "logs/diagnostics"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    if path.exists() and path.stat().st_size > 10_000_000:
        archive = Path(state) / "logs/archives/diagnostics"
        archive.mkdir(parents=True, exist_ok=True)
        path.rename(archive / (datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6] + "-" + name))
    return path


class LogStore:
    def __init__(self, activity, settings, active_jobs=lambda: [], running_jobs=None):
        self.activity, self.settings, self.active_jobs = activity, settings, active_jobs
        self.running_jobs = running_jobs or active_jobs
        self.directory = activity.directory
        self.lock = threading.RLock()

    def policy(self):
        return {**DEFAULT_POLICY, **(self.settings.get("logs") if self.settings else {})}

    def set_policy(self, **values):
        if set(values) - set(DEFAULT_POLICY): raise ValueError("未知日志策略")
        for key, value in values.items():
            if key.startswith("protect_"):
                if not isinstance(value, bool): raise ValueError("保护选项必须为布尔值")
            elif type(value) is not int or not 1 <= value <= 36500:
                raise ValueError("保留天数及容量必须为 1 至 36500 的整数")
        self.settings.update("logs", values)
        return self.policy()

    @staticmethod
    def filters(component="", kind="", client="", start="", end="", before=0):
        if start and end and start > end: raise ValueError("开始日期不能晚于结束日期")
        clauses, parameters = ["1=1"], []
        for key, value in (("component", component), ("kind", kind), ("client", client)):
            if value:
                clauses.append(f"json_extract(payload, '$.{key}') = ?")
                parameters.append(value)
        for key, value, operator in (("start", start, ">="), ("end", end, "<")):
            if value:
                date = datetime.strptime(value, "%Y-%m-%d")
                if key == "end": date += timedelta(days=1)
                clauses.append(f"json_extract(payload, '$.time') {operator} ?")
                parameters.append(date.strftime("%Y-%m-%d"))
        if before:
            clauses.append("id < ?")
            parameters.append(int(before))
        return " AND ".join(clauses), parameters

    def query(self, limit=200, **filters):
        where, parameters = self.filters(**filters)
        with self.activity.lock:
            rows = list(self.activity.database.execute("SELECT payload FROM events WHERE " + where + " ORDER BY id DESC LIMIT ?",
                        [*parameters, max(1, min(int(limit), 1000)) + 1]))
        maximum = max(1, min(int(limit), 1000))
        items = [json.loads(row[0]) for row in rows[:maximum]]
        return dict(events=items, next_before=items[-1]["id"] if len(rows) > maximum else None,
                    scope="online", policy=self.policy())

    def inventory(self):
        with self.lock:
            return self._inventory()

    def _inventory(self):
        categories = {name: dict(bytes=0, files=0) for name in ("events", "flash", "slogic", "diagnostics", "archives", "exports", "other")}
        for path in self.directory.rglob("*"):
            if not path.is_file() or path.is_symlink(): continue
            part = path.relative_to(self.directory).parts[0]
            category = (part if part in categories else "flash" if part.startswith("flash-") else
                        "events" if part.startswith("activity.") else "other")
            try:
                categories[category]["bytes"] += path.stat().st_size
                categories[category]["files"] += 1
            except FileNotFoundError: pass
        total = sum(x["bytes"] for x in categories.values())
        policy = self.policy()
        with self.activity.lock:
            count, first, last = self.activity.database.execute(
                "SELECT COUNT(*), MIN(json_extract(payload,'$.time')), MAX(json_extract(payload,'$.time')) FROM events").fetchone()
        return dict(directory=str(self.directory), categories=categories, bytes=total, events=count,
                    first=first, last=last, policy=policy, over_limit=total > policy["max_mb"] * 1024**2,
                    note="受保护历史、固件、导出包及运行中任务不自动删除；容量上限可能因此无法达到。")

    def export(self, filters=None, include_firmware=False, destination=""):
        with self.lock:
            result = self._export(filters, include_firmware)
            if destination:
                target = Path(destination).resolve()
                if target.suffix.lower() != ".zip": raise ValueError("导出目标须为 .zip 文件")
                if target != Path(result["path"]).resolve(): shutil.copy2(result["path"], target)
                result["destination"] = str(target)
            return result

    def _export(self, filters=None, include_firmware=False):
        if not isinstance(include_firmware, bool): raise ValueError("include_firmware 必须为布尔值")
        where, parameters = self.filters(**(filters or {}))
        directory = self.directory / "exports"
        directory.mkdir(exist_ok=True)
        target = directory / ("nexus-logs-" + datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6] + ".zip")
        temporary = target.with_suffix(".tmp")
        # A separate read transaction gives a consistent export without blocking RX writes.
        import sqlite3
        database = sqlite3.connect(self.directory / "activity.sqlite3")
        count = 0
        try:
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
                with archive.open("events.jsonl", "w") as stream:
                    for row in database.execute("SELECT payload FROM events WHERE " + where + " ORDER BY id", parameters):
                        stream.write((row[0] + "\n").encode("utf-8"))
                        count += 1
                archive.writestr("manifest.json", json.dumps(dict(format_version=1, app="EEDP Nexus",
                    created=datetime.now().astimezone().isoformat(), filters=filters or {}, events=count,
                    scope="online events filtered; diagnostics and completed flash artifacts unfiltered",
                    include_firmware=include_firmware), ensure_ascii=False, indent=2))
                active = set(self.running_jobs())
                for path in self.directory.rglob("*"):
                    if not path.is_file() or path.is_symlink(): continue
                    relative = path.relative_to(self.directory)
                    first = relative.parts[0]
                    if first in active or (first == "slogic" and len(relative.parts)>1 and relative.parts[1] in active): continue
                    selected = first in ("diagnostics", "slogic") or first.startswith("flash-") or first == "last-flash.json" or relative.parts[:2] in (("archives", "flash"),("archives","slogic"))
                    if selected and (include_firmware or path.name != "firmware.bin"):
                        archive.write(path, str(Path("artifacts") / relative))
            temporary.replace(target)
        finally:
            database.close()
            temporary.unlink(missing_ok=True)
        return dict(path=str(target), bytes=target.stat().st_size, events=count)

    def maintain(self):
        with self.lock:
            policy = self.policy()
            cutoff = (datetime.now().astimezone() - timedelta(days=policy["history_days"])).isoformat()
            with self.activity.lock:
                archived = archive_rows(self.activity, "json_extract(payload,'$.time') < ?", [cutoff])
                self.activity.database.commit()
                self.activity.database.execute("PRAGMA wal_checkpoint(PASSIVE)")
            # Archive completed flash jobs once they leave the online retention window.
            active = set(self.active_jobs())
            archived_jobs = 0
            for job in self.directory.glob("flash-*"):
                if not job.is_dir() or job.is_symlink() or job.name in active: continue
                if time.time() - job.stat().st_mtime < policy["history_days"] * 86400: continue
                destination = self.directory / "archives/flash" / job.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.exists():
                    job.rename(destination)
                    archived_jobs += 1
            logic_dir = self.directory / "slogic"
            if logic_dir.exists():
                for job in logic_dir.iterdir():
                    if not job.is_dir() or job.is_symlink() or job.name in active: continue
                    if time.time()-job.stat().st_mtime < policy["history_days"]*86400: continue
                    destination = self.directory / "archives/slogic" / job.name
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    if not destination.exists():
                        job.rename(destination)
                        archived_jobs += 1
            deleted = 0
            archive_dir = self.directory / "archives"
            candidates = []
            if archive_dir.exists():
                for path in archive_dir.rglob("*"):
                    if not path.is_file() or path.is_symlink(): continue
                    category = path.relative_to(archive_dir).parts[0]
                    if category in ("events", "text", "slogic") and policy["protect_history"]: continue
                    if category == "flash":
                        if path.name == "firmware.bin" and policy["protect_firmware"]: continue
                        if path.name != "firmware.bin" and policy["protect_history"]: continue
                    candidates.append(path)
            total = self.inventory()["bytes"]
            for path in sorted(candidates, key=lambda p: p.stat().st_mtime):
                size, modified = path.stat().st_size, path.stat().st_mtime
                if time.time() - modified > policy["archive_days"] * 86400 or total > policy["max_mb"] * 1024**2:
                    path.unlink()
                    total -= size
                    deleted += 1
            return dict(archived_events=archived, archived_jobs=archived_jobs, deleted_archive_files=deleted,
                        inventory=self.inventory())
