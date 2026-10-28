# qBittorrent

The production workload runs on `k8s-w-1`, using app-template 5.3.0 and
LinuxServer qBittorrent 5.3.0. It currently has zero torrents. Torrent start
remains gated on peer ingress and the network safety review recorded in
[`qbittorrent-egress/README.md`](../qbittorrent-egress/README.md).
UPnP/NAT-PMP, DHT, PeX and LSD are disabled.

## Exposure and credentials

URL: `https://qbittorrent.tail.davegallant.ca`. Userspace Tailscale
forwards HTTPS to loopback Caddy, then WebUI port 8080. The Kubernetes
identity uses `tag:monitored`; Headscale member devices, including the
member-owned *arr identities, can reach it.

`provision.yml` materializes external Secrets with `no_log: true` and stdin,
using Ansible Vault. `qbittorrent_webui_password` is the PBKDF2 hash;
`qbittorrent_webui_login_password` is used only for login verification.
Neither credential is committed. The bootstrap Secret is copied only when
the config file is absent. The notification script is projected from a
Secret at mode 0644, and the repository malware script is projected at 0750.

Dracula is downloaded from pinned revision
`9020f6eb457087270179beb86d45914d434adb6b` during bootstrap. A marker prevents
re-downloading it on every restart.

## Storage and backups

Config uses a 1 GiB local-path PVC annotated `volumeType: local`. Download
data uses a hand-applied NFS RWX PV/PVC from `192.168.1.83:/mnt/pool`, with
the `torrents` subdirectory mounted at `/mnt/torrents`. NAS snapshots and
offsite protection cover downloads. Config and Caddy state are opted into
Velero; NFS and Tailscale identities are excluded. The tracked daily schedule
runs at 04:40 UTC with a 336-hour TTL and excludes Secrets.

Namespace and NFS PV/PVC in `storage.yaml` are hand-applied external
resources, not Argo-owned. The chart resources use manual Argo sync without
prune or force.

## Provisioning

From the repository root, with the intended default kubeconfig:

```sh
ansible-playbook kubernetes/apps/qbittorrent/provision.yml \
  -i localhost, --vault-password-file ansible/.vault_pass
kubectl --context homelab apply -f kubernetes/apps/argocd/applications/qbittorrent.yaml
```

Provisioning does not rotate an existing Tailscale registration Secret;
refresh expired keys through a separately reviewed change. Keep the workload
pinned to w-1 unless local-volume recovery and relocation are explicitly
approved.

The gateway policy, deletion protections, monitor, packet evidence, and
remaining network risks are documented in
[`../qbittorrent-egress/README.md`](../qbittorrent-egress/README.md).

## Build record

The WebUI build verification recorded pod readiness, authenticated API
access, the Dracula theme, and zero torrents. Sonarr's download-client API
test returned HTTP 200 during that build; current *arr endpoint and gateway
checks are recorded in the egress guardrail runbook. See
[`BUILD-REPORT.md`](BUILD-REPORT.md) for the historical build details.
