"""Fail-closed waiting logic for pre-sync Velero backups."""

from urllib.request import HTTPRedirectHandler


def wait_for_backup(read_backup, verify_coverage, max_polls, pause):
    """Wait for completion and verify coverage, failing on errors or timeout."""
    for attempt in range(max_polls):
        backup = read_backup()
        phase = backup.get("status", {}).get("phase")
        if phase == "Completed":
            return backup.get("status", {}).get("errors", 0) == 0 and verify_coverage(backup)
        if phase in {"Failed", "PartiallyFailed", "FailedValidation", "Deleting"}:
            return False
        if attempt + 1 < max_polls:
            pause()
    return False


def matching_schedule(schedules, namespace):
    """Find the single Velero Schedule whose template includes namespace."""
    found = [item for item in schedules if namespace in
             item.get("spec", {}).get("template", {}).get("includedNamespaces", [])]
    if len(found) > 1:
        raise ValueError("more than one Velero Schedule includes the target namespace")
    return found[0] if found else None


def baseline_diff_args(plan):
    """Build repeated Argo CLI flags for source-specific history revisions."""
    args = []
    for revision, position in zip(plan["revisions"], plan["source_positions"]):
        args.extend(["--revisions", revision, "--source-positions", str(position)])
    return args


def build_backup(schedule, app, namespace, previous_revision=None, excluded_resources=()):
    """Build a narrowly scoped pre-sync backup from an optional Schedule."""
    if previous_revision is None:  # compatibility with the original pilot API
        previous_revision, namespace = namespace, app
    if not app or not namespace or not previous_revision:
        raise ValueError("application, namespace, and previous revision are required")
    template = (schedule or {}).get("spec", {}).get("template", {})
    included = template.get("includedNamespaces", [])
    if schedule and namespace not in included:
        raise ValueError("schedule does not cover the target namespace")
    resources = set(template.get("excludedResources", [])) | set(excluded_resources) | {"secrets"}
    if namespace == "velero":
        resources |= {"backups", "restores", "schedules", "podvolumebackups", "backuprepositories"}
    spec = {
        "includedNamespaces": [namespace],
        "excludedResources": sorted(resources),
        "defaultVolumesToFsBackup": bool(template.get("defaultVolumesToFsBackup", False)),
        "snapshotVolumes": False,
        "includeClusterResources": False,
        "ttl": "168h",
    }
    spec["storageLocation"] = template.get("storageLocation") or "default"
    return {
        "apiVersion": "velero.io/v1",
        "kind": "Backup",
        "metadata": {
            "generateName": f"presync-{app}-",
            "namespace": "velero",
            "labels": {"homelab.davegallant.ca/pre-sync-app": app,
                       "homelab.davegallant.ca/pre-sync-namespace": namespace},
            "annotations": {"homelab.davegallant.ca/previous-revision": previous_revision},
        },
        "spec": spec,
    }


def create_backup(api, schedule, app, namespace, previous_revision=None, excluded_resources=()):
    """Submit a schedule-derived backup through the Kubernetes API."""
    return api.request(
        "POST", "/apis/velero.io/v1/namespaces/velero/backups",
        build_backup(schedule, app, namespace, previous_revision, excluded_resources),
    )


