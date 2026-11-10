import importlib.util
from datetime import datetime, timezone, timedelta
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('watchdog_gate', Path(__file__).resolve().parents[1] / 'watchdog_resize_gate.py')
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class WatchdogResizeGateTest(unittest.TestCase):
    def test_requires_fresh_successful_matching_watchdog_job_without_gaps(self):
        now = datetime.now(timezone.utc)
        job = {'metadata': {'labels': {'app.kubernetes.io/name': 'backup-watchdog'}}, 'status': {'succeeded': 1, 'completionTime': now.isoformat()}, 'spec': {'template': {'spec': {'serviceAccountName': 'backup-watchdog', 'containers': [{'command': ['python3', '/app/check.py']}], 'volumes': [{'configMap': {'name': 'backup-watchdog'}}]}}}}
        report = {'generated_at': now.isoformat(), 'gaps': [], 'covered_namespaces': ['monitoring'], 'backups_checked': {'monitoring': {'phase': 'Completed'}}}
        cronjob = {'status': {'lastScheduleTime': (now - timedelta(minutes=5)).isoformat()}}
        self.assertTrue(GATE.valid_evidence(job, report, cronjob, now))
        self.assertFalse(GATE.valid_evidence(job, dict(report, gaps=['missing backup']), cronjob, now))
        self.assertFalse(GATE.valid_evidence(job, dict(report, covered_namespaces=[]), cronjob, now))
        self.assertFalse(GATE.valid_evidence(job, report, {'spec': {'suspend': True}, **cronjob}, now))
        self.assertFalse(GATE.valid_evidence(job, dict(report, generated_at=(now - timedelta(hours=2)).isoformat()), cronjob, now))
        self.assertFalse(GATE.valid_evidence(dict(job, status={'failed': 1}), report, cronjob, now))
        self.assertFalse(GATE.valid_evidence(dict(job, metadata={'labels': {}}), report, cronjob, now))
        self.assertFalse(GATE.valid_evidence(job, report, {'status': {'lastScheduleTime': (now + timedelta(minutes=1)).isoformat()}}, now))


if __name__ == '__main__':
    unittest.main()
