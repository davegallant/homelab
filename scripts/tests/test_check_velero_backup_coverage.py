import subprocess
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CHECKER = REPO / "scripts" / "check-velero-backup-coverage.py"


class VeleroBackupCoverageTest(unittest.TestCase):
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