class NoRedirect(HTTPRedirectHandler):
    """Never forward Kubernetes credentials to a redirected endpoint."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class KubernetesAPI:
    """Minimal in-cluster Kubernetes client using the service account CA."""

    def __init__(self, base_url, token, context):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.context = context

    def request(self, method, path, payload=None):
        import json
        import urllib.request

        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("API path must be absolute and local")
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            self.base_url + path, method=method, data=data,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=self.context))
        with opener.open(request, timeout=30) as response:
            return json.load(response)


def read_coverage_inputs(api, namespace, backup_name):
    """Read namespace-scoped claims and pods and backup-scoped volume backups."""
    import re
    from urllib.parse import urlencode

    pattern = r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?"
    if not re.fullmatch(pattern, namespace) or not re.fullmatch(pattern, backup_name):
        raise ValueError("invalid namespace or backup name")
    claims = api.request("GET", f"/api/v1/namespaces/{namespace}/persistentvolumeclaims")["items"]
    pods = api.request("GET", f"/api/v1/namespaces/{namespace}/pods")["items"]
    query = urlencode({"labelSelector": "velero.io/backup-name=" + backup_name})
    pvbs = api.request("GET", "/apis/velero.io/v1/namespaces/velero/podvolumebackups?" + query)["items"]
    return claims, pods, pvbs


def run_backup(api, schedule, namespace, previous_revision, required_claims, max_polls, pause,
               application=None, required_hooks=(), expected_exclusions=()):
    """Create a backup and verify every configured namespace volume and hook."""
    from presync_coverage import (backup_hook_policy, validate_expected_coverage,
                                 validate_hook_status, volume_policy)

    application = application or namespace
    created = create_backup(api, schedule, application, namespace, previous_revision)
    name = created["metadata"]["name"]
    backup_uid = created["metadata"].get("uid")
    if not backup_uid:
        raise ValueError("backup UID missing from API response")
    import re
    if (not isinstance(name, str) or not name.startswith("presync-" + application + "-")
            or not re.fullmatch(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", name)):
        raise ValueError("invalid backup name returned by API")
    print(f"Created pre-sync backup: {name}; previous revision: {previous_revision}", flush=True)
    path = "/apis/velero.io/v1/namespaces/velero/backups/" + name

    def read_backup():
        return api.request("GET", path)

    def verify(backup):
        if backup.get("metadata", {}).get("uid") != backup_uid:
            return False
        claims, pods, pvbs = read_coverage_inputs(api, namespace, name)
        try:
            policy = volume_policy(pods, claims, bool((schedule or {}).get("spec", {}).get("template", {}).get("defaultVolumesToFsBackup", False)), expected_exclusions)
            identities = backup_hook_policy(pods, required_hooks)
        except ValueError:
            return False
        if required_claims and not set(required_claims).issubset({c for _, c, _ in policy["included"]}):
            return False
        return (validate_hook_status(backup, identities)
                and validate_expected_coverage(backup, policy["included"], policy["excluded"], claims, pvbs))

    return wait_for_backup(read_backup, verify, max_polls, pause)


def run_gate(revision, compare_baseline, perform_backup):
    """Require the same verified baseline before and after a backup."""
    if not revision or not compare_baseline(revision):
        return False
    if not perform_backup():
        return False
    return bool(compare_baseline(revision))


def main():
    """Run the gate inside a pod using an in-cluster service account."""
    import os
    from pathlib import Path
    import re
    import ssl
    import subprocess
    import time
    import json
    from presync_coverage import baseline_sources

    namespace = os.environ["PRESYNC_NAMESPACE"]
    app = os.environ["PRESYNC_APPLICATION"]
    schedule_name = os.environ.get("PRESYNC_SCHEDULE", "")
    claims = [value for value in os.environ.get("PRESYNC_CLAIMS", "").split(",") if value]
    required_hooks = json.loads(os.environ.get("PRESYNC_REQUIRED_HOOKS", "[]"))
    excluded_volumes = json.loads(os.environ.get("PRESYNC_EXCLUDED_VOLUMES", "[]"))
    pattern = r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?"
    if not all(re.fullmatch(pattern, value) for value in [namespace, app, *claims]):
        raise ValueError("invalid app, namespace or claim name")
    account = Path("/var/run/secrets/kubernetes.io/serviceaccount")
    context = ssl.create_default_context(cafile=str(account / "ca.crt"))
    api = KubernetesAPI("https://kubernetes.default.svc", (account / "token").read_text().strip(), context)
    app_path = "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/" + app
    application = api.request("GET", app_path)
    baseline = baseline_sources(application)
    if not baseline:
        raise RuntimeError("unable to establish the previous revision")

    def compare(expected):
        if baseline_sources(api.request("GET", app_path)) != expected:
            return False
        result = subprocess.run(
            ["argocd", "--plaintext", "app", "diff", app, *baseline_diff_args(expected), "--server",
             os.environ["ARGOCD_SERVER"]],
            capture_output=True, timeout=180, check=False,
        )
        if result.returncode:
            detail = result.stderr.decode(errors="replace")
            detail = detail.replace(os.environ["ARGOCD_AUTH_TOKEN"], "[redacted]")
            print(f"Argo baseline diff failed ({result.returncode}): {detail[:500]}", flush=True)
        return result.returncode == 0

    def perform():
        schedule = None
        if schedule_name:
            if not re.fullmatch(pattern, schedule_name):
                raise ValueError("invalid schedule name")
            schedule = api.request("GET", "/apis/velero.io/v1/namespaces/velero/schedules/" + schedule_name)
            if namespace not in schedule.get("spec", {}).get("template", {}).get("includedNamespaces", []):
                raise ValueError("configured schedule does not include target namespace")
        return run_backup(api, schedule, namespace, " ".join(baseline["revisions"]), claims,
                          180, lambda: time.sleep(10), application=app,
                          required_hooks=required_hooks, expected_exclusions=excluded_volumes)

    if not run_gate(baseline, compare, perform):
        raise RuntimeError("pre-sync backup gate failed; inspect backup and baseline")
    print("Pre-sync backup coverage and baseline verified", flush=True)


if __name__ == "__main__":
    main()
