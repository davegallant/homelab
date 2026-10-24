# Navidrome on the Talos cluster (Argo CD)

Navidrome runs from the bjw-s **app-template** chart (5.3.0) as an
Argo CD Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application definition
is `../argocd/applications/navidrome.yaml`. Syncs are manual, pruning
is off, and deleting the Application preserves the workload.

Workload source of truth: `playbooks/navidrome/docker-compose.yml`
(image `docker.io/deluan/navidrome:0.64.2`, port 4533, `./data:/data`,
`/music:/music:ro`).

Exposure is **public via Pangolin** — the compose pairs the app with a
Newt sidecar, reproduced in-pod with the *same* Newt identity, so the
existing Pangolin route and public URL carry over unchanged. Do not
rewrite this app as tailnet-only.

The music library is a static NFS PV (`storage.yaml`) onto the
existing TrueNAS export (`/mnt/tank/media/Music`), read-only; it never
moves and is never Velero-backed-up (TrueNAS snapshots + Drive sync).
Verify the share path against the LXC's `/music` mount source before
applying `storage.yaml`. The app state (`./data`: sqlite DB, cache)
lands on the chart-managed local-path PVC (volume `data`, 5Gi). The
chart names a lone PVC after the release, so the claim is
`navidrome` — and it renames to `navidrome-data` if a second chart
PVC is ever added; bind by provisioned path, not by name.

Secrets stay in Vault and outside Argo's ownership, both created by
`playbooks/talos-cluster/navidrome-secret.yml`: `navidrome-newt-external`
(Pangolin/Newt) and `navidrome-external` (Last.fm keys).

Backups: Velero Schedule `navidrome-daily` (in the values, opt-in
mode) with pod annotation `backup.velero.io/backup-volumes: data-local`.
The network policy is the house default-deny CiliumNetworkPolicy, in
the values as `rawResources.defaultDenyNetworkPolicy`.

One deliberate config change from the LXC: `ND_LISTENBRAINZ_BASEURL`
points at Maloja's in-cluster Service DNS
(`maloja.maloja.svc.cluster.local:42010`) instead of its tailnet URL,
which a pod can neither resolve nor route to. The default-deny
policy's cluster egress permits it. If Maloja later gains an ingress
policy, it needs a `fromEndpoints` exception for the `navidrome`
namespace or scrobbles start failing (playback is unaffected either
way).
