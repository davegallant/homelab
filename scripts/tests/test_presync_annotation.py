import importlib.util
from pathlib import Path
import tempfile
import unittest

FILE = Path(__file__).parents[1] / "check_presync_annotation.py"
spec = importlib.util.spec_from_file_location("check_presync_annotation", FILE)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class PreSyncAnnotationTest(unittest.TestCase):
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
