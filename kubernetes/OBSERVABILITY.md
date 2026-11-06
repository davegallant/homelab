# Kubernetes logging and Loki operations

The [Alloy configuration](apps/alloy-argo/configmap.yaml) discovers node-local
pods and reads logs through the Kubernetes API. It does not collect Talos node
service logs. LXC agents have a separate configuration under `ansible/tasks/`.

Check the actual write URL in each shipper configuration and verify it against
the deployed Loki endpoint before rollout. The Kubernetes Loki chart lives in
[apps/loki](apps/loki/); do not assume an old Grafana LXC address has followed
a backend cutover. Review Cilium policy and Headscale ACLs together with the
endpoint change. Loki has no application authentication.

## Verification and troubleshooting

1. Check Alloy readiness, discovery and write errors.
2. Generate a known log entry and query Loki for that entry with its namespace,
   pod and container labels. Readiness alone does not prove ingestion.
3. Check filesystem free blocks **and inodes** before adding sources. Small
   chunk files can exhaust inodes while substantial space remains. Grafana's
   `/var` inode alerts warn above 80% and go critical above 90% for five
   minutes. They monitor the whole node filesystem, including Loki's local-path
   PVC on `k8s-w-1`; they do not report per-PVC usage.
4. Loki retains logs for 744 hours (31 days). Review retention behavior against
   actual stored chunks. After a Loki restart, wait for `/ready` and check WAL
   recovery errors and fresh ingestion.
5. Verify logs from both Kubernetes and an LXC shipper after a backend move.

Use `ansible/playbooks/talos-cluster/verify-alloy.yml` for the repository's
verification flow. Review deployment ownership in
[release management](apps/argocd/MANAGEMENT.md) before applying or removing
resources; a historical apply playbook is not authority to overwrite Argo-owned
objects. Pass the protected Vault password helper when a playbook loads Vault.
