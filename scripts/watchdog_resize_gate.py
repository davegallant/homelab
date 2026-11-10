"""Validate fresh watchdog evidence for a reviewed resize exception."""

import json
import sys
from datetime import datetime, timedelta, timezone


def valid_evidence(job, report, cronjob, now):
    try:
        status = job['status']
        finished = datetime.fromisoformat(status['completionTime'].replace('Z', '+00:00'))
        generated = datetime.fromisoformat(report['generated_at'].replace('Z', '+00:00'))
        scheduled = datetime.fromisoformat(cronjob['status']['lastScheduleTime'].replace('Z', '+00:00'))
        spec = job['spec']['template']['spec']
        covered = report['covered_namespaces']
        checked = report['backups_checked']
        return (
            job['metadata']['labels'].get('app.kubernetes.io/name') == 'backup-watchdog'
            and spec.get('serviceAccountName') == 'backup-watchdog'
            and not cronjob.get('spec', {}).get('suspend', False)
            and any(c.get('command') == ['python3', '/app/check.py'] for c in spec.get('containers', []))
            and any(v.get('configMap', {}).get('name') == 'backup-watchdog' for v in spec.get('volumes', []))
            and status.get('succeeded', 0) >= 1
            and report['gaps'] == []
            and bool(covered)
            and all(checked.get(ns, {}).get('phase') == 'Completed' for ns in covered)
            and timedelta(0) <= now - finished <= timedelta(hours=1)
            and timedelta(0) <= now - generated <= timedelta(hours=1)
            and generated <= finished
            and scheduled <= generated
        )
    except (KeyError, TypeError, ValueError):
        return False


def main():
    try:
        evidence = json.load(sys.stdin)
        valid = valid_evidence(evidence['job'], evidence['report'], evidence['cronjob'], datetime.now(timezone.utc))
    except (KeyError, ValueError, TypeError):
        valid = False
    if not valid:
        print('Watchdog exception requires a successful, gap-free watchdog job from the last hour', file=sys.stderr)
        return 1
    print('Fresh watchdog evidence verified')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
