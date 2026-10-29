# Kubernetes logging and Loki operations

The [Alloy configuration](apps/alloy/configmap.yaml.j2) discovers node-local
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
   chunk files can exhaust inodes while substantial space remains.
4. After a Loki restart, wait for `/ready` and check WAL recovery errors and
   fresh ingestion. Review retention behavior against actual stored chunks.
5. Verify logs from both Kubernetes and an LXC shipper after a backend move.

Use `ansible/playbooks/talos-cluster/verify-alloy.yml` for the repository's
verification flow. Review deployment ownership in
[release management](apps/argocd/MANAGEMENT.md) before applying or removing
resources; a historical apply playbook is not authority to overwrite Argo-owned
objects. Pass the protected Vault password helper when a playbook loads Vault.
