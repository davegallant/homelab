import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("presync", Path(__file__).parents[2] / "kubernetes/apps/presync-gate/presync_coverage.py")
presync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(presync)


class CoverageTest(unittest.TestCase):
    def test_generic_volume_policy_tracks_all_consumers_and_init_mounts(self):
        pods = [
            {"metadata": {"uid": "p1"}, "status": {"phase": "Running"}, "spec": {
                "initContainers": [{"volumeMounts": [{"name": "data"}]}],
                "containers": [], "volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": "db"}}]}},
            {"metadata": {"uid": "p2"}, "status": {"phase": "Running"}, "spec": {
                "containers": [{"volumeDevices": [{"name": "data"}]}],
                "volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": "db"}}]}},
        ]
        pods[0]["metadata"]["annotations"] = {"backup.velero.io/backup-volumes": "data"}
        pods[1]["metadata"]["annotations"] = {"backup.velero.io/backup-volumes": "data"}
        actual = presync.volume_policy(pods, [{"metadata": {"name": "db"}, "status": {"phase": "Bound"}}], False, [])
        self.assertEqual(actual["included"], [("p1", "db", "data"), ("p2", "db", "data")])

    def test_registry_exclusion_covers_a_live_pvc_volume_without_pod_annotation(self):
        pod = {"metadata": {"uid": "p1"}, "status": {"phase": "Running"}, "spec": {
            "containers": [{"volumeMounts": [{"name": "media"}]}],
            "volumes": [{"name": "media", "persistentVolumeClaim": {"claimName": "library"}}]}}
        policy = presync.volume_policy([pod], [{"metadata": {"name": "library"}, "status": {"phase": "Bound"}}], False, ["media"])
        self.assertEqual(policy["excluded"], [("p1", "library", "media")])

    def test_generic_volume_policy_fails_closed_for_unconsumed_claim(self):
        with self.assertRaises(ValueError):
            presync.volume_policy([], [{"metadata": {"name": "db"}, "status": {"phase": "Bound"}}], False, [])
        result = presync.volume_policy([], [{"metadata": {"name": "db"}, "status": {"phase": "Bound"}}], False, ["db"])
        self.assertEqual(result["excluded_claims"], ["db"])

    def test_generic_hook_policy_requires_exact_attempt_count(self):
        annotation = {"pre.hook.backup.velero.io/command": '["/bin/sh", "-c", "dump"]',
                      "pre.hook.backup.velero.io/container": "db", "pre.hook.backup.velero.io/on-error": "Fail"}
        pod = {"metadata": {"name": "db-0", "labels": {"app": "db"}, "annotations": annotation}}
        expected = [{"selector": {"app": "db"}, "container": "db"}]
        identities = presync.backup_hook_policy([pod], expected)
        self.assertEqual(len(identities), 1)
        self.assertTrue(presync.validate_hook_status({"status": {"hookStatus": {"hooksAttempted": 1, "hooksFailed": 0}}}, identities))
        self.assertFalse(presync.validate_hook_status({"status": {"hookStatus": {"hooksAttempted": 0, "hooksFailed": 0}}}, identities))

    def test_no_required_hooks_accepts_missing_hook_status(self):
        self.assertTrue(presync.validate_hook_status({"status": {}}, []))

    def test_multi_source_baseline_allows_only_appended_gate_source(self):
        base = {"repoURL": "repo", "targetRevision": "main", "path": "app"}
        gate = {"repoURL": "repo", "targetRevision": "main", "path": "kubernetes/apps/presync-gate/chart", "ref": "gate"}
        previous = {**base, "path": "other"}
        app = {"spec": {"sources": [base, gate]}, "status": {"history": [{"revisions": ["a" * 40], "sources": [base]}]}}
        plan = presync.baseline_sources(app)
        self.assertEqual(plan["revisions"], ["a" * 40])
        self.assertEqual(plan["source_positions"], [1])
        app["status"]["history"][0]["sources"] = [previous]
        self.assertIsNone(presync.baseline_sources(app))
        app["status"]["history"][0]["sources"] = [base, {**gate, "path": "wrong"}]
        app["status"]["history"][0]["revisions"] = ["a" * 40, "b" * 40]
        self.assertIsNone(presync.baseline_sources(app))

    def test_rejects_changed_historical_source(self):
        current = {"repoURL": "repo", "targetRevision": "main", "path": "chart"}
        prior = {**current, "path": "other"}
        app = {"spec": {"source": current}, "status": {"history": [{"revision": "a" * 40, "source": prior}]}}
        self.assertIsNone(presync.baseline_revision(app))
        app["status"]["history"][0]["source"] = current
        self.assertEqual(presync.baseline_revision(app), "a" * 40)
        app["status"]["history"][0]["revision"] = "main"
        self.assertIsNone(presync.baseline_revision(app))
        app["status"]["history"][0]["revision"] = "a" * 40
        app["spec"]["ignoreDifferences"] = [{"group": "apps", "kind": "Deployment"}]
        self.assertIsNone(presync.baseline_revision(app))
        app["spec"].pop("ignoreDifferences")
        app["status"]["history"] = []
        self.assertIsNone(presync.baseline_revision(app))

    def test_miniflux_dump_hook_must_be_configured_and_attempted(self):
        pod = {"metadata": {"name": "miniflux-db-0", "annotations": {"pre.hook.backup.velero.io/container": "miniflux-db", "pre.hook.backup.velero.io/command": '["/bin/sh", "-c", "pg_dump -d miniflux > $PGDATA/dump.sql.tmp && mv $PGDATA/dump.sql.tmp $PGDATA/dump.sql"]' }}}
        backup = {"status": {"hookStatus": {"hooksAttempted": 1}}}
        expected = pod["metadata"]["annotations"].copy()
        self.assertTrue(presync.miniflux_dump_hook_observed(backup, [pod], expected))
        self.assertFalse(presync.miniflux_dump_hook_observed(backup, [pod], {**expected, "pre.hook.backup.velero.io/command": "echo pg_dump"}))
        self.assertFalse(presync.miniflux_dump_hook_observed({"status": {}}, [pod], expected))
        self.assertFalse(presync.miniflux_dump_hook_observed({"status": {"hookStatus": {"hooksAttempted": 1, "hooksFailed": 1}}}, [pod], expected))
        self.assertFalse(presync.miniflux_dump_hook_observed(backup, [], expected))
        pod["metadata"]["annotations"]["pre.hook.backup.velero.io/command"] = "echo pg_dump"
        expected["pre.hook.backup.velero.io/command"] = "echo pg_dump"
        self.assertFalse(presync.miniflux_dump_hook_observed(backup, [pod], expected))
        pod["metadata"]["annotations"]["pre.hook.backup.velero.io/on-error"] = "Continue"
        expected["pre.hook.backup.velero.io/on-error"] = "Continue"
        self.assertFalse(presync.miniflux_dump_hook_observed(backup, [pod], expected))

    def test_backup_fails_if_required_claim_is_missing(self):
        backup = {"metadata": {"uid": "backup"}, "status": {"phase": "Completed"}}
        self.assertFalse(presync.validate_coverage(backup, ["db"], [], [], []))
        self.assertFalse(presync.validate_coverage(backup, [], [], [], []))
        pvc = {"metadata": {"name": "db", "uid": "claim"}, "status": {"phase": "Bound"}}
        pod = {"metadata": {"uid": "pod"}, "status": {"phase": "Running"}, "spec": {"containers": [{"volumeMounts": [{"name": "data"}]}], "volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": "db"}}]}}
        pvb = {"metadata": {"labels": {"velero.io/backup-uid": "backup", "velero.io/pvc-uid": "claim"}}, "spec": {"pod": {"uid": "pod"}, "volume": "data"}, "status": {"phase": "Completed", "progress": {"totalBytes": 1}}}
        self.assertTrue(presync.validate_coverage(backup, ["db"], [pvc], [pod], [pvb]))
        self.assertFalse(presync.validate_coverage(backup, ["db"], [pvc], [pod], []))

    def test_resolves_only_running_pod_volume_for_pvc(self):
        pod = {"metadata": {"uid": "pod"}, "status": {"phase": "Running"}, "spec": {"containers": [{"volumeMounts": [{"name": "data"}]}], "volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": "db"}}]}}
        self.assertEqual(presync.pvc_mount("db", [pod]), ("pod", "data"))
        self.assertIsNone(presync.pvc_mount("other", [pod]))
        self.assertIsNone(presync.pvc_mount("db", [pod, pod]))
        pod["spec"]["containers"] = []
        self.assertIsNone(presync.pvc_mount("db", [pod]))
        pod["spec"]["initContainers"] = [{"volumeMounts": [{"name": "data"}]}]
        self.assertIsNone(presync.pvc_mount("db", [pod]))
        pod["status"]["phase"] = "Pending"
        self.assertIsNone(presync.pvc_mount("db", [pod]))

    def test_backup_must_complete_without_errors(self):
        self.assertTrue(presync.backup_succeeded({"status": {"phase": "Completed", "errors": 0}}))
        for status in ({"phase": "PartiallyFailed", "errors": 0}, {"phase": "Completed", "errors": 1}, {"phase": "InProgress"}):
            self.assertFalse(presync.backup_succeeded({"status": status}))

    def test_valid_completed_volume(self):
        pvb = {"metadata": {"labels": {"velero.io/backup-uid": "b", "velero.io/pvc-uid": "p"}}, "spec": {"pod": {"uid": "pod"}, "volume": "data"}, "status": {"phase": "Completed", "progress": {"totalBytes": 4}}}
        self.assertTrue(presync.covered("b", "p", "pod", "data", [pvb]))
        self.assertFalse(presync.covered("b", "p", "pod", "data", [pvb, pvb]))
        failed = {**pvb, "status": {"phase": "Failed"}}
        self.assertFalse(presync.covered("b", "p", "pod", "data", [pvb, failed]))
        for field, value in (("phase", "Failed"),):
            invalid = {**pvb, "status": {**pvb["status"], field: value}}
            self.assertFalse(presync.covered("b", "p", "pod", "data", [invalid]))
        self.assertFalse(presync.covered("other", "p", "pod", "data", [pvb]))
        self.assertFalse(presync.covered("b", "other", "pod", "data", [pvb]))
        self.assertFalse(presync.covered("b", "p", "other", "data", [pvb]))
        self.assertFalse(presync.covered("b", "p", "pod", "other", [pvb]))

    def test_zero_byte_completed_volume_is_valid(self):
        pvb = {"metadata": {"labels": {"velero.io/backup-uid": "b", "velero.io/pvc-uid": "p"}}, "spec": {"pod": {"uid": "pod"}, "volume": "data"}, "status": {"phase": "Completed", "progress": {"totalBytes": 0}}}
        self.assertTrue(presync.covered("b", "p", "pod", "data", [pvb]))


if __name__ == "__main__":
    unittest.main()
