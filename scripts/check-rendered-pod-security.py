#!/usr/bin/env python3
"""Render Argo-managed workloads in Restricted namespaces and inspect their Pods."""

import argparse
import importlib.util
import os
import subprocess
import sys
import tempfile
from urllib.parse import urlparse
from pathlib import Path

import yaml

_CHECKER_SPEC = importlib.util.spec_from_file_location(
    "check_pod_security", Path(__file__).with_name("check-pod-security.py")
)
_CHECKER = importlib.util.module_from_spec(_CHECKER_SPEC)
_CHECKER_SPEC.loader.exec_module(_CHECKER)
inspect_documents = _CHECKER.inspect_documents


APP_DIR = Path("kubernetes/apps/argocd/applications")


def documents(path):
    return [item for item in yaml.safe_load_all(path.read_text(encoding="utf-8")) if isinstance(item, dict)]


def restricted_namespaces(root):
    result = set()
    for path in (root / "kubernetes/apps").rglob("*.yaml"):
        if "chart/templates" in path.as_posix():
            continue
        try:
            for item in documents(path):
                metadata = item.get("metadata", {})
                if item.get("kind") == "Namespace" and metadata.get("labels", {}).get(
                    "pod-security.kubernetes.io/enforce"
                ) == "restricted":
                    result.add(metadata.get("name"))
        except yaml.YAMLError:
            continue
    return result


def run(command, env, app_name):
    result = subprocess.run(command, check=False, capture_output=True, text=True, env=env)
    if result.returncode:
        # Helm and kubectl errors can include rendered values. Never echo their output.
        raise RuntimeError("{}: renderer exited {} ({})".format(app_name, result.returncode, command[0]))
    return result.stdout


def render_source(root, source, namespace, app_name, values_sources, env):
    path_value = source.get("path")
    chart = source.get("chart")
    helm = source.get("helm", {}) or {}
    command = None
    if chart or (path_value and (root / path_value / "Chart.yaml").is_file()):
        chart_ref = chart or str(root / path_value)
        command = ["helm", "template", helm.get("releaseName", app_name), chart_ref, "--namespace", namespace]
        if chart:
            repository = source["repoURL"]
            if repository.startswith("oci://") or not urlparse(repository).scheme:
                repository = repository.removeprefix("oci://")
                command[3] = repository.rstrip("/") + "/" + chart
                command[3] = "oci://" + command[3]
                command.extend(["--version", str(source["targetRevision"])])
            else:
                command.extend(["--repo", repository, "--version", str(source["targetRevision"])])
        for value_file in helm.get("valueFiles", []) or []:
            if value_file.startswith("$values/"):
                ref = value_file.split("/", 1)[0][1:]
                base = values_sources.get(ref)
                if base is None:
                    raise RuntimeError("{}: unresolved values source {}".format(app_name, ref))
                value_path = base / value_file.split("/", 1)[1]
            else:
                value_path = (root / path_value / value_file) if path_value else root / value_file
            command.extend(["--values", str(value_path)])
        if helm.get("values"):
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".yaml") as values_file:
                values_file.write(helm["values"])
                values_file.flush()
                command.extend(["--values", values_file.name])
                output = run(command, env, app_name)
        elif helm.get("valuesObject"):
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".yaml") as values_file:
                yaml.safe_dump(helm["valuesObject"], values_file)
                values_file.flush()
                command.extend(["--values", values_file.name])
                output = run(command, env, app_name)
        else:
            output = run(command, env, app_name)
    elif path_value:
        path = root / path_value
        if (path / "kustomization.yaml").exists() or (path / "Kustomization").exists():
            output = run(["kubectl", "kustomize", str(path)], env, app_name)
        else:
            files = sorted(path.glob("*.yaml")) + sorted(path.glob("*.yml"))
            output = "\n---\n".join(file.read_text(encoding="utf-8") for file in files)
    else:
        return []
    parsed = [item for item in yaml.safe_load_all(output) if isinstance(item, dict)]
    for item in parsed:
        if item.get("kind") in {"Pod", "Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "ReplicaSet", "ReplicationController"}:
            item.setdefault("metadata", {}).setdefault("namespace", namespace)
    return parsed


def inspect(root):
    restricted = restricted_namespaces(root)
    findings = []
    rendered_apps = []
    with tempfile.TemporaryDirectory(prefix="pod-security-helm-") as temporary:
        env = os.environ.copy()
        env.update(
            HELM_CONFIG_HOME=temporary + "/config",
            HELM_CACHE_HOME=temporary + "/cache",
            HELM_DATA_HOME=temporary + "/data",
        )
        for app_file in sorted((root / APP_DIR).glob("*.yaml")):
            for app in documents(app_file):
                if app.get("kind") != "Application":
                    continue
                spec = app.get("spec", {})
                namespace = spec.get("destination", {}).get("namespace", "default")
                if namespace not in restricted:
                    continue
                sources = spec.get("sources") or [spec.get("source", {})]
                values_sources = {
                    source["ref"]: root
                    for source in sources
                    if source.get("ref") and source.get("repoURL", "").rstrip("/").endswith("homelab.git")
                }
                rendered = []
                for source in sources:
                    if source.get("ref"):
                        continue
                    rendered.extend(render_source(root, source, namespace, app["metadata"]["name"], values_sources, env))
                findings.extend(inspect_documents(rendered))
                rendered_apps.append(app["metadata"]["name"])
    return rendered_apps, findings


def check_exceptions(root, findings):
    exception_file = root / "kubernetes/pod-security-exceptions.yaml"
    if not exception_file.exists():
        return findings, []
    config = yaml.safe_load(exception_file.read_text(encoding="utf-8")) or {}
    exceptions = config.get("exceptions", {})
    observed = set(findings)
    allowed = set(exceptions)
    return sorted(observed - allowed), sorted(allowed - observed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        apps, findings = inspect(root)
        findings, stale_exceptions = check_exceptions(root, findings)
    except (OSError, RuntimeError, yaml.YAMLError) as error:
        print("Pod security render failed: {}".format(error), file=sys.stderr)
        return 2
    print("Rendered {} applications in Restricted namespaces".format(len(apps)))
    if findings:
        for finding in sorted(set(findings)):
            print(finding)
        return 1
    if stale_exceptions:
        print("Unused Pod security exceptions:", file=sys.stderr)
        for exception in stale_exceptions:
            print("  {}".format(exception), file=sys.stderr)
        return 1
    print("Rendered workloads pass the requested Pod security controls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
