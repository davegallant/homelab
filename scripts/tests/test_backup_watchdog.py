import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

import yaml

ROOT = Path(__file__).resolve().parents[2]


class BackupWatchdogTest(unittest.TestCase):
    def test_unselected_local_claim_is_a_gap(self):
        config = yaml.safe_load((ROOT / 'kubernetes/apps/backup-watchdog/configmap.yaml').read_text())
        now = datetime.now(timezone.utc).isoformat()
        fixtures = {
            'pvcs': [{'metadata': {'namespace': 'app', 'name': 'data'}, 'spec': {'volumeName': 'pv'}, 'status': {'phase': 'Bound'}}],
            'pvs': [{'metadata': {'name': 'pv'}, 'spec': {'local': {'path': '/data'}}}],
            'pods': [{'metadata': {'namespace': 'app'}, 'spec': {'volumes': [{'name': 'data', 'persistentVolumeClaim': {'claimName': 'data'}}]}}],
            'schedules': [{'metadata': {'name': 'daily'}, 'spec': {'template': {'includedNamespaces': ['app'], 'defaultVolumesToFsBackup': False}}}],
            'backups': [{'metadata': {'name': 'backup', 'labels': {'velero.io/schedule-name': 'daily'}}, 'status': {'phase': 'Completed', 'startTimestamp': now}}],
            'pvbs': [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            for name, items in fixtures.items():
                (path / (name + '.json')).write_text(json.dumps({'items': items}))
            script = path / 'check.py'
            script.write_text(config['data']['check.py'])
            env = dict(os.environ, WATCHDOG_FIXTURE_DIR=tmp, GOTIFY_TOKEN='')
            result = subprocess.run([sys.executable, str(script)], env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('app/data', result.stdout)


if __name__ == '__main__':
    unittest.main()
