"""Verify component scheduling without launching devices or GUI windows."""
import threading
import unittest
from unittest.mock import Mock

from core import Registry, Resources


class ComponentConcurrencyTests(unittest.TestCase):
    def test_different_components_can_run_while_same_component_is_serialized(self):
        registry = Registry(Mock(), Resources())
        started = threading.Event()
        release = threading.Event()
        other_finished = threading.Event()
        same_finished = threading.Event()

        class Component:
            actions = {"work": dict(label="work", fields=[], read_only=True, destructive=False)}
            def __init__(self, name): self.id = name
            def work(self):
                if self.id == "first" and not started.is_set():
                    started.set()
                    if not release.wait(5): raise TimeoutError("test release timed out")
                return {"ok": True}
            def status(self): return {"state": "idle"}
            def close(self): pass

        registry.register(Component("first"))
        registry.register(Component("second"))
        errors = []
        def invoke(target, finished=None):
            try:
                registry.invoke(target, {})
                if finished: finished.set()
            except Exception as exc: errors.append(exc)
        workers = [threading.Thread(target=invoke, args=("first.work",)),
                   threading.Thread(target=invoke, args=("first.work", same_finished)),
                   threading.Thread(target=invoke, args=("second.work", other_finished))]
        try:
            workers[0].start()
            self.assertTrue(started.wait(2))
            workers[1].start()
            workers[2].start()
            self.assertTrue(other_finished.wait(2), "a different component was blocked")
            self.assertFalse(same_finished.is_set(), "same-component calls overlapped")
        finally:
            release.set()
            for worker in workers:
                if worker.ident is not None: worker.join(3)
            registry.close()
        self.assertTrue(same_finished.is_set())
        self.assertFalse(errors)


if __name__ == "__main__": unittest.main()
