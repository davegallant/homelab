#!/usr/bin/env python3
"""List candidate pre-sync backup points without mutating the cluster."""

import json
import re
import subprocess
import sys


def recovery_points(backups, app):
    """Return completed app-specific backups with immutable prior revisions."""
    points = []
    for backup in backups:
        metadata = backup.get("metadata", {})
        status = backup.get("status", {})
        revision = metadata.get("annotations", {}).get("homelab.davegallant.ca/previous-revision", "")
        if (metadata.get("labels", {}).get("homelab.davegallant.ca/pre-sync-app") == app
                and status.get("phase") == "Completed" and status.get("errors", 0) == 0
                and isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision)
                and metadata.get("name") and metadata.get("creationTimestamp") and status.get("expiration")):
            points.append({"name": metadata["name"], "revision": revision, "expires": status["expiration"], "created": metadata["creationTimestamp"]})
    return sorted(points, key=lambda point: point["created"], reverse=True)


def main():
    app = sys.argv[1] if len(sys.argv) == 2 else "miniflux"
    if app != "miniflux":
        raise SystemExit("Only Miniflux is supported by the pilot")
    result = subprocess.run(["kubectl", "-n", "velero", "get", "backups", "-o", "json"], check=True, capture_output=True, text=True)
    points = recovery_points(json.loads(result.stdout)["items"], app)
    if not points:
        print("No completed pre-sync backup candidates found.")
        return
    print("Candidate backup | previous revision | expires (UTC)")
    for point in points:
        print(f'{point["name"]} | {point["revision"]} | {point["expires"]}')
    print("Candidates require volume, hook, revision and restore verification; completion alone is not sufficient.")


if __name__ == "__main__":
    main()
