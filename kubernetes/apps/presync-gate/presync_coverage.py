"""Validate that a Velero pod-volume backup covers a specific live volume."""


def covered(backup_uid, pvc_uid, pod_uid, volume, backups):
    """Return whether this exact backup includes a completed, nonempty volume."""
    if not all((backup_uid, pvc_uid, pod_uid, volume)):
        return False
    matches = []
    for backup in backups:
        labels = backup.get("metadata", {}).get("labels", {})
        spec = backup.get("spec", {})
        if (labels.get("velero.io/backup-uid") == backup_uid
                and labels.get("velero.io/pvc-uid") == pvc_uid
                and spec.get("pod", {}).get("uid") == pod_uid
                and spec.get("volume") == volume):
            matches.append(backup)
    if len(matches) != 1:
        return False
    status = matches[0].get("status", {})
    size = status.get("progress", {}).get("totalBytes", 0)
    return status.get("phase") == "Completed" and isinstance(size, int) and not isinstance(size, bool) and size > 0



def baseline_revision(application):
    """Return the last full-sync revision only for an unchanged source."""
    spec = application.get("spec", {})
    if "sources" in spec or spec.get("ignoreDifferences"):
        return None
    source = spec.get("source")
    history = application.get("status", {}).get("history", [])
    if not source or not history:
        return None
    previous = history[-1]
    if previous.get("source") != source:
        return None
    revision = previous.get("revision")
    import re
    return revision if isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision) else None


def backup_succeeded(backup):
    """Require Velero completion without reported errors."""
    status = backup.get("status", {})
    return status.get("phase") == "Completed" and status.get("errors", 0) == 0


def pvc_mount(claim, pods):
    """Find a single running pod volume referencing a claim, or fail closed."""
    matches = []
    for pod in pods:
        metadata = pod.get("metadata", {})
        if pod.get("status", {}).get("phase") != "Running" or metadata.get("deletionTimestamp"):
            continue
        pod_spec = pod.get("spec", {})
        mounts = {mount.get("name") for container in pod_spec.get("containers", []) for mount in container.get("volumeMounts", [])}
        for volume in pod_spec.get("volumes", []):
            if volume.get("persistentVolumeClaim", {}).get("claimName") == claim:
                if not metadata.get("uid") or not volume.get("name") or volume["name"] not in mounts:
                    return None
                matches.append((metadata["uid"], volume["name"]))
    return matches[0] if len(matches) == 1 else None


def validate_coverage(backup, required_claims, claims, pods, pod_volume_backups):
    """Verify every required claim has a unique, successful volume backup."""
    backup_uid = backup.get("metadata", {}).get("uid")
    if not backup_uid or not backup_succeeded(backup) or not required_claims:
        return False
    if len(required_claims) != len(set(required_claims)):
        return False
    for claim in required_claims:
        matches = [item for item in claims if item.get("metadata", {}).get("name") == claim]
        if len(matches) != 1 or matches[0].get("status", {}).get("phase") != "Bound":
            return False
        pvc_uid = matches[0].get("metadata", {}).get("uid")
        mount = pvc_mount(claim, pods)
        if not mount or not covered(backup_uid, pvc_uid, *mount, pod_volume_backups):
            return False
    return True



def miniflux_dump_hook_observed(backup, pods, expected_annotations):
    """Require one Miniflux dump hook configuration and a successful attempt.

    This is a gate, not proof the dump contents are restorable.
    """
    hook_status = backup.get("status", {}).get("hookStatus", {})
    if hook_status.get("hooksAttempted") != 1 or hook_status.get("hooksFailed", 0) != 0:
        return False
    hooks = []
    for pod in pods:
        annotations = pod.get("metadata", {}).get("annotations", {})
        command = annotations.get("pre.hook.backup.velero.io/command")
        if command:
            keys = ("pre.hook.backup.velero.io/command", "pre.hook.backup.velero.io/container", "pre.hook.backup.velero.io/on-error")
            if any(annotations.get(key) != expected_annotations.get(key) for key in keys):
                return False
            if annotations.get("pre.hook.backup.velero.io/on-error", "Fail").lower() != "fail":
                return False
            hooks.append((pod.get("metadata", {}).get("name"), annotations.get("pre.hook.backup.velero.io/container"), command))
    if len(hooks) != 1 or hooks[0][:2] != ("miniflux-db-0", "miniflux-db"):
        return False
    import json
    try:
        command = json.loads(hooks[0][2])
    except (TypeError, ValueError):
        return False
    return (isinstance(command, list) and len(command) == 3 and command[:2] == ["/bin/sh", "-c"]
            and isinstance(command[2], str) and "pg_dump " in command[2]
            and "dump.sql.tmp" in command[2] and "dump.sql" in command[2])
