import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('storage_orphans', Path(__file__).resolve().parents[2] / 'kubernetes/apps/popeye/chart/files/storage-audit.py')
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def pv(name, path, node='w1', phase='Bound'):
    return {'metadata': {'name': name}, 'status': {'phase': phase}, 'spec': {
        'local': {'path': path}, 'nodeAffinity': {'required': {'nodeSelectorTerms': [
            {'matchExpressions': [{'key': 'kubernetes.io/hostname', 'operator': 'In', 'values': [node]}]}]}}}}


class StorageOrphansTest(unittest.TestCase):
    def test_released_is_reported_even_when_claim_name_has_been_reused(self):
        old = pv('old', '/old', phase='Released')
        old['spec']['claimRef'] = {'namespace': 'app', 'name': 'data', 'uid': 'old-uid'}
        claim = {'metadata': {'namespace': 'app', 'name': 'data', 'uid': 'new-uid'}}
        result = AUDIT.audit([old], [claim], [])
        self.assertEqual(result['released_volumes'][0]['pv'], 'old')
        self.assertFalse(result['released_volumes'][0]['claim_uid_matches'])

    def test_reports_shared_directory_and_parent_overlap(self):
        result = AUDIT.audit([pv('a', '/data'), pv('b', '/data'), pv('c', '/data/sub')], [], [])
        self.assertEqual(len(result['path_overlaps']), 3)

    def test_same_path_on_different_workers_is_not_an_alias(self):
        result = AUDIT.audit([pv('a', '/data', 'w1'), pv('b', '/data', 'w2')], [], [])
        self.assertEqual(result['path_overlaps'], [])

    def test_controller_reference_protects_claim_without_running_pod(self):
        claim = {'metadata': {'namespace': 'app', 'name': 'data'}}
        controller = {'metadata': {'namespace': 'app'}, 'spec': {'replicas': 0, 'template': {
            'spec': {'volumes': [{'persistentVolumeClaim': {'claimName': 'data'}}]}}}}
        self.assertEqual(AUDIT.audit([], [claim], [controller])['unreferenced_claims'], [])
        self.assertEqual(AUDIT.audit([], [claim], [])['unreferenced_claims'], ['app/data'])

    def test_reference_in_another_namespace_does_not_protect_claim(self):
        claim = {'metadata': {'namespace': 'app', 'name': 'data'}}
        pod = {'metadata': {'namespace': 'other'}, 'spec': {'volumes': [
            {'persistentVolumeClaim': {'claimName': 'data'}}]}}
        self.assertEqual(AUDIT.audit([], [claim], [pod])['unreferenced_claims'], ['app/data'])

    def test_scaled_down_statefulset_volume_template_protects_claim(self):
        claim = {'metadata': {'namespace': 'app', 'name': 'data-database-0'}}
        statefulset = {'kind': 'StatefulSet', 'metadata': {'namespace': 'app', 'name': 'database'},
                       'spec': {'replicas': 0, 'volumeClaimTemplates': [{'metadata': {'name': 'data'}}]}}
        self.assertEqual(AUDIT.audit([], [claim], [statefulset])['unreferenced_claims'], [])

    def test_storage_metrics_expose_freshness_and_actionable_counts(self):
        report = {'actionable_released_count': 2, 'unreferenced_claim_count': 3, 'path_overlap_count': 4}
        metrics = AUDIT.storage_metrics(report, 1234)
        self.assertIn('homelab_storage_actionable_released_volumes{cluster="homelab"} 2', metrics)
        self.assertIn('homelab_cluster_audit_timestamp_seconds{cluster="homelab"} 1234', metrics)
