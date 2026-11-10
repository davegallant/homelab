# Approved Released PV cleanup — 2026-11-10

Dave authorized the cleanup candidates from the
[52-volume review](released-pv-review-2026-11-10.md).

Removed 45 Released PV objects with their reclaim policy left at Retain,
then removed the exact corresponding directories: 25 former restore-drill
volumes and 20 retired Caddy/Tailscale sidecar volumes. The seven historical
application-data PVs and their directories were preserved. No current PVC,
NAS data, backup or Restore object was deleted.

Fresh preflight checks verified the intended cluster API and three Ready nodes,
Released phase, historical claim UIDs, Retain policy, absent claims/controller
references, and no equal or nested path overlap with any other PV. Saved resource
manifests and the exact plan in a protected local temporary evidence directory.

Two temporary cleanup Pods ran on the recorded workers in the existing
local-path-storage namespace. They used the pinned BusyBox helper image, no API
token, dropped capabilities with only DAC_OVERRIDE added, and a host mount limited
to `/var/mnt/local-path`. Every approved directory passed symlink/canonical-path
checks before any deletion on that worker. The larger Loki directories took
several minutes; both Pods completed successfully. Both were removed after
preserving their 45 directory-removal confirmations.

Post-cleanup Kubernetes inventory confirms all 45 selected PVs absent and exactly
seven Released PVs retained. Fresh Talos directory listings independently confirm
all 45 selected paths absent and all seven retained paths present. All active
Deployments had their desired ready replicas, and all three nodes remained Ready.
The pre-review size total was incomplete because five Loki scans timed out; no
claim is made about exact reclaimed filesystem capacity.

Popeye's temporary in-cluster validation scan subsequently reported seven
explicitly retained Released volumes, zero unreferenced claims and 15 remaining
shared-path pairs. Those pairs are findings for separate review, not deletion
approvals. Their backing data was not touched by this cleanup.
