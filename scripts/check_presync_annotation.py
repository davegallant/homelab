#!/usr/bin/env python3
"""Check annotated applications' actual Helm render for a pre-sync gate."""

from pathlib import Path
import subprocess
import sys
import tempfile

import yaml

ANNOTATION = "homelab.davegallant.ca/pre-sync-backup"
HOOK_LABEL = "homelab.davegallant.ca/pre-sync-backup"


def valid(application, gate_enabled):
    policy = application.get("metadata", {}).get("annotations", {}).get(ANNOTATION)
    return policy in {"enabled", "disabled"} and gate_enabled == (policy == "enabled")


GATE_CHART = "kubernetes/apps/presync-gate/chart"


def gate_source(application):
    spec = application.get("spec", {})
    sources = spec.get("sources")
    if sources is None:
        sources = [spec.get("source", {})]
    return next((source for source in sources if source.get("path") == GATE_CHART), None)


def registry_matches(application, registry):
    name = application.get("metadata", {}).get("name")
    entry = registry.get(name)
    source = gate_source(application)
    if not entry or not source:
        return False
    values = source.get("helm", {}).get("valuesObject", {})
    expected = {"project": application.get("spec", {}).get("project"),
                "application": name,
                "targetNamespace": application.get("spec", {}).get("destination", {}).get("namespace"),
                "gateNamespace": "presync-gate",
                "requiredHooks": [], "excludedVolumes": [], "scheduleName": "",
                "defaultVolumesToFsBackup": False}
    expected.update({key: values.get(key, default) for key, default in expected.items() if key not in {"project", "application", "targetNamespace", "gateNamespace"}})
    return entry == expected and values == {key: value for key, value in expected.items() if key != "project"}


def project_covers_registry(project, registry):
    """Check that the dedicated gate project can deploy only its required resource types."""
    if project.get("metadata", {}).get("name") != registry.get("presync-gate", {}).get("project"):
        return False
    spec = project.get("spec", {})
    destinations = {item.get("namespace") for item in spec.get("destinations", [])}
    required_namespaces = {entry["targetNamespace"] for entry in registry.values()} | {"presync-gate"}
    if not required_namespaces.issubset(destinations):
        return False
    cluster_resources = {
        (item.get("group", ""), item.get("kind"))
        for item in spec.get("clusterResourceWhitelist", [])
    }
    namespaced_resources = {
        (item.get("group", ""), item.get("kind"))
        for item in spec.get("namespaceResourceWhitelist", [])
    }
    return (
        {("", "Namespace"), ("admissionregistration.k8s.io", "ValidatingAdmissionPolicy"),
         ("admissionregistration.k8s.io", "ValidatingAdmissionPolicyBinding")}.issubset(cluster_resources)
        and {("", "ServiceAccount"), ("", "ConfigMap"), ("rbac.authorization.k8s.io", "Role"),
             ("rbac.authorization.k8s.io", "RoleBinding"), ("batch", "Job"),
             ("cilium.io", "CiliumNetworkPolicy")}.issubset(namespaced_resources)
    )


def render_gate(application, source, root):
    chart = (root / source["path"]).resolve()
    if not chart.is_relative_to(root.resolve()):
        raise ValueError("chart outside repository")
    values = source.get("helm", {}).get("valuesObject", {})
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as values_file:
        yaml.safe_dump(values, values_file)
        values_file.flush()
        command = ["helm", "template", application["metadata"]["name"], str(chart),
                   "--namespace", values.get("gateNamespace", "presync-gate"), "--values", values_file.name]
        rendered = subprocess.run(command, check=True, capture_output=True, text=True).stdout
    jobs = [item for item in yaml.safe_load_all(rendered) if item and item.get("kind") == "Job"]
    expected = "presync-" + application["metadata"]["name"] + "-backup"
    if len(jobs) != 1 or jobs[0].get("metadata", {}).get("name") != expected:
        raise ValueError("shared chart must render exactly one app-specific gate Job")
    if jobs[0].get("metadata", {}).get("namespace") != values.get("gateNamespace", "presync-gate"):
        raise ValueError("gate Job is not in the shared namespace")
    if jobs[0].get("metadata", {}).get("annotations", {}).get("argocd.argoproj.io/hook") != "PreSync":
        raise ValueError("gate Job is not a PreSync hook")
    return True


def enabled(application, root):
    shared = gate_source(application)
    if shared:
        return render_gate(application, shared, root)
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
    registry_resource = yaml.safe_load((root / "kubernetes/apps/presync-gate/applications.yaml").read_text())
    registry = yaml.safe_load(registry_resource["data"]["applications.yaml"])["applications"]
    project = yaml.safe_load((root / "kubernetes/apps/argocd/project-presync-gate.yaml").read_text())
    if not project_covers_registry(project, registry):
        print("Pre-sync gate AppProject does not cover the registered namespaces/resources", file=sys.stderr)
        return 1
    failed = []
    for path in sorted(apps.glob("*.yaml")):
        app = yaml.safe_load(path.read_text())
        if not app or app.get("kind") != "Application":
            continue
        try:
            policy = app.get("metadata", {}).get("annotations", {}).get(ANNOTATION)
            shared = gate_source(app)
            if policy == "enabled":
                okay = registry_matches(app, registry) and enabled(app, root)
            elif policy == "disabled":
                okay = not shared and app["metadata"]["name"] not in registry
            else:
                okay = False
            if not okay or not valid(app, shared is not None):
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
