import importlib.util
from pathlib import Path
import unittest

FILE = Path(__file__).parents[2] / "kubernetes/apps/presync-gate/recovery_points.py"
spec = importlib.util.spec_from_file_location("recovery_points", FILE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RecoveryPointsTest(unittest.TestCase):
    def test_only_completed_labeled_points_with_immutable_revision_are_listed(self):
        def item(name, phase, rev, app="miniflux"):
            return {"metadata": {"name": name, "creationTimestamp": "2026-11-02T00:00:00Z", "labels": {"homelab.davegallant.ca/pre-sync-app": app}, "annotations": {"homelab.davegallant.ca/previous-revision": rev}}, "status": {"phase": phase, "expiration": "2026-11-09T00:00:00Z"}}
        data = [item("good", "Completed", "a" * 40), item("failed", "Failed", "b" * 40), item("badrev", "Completed", "main"), item("other", "Completed", "c" * 40, "other")]
        self.assertEqual(module.recovery_points(data, "miniflux"), [{"name": "good", "revision": "a" * 40, "expires": "2026-11-09T00:00:00Z", "created": "2026-11-02T00:00:00Z"}])


if __name__ == "__main__":
    unittest.main()
