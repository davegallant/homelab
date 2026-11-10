"""Check whether mounted claims are selected by a Velero schedule."""


def unselected_claims(namespace, pod, default_fs, exclusions, claim_templates=()):
    annotations = pod.get('metadata', {}).get('annotations', {}) or {}
    selected = {name.strip() for name in annotations.get('backup.velero.io/backup-volumes', '').split(',') if name.strip()}
    excluded = {name.strip() for name in annotations.get('backup.velero.io/backup-volumes-excludes', '').split(',') if name.strip()}
    missing = []
    volumes = list(pod.get('spec', {}).get('volumes', []) or [])
    volumes.extend({'name': claim['metadata']['name'], 'persistentVolumeClaim': {'claimName': claim['metadata']['name']}} for claim in claim_templates)
    for volume in volumes:
        claim = (volume.get('persistentVolumeClaim') or {}).get('claimName')
        if not claim:
            continue
        key = f'{namespace}/{claim}'
        if exclusions.get(key):
            continue
        if volume['name'] in selected or (default_fs and volume['name'] not in excluded):
            continue
        missing.append(key)
    return missing


def main():
    import importlib.util
    import json
    import os
    from pathlib import Path
    import sys
    import tempfile
    import yaml

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('renderer', root / 'scripts/check-rendered-pod-security.py')
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    schedule_defaults = {}
    for path in (root / 'kubernetes/apps/velero-schedules').glob('*.yaml'):
        schedule = yaml.safe_load(path.read_text())
        template = schedule.get('spec', {}).get('template', {})
        for namespace in template.get('includedNamespaces', []):
            schedule_defaults[namespace] = template.get('defaultVolumesToFsBackup', False)
    config = yaml.safe_load((root / 'kubernetes/apps/backup-watchdog/configmap.yaml').read_text())
    allow = json.loads(config['data']['allowlist.json'])
    exclusions = dict(allow.get('volumes', {}))
    exclusions.update(yaml.safe_load((root / 'kubernetes/backup-rendered-exclusions.yaml').read_text()) or {})
    suffixes = allow.get('volume_suffixes', [])
    findings = set()
    with tempfile.TemporaryDirectory(prefix='backup-render-') as tmp:
        env = dict(os.environ, HELM_CONFIG_HOME=tmp+'/config', HELM_CACHE_HOME=tmp+'/cache', HELM_DATA_HOME=tmp+'/data')
        for path in sorted((root / renderer.APP_DIR).glob('*.yaml')):
            for app in renderer.documents(path):
                if app.get('kind') != 'Application':
                    continue
                namespace = app.get('spec', {}).get('destination', {}).get('namespace', 'default')
                if namespace not in schedule_defaults:
                    continue
                sources = app['spec'].get('sources') or [app['spec'].get('source', {})]
                values_sources = {s['ref']: root for s in sources if s.get('ref') and s.get('repoURL', '').rstrip('/').endswith('homelab.git')}
                for source in sources:
                    if source.get('ref'):
                        continue
                    for doc in renderer.render_source(root, source, namespace, app['metadata']['name'], values_sources, env):
                        for metadata, pod_spec in renderer._CHECKER.workload_pod_spec(doc):
                            templates = doc.get('spec', {}).get('volumeClaimTemplates', []) if doc.get('kind') == 'StatefulSet' else []
                            for claim in unselected_claims(namespace, {'metadata': metadata, 'spec': pod_spec}, schedule_defaults[namespace], exclusions, templates):
                                if not any(claim.endswith(suffix) for suffix in suffixes):
                                    findings.add(claim)
    if findings:
        print('\n'.join(sorted(findings)), file=sys.stderr)
        return 1
    print('Rendered mounted claims are selected or explicitly excluded')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
