import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('service_audit', Path(__file__).resolve().parents[1] / 'service_audit.py')
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class ServiceAuditTest(unittest.TestCase):
    def test_only_unmounted_claims_are_candidates(self):
        claims = [{'metadata': {'namespace': 'app', 'name': 'used'}},
                  {'metadata': {'namespace': 'app', 'name': 'old'}}]
        pods = [{'metadata': {'namespace': 'app'}, 'spec': {'volumes': [
            {'persistentVolumeClaim': {'claimName': 'used'}}]}}]
        self.assertEqual(AUDIT.unmounted_claims(claims, pods), ['app/old'])

    def test_pending_pods_also_protect_claims(self):
        claims = [{'metadata': {'namespace': 'app', 'name': 'used'}}]
        pods = [{'metadata': {'namespace': 'app'}, 'status': {'phase': 'Pending'},
                 'spec': {'volumes': [{'persistentVolumeClaim': {'claimName': 'used'}}]}}]
        self.assertEqual(AUDIT.unmounted_claims(claims, pods), [])

    def test_missing_application_owner_requires_tracking_annotation(self):
        resources = [{'kind': 'Deployment', 'metadata': {'namespace': 'app', 'name': 'old',
                      'annotations': {'argocd.argoproj.io/tracking-id': 'retired:apps/Deployment:app/old'}}},
                     {'kind': 'Service', 'metadata': {'namespace': 'app', 'name': 'manual'}}]
        self.assertEqual(AUDIT.missing_owners(resources, {'current'}), ['Deployment app/old (retired)'])
