import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml

FILE = Path(__file__).parents[1] / "check_presync_annotation.py"
spec = importlib.util.spec_from_file_location("check_presync_annotation", FILE)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class PreSyncAnnotationTest(unittest.TestCase):
    def test_dedicated_project_covers_every_registered_namespace_and_gate_job(self):
        root = Path(__file__).parents[2]
        registry_resource = yaml.safe_load((root / "kubernetes/apps/presync-gate/applications.yaml").read_text())
        registry = yaml.safe_load(registry_resource["data"]["applications.yaml"])["applications"]
        project = yaml.safe_load((root / "kubernetes/apps/argocd/project-presync-gate.yaml").read_text())
        self.assertTrue(checker.project_covers_registry(project, registry))

    def test_gate_source_is_detected_in_single_or_multi_source_application(self):
        source = {"repoURL": "repo", "targetRevision": "main", "path": "kubernetes/apps/presync-gate/chart"}
        app = {"spec": {"sources": [{"repoURL": "app", "path": "workload"}, source]}}
        self.assertEqual(checker.gate_source(app), source)
        app["spec"] = {"source": source}
        self.assertEqual(checker.gate_source(app), source)
        app["spec"] = {"source": {"path": "workload"}}
        self.assertIsNone(checker.gate_source(app))

    def test_application_values_must_match_central_registry(self):
        app = {"metadata": {"name": "demo"}, "spec": {"project": "homelab", "destination": {"namespace": "demo"},
               "sources": [{"path": "kubernetes/apps/presync-gate/chart", "helm": {"valuesObject": {"application": "demo", "targetNamespace": "demo", "gateNamespace": "presync-gate", "requiredHooks": [], "excludedVolumes": [], "scheduleName": "", "defaultVolumesToFsBackup": False}}}]}}
        registry = {"demo": {"project": "homelab", "application": "demo", "targetNamespace": "demo", "gateNamespace": "presync-gate", "requiredHooks": [], "excludedVolumes": [], "scheduleName": "", "defaultVolumesToFsBackup": False}}
        self.assertTrue(checker.registry_matches(app, registry))
        registry["demo"]["targetNamespace"] = "other"
        self.assertFalse(checker.registry_matches(app, registry))

    def test_opt_in_must_match_rendered_gate(self):
        app = {"metadata": {"annotations": {"homelab.davegallant.ca/pre-sync-backup": "enabled"}}}
        self.assertTrue(checker.valid(app, True))
        self.assertFalse(checker.valid(app, False))
        app["metadata"]["annotations"]["homelab.davegallant.ca/pre-sync-backup"] = "disabled"
        self.assertTrue(checker.valid(app, False))
        self.assertFalse(checker.valid(app, True))
        app["metadata"]["annotations"]["homelab.davegallant.ca/pre-sync-backup"] = "typo"
        self.assertFalse(checker.valid(app, False))

    def test_helm_values_override_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chart = root / "app" / "chart"
            chart.mkdir(parents=True)
            (chart / "Chart.yaml").write_text("apiVersion: v2\nname: test\nversion: 0.1.0\n")
            (chart / "templates").mkdir()
            (chart / "templates/job.yaml").write_text('{{- if .Values.preSyncBackup.enabled }}\napiVersion: batch/v1\nkind: Job\nmetadata:\n  name: test\n  annotations:\n    homelab.davegallant.ca/pre-sync-backup: "true"\n    argocd.argoproj.io/hook: PreSync\n{{- end }}\n')
            (chart / "values.yaml").write_text("preSyncBackup:\n  enabled: false\n")
            (chart.parent / "values.production.yaml").write_text("preSyncBackup:\n  enabled: true\n")
            app = {"metadata": {"name": "test"}, "spec": {"destination": {"namespace": "test"}, "source": {"path": "app/chart", "helm": {"valueFiles": ["../values.production.yaml"]}}}}
            self.assertTrue(checker.enabled(app, root))
            template = chart / "templates/job.yaml"
            template.write_text(template.read_text().replace("    argocd.argoproj.io/hook: PreSync\n", ""))
            with self.assertRaises(ValueError):
                checker.enabled(app, root)
            template.write_text(template.read_text().replace('    homelab.davegallant.ca/pre-sync-backup: "true"\n', '    homelab.davegallant.ca/pre-sync-backup: "true"\n    argocd.argoproj.io/hook: PreSync\n'))
            app["spec"]["source"]["helm"]["parameters"] = [{"name": "preSyncBackup.enabled", "value": "false"}]
            self.assertFalse(checker.enabled(app, root))


if __name__ == "__main__":
    unittest.main()
