import importlib.util
import pathlib
import unittest


REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check-pod-security.py"
FIXTURES = REPO / "scripts" / "tests" / "fixtures" / "pod-security"
class InventoryTests(unittest.TestCase):
    def load_checker(self):
        self.assertTrue(SCRIPT.exists(), "pod security inventory checker is missing")
        spec = importlib.util.spec_from_file_location("check_pod_security", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def read_fixture(self, name):
        return self.load_checker().load_documents(FIXTURES / name)[0]

    def test_compliant_pod_has_no_hardening_findings(self):
        checker = self.load_checker()
        pod = checker.load_documents(FIXTURES / "compliant-pod.yaml")[0]
        self.assertEqual(checker.inspect_document(pod), [])

    def test_regular_and_init_container_findings_are_reported(self):
        pod = self.read_fixture("violating-pod.yaml")
        findings = self.load_checker().inspect_document(pod)
        rendered = {finding for finding in findings}
        self.assertIn("sample/violating containers:app runAsNonRoot", rendered)
        self.assertIn("sample/violating containers:app allowPrivilegeEscalation", rendered)
        self.assertIn("sample/violating containers:app dropAllCapabilities", rendered)
        self.assertIn("sample/violating initContainers:prepare runAsNonRoot", rendered)
        self.assertIn("sample/violating initContainers:prepare RuntimeDefaultSeccomp", rendered)

    def test_pod_level_seccomp_is_effective_for_ephemeral_container(self):
        pod = self.read_fixture("inherited-seccomp-pod.yaml")
        findings = self.load_checker().inspect_document(pod)
        self.assertFalse(any("ephemeralContainers:debug RuntimeDefaultSeccomp" in x for x in findings))

    def test_exception_classification_does_not_hide_findings(self):
        pod = self.read_fixture("platform-exception-pod.yaml")
        checker = self.load_checker()
        findings = checker.inspect_document(pod, exceptions={"platform-example"})
        self.assertIn("platform-example/platform-agent containers:agent privileged [exception]", findings)
        self.assertTrue(checker.is_exception(pod, {"platform-example"}))

    def test_exception_classification_reads_controller_template_namespace(self):
        pod = self.read_fixture("platform-exception-pod.yaml")
        deployment = {
            "kind": "Deployment",
            "metadata": {"name": "platform-agent"},
            "spec": {
                "template": {
                    "metadata": {"namespace": "platform-example", "name": "platform-agent"},
                    "spec": pod["spec"],
                }
            },
        }
        checker = self.load_checker()
        self.assertTrue(checker.is_exception(deployment, {"platform-example"}))

    def test_rendered_controller_templates_convert_to_server_dry_run_pods(self):
        checker = self.load_checker()
        self.assertTrue(hasattr(checker, "render_pods"), "rendered Pod conversion is missing")
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "web", "namespace": "sample"},
            "spec": {
                "template": {
                    "metadata": {"labels": {"app": "web"}},
                    "spec": {
                        "hostNetwork": True,
                        "containers": [
                            {
                                "name": "app",
                                "image": "example.invalid/app:1",
                                "env": [{"name": "TOKEN", "value": "do-not-copy"}],
                                "livenessProbe": {
                                    "httpGet": {
                                        "host": "127.0.0.1",
                                        "path": "/health",
                                        "httpHeaders": [{"name": "Authorization", "value": "do-not-copy"}],
                                    }
                                },
                            }
                        ],
                        "initContainers": [{"name": "init", "image": "example.invalid/app:1"}],
                        "volumes": [{"name": "host", "hostPath": {"path": "/var/run"}}],
                    },
                }
            },
        }
        pods = checker.render_pods(deployment)
        self.assertEqual(len(pods), 1)
        self.assertEqual(pods[0]["kind"], "Pod")
        self.assertEqual(pods[0]["metadata"]["namespace"], "sample")
        self.assertLessEqual(len(pods[0]["metadata"]["name"]), 63)
        self.assertEqual(pods[0]["spec"]["initContainers"][0]["name"], "init")
        self.assertTrue(pods[0]["spec"]["hostNetwork"])
        self.assertEqual(pods[0]["spec"]["volumes"][0]["hostPath"]["path"], "/var/run")
        self.assertNotIn("example.invalid/app:1", str(pods[0]))
        self.assertNotIn("do-not-copy", str(pods[0]))
        container = pods[0]["spec"]["containers"][0]
        self.assertIn("livenessProbe", container, "host probe fields were omitted")
        self.assertEqual(container["livenessProbe"]["httpGet"]["host"], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
