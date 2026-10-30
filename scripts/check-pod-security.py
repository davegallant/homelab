#!/usr/bin/env python3
"""Inventory requested Pod hardening settings in rendered or live manifests.

Pod Security Admission remains authoritative for the complete Kubernetes
Restricted profile. This script reports the additional settings requested by
the homelab rollout and does not hide findings for exception namespaces.
"""

import argparse
import copy
import hashlib
import sys
from pathlib import Path

import yaml


CONTAINER_GROUPS = ("containers", "initContainers", "ephemeralContainers")


def load_documents(source):
    """Load Kubernetes YAML documents from a path or an already parsed stream."""
    if isinstance(source, (str, Path)):
        content = Path(source).read_text(encoding="utf-8")
    else:
        content = source.read()
    return [doc for doc in yaml.safe_load_all(content) if isinstance(doc, dict)]


def workload_pod_spec(document):
    """Return the embedded Pod template, if this object defines one."""
    kind = document.get("kind")
    if kind == "List":
        for item in document.get("items", []):
            yield from workload_pod_spec(item)
        return

    if kind == "Pod":
        yield document.get("metadata", {}), document.get("spec", {})
        return

    spec = document.get("spec", {})
    if kind == "CronJob":
        spec = spec.get("jobTemplate", {}).get("spec", {})
    template = spec.get("template")
    if isinstance(template, dict):
        yield template.get("metadata", {}), template.get("spec", {})


def is_exception(document, exceptions):
    """Whether the document's namespace is classified as a platform exception."""
    document_namespace = document.get("metadata", {}).get("namespace", "default")
    return any(
        (metadata.get("namespace") or document_namespace) in exceptions
        for metadata, _pod_spec in workload_pod_spec(document)
    )


def render_pods(document):
    """Build minimal Pod objects for server-side Pod Security dry-run checks."""
    rendered = []
    for index, (metadata, pod_spec) in enumerate(workload_pod_spec(document)):
        source_metadata = document.get("metadata", {})
        namespace = metadata.get("namespace") or source_metadata.get("namespace", "default")
        identity = "{}/{}/{}".format(namespace, metadata.get("name", source_metadata.get("name", "workload")), index)
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        rendered_spec = {}

        # These Pod-level fields cover the Restricted/Baseline checks while
        # avoiding application env values, commands, probes, and credentials.
        for field in (
            "os",
            "hostNetwork",
            "hostPID",
            "hostIPC",
            "shareProcessNamespace",
            "securityContext",
            "volumes",
        ):
            if field in pod_spec:
                rendered_spec[field] = copy.deepcopy(pod_spec[field])

        for group in ("initContainers", "containers"):
            rendered_containers = []
            for container in pod_spec.get(group, []) or []:
                item = {
                    "name": container.get("name", "unnamed"),
                    "image": "example.invalid/pod-security-inventory:0",
                }
                if "securityContext" in container:
                    item["securityContext"] = copy.deepcopy(container["securityContext"])
                for probe_name in ("livenessProbe", "readinessProbe", "startupProbe"):
                    probe = container.get(probe_name, {}) or {}
                    sanitized_probe = {}
                    for action_name in ("httpGet", "tcpSocket"):
                        action = probe.get(action_name, {}) or {}
                        if action.get("host"):
                            sanitized_probe[action_name] = {
                                "host": action["host"],
                                "port": action.get("port", 80),
                            }
                            if action_name == "httpGet":
                                sanitized_probe[action_name]["path"] = action.get("path", "/")
                    if sanitized_probe:
                        item[probe_name] = sanitized_probe
                lifecycle = container.get("lifecycle", {}) or {}
                sanitized_lifecycle = {}
                for event_name in ("postStart", "preStop"):
                    event = lifecycle.get(event_name, {}) or {}
                    for action_name in ("httpGet", "tcpSocket"):
                        action = event.get(action_name, {}) or {}
                        if action.get("host"):
                            sanitized_lifecycle[event_name] = {
                                action_name: {
                                    "host": action["host"],
                                    "port": action.get("port", 80),
                                    **({"path": action.get("path", "/")} if action_name == "httpGet" else {}),
                                }
                            }
                if sanitized_lifecycle:
                    item["lifecycle"] = sanitized_lifecycle
                host_ports = [
                    {key: port[key] for key in ("containerPort", "hostPort", "protocol") if key in port}
                    for port in container.get("ports", [])
                    if "hostPort" in port
                ]
                if host_ports:
                    item["ports"] = host_ports
                rendered_containers.append(item)
            if rendered_containers:
                rendered_spec[group] = rendered_containers

        rendered_metadata = {"name": "psa-audit-{}".format(digest), "namespace": namespace}
        apparmor_annotations = {
            key: value
            for key, value in (metadata.get("annotations", {}) or {}).items()
            if key.startswith("container.apparmor.security.beta.kubernetes.io/")
        }
        if apparmor_annotations:
            rendered_metadata["annotations"] = apparmor_annotations

        rendered.append(
            {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": rendered_metadata,
                "spec": rendered_spec,
            }
        )
    return rendered


