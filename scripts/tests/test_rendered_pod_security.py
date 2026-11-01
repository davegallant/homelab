import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check-rendered-pod-security.py"
SPEC = importlib.util.spec_from_file_location("rendered_pod_security", SCRIPT)
RENDERED_CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDERED_CHECKER)


class RenderedPodSecurityTests(unittest.TestCase):
    def test_all_rendered_containers_need_cpu_and_memory_limits(self):
        self.assertEqual(
            RENDERED_CHECKER.missing_resource_limits({"limits": {"cpu": "250m", "memory": "128Mi"}}),
            [],
        )
        self.assertEqual(
            RENDERED_CHECKER.missing_resource_limits({"limits": {"memory": "128Mi"}}),
            ["cpu"],
        )
        self.assertEqual(RENDERED_CHECKER.missing_resource_limits({}), ["cpu", "memory"])

    def test_image_requires_version_tag_and_sha256_digest(self):
        digest = "a" * 64
        self.assertTrue(RENDERED_CHECKER.image_is_pinned("registry.example/app:1.2.3@sha256:" + digest))
        self.assertFalse(RENDERED_CHECKER.image_is_pinned("registry.example/app:1.2.3"))
        self.assertFalse(RENDERED_CHECKER.image_is_pinned("registry.example/app@sha256:" + digest))
        self.assertFalse(RENDERED_CHECKER.image_is_pinned("registry.example/app:1.2.3@sha256:xyz"))
        self.assertFalse(RENDERED_CHECKER.image_is_pinned("registry.example/app:latest@sha256:" + digest))

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
