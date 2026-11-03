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


def build_backup(schedule, app, previous_revision):
    """Create a named Velero backup request from the existing schedule."""
    import copy

    if not app or not previous_revision:
        raise ValueError("application and previous revision are required")
    spec = copy.deepcopy(schedule["spec"]["template"])
    if spec.get("includedNamespaces") != [app] or "secrets" not in spec.get("excludedResources", []):
        raise ValueError("schedule must cover only the app namespace and exclude secrets")
    spec["ttl"] = "168h"
    return {
        "apiVersion": "velero.io/v1",
        "kind": "Backup",
        "metadata": {
            "generateName": f"presync-{app}-",
            "namespace": "velero",
            "labels": {"homelab.davegallant.ca/pre-sync-app": app},
            "annotations": {"homelab.davegallant.ca/previous-revision": previous_revision},
        },
        "spec": spec,
    }


def create_backup(api, schedule, app, previous_revision):
    """Submit a schedule-derived backup through the Kubernetes API."""
    return api.request(
        "POST", "/apis/velero.io/v1/namespaces/velero/backups",
        build_backup(schedule, app, previous_revision),
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


def run_backup(api, schedule, namespace, previous_revision, required_claims, max_polls, pause):
    """Create a backup and wait for verified coverage of required claims."""
    from presync_coverage import miniflux_dump_hook_observed, validate_coverage

    created = create_backup(api, schedule, namespace, previous_revision)
    name = created["metadata"]["name"]
    backup_uid = created["metadata"].get("uid")
    if not backup_uid:
        raise ValueError("backup UID missing from API response")
    import re
    if (not isinstance(name, str) or not name.startswith("presync-" + namespace + "-")
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
        if namespace != "miniflux":
            return False
        statefulset = api.request("GET", "/apis/apps/v1/namespaces/miniflux/statefulsets/miniflux-db")
        annotations = statefulset.get("spec", {}).get("template", {}).get("metadata", {}).get("annotations", {})
        return (miniflux_dump_hook_observed(backup, pods, annotations)
                and validate_coverage(backup, required_claims, claims, pods, pvbs))

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
    from presync_coverage import baseline_revision

    namespace = os.environ["PRESYNC_NAMESPACE"]
    app = os.environ["PRESYNC_APPLICATION"]
    schedule_name = os.environ["PRESYNC_SCHEDULE"]
    claims = os.environ["PRESYNC_CLAIMS"].split(",")
    pattern = r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?"
    if not all(re.fullmatch(pattern, value) for value in [namespace, app, schedule_name, *claims]):
        raise ValueError("invalid app, namespace, schedule or claim name")
    if app != namespace:
        raise ValueError("this pilot requires matching app and namespace names")
    account = Path("/var/run/secrets/kubernetes.io/serviceaccount")
    context = ssl.create_default_context(cafile=str(account / "ca.crt"))
    api = KubernetesAPI("https://kubernetes.default.svc", (account / "token").read_text().strip(), context)
    app_path = "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/" + app
    schedule_path = "/apis/velero.io/v1/namespaces/velero/schedules/" + schedule_name
    revision = baseline_revision(api.request("GET", app_path))
    if not revision:
        raise RuntimeError("unable to establish the previous revision")

    def compare(expected):
        if baseline_revision(api.request("GET", app_path)) != expected:
            return False
        result = subprocess.run(
            ["argocd", "app", "diff", app, "--revision", expected, "--server",
             os.environ["ARGOCD_SERVER"]],
            capture_output=True, timeout=180, check=False,
        )
        return result.returncode == 0

    def perform():
        schedule = api.request("GET", schedule_path)
        return run_backup(api, schedule, namespace, revision, claims, 180, lambda: time.sleep(10))

    if not run_gate(revision, compare, perform):
        raise RuntimeError("pre-sync backup gate failed; inspect backup and baseline")
    print("Pre-sync backup coverage and baseline verified", flush=True)


if __name__ == "__main__":
    main()