def inspect_document(document, exceptions=None):
    """Return requested hardening findings for every Pod template in a document."""
    exceptions = exceptions or set()
    findings = []
    for metadata, pod_spec in workload_pod_spec(document):
        document_meta = document.get("metadata", {})
        namespace = metadata.get("namespace") or document_meta.get("namespace", "default")
        name = metadata.get("name") or document_meta.get("name", "unnamed")
        pod_security = pod_spec.get("securityContext", {}) or {}
        prefix = "{}/{}".format(namespace, name)

        if pod_spec.get("automountServiceAccountToken") is not False:
            findings.append("{} pod automountServiceAccountToken".format(prefix))

        for group in CONTAINER_GROUPS:
            for container in pod_spec.get(group, []) or []:
                security = container.get("securityContext", {}) or {}
                identity = "{} {}:{}".format(prefix, group, container.get("name", "unnamed"))

                if security.get("runAsNonRoot", pod_security.get("runAsNonRoot")) is not True:
                    findings.append("{} runAsNonRoot".format(identity))
                if security.get("runAsUser", pod_security.get("runAsUser")) == 0:
                    findings.append("{} runAsUserRoot".format(identity))
                if security.get("allowPrivilegeEscalation") is not False:
                    findings.append("{} allowPrivilegeEscalation".format(identity))
                if "ALL" not in (security.get("capabilities", {}).get("drop") or []):
                    findings.append("{} dropAllCapabilities".format(identity))
                seccomp = security.get("seccompProfile", pod_security.get("seccompProfile", {})) or {}
                if seccomp.get("type") != "RuntimeDefault":
                    findings.append("{} RuntimeDefaultSeccomp".format(identity))
                if security.get("readOnlyRootFilesystem") is not True:
                    findings.append("{} readOnlyRootFilesystem".format(identity))
                if security.get("privileged") is True:
                    findings.append("{} privileged".format(identity))

        # Keep exceptions visible in the report; this marker is informational.
        if namespace in exceptions:
            findings = ["{} [exception]".format(item) if item.startswith(prefix) else item for item in findings]
    return findings


def run_self_test():
    fixtures = Path(__file__).parent / "tests" / "fixtures" / "pod-security"
    compliant = inspect_document(load_documents(fixtures / "compliant-pod.yaml")[0])
    if compliant:
        raise AssertionError("compliant fixture produced findings: {}".format(compliant))

    violating = inspect_document(load_documents(fixtures / "violating-pod.yaml")[0])
    required = {
        "sample/violating containers:app runAsNonRoot",
        "sample/violating containers:app allowPrivilegeEscalation",
        "sample/violating containers:app dropAllCapabilities",
        "sample/violating initContainers:prepare RuntimeDefaultSeccomp",
    }
    if not required.issubset(set(violating)):
        raise AssertionError("violating fixture missed findings: {}".format(required - set(violating)))

    inherited = inspect_document(load_documents(fixtures / "inherited-seccomp-pod.yaml")[0])
    if any("ephemeralContainers:debug RuntimeDefaultSeccomp" in item for item in inherited):
        raise AssertionError("pod-level RuntimeDefault seccomp was not inherited")

    exception_doc = load_documents(fixtures / "platform-exception-pod.yaml")[0]
    exception_findings = inspect_document(exception_doc, exceptions={"platform-example"})
    if not any("[exception]" in item and "privileged" in item for item in exception_findings):
        raise AssertionError("exception classification hid or failed to mark a finding")
    print("Pod security inventory self-test passed (4 fixture cases)")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", help="manifest path; defaults to standard input")
    parser.add_argument(
        "--exceptions",
        default="",
        help="comma-separated exception namespaces; findings remain visible",
    )
    parser.add_argument("--self-test", action="store_true", help="run built-in fixture checks")
    parser.add_argument(
        "--emit-pods",
        action="store_true",
        help="emit sanitized Pod objects for Kubernetes server-side admission dry runs",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        run_self_test()
        return 0

    documents = load_documents(args.manifest) if args.manifest else load_documents(sys.stdin)
    if args.emit_pods:
        pods = [pod for document in documents for pod in render_pods(document)]
        yaml.safe_dump_all(pods, sys.stdout, explicit_start=True, sort_keys=False)
        return 0

    exceptions = {name for name in args.exceptions.split(",") if name}
    for document in documents:
        for finding in inspect_document(document, exceptions=exceptions):
            print(finding)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
