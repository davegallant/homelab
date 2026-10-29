# Kubernetes backups and Homepage restore drill

The Kubernetes layer is backed up by Velero with Kopia filesystem backups:
Talos cluster → Velero/node-agent → Garage on TrueNAS → covered by Dave's
existing TrueNAS-to-Drive sync. The `homepage-daily` schedule runs at 03:15 UTC,
keeps backups for 14 days, includes only `homepage`, and excludes Secrets.
Secrets are intentionally excluded because Velero's resource archive is not
encrypted. Recreate them from Vault before judging restored workloads.

Daily namespace backup start times are in UTC (23:00–00:30 Toronto during
daylight saving time; 22:00–23:30 in winter):

| Namespace | Start (UTC) |
|---|---|
| `bentopdf` | 03:00 |
| `searxng` | 03:05 |
| `kiwix` | 03:10 |
| `homepage` | 03:15 |
| `changedetection` | 03:20 |
| `lubelogger` | 03:25 |
| `maloja` | 03:30 |
| `seerr` | 03:35 |
| `miniflux` | 03:40 |
| `navidrome` | 03:45 |
| `audiobookshelf` | 03:50 |
| `invidious` | 03:55 |
| `umami` | 04:00 |
| `speedtest-tracker` | 04:05 |
| `paperless-ngx` | 04:15 |
| `romm` | 04:30 |
| `forgejo`, `forgejo-runner` | 05:00 |
| `prowlarr` | 04:10 |
| `sonarr` | 04:20 |
| `radarr` | 04:25 |
| `lidarr` | 04:50 |

`forgejo-daily` includes `forgejo` and `forgejo-runner` with the same 14-day
TTL and currently includes Secrets. Forgejo's database and data are in the
Kopia-encrypted volume backup, but its Kubernetes resource archive is not
encrypted. The 2026-10-26 through 2026-10-28 scheduled backups completed under
this policy.

The Forgejo URL and Newt Secrets can be recreated from Ansible Vault with
`just run talos-cluster/gitops-secrets --tags forgejo-secrets`; this was applied
to the live cluster on 2026-10-29 without displaying credential data. The ten
Newt app Secrets were also reapplied and verified by name, key names, and
workload readiness.

