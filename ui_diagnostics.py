"""Keep a stack trace when the GUI event loop stalls or a native fault occurs."""
from datetime import datetime
import faulthandler
import sys
import threading
import time


class UIDiagnostics:
    def __init__(self, path):
        self.stream = path.open("a", encoding="utf-8")
        self.previously_enabled = faulthandler.is_enabled()
        faulthandler.enable(file=self.stream, all_threads=True)
        self.heartbeat = time.monotonic()
        self.stopped = threading.Event()
        self.worker = threading.Thread(target=self._watch, daemon=True)
        self.worker.start()

    def tick(self):
        self.heartbeat = time.monotonic()

    def _watch(self):
        last_dump = 0
        while not self.stopped.wait(.5):
            now = time.monotonic()
            if now - self.heartbeat > 3 and now - last_dump > 30:
                self.stream.write(f"\n{datetime.now().isoformat()} GUI heartbeat delayed {now-self.heartbeat:.1f}s\n")
                self.stream.flush()
                faulthandler.dump_traceback(file=self.stream, all_threads=True)
                last_dump = now

    def close(self):
        self.stopped.set()
        self.worker.join(1)
        faulthandler.disable()
        if self.previously_enabled and sys.stderr is not None: faulthandler.enable()
        self.stream.close()
