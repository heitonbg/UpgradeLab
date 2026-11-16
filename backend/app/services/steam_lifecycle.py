"""One supervised child for a shared SQLite database; failures never stop HTTP."""
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading

from app.core.config import settings
from app.db.base import engine

LOG = logging.getLogger('steam_requirements')


class SteamSupervisor:
    def __init__(self):
        self.process = None
        self.stopped = threading.Event()
        self.mutex = threading.Lock()
        self.thread = None
        self.guard = None

    def check(self):
        with self.mutex:
            if self.stopped.is_set():
                return
            if self.process is not None and self.process.poll() is None:
                return
            if self.process is not None:
                LOG.warning('steam_worker status=exited returncode=%s; restarting', self.process.returncode)
            try:
                # An explicit effective URL prevents a child's cwd/.env from selecting another DB.
                environment = dict(os.environ, DATABASE_URL=engine.url.render_as_string(hide_password=False))
                self.process = subprocess.Popen(
                    [sys.executable, '-m', 'app.workers.steam_requirements_worker'],
                    cwd=Path(__file__).resolve().parents[2], env=environment,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                LOG.info('steam_worker status=spawned pid=%s', self.process.pid)
            except OSError:
                self.process = None
                LOG.exception('steam_worker status=spawn_failed; HTTP remains available')

    def start(self):
        from scripts.startup import bootstrap_lock
        from app.services.catalog_files import CatalogError
        filename = engine.url.database
        if engine.url.get_backend_name() != 'sqlite' or not filename or filename == ':memory:':
            LOG.error('steam_worker status=disabled code=file_sqlite_required')
            return
        try:
            location = Path(filename).resolve()
            location.parent.mkdir(parents=True, exist_ok=True)
            self.guard = bootstrap_lock(location.with_name(location.name + '.steam-supervisor'))
            self.guard.__enter__()
        except (OSError, CatalogError):
            self.guard = None
            LOG.warning('steam_worker supervisor not acquired; another API process may own it')
            return
        self.check()
        self.thread = threading.Thread(target=self.run, name='steam-supervisor', daemon=True)
        self.thread.start()

    def run(self):
        # No SQLite polling here. A failed child is retried at most once per 15 seconds.
        while not self.stopped.wait(15):
            self.check()

    def close(self):
        self.stopped.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
        with self.mutex:
            if self.process is not None and self.process.poll() is None:
                if os.name == 'nt':
                    # Windows venv python is a launcher with another Python child.
                    # Terminating only the launcher would orphan the real worker/lock.
                    subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                else:
                    self.process.terminate()
                try:
                    self.process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        if self.guard is not None:
            self.guard.__exit__(None, None, None)
            self.guard = None