Forgejo Runner recovery will use a fresh registration after restoring Forgejo,
so the current runner identity is not stored in Ansible Vault. Forgejo's
registration UI creates a UUID and token, while the deployed runner chart 0.7.5
uses `runner.config.existingSecret` with a `.runner` file. The documented
registration-to-chart handoff has not yet been tested, so `forgejo-daily`
continues to include Secrets. Do not exclude them until a fresh registration is
proven to work with the deployed chart. Forgejo's official [runner registration
guide](https://forgejo.org/docs/latest/admin/actions/registration/) documents
the new UUID/token registration flow.

The completed backup `forgejo-daily-20261029050007` expires on 2026-11-12 at
05:00 UTC under its 14-day TTL. Its seven Secret resources were restored into
isolated scratch namespaces; all seven restored data maps matched their live
counterparts in memory. The source backup was not modified. Preserve existing
Secret-bearing backups and their TTLs; manual backups may have a 30-day TTL.
The Velero Kubernetes resource archive in Garage is not encrypted. Keep Garage
and off-site copies restricted for the full retention period; retention of
deleted objects in the Drive copy has not been verified.

Velero has 26 Ready Kopia repositories, one per namespace with filesystem
backups. The `velero-repo-credentials` Secret currently contains Velero's
static default repository password; that password is not in Ansible Vault.
Kopia encrypts the volume data, but the current key is not private. Do not
replace the Secret directly: Velero warns that repositories created with the
old password will become inaccessible. Migrate and verify all repositories
with Kopia's password-change procedure before updating the Secret, and retain
the new password in Vault for disaster recovery. Secret encryption in the
Kubernetes API is enabled with Talos `secretbox`; the etcd and VM snapshots
still require the separately protected Talos cluster credentials to restore.

On 2026-10-29, a copy rehearsal used the completed Homepage backup
`homepage-daily-20261029031507`, snapshot
`7bce6c6ceb53c352986b2f89a38bdfa4`, and namespace repository
`kopia/homepage/`. The protected Garage copy contained 235 objects totaling
1,199,289 bytes. Kopia v0.16.0 connected to the isolated copy as
`default@default`; after changing only the copy to the Vault-held password, it
listed the same 29 snapshots and restored the selected snapshot to encrypted
Mac scratch storage. The restore matched Kopia's metadata: 17 files and
287,717 bytes. The temporary Garage access pods and local copy, credentials,
Kopia binary, config, cache, and restored files were removed. The source
repository and live Velero credential were unchanged. Garage object names need
the filesystem backend's `.f` suffix and flat layout when represented as a
local Kopia filesystem repository; the object contents were preserved. This
validates the password-change and restore path on one copied namespace only;
the live repositories still require their separate preflight and migration.

The live Kopia rotation preflight on 2026-10-29 found 26/26 repositories Ready,
no active Velero Backup, Restore, PodVolumeBackup, or Kopia maintenance job,
and an Available Garage location. Kopia v0.16.0 captured a read-only manifest
count for each repository namespace as the rotation validation baseline.

Before pausing writers, the off-host etcd snapshot
`etcd-homelab-20261029T122913Z.snap` was created with mode `0600` and its
checksum was verified against the protected local copy. All 26 repositories
were rotated and verified with the new password, and their snapshot counts
remain unchanged. The Vault-backed Velero Secret is updated and all 26
`BackupRepository` objects are Ready. The post-rotation Homepage restore and
fresh-backup checks passed, and all 27 schedules are unpaused. `kiwix` and
`searxng` have schedules but no repository yet; the `monitoring` repository
has no schedule. The Homepage restore verified only its 287,717-byte config
volume; the selected backup contains no Caddy or Tailscale volume data and
excludes Kubernetes Secrets. TrueNAS-to-Drive client-side encryption and
deletion retention remain unverified; do not treat the Drive copy as encrypted
or protected from deletion until the actual task settings are checked.

Each daily schedule now has a distinct UTC start. The media automation
backups run at 04:10, 04:20, 04:25, and 04:50; their latest runs on
2026-10-25 took 12–30 seconds. Paperless remains at 04:15, RomM at 04:30,
and Forgejo at 05:00. Lidarr starts 20 minutes after RomM to allow for
its previously observed longer runs.
This leaves a buffer before the NAS 01:00 Toronto offsite sync and Proxmox
02:00 Toronto backup job at the observed durations. Staggering is not a
global concurrency lock: longer runs or manual backups can still overlap.
Keep schedule names stable; when a chart rename creates a replacement,
remove the obsolete Schedule explicitly after checking equivalent coverage,
using orphan deletion to preserve existing Backups.

## Recovery safeguards

Proxmox VM backups cover the Talos disks, including local PV data. Separate
off-host etcd snapshots protect cluster state. Protect the operator's Talos
credentials and Ansible Vault too. Isolate a full VM restore from the live
cluster until node identity and etcd membership are reconciled.

## RomM current backup

The current RomM backup is `romm-current-20261024022620`. It completed on
2026-10-24 with no Velero warnings or errors and a 14-day TTL. Its four
annotated volumes all have completed Kopia PodVolumeBackups: config (95 bytes),
resources (1,217,172,959 bytes), Redis (6,867,498 bytes), and MariaDB
(191,548,412 bytes). The MariaDB pre-backup hook succeeded (`HooksFailed: 0`)
and left a 3,206,043-byte `romm-backup.sql` in the backed-up database volume.

These four claims use static Kubernetes `local` PVs on `k8s-w-1`, declared in
`apps/romm/state-local-pv.yaml`, and point at the existing active data
directories. Rancher's local-path provisioner defaults to `hostPath`, which
Velero does not support for filesystem backups. The stale RomM PVC/PV objects
on `k8s-w-2` were removed after backup verification; their directories remain
on disk because the reclaim policy is `Retain`. The ROM library remains on
TrueNAS and is protected by its separate NAS backup path. Verify future RomM
backups by checking all four PodVolumeBackups and their nonzero byte counts;
the top-level `Completed` phase by itself is insufficient.

For large data transfers, use a tar stream or another length-preserving copy
method. Piping a large SQL dump through `kubectl exec -i ... cat > file` can
truncate it. Compare file counts and byte totals, verify dump checksums before
restore, and compare exact per-table `COUNT(*)` results for databases rather
than relying on `information_schema` estimates.

## Homepage restore drill

Use direct `kubectl` and `talosctl` commands for recovery; no Ansible playbook
is required. Set the context and backup name first, and stop if the cluster,
backup, or Garage storage location is not healthy:

```bash
set -euo pipefail
CTX=homelab
BACKUP=replace-with-a-completed-homepage-backup
kubectl --context "$CTX" get nodes
kubectl --context "$CTX" -n velero get backup "$BACKUP"
kubectl --context "$CTX" -n velero get backupstoragelocation default
kubectl --context "$CTX" -n velero backup describe "$BACKUP" --details
```

For Homepage, use the existing dynamic `local-path` provisioner. Restore its
PVCs with the `volumeType: local` annotation and let the saved Deployment's
required node affinity place them on `k8s-w-1`. This creates no separate host
directories, machine-config entries, or PV manifests. Never map a restored
claim to a live production PV. Keep both PVCs and PVs included in Velero's
resource filters so it creates the PodVolumeRestore; use
`--include-cluster-resources=false` to keep the cluster-scoped PV objects out of
the restore.

Create the target namespace, then recreate its Secrets before restoring. For
an in-cluster drill where the source namespace still exists, copy Secret objects
without printing their data:

```bash
CTX=homelab
SOURCE_NS=homepage
TARGET_NS=homepage-drill
kubectl --context "$CTX" create namespace "$TARGET_NS"
kubectl --context "$CTX" label namespace "$TARGET_NS" name="$TARGET_NS"
kubectl --context "$CTX" -n "$SOURCE_NS" get secret homepage-environment-external -o json \
  | jq --arg ns "$TARGET_NS" \
    'del(.metadata.uid,.metadata.resourceVersion,.metadata.creationTimestamp,.metadata.managedFields,.metadata.ownerReferences) | .metadata.namespace=$ns' \
  | kubectl --context "$CTX" apply -f -
```

For a recovery where the source namespace is unavailable, create
`homepage-environment-external` from protected local files populated from the
existing Vault values. Keep the file outside the repository with mode `0600`;
its keys are the `HOMEPAGE_VAR_*` entries supplied by Vault through
`apps/homepage/values.ansible.yaml.j2`:

```bash
set -euo pipefail
CTX=homelab
TARGET_NS=homepage-drill
umask 077
HOMEPAGE_SECRETS_ENV_FILE="$HOME/.local/share/homepage-secrets.env"
kubectl --context "$CTX" -n "$TARGET_NS" create secret generic homepage-environment-external \
  --from-env-file="$HOMEPAGE_SECRETS_ENV_FILE" --dry-run=client -o yaml \
  | kubectl --context "$CTX" apply -f -
```

Modify the restored claims to use `local-path`. The modifier removes the saved
static PV binding and adds the Velero-supported local volume annotation:

```bash
CTX=homelab
TARGET_NS=homepage-drill
BACKUP=replace-with-a-completed-homepage-backup
kubectl --context "$CTX" -n velero apply -f - <<'YAML'
apiVersion: v1
kind: ConfigMap
metadata:
  name: homepage-drill-restore-modifiers
data:
  resource-modifiers.yaml: |
    version: v1
    resourceModifierRules:
      - conditions:
          groupResource: persistentvolumeclaims
          resourceNameRegex: '^homepage-(config|caddy|tailscale)$'
          namespaces: [homepage]
        patches:
          - operation: remove
            path: /spec/volumeName
          - operation: replace
            path: /spec/storageClassName
            value: local-path
          - operation: add
            path: /metadata/annotations/volumeType
            value: local
YAML
kubectl --context "$CTX" -n velero exec deployment/velero -- /velero restore create \
  homepage-drill-restore --from-backup "$BACKUP" \
  --namespace-mappings homepage:homepage-drill \
  --include-cluster-resources=false \
  --resource-modifier-configmap homepage-drill-restore-modifiers \
  --exclude-resources httproutes.gateway.networking.k8s.io,ciliumendpoints.cilium.io,endpoints,endpointslices.discovery.k8s.io \
  --wait
kubectl --context "$CTX" -n velero get restore homepage-drill-restore
kubectl --context "$CTX" -n velero get podvolumerestores \
  -l velero.io/restore-name=homepage-drill-restore \
  -o custom-columns=VOLUME:.spec.volume,PHASE:.status.phase,BYTES:.status.progress.totalBytes
kubectl --context "$CTX" -n homepage-drill get pvc -o wide
```

The 2026-10-29 backup contains one completed PodVolumeBackup for
`homepage-config` (287,717 bytes); it does not contain Caddy or Tailscale volume
data. Its Deployment already has only the Homepage container. Require a
completed PodVolumeRestore with the expected byte count and a Running, Ready
pod before comparing data. Check each selected backup's own resource list and
PodVolumeBackups; do not assume older sidecars or volumes are present:

Compare resource inventories and `/app/config` file lists/checksums. Exclude
logs, icons, the Velero-generated `.velero/` marker, and the ConfigMap-managed
`manifest.json`, `services.yaml`, and `settings.yaml` from the config comparison:

```bash
CTX=homelab
diff -u \
  <(kubectl --context "$CTX" -n homepage get all,pvc -o name | sort) \
  <(kubectl --context "$CTX" -n homepage-drill get all,pvc -o name | sort) || true
CONFIG_CHECK='find /app/config -type f ! -path "/app/config/logs/*" ! -path "/app/config/icons/*" ! -path "/app/config/.velero/*" ! -name manifest.json ! -name services.yaml ! -name settings.yaml -print0 | sort -z | xargs -0 sha256sum'
diff -u \
  <(kubectl --context "$CTX" -n homepage exec deployment/homepage -c homepage -- sh -c "$CONFIG_CHECK") \
  <(kubectl --context "$CTX" -n homepage-drill exec deployment/homepage -c homepage -- sh -c "$CONFIG_CHECK")
```

Require the restored Homepage pod to be Running and Ready, and request `/`
through its ClusterIP using the Host header from the production readiness
probe:

```bash
CTX=homelab
SERVICE_IP="$(kubectl --context "$CTX" -n homepage-drill get service homepage -o jsonpath='{.spec.clusterIP}')"
HOST="$(kubectl --context "$CTX" -n homepage get deployment homepage -o json \
  | jq -r '.spec.template.spec.containers[] | select(.name=="homepage") | .readinessProbe.httpGet.httpHeaders[] | select(.name=="Host") | .value')"
kubectl --context "$CTX" -n homepage-drill exec deployment/homepage -c homepage -- \
  node -e 'const http=require("http"); const [host,expected]=process.argv.slice(1); const req=http.get({host,port:3000,path:"/",headers:{Host:expected}},res=>{console.log(res.statusCode);res.resume();process.exitCode=res.statusCode===200?0:1}); req.setTimeout(10000,()=>req.destroy(new Error("timeout"))); req.on("error",e=>{console.error(e.message);process.exit(1)});' \
  "$SERVICE_IP" "$HOST"
```

## Remove a completed drill

Run cleanup only after verification is finished. This example deletes the
temporary namespace and its dynamic local-path volumes. It verifies each PV is
a `local-path` volume under `/var/mnt/local-path`, then changes only those drill
PVs to `Delete` so the provisioner removes their directories when the claims
are deleted:

```bash
set -euo pipefail
CTX=homelab
TARGET_NS=homepage-drill
kubectl --context "$CTX" -n "$TARGET_NS" scale deployment/homepage --replicas=0
kubectl --context "$CTX" -n "$TARGET_NS" wait --for=delete pod \
  -l app.kubernetes.io/name=homepage --timeout=180s
PV_NAMES="$(kubectl --context "$CTX" get pv -o json \
  | jq -r --arg ns "$TARGET_NS" \
    '.items[] | select(.spec.claimRef.namespace == $ns) | .metadata.name')"
PV_ARRAY=()
if [[ -n "$PV_NAMES" ]]; then
  readarray -t PV_ARRAY <<< "$PV_NAMES"
fi
for pv in "${PV_ARRAY[@]}"; do
  kubectl --context "$CTX" get pv "$pv" -o json \
    | jq -e '(.spec.storageClassName == "local-path") and
      (.spec.local.path | startswith("/var/mnt/local-path/"))' >/dev/null
done
if [[ "${#PV_ARRAY[@]}" -gt 0 ]]; then
  kubectl --context "$CTX" patch pv "${PV_ARRAY[@]}" --type=merge \
    -p '{"spec":{"persistentVolumeReclaimPolicy":"Delete"}}'
fi
kubectl --context "$CTX" delete namespace "$TARGET_NS" --wait=true --timeout=300s
for pv in "${PV_ARRAY[@]}"; do
  kubectl --context "$CTX" wait --for=delete "pv/$pv" --timeout=180s
done
kubectl --context "$CTX" -n velero delete configmap \
  homepage-drill-restore-modifiers --ignore-not-found=true
kubectl --context "$CTX" -n homepage rollout status deployment/homepage --timeout=300s
```

Confirm the drill namespace and its PVs are absent, production Homepage is
healthy, and its three production PV claims remain Bound to their original PVs.


[Back to Kubernetes overview](README.md).
