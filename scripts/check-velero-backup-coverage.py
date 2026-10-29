#!/usr/bin/env python3
"""Require an explicit backup decision for every ordinary Argo CD app."""

from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
APPLICATIONS_DIR = ROOT / "kubernetes/apps/argocd/applications"
SCHEDULES_DIR = ROOT / "kubernetes/apps/velero-schedules"
POLICY_ANNOTATION = "homelab.davegallant.ca/backup-policy"


def fail(message: str) -> None:
    print(f"Velero backup coverage: {message}", file=sys.stderr)
    raise SystemExit(1)


apps = {}
for path in sorted(APPLICATIONS_DIR.glob("*.yaml")):
    application = yaml.safe_load(path.read_text())
    if application.get("kind") != "Application":
        continue
    if application.get("spec", {}).get("project") != "homelab":
        continue

    name = application["metadata"]["name"]
    namespace = application.get("spec", {}).get("destination", {}).get("namespace")
    policy = application.get("metadata", {}).get("annotations", {}).get(POLICY_ANNOTATION)
    if policy not in {"scheduled", "not-required"}:
        fail(f"{path.relative_to(ROOT)} must declare {POLICY_ANNOTATION}: scheduled|not-required")
    if not namespace:
        fail(f"{path.relative_to(ROOT)} has no destination namespace")
    apps[name] = {"namespace": namespace, "policy": policy}

schedule_targets = {}
for path in sorted(SCHEDULES_DIR.glob("*.yaml")):
    schedule = yaml.safe_load(path.read_text())
    if schedule.get("kind") != "Schedule" or schedule.get("metadata", {}).get("namespace") != "velero":
        fail(f"{path.relative_to(ROOT)} must define a Velero Schedule")
    name = schedule["metadata"]["name"]
    if name in schedule_targets:
        fail(f"duplicate Schedule name {name}")
    namespaces = schedule.get("spec", {}).get("template", {}).get("includedNamespaces", [])
    if not namespaces:
        fail(f"{name} has no includedNamespaces")
    for namespace in namespaces:
        if namespace in schedule_targets:
            fail(f"multiple central Schedules target namespace {namespace}")
        schedule_targets[namespace] = name

for name, app in apps.items():
    namespace = app["namespace"]
    has_schedule = namespace in schedule_targets
    if app["policy"] == "scheduled" and not has_schedule:
        fail(f"{name} declares scheduled backups but {namespace} has no Schedule")
    if app["policy"] == "not-required" and has_schedule:
        fail(f"{name} declares no backup schedule but {namespace} is targeted by {schedule_targets[namespace]}")

unmatched = set(schedule_targets) - {app["namespace"] for app in apps.values()}
if unmatched:
    fail(f"Schedules target namespaces without an ordinary homelab Application: {', '.join(sorted(unmatched))}")

print(f"Velero backup coverage is explicit for {len(apps)} homelab Applications; {len(schedule_targets)} namespaces have Schedules.")
