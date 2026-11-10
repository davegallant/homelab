# Approved PVC cleanup — 2026-11-10

Dave approved the reviewed cleanup. Execution targeted context `homelab`, API
`https://192.168.1.210:6443`, after verifying all three expected nodes Ready.

## Removed

Fifteen obsolete PVCs and their fifteen PVs were deleted with reclaim policy
left at Retain. No provisioner teardown was requested for shared storage.

| Namespace | Removed claims | Backing data |
|---|---|---|
| argocd | argocd-caddy, argocd-tailscale | Removed |
| homepage | homepage-caddy, homepage-tailscale | Removed |
| kiwix | kiwix-caddy, kiwix-tailscale | Removed |
| romm | romm-caddy-state-w1, romm-tailscale-state-w1 | Removed |
| seerr | seerr-caddy-state, seerr-tailscale-state | Removed |
| lidarr | lidarr-config | Preserved: active lidarr-config-local PV uses the same path |
| prowlarr | prowlarr-config | Preserved: active prowlarr-config-local PV uses the same path |
| radarr | radarr-config | Preserved: active radarr-config-local PV uses the same path |
| sonarr | sonarr-config | Preserved: active sonarr-config-local PV uses the same path |
| qbittorrent | qbittorrent-downloads | Preserved: NAS export is used by current claims |

Before deletion, checked all Pods and Deployment, StatefulSet, DaemonSet, Job
and CronJob templates for references. Verified resource UIDs and Retain policies.
Checked the ten sidecar paths against every PV for equal or ancestor/descendant
path overlaps. Saved pre-deletion resource manifests in a protected local
`homelab-approved-pvc-cleanup-*` temporary directory; no Secret or volume content
was exported.

Two temporary cleanup Pods in the existing privileged local-path-storage
namespace removed only the ten allowlisted sidecar paths, after canonical-path
checks. They used the existing pinned BusyBox helper image, no API token, no
privileged container and only DAC_OVERRIDE beyond dropped capabilities. Both
completed successfully and were deleted. Reported pre-removal allocation was
364 KiB combined; this is not a filesystem-wide capacity measurement.

## Verification

All 15 obsolete claims and PVs are absent. No unmounted claims remain in the
live inventory. The four active config-local claims remain Bound to their
original directories; in-container directory checks passed. Both current
qBittorrent NFS claims remain Bound and its torrents mount is accessible.
All affected active Deployments retain their desired ready replicas.
The separate batch of 52 Released PVs was unchanged.

Tracked Homepage/Kiwix sidecar storage and the obsolete qBittorrent NFS binding
were removed. Desired worker marker entries for retired sidecar directories
were removed; no Talos config was applied and no node rebooted. Existing live
machine configs may recreate empty marker directories on a future reboot until
normally reconciled. Do not reapply a partial machine config to avoid that.

The local source changes still require an explicitly approved push. No push,
Argo sync, NAS deletion or application credential rotation was performed.

Repository validation: `just lint` passed after removing trailing blank lines.
This included 35 Python tests, rendered Pod Security and backup coverage checks,
Ansible lint, shellcheck and Renovate validation. `git diff --check` passed.
