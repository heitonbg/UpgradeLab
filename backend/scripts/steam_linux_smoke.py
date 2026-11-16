"""Explicit Linux/container smoke against a disposable DB; never opens production DB."""
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time


def main():
    if sys.platform != 'linux':
        raise SystemExit('NOT RUN: Linux is required for SIGTERM/SIGINT and flock verification')
    with tempfile.TemporaryDirectory(prefix='steam-smoke-', dir='/data' if Path('/data').is_dir() else None) as directory:
        database = Path(directory) / 'smoke.db'
        os.environ.update(AMVERA='0', STEAM_WORKER_ENABLED='false', DATABASE_URL='sqlite:///' + database.as_posix())
        from app.db.base import Base, engine
        from app.db import models
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE smoke_sentinel (value TEXT)')
            connection.exec_driver_sql("INSERT INTO smoke_sentinel VALUES ('preserved')")
            assert connection.exec_driver_sql('PRAGMA journal_mode').scalar() == 'delete'
        report = {'database': 'disposable', 'journal': 'delete', 'signals': []}
        command = [sys.executable, '-m', 'app.workers.steam_requirements_worker']
        for sig in (signal.SIGTERM, signal.SIGINT):
            with open(Path(directory) / 'worker.log', 'w+') as log:
                worker = subprocess.Popen(command, stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        log.seek(0)
                        if 'status=started' in log.read(): break
                        if worker.poll() is not None: raise AssertionError('worker exited before ready')
                        time.sleep(.1)
                    else: raise AssertionError('worker startup timeout')
                    duplicate = subprocess.run(command, capture_output=True, text=True, timeout=15)
                    assert duplicate.returncode == 0 and 'another_worker' in duplicate.stderr
                    worker.send_signal(sig)
                    assert worker.wait(timeout=20) == 0
                    report['signals'].append(sig.name)
                finally:
                    if worker.poll() is None:
                        worker.kill(); worker.wait(timeout=5)
        # Simulate a writer dying during an uncommitted transaction on this mount.
        writer_code = "import sqlite3,sys,time; c=sqlite3.connect(sys.argv[1]); c.execute('BEGIN IMMEDIATE'); c.execute(\"UPDATE smoke_sentinel SET value='uncommitted'\"); print('locked',flush=True); time.sleep(60)"
        writer = subprocess.Popen([sys.executable, '-c', writer_code, str(database)], stdout=subprocess.PIPE, text=True)
        try:
            assert writer.stdout.readline().strip() == 'locked'
            with sqlite3.connect(database, timeout=.2) as connection:
                assert connection.execute('SELECT value FROM smoke_sentinel').fetchone()[0] == 'preserved'
                try:
                    connection.execute("UPDATE smoke_sentinel SET value='bad'")
                except sqlite3.OperationalError as exc:
                    assert 'locked' in str(exc)
                else: raise AssertionError('SQLite did not enforce writer locking')
            writer.kill(); writer.wait(timeout=5)
            with sqlite3.connect(database) as connection:
                assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
                assert connection.execute('SELECT value FROM smoke_sentinel').fetchone()[0] == 'preserved'
            report['writer_lock_and_crash_recovery'] = True
        finally:
            if writer.poll() is None: writer.kill(); writer.wait(timeout=5)
            if writer.stdout: writer.stdout.close()
        engine.dispose()
        print(json.dumps(report))


if __name__ == '__main__':
    main()
