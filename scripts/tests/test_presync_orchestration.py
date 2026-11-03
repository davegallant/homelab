import importlib.util
from pathlib import Path
import unittest
import sys

sys.path.insert(0, str(Path(__file__).parents[2] / "kubernetes/apps/presync-gate"))

spec = importlib.util.spec_from_file_location("presync_orchestration", Path(__file__).parents[2] / "kubernetes/apps/presync-gate/presync_orchestration.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BackupGateTest(unittest.TestCase):
    def test_source_aware_diff_arguments_use_historical_source_positions(self):
        args = module.baseline_diff_args({"revisions": ["a" * 40, "b" * 40], "source_positions": [1, 2]})
        self.assertEqual(args, ["--revisions", "a" * 40, "--source-positions", "1", "--revisions", "b" * 40, "--source-positions", "2"])

    def test_schedule_discovery_requires_one_matching_schedule(self):
        schedules = [{"metadata": {"name": "daily"}, "spec": {"template": {"includedNamespaces": ["ns", "other"]}}}]
        self.assertEqual(module.matching_schedule(schedules, "ns"), schedules[0])
        self.assertIsNone(module.matching_schedule([], "ns"))
        self.assertRaises(ValueError, module.matching_schedule, schedules * 2, "ns")

    def test_backup_builder_is_namespace_scoped_and_resources_only_without_schedule(self):
        request = module.build_backup(None, "reader", "reader-ns", "a" * 40)
        self.assertEqual(request["spec"]["includedNamespaces"], ["reader-ns"])
        self.assertEqual(request["spec"]["defaultVolumesToFsBackup"], False)
        self.assertEqual(request["spec"]["excludedResources"], ["secrets"])
        self.assertEqual(request["spec"]["ttl"], "168h")

    def test_backup_builder_copies_only_safe_schedule_fields(self):
        schedule = {"spec": {"template": {"includedNamespaces": ["app"], "excludedResources": ["secrets"], "defaultVolumesToFsBackup": True,
                  "storageLocation": "default", "ttl": "336h", "labelSelector": {"matchLabels": {"unsafe": "yes"}}, "hooks": {"resources": [{}]}}}}
        request = module.build_backup(schedule, "reader", "app", "a" * 40)
        self.assertEqual(request["spec"]["includedNamespaces"], ["app"])
        self.assertNotIn("labelSelector", request["spec"])
        self.assertNotIn("hooks", request["spec"])
        self.assertEqual(request["spec"]["defaultVolumesToFsBackup"], True)

    def test_redirect_handler_never_forwards_credentials(self):
        handler = module.NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", {}, "https://other.example/"))

    def test_gate_stops_when_backup_fails(self):
        comparisons = []
        self.assertFalse(module.run_gate("a" * 40, lambda rev: comparisons.append(rev) or True, lambda: False))
        self.assertEqual(comparisons, ["a" * 40])

    def test_gate_compares_baseline_both_before_and_after_backup(self):
        calls = []
        def compare(revision):
            calls.append(revision)
            return len(calls) == 1
        backup_calls = []
        result = module.run_gate("a" * 40, compare, lambda: backup_calls.append(True) or True)
        self.assertFalse(result)
        self.assertEqual(calls, ["a" * 40, "a" * 40])
        self.assertEqual(backup_calls, [True])
        self.assertFalse(module.run_gate("a" * 40, lambda _: False, lambda: self.fail("backup should not run")))

    def test_full_backup_checks_dump_hook_and_volume(self):
        class FakeAPI:
            hook_attempted = 1
            def request(self, method, path, payload=None):
                if method == "POST":
                    return {"metadata": {"name": "presync-miniflux-a", "uid": "backup"}}
                if path.endswith("/presync-miniflux-a"):
                    return {"metadata": {"uid": "backup"}, "status": {"phase": "Completed", "hookStatus": {"hooksAttempted": self.hook_attempted}}}
                if path.endswith("/statefulsets/miniflux-db"):
                    return {"spec": {"template": {"metadata": {"annotations": {"pre.hook.backup.velero.io/command": '["/bin/sh", "-c", "pg_dump > $PGDATA/dump.sql.tmp && mv $PGDATA/dump.sql.tmp $PGDATA/dump.sql"]' , "pre.hook.backup.velero.io/container": "miniflux-db"}}}}}
                if path.endswith("persistentvolumeclaims"):
                    return {"items": [{"metadata": {"name": "db", "uid": "pvc"}, "status": {"phase": "Bound"}}]}
                if path.endswith("/pods"):
                    return {"items": [{"metadata": {"name": "miniflux-db-0", "uid": "pod", "annotations": {"pre.hook.backup.velero.io/command": '["/bin/sh", "-c", "pg_dump > $PGDATA/dump.sql.tmp && mv $PGDATA/dump.sql.tmp $PGDATA/dump.sql"]' , "pre.hook.backup.velero.io/container": "miniflux-db", "backup.velero.io/backup-volumes": "data"}}, "status": {"phase": "Running"}, "spec": {"containers": [{"volumeMounts": [{"name": "data"}]}], "volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": "db"}}]}}]}
                return {"items": [{"metadata": {"labels": {"velero.io/backup-uid": "backup", "velero.io/pvc-uid": "pvc"}}, "spec": {"pod": {"uid": "pod"}, "volume": "data"}, "status": {"phase": "Completed", "progress": {"totalBytes": 1}}}]}
        schedule = {"spec": {"template": {"includedNamespaces": ["miniflux"], "excludedResources": ["secrets"]}}}
        api = FakeAPI()
        self.assertTrue(module.run_backup(api, schedule, "miniflux", "a" * 40, ["db"], 1, lambda: None,
                                          application="miniflux", required_hooks=[{"selector": {}, "container": "miniflux-db"}]))
        api.hook_attempted = 0
        self.assertFalse(module.run_backup(api, schedule, "miniflux", "a" * 40, ["db"], 1, lambda: None,
                                           application="miniflux", required_hooks=[{"selector": {}, "container": "miniflux-db"}]))

    def test_rejects_malformed_server_generated_backup_name(self):
        class FakeAPI:
            def request(self, method, path, payload=None):
                if method == "POST":
                    return {"metadata": {"name": "other-backup", "uid": "backup"}}
                self.fail("must not request another path")
        schedule = {"spec": {"template": {"includedNamespaces": ["miniflux"], "excludedResources": ["secrets"]}}}
        with self.assertRaises(ValueError):
            module.run_backup(FakeAPI(), schedule, "miniflux", "a" * 40, ["db"], 1, lambda: None)

    def test_rejects_recreated_backup_with_same_name(self):
        class FakeAPI:
            def request(self, method, path, payload=None):
                if method == "POST":
                    return {"metadata": {"name": "presync-miniflux-a", "uid": "original"}}
                return {"metadata": {"uid": "replacement"}, "status": {"phase": "Completed"}}
        schedule = {"spec": {"template": {"includedNamespaces": ["miniflux"], "excludedResources": ["secrets"]}}}
        self.assertFalse(module.run_backup(FakeAPI(), schedule, "miniflux", "a" * 40, ["db"], 1, lambda: None))

    def test_full_backup_fails_closed_when_no_required_volume_is_backed_up(self):
        class FakeAPI:
            def request(self, method, path, payload=None):
                if method == "POST":
                    return {"metadata": {"name": "presync-miniflux-a", "uid": "backup"}}
                if path.endswith("/presync-miniflux-a"):
                    return {"metadata": {"uid": "backup"}, "status": {"phase": "Completed"}}
                return {"items": []}
        schedule = {"spec": {"template": {"includedNamespaces": ["miniflux"], "excludedResources": ["secrets"]}}}
        self.assertFalse(module.run_backup(FakeAPI(), schedule, "miniflux", "a" * 40, ["db"], 1, lambda: None))

    def test_api_rejects_external_url_and_non_json_payload(self):
        client = module.KubernetesAPI("https://kubernetes.default.svc", "token", None)
        with self.assertRaises(ValueError):
            client.request("GET", "https://example.com/steal")

    def test_api_request_posts_only_to_velero_backups(self):
        class FakeAPI:
            def __init__(self): self.requests = []
            def request(self, method, path, payload=None):
                self.requests.append((method, path, payload))
                return {"metadata": {"name": "presync-miniflux-123"}}
        api = FakeAPI()
        schedule = {"spec": {"template": {"includedNamespaces": ["miniflux"], "excludedResources": ["secrets"]}}}
        result = module.create_backup(api, schedule, "miniflux", "abc")
        self.assertEqual(result["metadata"]["name"], "presync-miniflux-123")
        self.assertEqual(api.requests[0][:2], ("POST", "/apis/velero.io/v1/namespaces/velero/backups"))

    def test_list_scope_is_namespace_and_backup_specific(self):
        class FakeAPI:
            def __init__(self): self.paths = []
            def request(self, method, path, payload=None):
                self.paths.append(path)
                return {"items": []}
        api = FakeAPI()
        module.read_coverage_inputs(api, "miniflux", "presync-miniflux-123")
        self.assertEqual(api.paths, ["/api/v1/namespaces/miniflux/persistentvolumeclaims", "/api/v1/namespaces/miniflux/pods", "/apis/velero.io/v1/namespaces/velero/podvolumebackups?labelSelector=velero.io%2Fbackup-name%3Dpresync-miniflux-123"])
        with self.assertRaises(ValueError):
            module.read_coverage_inputs(api, "../velero", "x")

    def test_request_keeps_schedule_scope_and_records_baseline(self):
        schedule = {"spec": {"template": {"includedNamespaces": ["miniflux"], "excludedResources": ["secrets"], "ttl": "336h"}}}
        request = module.build_backup(schedule, "miniflux", "abc")
        self.assertEqual(request["spec"]["ttl"], "168h")
        self.assertEqual(request["spec"]["includedNamespaces"], ["miniflux"])
        self.assertEqual(request["metadata"]["annotations"]["homelab.davegallant.ca/previous-revision"], "abc")
        self.assertEqual(schedule["spec"]["template"]["ttl"], "336h")

    def test_request_rejects_schedule_outside_app_and_always_excludes_secrets(self):
        with self.assertRaises(ValueError):
            module.build_backup({"spec": {"template": {"includedNamespaces": ["other"]}}}, "miniflux", "abc")
        result = module.build_backup({"spec": {"template": {"includedNamespaces": ["miniflux"]}}}, "miniflux", "abc")
        self.assertIn("secrets", result["spec"]["excludedResources"])

    def test_success_waits_for_finished_backup_and_checks_coverage(self):
        states = iter([{"status": {"phase": "InProgress"}}, {"status": {"phase": "Completed"}}])
        checked = []
        result = module.wait_for_backup(lambda: next(states), lambda backup: checked.append(backup) or True, 3, lambda: None)
        self.assertTrue(result)
        self.assertEqual(len(checked), 1)

    def test_failure_or_timeout_never_passes(self):
        for phase in ("Failed", "PartiallyFailed"):
            self.assertFalse(module.wait_for_backup(lambda: {"status": {"phase": phase}}, lambda _: True, 3, lambda: None))
        self.assertFalse(module.wait_for_backup(lambda: {"status": {"phase": "InProgress"}}, lambda _: True, 2, lambda: None))
        self.assertFalse(module.wait_for_backup(lambda: {"status": {"phase": "Completed"}}, lambda _: False, 1, lambda: None))


if __name__ == "__main__":
    unittest.main()
