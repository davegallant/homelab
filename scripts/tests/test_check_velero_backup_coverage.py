import subprocess
import sys
import unittest
import tempfile
import shutil
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CHECKER = REPO / "scripts" / "check-velero-backup-coverage.py"


class VeleroBackupCoverageTest(unittest.TestCase):
    def test_paused_schedule_does_not_count_as_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            shutil.copy(CHECKER, root / "scripts" / CHECKER.name)
            apps = root / "kubernetes/apps/argocd/applications"
            schedules = root / "kubernetes/apps/velero-schedules"
            apps.mkdir(parents=True)
            schedules.mkdir(parents=True)
            (apps / "app.yaml").write_text('''kind: Application
metadata:
  name: app
  annotations: {homelab.davegallant.ca/backup-policy: scheduled}
spec: {project: homelab, destination: {namespace: app}}
''')
            (schedules / "app.yaml").write_text('''kind: Schedule
metadata: {name: app, namespace: velero}
spec:
  paused: true
  template: {includedNamespaces: [app]}
''')
            result = subprocess.run([sys.executable, str(root / "scripts" / CHECKER.name)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("paused", result.stderr)

    def test_reviewed_monitoring_namespace_can_have_a_schedule_without_an_app(self):
        result = subprocess.run(
            [sys.executable, str(CHECKER)],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
