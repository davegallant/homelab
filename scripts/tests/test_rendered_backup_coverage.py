import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'rendered_backup_coverage.py'
SPEC = importlib.util.spec_from_file_location('rendered_backup_coverage', SCRIPT)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class RenderedBackupCoverageTest(unittest.TestCase):
    def test_local_claim_must_be_selected_or_excluded(self):
        pod = {'metadata': {'name': 'app'}, 'spec': {'volumes': [{'name': 'data', 'persistentVolumeClaim': {'claimName': 'data'}}]}}
        self.assertEqual(CHECK.unselected_claims('app', pod, False, {}), ['app/data'])
        pod['metadata']['annotations'] = {'backup.velero.io/backup-volumes': 'data'}
        self.assertEqual(CHECK.unselected_claims('app', pod, False, {}), [])
        pod['metadata']['annotations'] = {}
        self.assertEqual(CHECK.unselected_claims('app', pod, True, {}), [])
        pod['metadata']['annotations'] = {'backup.velero.io/backup-volumes-excludes': 'data'}
        self.assertEqual(CHECK.unselected_claims('app', pod, True, {}), ['app/data'])
        pod['metadata']['annotations'] = {}
        self.assertEqual(CHECK.unselected_claims('app', pod, False, {'app/data': 'externally backed up'}), [])


if __name__ == '__main__':
    unittest.main()
