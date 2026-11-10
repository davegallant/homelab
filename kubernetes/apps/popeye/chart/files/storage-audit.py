#!/usr/bin/env python3
"""Report storage candidates using read-only APIs; never mutate or delete."""
import json
import os
from pathlib import Path, PurePosixPath
import ssl
import time
import urllib.parse
import urllib.request


def claim_refs(value):
    if isinstance(value, dict):
        if 'persistentVolumeClaim' in value:
            yield value['persistentVolumeClaim']['claimName']
        for child in value.values():
            yield from claim_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from claim_refs(child)


def local_path(volume):
    spec = volume['spec']
    return (spec.get('local') or spec.get('hostPath') or {}).get('path')


def nodes(volume):
    terms = volume['spec'].get('nodeAffinity', {}).get('required', {}).get('nodeSelectorTerms', [])
    selected = set()
    for term in terms:
        matches = [e for e in term.get('matchExpressions', [])
                   if e['key'] == 'kubernetes.io/hostname' and e['operator'] == 'In']
        if not matches:
            return set()  # Unknown placement: conservatively allow overlap.
        selected.update(matches[0]['values'])
    return selected


def audit(volumes, claims, workloads):
    by_claim = {(c['metadata']['namespace'], c['metadata']['name']): c for c in claims}
    referenced = {(o['metadata'].get('namespace'), name)
                  for o in workloads for name in claim_refs(o.get('spec', {}))}
    # Retained StatefulSet claims remain intentional even after scale-to-zero.
    for workload in workloads:
        if workload.get('kind') != 'StatefulSet':
            continue
        meta = workload['metadata']
        for template in workload.get('spec', {}).get('volumeClaimTemplates', []):
            prefix = template['metadata']['name'] + '-' + meta['name'] + '-'
            for namespace, name in by_claim:
                if namespace == meta.get('namespace') and name.startswith(prefix) and name[len(prefix):].isdigit():
                    referenced.add((namespace, name))
    result = {'released_volumes': [], 'unreferenced_claims': [], 'path_overlaps': []}
    for volume in volumes:
        if volume.get('status', {}).get('phase') != 'Released':
            continue
        old = volume['spec'].get('claimRef', {})
        current = by_claim.get((old.get('namespace'), old.get('name')), {})
        result['released_volumes'].append({
            'pv': volume['metadata']['name'], 'former_claim': old.get('namespace', '') + '/' + old.get('name', ''),
            'claim_uid_matches': bool(old.get('uid')) and current.get('metadata', {}).get('uid') == old['uid'],
            'path': local_path(volume), 'nodes': sorted(nodes(volume))})
    result['unreferenced_claims'] = sorted(f'{ns}/{name}' for ns, name in by_claim if (ns, name) not in referenced)
    local = [v for v in volumes if local_path(v)]
    for i, first in enumerate(local):
        for second in local[i + 1:]:
            first_nodes, second_nodes = nodes(first), nodes(second)
            if first_nodes and second_nodes and not first_nodes.intersection(second_nodes):
                continue
            a, b = PurePosixPath(local_path(first)), PurePosixPath(local_path(second))
            if a == b or a in b.parents or b in a.parents:
                result['path_overlaps'].append([first['metadata']['name'], second['metadata']['name']])
    return result


def storage_metrics(report, timestamp):
    metrics = {
        'homelab_storage_actionable_released_volumes': report['actionable_released_count'],
        'homelab_storage_unreferenced_claims': report['unreferenced_claim_count'],
        'homelab_storage_path_overlaps': report['path_overlap_count'],
        'homelab_cluster_audit_timestamp_seconds': timestamp,
    }
    return ''.join(f'{name}{{cluster="homelab"}} {value}\n' for name, value in metrics.items())


def main():
    base = 'https://' + os.environ['KUBERNETES_SERVICE_HOST'] + ':' + os.environ.get('KUBERNETES_SERVICE_PORT_HTTPS', '443')
    identity = Path('/var/run/secrets/kubernetes.io/serviceaccount')
    token = (identity / 'token').read_text().strip()
    context = ssl.create_default_context(cafile=str(identity / 'ca.crt'))

    def items(path):
        values, continuation = [], ''
        while True:
            query = urllib.parse.urlencode({'limit': 500, 'continue': continuation})
            request = urllib.request.Request(base + path + '?' + query, headers={'Authorization': 'Bearer ' + token})
            with urllib.request.urlopen(request, context=context, timeout=30) as response:
                page = json.load(response)
            values.extend(page['items'])
            continuation = page.get('metadata', {}).get('continue', '')
            if not continuation:
                return values

    workloads = []
    for path in ['/api/v1/pods', '/apis/apps/v1/deployments', '/apis/apps/v1/statefulsets',
                 '/apis/apps/v1/daemonsets', '/apis/batch/v1/cronjobs', '/apis/batch/v1/jobs']:
        workloads.extend(items(path))
    result = audit(items('/api/v1/persistentvolumes'), items('/api/v1/persistentvolumeclaims'), workloads)
    retained = json.loads(Path('/app/retained-volumes.json').read_text())
    for volume in result['released_volumes']:
        volume['retention_reason'] = retained.get(volume['pv'])
    result['actionable_released_count'] = sum(not v['retention_reason'] for v in result['released_volumes'])
    result['unreferenced_claim_count'] = len(result['unreferenced_claims'])
    result['path_overlap_count'] = len(result['path_overlaps'])
    print(json.dumps(result), flush=True)
    payload = storage_metrics(result, int(time.time())).encode()
    request = urllib.request.Request(
        os.environ['PUSHGATEWAY_URL'] + '/metrics/job/homelab_storage_audit/instance/homelab',
        data=payload, method='PUT', headers={'Content-Type': 'text/plain; version=0.0.4'})
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()


if __name__ == '__main__':
    main()
