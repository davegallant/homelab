# Kubernetes logging and Loki operations

The Alloy DaemonSet under `apps/alloy/` reads Kubernetes pod
logs through the Kubernetes API, with one non-root pod per node and no host
mounts. This respects Talos's Pod Security baseline. It does not collect
Talos node service logs or replace Beszel metrics. Each Alloy pod discovers
only pods on its own node and writes to the existing Loki instance over the
Grafana LXC's LAN address.

Loki has no authentication. The Grafana playbook's Docker firewall rule admits
TCP 3100 only from the three Talos node IPs in `cluster/vars.yaml`; existing
tailnet access stays in place. The Alloy apply playbook checks the configured
Grafana LAN address before mutating the cluster. The existing Grafana Alloy
process used about 85 MiB RSS and 0.2% CPU during inspection; the DaemonSet
requests 128 MiB and 50m CPU per node, with 256 MiB and 200m limits. Review
worker memory after rollout; current sizing is in [the cluster README](cluster/README.md).

For reapplication, run the Grafana playbook before Alloy so Loki admits the
Talos node IPs. The Alloy playbook is manual; the Grafana playbook also runs
in the normal all-host CI flow. Commands below run from `ansible/`.

On 2026-10-21, Grafana's 12 GiB LXC root filesystem exhausted its ext4 inodes
on Loki chunks while 2.1 GiB of blocks remained free. Loki rejected WAL and
chunk writes. The separately approved `expand-grafana-rootfs.yml` playbook
expanded CT 115 to 24 GiB on `pve-g3-2`. It checks the container identity,
local-lvm capacity, an existing off-host backup, and free inodes after the
resize. Re-run it only when the root disk is at 12 or 24 GiB; its guard rejects
other sizes.

```sh
ansible-playbook playbooks/talos-cluster/expand-grafana-rootfs.yml -i inventory \
  --vault-password-file .vault_pass
```

The Grafana playbook subsequently installed the TCP 3100 source exceptions, and
the Alloy DaemonSet reached three Ready pods. `verify-alloy.yml` confirmed
cluster pod logs in Loki. The Grafana playbook also restarted Loki; `/ready`
briefly returned 503 during startup, and Loki reported WAL recovery errors
from the earlier inode outage. Check for missing log entries around that time.
A read-only scan found 1,608 chunk files older than 35 days despite 31-day
retention; review their lifecycle separately before widening log collection.

For later reapplication, use the same playbooks:

```sh
ansible-playbook playbooks/grafana/main.yml -i inventory \
  --vault-password-file .vault_pass
KUBECONFIG="$HOME/.local/share/homelab-talos/kubeconfig" \
  ansible-playbook playbooks/talos-cluster/apply-alloy.yml \
  -i inventory -e talos_kube_context=homelab
KUBECONFIG="$HOME/.local/share/homelab-talos/kubeconfig" \
  ansible-playbook playbooks/talos-cluster/verify-alloy.yml -i inventory
```

If Alloy causes trouble, run `remove-alloy.yml` with the same kubeconfig and
explicit context to remove its DaemonSet while leaving Homepage running. A
separate approved Grafana playbook run after removing the source-and-port rule
from the repo closes the LAN path again. The Alloy RBAC and ConfigMap can stay
for troubleshooting until their removal is separately approved.


[Back to Kubernetes overview](README.md).
