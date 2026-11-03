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
    return status.get("phase") == "Completed" and isinstance(size, int) and not isinstance(size, bool) and size >= 0



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


def baseline_sources(application):
    """Map the last successful source history to current source positions.

    The only permitted source-set change is appending this repository's gate
    chart. Existing sources must remain byte-for-byte equivalent and ordered.
    """
    import re
    spec = application.get("spec", {})
    sources = spec.get("sources")
    if sources is None and isinstance(spec.get("source"), dict):
        sources = [spec["source"]]
    history = application.get("status", {}).get("history", [])
    if not isinstance(sources, list) or not sources or not history:
        return None
    prior = history[-1]
    old_sources = prior.get("sources")
    revisions = prior.get("revisions")
    if old_sources is None and isinstance(prior.get("source"), dict) and isinstance(prior.get("revision"), str):
        old_sources, revisions = [prior["source"]], [prior["revision"]]
    if not isinstance(old_sources, list) or not isinstance(revisions, list):
        return None
    if len(old_sources) != len(revisions) or not old_sources or len(sources) not in {len(old_sources), len(old_sources) + 1}:
        return None
    if sources[:len(old_sources)] != old_sources:
        return None
    if len(sources) == len(old_sources) + 1:
        gate = sources[-1]
        if gate.get("path") != "kubernetes/apps/presync-gate/chart":
            return None
    if any(not isinstance(revision, str) or not revision for revision in revisions):
        return None
    return {"revisions": revisions, "source_positions": list(range(1, len(revisions) + 1))}


def volume_policy(pods, claims, default_volumes_to_fs_backup, expected_exclusions):
    """Classify every PVC-backed Pod volume as included or explicitly excluded."""
    expected_exclusions = list(expected_exclusions or [])
    excluded_claims = {item for item in expected_exclusions if isinstance(item, str)}
    expected_exclusions = set(tuple(item) if isinstance(item, list) else item
                              for item in expected_exclusions if not isinstance(item, str))
    result = {"included": [], "excluded": [], "excluded_claims": []}
    seen_claims = set()
    for pod in pods:
        metadata = pod.get("metadata", {})
        if metadata.get("deletionTimestamp"):
            continue
        spec = pod.get("spec", {})
        status = pod.get("status", {}).get("phase")
        for volume in spec.get("volumes", []):
            pvc = volume.get("persistentVolumeClaim", {})
            claim, name = pvc.get("claimName"), volume.get("name")
            if not claim:
                continue
            if status != "Running":
                raise ValueError(f"PVC consumer {metadata.get('name')} is not running")
            if not metadata.get("uid") or not name:
                raise ValueError("PVC consumer is missing pod UID or volume name")
            refs = []
            for container in spec.get("containers", []) + spec.get("initContainers", []):
                refs += [m.get("name") for m in container.get("volumeMounts", [])]
                refs += [d.get("name") for d in container.get("volumeDevices", [])]
            if name not in refs:
                raise ValueError(f"PVC volume {metadata.get('name')}/{name} is not consumed")
            seen_claims.add(claim)
            annotations = metadata.get("annotations", {})
            included_names = set(filter(None, annotations.get("backup.velero.io/backup-volumes", "").split(",")))
            excluded_names = set(filter(None, annotations.get("backup.velero.io/backup-volumes-excludes", "").split(",")))
            explicit_exclusion = (claim in excluded_claims or name in excluded_claims or (claim, name) in expected_exclusions
                                  or (metadata["uid"], claim, name) in expected_exclusions or name in excluded_names)
            if name in included_names:
                result["included"].append((metadata["uid"], claim, name))
            elif explicit_exclusion:
                result["excluded"].append((metadata["uid"], claim, name))
            elif default_volumes_to_fs_backup and name not in excluded_names:
                result["included"].append((metadata["uid"], claim, name))
            else:
                raise ValueError(f"PVC volume {metadata.get('name')}/{name} has no explicit backup policy")
    for claim in claims:
        metadata = claim.get("metadata", {})
        if claim.get("status", {}).get("phase") == "Bound" and metadata.get("name") not in seen_claims:
            if metadata.get("name") in excluded_claims:
                result["excluded_claims"].append(metadata.get("name"))
            elif any(isinstance(item, tuple) and len(item) == 3 and item[1] == metadata.get("name") for item in expected_exclusions):
                result["excluded_claims"].append(metadata.get("name"))
            else:
                raise ValueError(f"Bound PVC {metadata.get('name')} has no live consumer")
    return result


def backup_hook_policy(pods, required_hooks):
    """Resolve required hook selectors against live pod hook annotations."""
    identities = []
    for required in required_hooks:
        matches = [pod for pod in pods if all(
            pod.get("metadata", {}).get("labels", {}).get(key) == value
            for key, value in required.get("selector", {}).items())]
        if len(matches) != 1:
            raise ValueError("required backup hook selector must match exactly one pod")
        pod = matches[0]
        annotations = pod.get("metadata", {}).get("annotations", {})
        command = annotations.get("pre.hook.backup.velero.io/command")
        if (not command or annotations.get("pre.hook.backup.velero.io/container") != required.get("container")
                or annotations.get("pre.hook.backup.velero.io/on-error", "Fail").lower() != "fail"):
            raise ValueError("required backup hook is not configured to fail closed")
        identities.append({"pod": pod["metadata"].get("name"), "container": required["container"], "command": command})
    return identities


def validate_hook_status(backup, expected_hook_identities):
    status = backup.get("status", {}).get("hookStatus", {})
    attempted = status.get("hooksAttempted", 0) if not expected_hook_identities else status.get("hooksAttempted")
    return (attempted == len(expected_hook_identities)
            and status.get("hooksFailed", 0) == 0)


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


def validate_expected_coverage(backup, expected_volumes, excluded_volumes, claims, pvbs):
    """Validate exact backup membership after volume_policy has classified pods."""
    backup_uid = backup.get("metadata", {}).get("uid")
    if not backup_uid or not backup_succeeded(backup):
        return False
    claim_uids = {item.get("metadata", {}).get("name"): item.get("metadata", {}).get("uid") for item in claims}
    for pod_uid, claim_name, volume in expected_volumes:
        pvc_uid = claim_uids.get(claim_name)
        if not pvc_uid or not covered(backup_uid, pvc_uid, pod_uid, volume, pvbs):
            return False
    for pod_uid, claim_name, volume in excluded_volumes:
        pvc_uid = claim_uids.get(claim_name)
        if not pvc_uid or any(
            item.get("metadata", {}).get("labels", {}).get("velero.io/backup-uid") == backup_uid
            and item.get("metadata", {}).get("labels", {}).get("velero.io/pvc-uid") == pvc_uid
            and item.get("spec", {}).get("pod", {}).get("uid") == pod_uid
            and item.get("spec", {}).get("volume") == volume for item in pvbs
        ):
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
