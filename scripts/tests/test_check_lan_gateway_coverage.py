import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_lan_gateway_coverage as coverage  # noqa: E402


VALUES = """
apps:
  - name: alpha
    port: 80
    selectorLabels: {app.kubernetes.io/name: alpha}
excluded:
  - name: beta
    reason: LXC without a published port.
"""

PROJECT = """
spec:
  destinations:
    - namespace: lan-gateway
    - namespace: alpha
"""


class LanGatewayCoverageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.write("kubernetes/apps/lan-gateway/chart/values.yaml", VALUES)
        self.write("kubernetes/apps/argocd/project-lan-gateway.yaml", PROJECT)
        self.write("kubernetes/apps/alpha/values.production.yaml", "image: docker.io/fosrl/newt:1.0\n")
        self.write("ansible/playbooks/beta/docker-compose.yml", "image: docker.io/fosrl/newt:1.0\n")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_covered_repository_passes(self):
        self.assertEqual(coverage.check(self.root), [])

    def test_new_newt_app_fails(self):
        self.write("kubernetes/apps/gamma/chart/values.yaml", "repository: docker.io/fosrl/newt\n")
        errors = coverage.check(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn("gamma runs Newt", errors[0])

    def test_entry_without_newt_fails(self):
        self.write("kubernetes/apps/alpha/values.production.yaml", "image: docker.io/other:1\n")
        errors = coverage.check(self.root)
        self.assertTrue(any("alpha has no Newt workload" in e for e in errors))

    def test_exclusion_needs_reason(self):
        self.write("kubernetes/apps/lan-gateway/chart/values.yaml",
                   VALUES.replace("reason: LXC without a published port.", "reason: ''"))
        self.assertTrue(any("needs a reason" in e for e in coverage.check(self.root)))

    def test_missing_project_destination_fails(self):
        self.write("kubernetes/apps/argocd/project-lan-gateway.yaml", "spec: {destinations: []}\n")
        self.assertTrue(any("destination namespace alpha" in e for e in coverage.check(self.root)))

    def test_pangolin_domain_not_covered_fails(self):
        errors = coverage.check_pangolin(
            self.root, ["alpha.davegallant.ca", "beta.davegallant.ca", "delta.davegallant.ca"])
        self.assertEqual(len(errors), 1)
        self.assertIn("delta.davegallant.ca", errors[0])


if __name__ == "__main__":
    unittest.main()
