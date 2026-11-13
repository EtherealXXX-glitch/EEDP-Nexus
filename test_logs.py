import gzip
import json
from pathlib import Path
import tempfile
import time
import unittest
import zipfile
import os

from core import Activity, Registry, Resources
from settings import Settings
from api import dispatch


class LogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.registry = Registry(Activity(self.path / "logs"), Resources(), Settings(self.path / "settings.json"))

    def tearDown(self):
        self.registry.close()
        self.temp.cleanup()

    def emit(self, component, kind, text, client):
        return self.registry.activity.emit(component, kind, text, client=client)

    def test_query_filters_newest_pagination_and_export(self):
        first = self.emit("serial", "call", "first", "wsl-test")
        self.emit("serial", "rx", "not a call", "desktop")
        last = self.emit("serial", "call", "last", "wsl-test")
        day = first["time"][:10]
        filters = dict(component="serial", kind="call", client="wsl-test", start=day, end=day)
        page = dispatch(self.registry, "logs.query", dict(filters, limit=1))
        self.assertEqual(page["events"][0]["id"], last["id"])
        older = dispatch(self.registry, "logs.query", dict(filters, before=page["next_before"], limit=1))
        self.assertEqual(older["events"][0]["id"], first["id"])
        self.assertIsNone(older["next_before"])
        job = self.path / "logs/flash-test"
        job.mkdir()
        (job / "firmware.bin").write_bytes(b"private firmware")
        (job / "engine.log").write_text("success")
        result = dispatch(self.registry, "logs.export", {"filters": filters})
        with zipfile.ZipFile(result["path"]) as archive:
            exported = [json.loads(line) for line in archive.read("events.jsonl").decode().splitlines()]
            self.assertEqual([x["text"] for x in exported], ["first", "last"])
            self.assertFalse(any("firmware.bin" in x for x in archive.namelist()))
            self.assertIn("artifacts/flash-test/engine.log", archive.namelist())
            self.assertFalse(any("endpoint" in x for x in archive.namelist()))
        with self.assertRaises(ValueError): dispatch(self.registry, "logs.query", {"start":"invalid"})

    def test_archive_before_pruning_preserves_cursor_across_empty_restart(self):
        item = self.emit("serial", "rx", "retained", "desktop")
        activity = self.registry.activity
        payload = {**item, "time":"2000-01-01T00:00:00+08:00"}
        activity.database.execute("UPDATE events SET payload=? WHERE id=?", (json.dumps(payload), item["id"]))
        activity.database.commit()
        result = self.registry.logs.maintain()
        self.assertEqual(result["archived_events"], 1)
        archived = next((self.path / "logs/archives/events").glob("*.gz"))
        with gzip.open(archived, "rt", encoding="utf-8") as stream:
            self.assertEqual(json.loads(stream.readline())["text"], "retained")
        self.registry.close()
        self.registry = Registry(Activity(self.path / "logs"), Resources(), Settings(self.path / "settings.json"))
        self.assertGreater(self.emit("serial", "rx", "next", "desktop")["id"], item["id"])

    def test_protected_archives_and_firmware_survive_capacity_maintenance(self):
        directory = self.path / "logs/archives/flash/old-job"
        directory.mkdir(parents=True)
        (directory / "firmware.bin").write_bytes(b"x" * (2 * 1024**2))
        (directory / "engine.log").write_text("old log")
        result = self.registry.logs.set_policy(max_mb=1)
        self.assertTrue(result["protect_history"])
        self.registry.logs.maintain()
        self.assertTrue((directory / "firmware.bin").exists())
        self.assertTrue(self.registry.logs.inventory()["over_limit"])
        self.registry.logs.set_policy(protect_history=False)
        self.registry.logs.maintain()
        self.assertTrue((directory / "firmware.bin").exists())
        self.registry.logs.set_policy(protect_firmware=False)
        result = self.registry.logs.maintain()
        self.assertFalse((directory / "firmware.bin").exists())
        self.assertGreater(result["deleted_archive_files"], 0)

    def test_running_and_latest_flash_are_not_archived(self):
        job = self.path / "logs/flash-active"
        job.mkdir()
        os.utime(job, (0, 0))
        self.registry.logs.active_jobs = lambda: [job.name]
        self.registry.logs.maintain()
        self.assertTrue(job.exists())
        self.registry.logs.active_jobs = lambda: []
        self.registry.logs.maintain()
        self.assertFalse(job.exists())
        self.assertTrue((self.path / "logs/archives/flash/flash-active").exists())

    def test_policy_validation_cannot_be_bypassed_through_settings(self):
        with self.assertRaises(ValueError): dispatch(self.registry, "settings.update", {"scope":"logs", "values":{"max_mb":0}})
        with self.assertRaises(ValueError): dispatch(self.registry, "logs.policy", {"protect_history":"false"})
        with self.assertRaises(ValueError): dispatch(self.registry, "logs.policy", {"max_mb":-1})


if __name__ == "__main__": unittest.main()
