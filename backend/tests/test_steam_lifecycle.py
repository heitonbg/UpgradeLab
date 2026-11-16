import unittest
from unittest.mock import Mock, patch

class SupervisorTests(unittest.TestCase):
    def test_spawn_failure_isolated_and_retried(self):
        from app.services.steam_lifecycle import SteamSupervisor
        process=Mock(); process.poll.return_value=None
        with patch('app.services.steam_lifecycle.subprocess.Popen',side_effect=[OSError('unavailable'),process]) as spawn:
            supervisor=SteamSupervisor()
            supervisor.check(); self.assertIsNone(supervisor.process)
            supervisor.check(); self.assertIs(supervisor.process,process)
            self.assertEqual(spawn.call_count,2)
    def test_running_child_not_duplicated_and_crash_restarts(self):
        from app.services.steam_lifecycle import SteamSupervisor
        first=Mock(); first.poll.side_effect=[None,1]
        second=Mock()
        with patch('app.services.steam_lifecycle.subprocess.Popen',side_effect=[first,second]) as spawn:
            supervisor=SteamSupervisor(); supervisor.check(); supervisor.check()
            self.assertEqual(spawn.call_count,1)
            supervisor.check(); self.assertEqual(spawn.call_count,2)
    def test_shutdown_waits_then_kills_unresponsive_child(self):
        import subprocess
        from app.services.steam_lifecycle import SteamSupervisor
        process=Mock(); process.poll.return_value=None
        process.wait.side_effect=[subprocess.TimeoutExpired('worker',20),0]
        supervisor=SteamSupervisor(); supervisor.process=process
        with patch('app.services.steam_lifecycle.os.name','posix'):
            supervisor.close()
        process.terminate.assert_called_once(); process.kill.assert_called_once()
        supervisor.check(); self.assertIs(supervisor.process,process)


class ProcessPersistenceTests(unittest.TestCase):
    def test_real_child_restart_lock_same_database_and_default_delete_journal(self):
        import json, os, subprocess, sys, tempfile
        from pathlib import Path
        code = r"""
import json,time,sqlite3,subprocess,sys,os
from app.db.base import engine,Base
from app.db import models
from app.services.steam_lifecycle import SteamSupervisor
Base.metadata.create_all(engine)
with engine.begin() as c:
 c.exec_driver_sql('CREATE TABLE persistence_probe (value TEXT)')
 c.exec_driver_sql("INSERT INTO persistence_probe VALUES ('preserved')")
s=SteamSupervisor()
try:
 s.start(); first=s.process.pid; time.sleep(1.5)
 assert s.process.poll() is None
 duplicate=subprocess.run([sys.executable,'-m','app.workers.steam_requirements_worker'],capture_output=True,text=True,timeout=15)
 assert duplicate.returncode==0 and 'another_worker' in duplicate.stderr
 if os.name=='nt':subprocess.run(['taskkill','/PID',str(first),'/T','/F'],capture_output=True,timeout=10)
 else:s.process.kill()
 s.process.wait(timeout=10); s.check()
 second=s.process.pid; assert first!=second
 time.sleep(1); assert s.process.poll() is None
 with engine.connect() as c:
  assert c.exec_driver_sql('SELECT value FROM persistence_probe').scalar()=='preserved'
  assert c.exec_driver_sql('PRAGMA journal_mode').scalar()=='delete'
 print(json.dumps({'first_pid':first,'second_pid':second,'duplicate_skipped':True,'journal':'delete'}))
finally:s.close()
with sqlite3.connect(engine.url.database) as c:
 assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 assert c.execute('SELECT value FROM persistence_probe').fetchone()[0]=='preserved'
"""
        with tempfile.TemporaryDirectory() as directory:
            environment=dict(os.environ,AMVERA='0',STEAM_WORKER_ENABLED='false',DATABASE_URL='sqlite:///'+(Path(directory)/'data.db').as_posix())
            result=subprocess.run([sys.executable,'-c',code],env=environment,capture_output=True,text=True,timeout=45)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('"duplicate_skipped": true',result.stdout)
