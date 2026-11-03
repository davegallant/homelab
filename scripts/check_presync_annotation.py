#!/usr/bin/env python3
"""Check annotated applications' actual Helm render for a pre-sync gate."""

from pathlib import Path
import subprocess
import sys

import yaml

ANNOTATION = "homelab.davegallant.ca/pre-sync-backup"
HOOK_LABEL = "homelab.davegallant.ca/pre-sync-backup"


def valid(application, gate_enabled):
    policy = application.get("metadata", {}).get("annotations", {}).get(ANNOTATION)
    return policy in {"enabled", "disabled"} and gate_enabled == (policy == "enabled")


def enabled(application, root):
    source = application["spec"]["source"]
    chart = (root / source["path"]).resolve()
    if not chart.is_relative_to(root.resolve()):
        raise ValueError("chart outside repository")
    helm = source.get("helm", {})
    name = helm.get("releaseName", application["metadata"]["name"])
    namespace = application["spec"]["destination"]["namespace"]
    command = ["helm", "template", name, str(chart), "--namespace", namespace]
    for value_file in helm.get("valueFiles", []):
        path = (chart / value_file).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("values file outside repository")
        command.extend(["--values", str(path)])
    for parameter in helm.get("parameters", []):
        command.extend(["--set-string" if parameter.get("forceString") else "--set", parameter["name"] + "=" + str(parameter["value"])])
    rendered = subprocess.run(command, check=True, capture_output=True, text=True).stdout
    jobs = [item for item in yaml.safe_load_all(rendered) if item and item.get("kind") == "Job" and item.get("metadata", {}).get("annotations", {}).get(HOOK_LABEL) == "true"]
    if jobs and jobs[0].get("metadata", {}).get("annotations", {}).get("argocd.argoproj.io/hook") != "PreSync":
        raise ValueError("gate Job is not a PreSync hook")
    if len(jobs) > 1:
        raise ValueError("more than one pre-sync gate rendered")
    return bool(jobs)


def main():
    root = Path(__file__).resolve().parents[1]
    apps = root / "kubernetes/apps/argocd/applications"
    failed = []
    for path in sorted(apps.glob("*.yaml")):
        app = yaml.safe_load(path.read_text())
        if not app or app.get("kind") != "Application" or ANNOTATION not in app.get("metadata", {}).get("annotations", {}):
            continue
        try:
            if not valid(app, enabled(app, root)):
                failed.append(path.name)
        except (KeyError, OSError, ValueError, subprocess.CalledProcessError):
            failed.append(path.name)
    if failed:
        print("Pre-sync annotation and rendered gate mismatch: " + ", ".join(failed), file=sys.stderr)
        return 1
    print("Pre-sync annotations match rendered Helm gates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
