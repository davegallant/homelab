#!/usr/bin/env python3
"""Derived deployment inventory and read-only retirement candidates. Never deletes."""
import argparse
import json
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]


def unmounted_claims(claims, pods):
    mounted = {(pod['metadata']['namespace'], volume['persistentVolumeClaim']['claimName'])
               for pod in pods for volume in pod.get('spec', {}).get('volumes', [])
               if 'persistentVolumeClaim' in volume}
    return sorted(f"{c['metadata']['namespace']}/{c['metadata']['name']}" for c in claims
                  if (c['metadata']['namespace'], c['metadata']['name']) not in mounted)


def missing_owners(resources, applications):
    result = []
    for resource in resources:
        meta = resource['metadata']
        tracking = meta.get('annotations', {}).get('argocd.argoproj.io/tracking-id', '')
        owner = tracking.split(':', 1)[0]
        if tracking and owner not in applications:
            result.append(f"{resource['kind']} {meta.get('namespace', '-')}/{meta['name']} ({owner})")
    return sorted(result)


def inventory():
    result = []
    for path in sorted((ROOT / 'kubernetes/apps/argocd/applications').glob('*.yaml')):
        for doc in yaml.safe_load_all(path.read_text()):
            if not doc or doc.get('kind') != 'Application':
                continue
            result.append({'name': doc['metadata']['name'], 'owner': 'argocd',
                           'namespace': doc['spec']['destination'].get('namespace'),
                           'backup_policy': doc['metadata'].get('annotations', {}).get(
                               'homelab.davegallant.ca/backup-policy', 'platform-or-unclassified'),
                           'source': str(path.relative_to(ROOT))})
    for play in yaml.safe_load((ROOT / 'ansible/playbooks/main.yml').read_text()):
        source = play.get('import_playbook')
        if source:
            result.append({'name': source.split('/')[0], 'owner': 'ansible',
                           'source': f'ansible/playbooks/{source}'})
    return result


def kubectl(*args):
    return json.loads(subprocess.check_output(['kubectl', *args, '-o', 'json'], text=True, timeout=60))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Read current kubeconfig context; no mutations')
    args = parser.parse_args()
    report = {'tracked_deployments': inventory()}
    if args.live:
        config = kubectl('config', 'view', '--minify')
        report['context'] = config.get('current-context')
        report['server'] = config['clusters'][0]['cluster']['server']
        apps = kubectl('get', 'applications.argoproj.io', '-n', 'argocd')['items']
        claims = kubectl('get', 'pvc', '-A')['items']
        pods = kubectl('get', 'pods', '-A')['items']
        resources = kubectl('get', 'deployments,statefulsets,daemonsets,services,configmaps,persistentvolumeclaims', '-A')['items']
        report['unmounted_claim_candidates'] = unmounted_claims(claims, pods)
        report['missing_application_owner_candidates'] = missing_owners(resources, {a['metadata']['name'] for a in apps})
        report['warning'] = 'Candidates only: scaled-down workloads and retained rollback data may be intentional. No Secrets are queried.'
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
