import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check-rendered-pod-security.py"


class RenderedPodSecurityTests(unittest.TestCase):
    def test_restricted_rendered_workload_with_missing_controls_fails(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            applications = root / "kubernetes/apps/argocd/applications"
            manifests = root / "kubernetes/apps/sample/manifests"
            manifests.mkdir(parents=True)
            applications.mkdir(parents=True)
            (applications / "sample.yaml").write_text(
                """apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: sample
spec:
  source:
    repoURL: https://github.com/davegallant/homelab.git
    path: kubernetes/apps/sample/manifests
  destination:
    namespace: sample
""",
                encoding="utf-8",
            )
            (root / "kubernetes/apps/sample/namespace.yaml").write_text(
                """apiVersion: v1
kind: Namespace
metadata:
  name: sample
  labels:
    pod-security.kubernetes.io/enforce: restricted
""",
                encoding="utf-8",
            )
            (manifests / "deployment.yaml").write_text(
                """apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  template:
    spec:
      containers:
        - name: app
          image: example.invalid/app:1
          securityContext:
            allowPrivilegeEscalation: true
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("sample/web containers:app allowPrivilegeEscalation", result.stdout)


if __name__ == "__main__":
    unittest.main()
