# Trivy Operator

Trivy Operator scans Kubernetes workloads and stores vulnerability and
configuration audit results as Kubernetes report resources. It has no user
interface. Argo CD installs the pinned Aqua Helm chart in `trivy-system`;
syncs remain manual and reports are created by the operator at runtime.

The initial configuration scans supported workloads across namespaces,
excluding `trivy-system` to avoid scanning its own operator and scan jobs. It
enables vulnerability and configuration audit scanning only. RBAC, cluster
infrastructure, compliance, SBOM and exposed-secret scanners are disabled.
The node collector is disabled because the initial scope does not include
host-level configuration scans. Scan jobs are limited to one concurrent job.
The operator and Trivy images are pinned by version and SHA-256 digest.
The controller and scanner jobs have bounded CPU and memory resources; scan
jobs also have bounded ephemeral storage.

No persistent storage, application Secret, ingress, or external URL is
required. Vulnerability scan jobs need registry access and fetch the Trivy
database; configuration audit needs the upstream policy bundle. With Trivy's
standalone mode, scan jobs download their own database, so registry egress and
GitHub rate limits can affect scan completion. The Cilium policy allows DNS,
the Kubernetes API, and outbound HTTPS so scans can reach the registries used
by workloads. Reports are Kubernetes API resources and do not require a backup
volume.

## Review reports

Check report coverage and scan errors with:

```sh
kubectl get vulnerabilityreports.aquasecurity.github.io -A
kubectl get configauditreports.aquasecurity.github.io -A
kubectl get jobs -n trivy-system
```

Inspect a report with `kubectl -n <namespace> get vulnerabilityreport <name>
-o yaml` or `kubectl -n <namespace> get configauditreport <name> -o yaml`.
These reports show findings for deployed images and workload configuration;
they do not block deployments. Check that reports are recent and scan jobs
complete before treating an empty result as clean.

## Deployment and recovery

Review the Argo CD diff and sync `trivy-operator` without prune or force. The
Application creates the `trivy-system` namespace with Pod Security Baseline
labels. Roll back by reverting the Git change and approving another Argo CD
sync. Removing the Application alone does not delete its resources.
