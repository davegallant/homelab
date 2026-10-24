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
| `prowlarr`, `sonarr`, `radarr`, `lidarr` | 03:00 |

The newer media automation schedules also start at 03:00 UTC, so the
schedule is not fully staggered. The earlier smaller backups start five minutes apart; Paperless and RomM have larger
slots after their recent runs took about 3 and 15 minutes respectively.
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

For a namespace using static local PVs, provision new scratch paths and PVs on
the node required by that workload before restoring. Never map restored claims
to a live production PV. For the Homepage drill, the scratch paths are
`/var/mnt/homepage-drill/{config,caddy,tailscale}` on `k8s-w-1`; the checked-in
PV definitions mirror production capacity, access mode, storage class, and
node affinity. On a fresh worker, add the `.keep` paths with the Talos machine
config patch, reboot only that worker if required to materialize them, and
verify the directories with `talosctl list` before applying PVs:

```bash
set -euo pipefail
CTX=homelab
W1_ADDR="$(kubectl --context "$CTX" get node k8s-w-1 -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')"
TALOSCONFIG="$HOME/.local/share/homelab-talos/base/talosconfig"
WORK="$(mktemp -d)"
chmod 700 "$WORK"
trap 'rm -rf "$WORK"' EXIT
cat >"$WORK/worker-patch.yaml" <<'YAML'
machine:
  files:
    - content: Talos local Homepage restore drill storage root
      permissions: 0o644
      path: /var/mnt/homepage-drill/config/.keep
      op: create
    - content: Talos local Homepage restore drill storage root
      permissions: 0o644
      path: /var/mnt/homepage-drill/caddy/.keep
      op: create
    - content: Talos local Homepage restore drill storage root
      permissions: 0o644
      path: /var/mnt/homepage-drill/tailscale/.keep
      op: create
YAML
talosctl patch machineconfig --nodes "$W1_ADDR" --endpoints "$W1_ADDR" \
  --talosconfig "$TALOSCONFIG" --mode no-reboot --patch "@$WORK/worker-patch.yaml"
PATHS_READY=true
for path in config caddy tailscale; do
  if ! talosctl list "/var/mnt/homepage-drill/$path" --nodes "$W1_ADDR" \
    --endpoints "$W1_ADDR" --talosconfig "$TALOSCONFIG" >/dev/null 2>&1; then
    PATHS_READY=false
  fi
done
if [[ "$PATHS_READY" != true ]]; then
  talosctl reboot --nodes "$W1_ADDR" --endpoints "$W1_ADDR" \
    --talosconfig "$TALOSCONFIG"
  kubectl --context "$CTX" wait --for=condition=Ready node/k8s-w-1 --timeout=600s
fi
for path in config caddy tailscale; do
  talosctl list "/var/mnt/homepage-drill/$path" --nodes "$W1_ADDR" \
    --endpoints "$W1_ADDR" --talosconfig "$TALOSCONFIG"
done
cat >"$WORK/scratch-pvs.yaml" <<'YAML'
apiVersion: v1
kind: PersistentVolume
metadata:
  name: homepage-drill-config
spec:
  capacity:
    storage: 1Gi
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Delete
  storageClassName: pve-g3-1-local
  volumeMode: Filesystem
  local:
    path: /var/mnt/homepage-drill/config
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - key: kubernetes.io/hostname
              operator: In
              values: [k8s-w-1]
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: homepage-drill-caddy
spec:
  capacity:
    storage: 256Mi
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Delete
  storageClassName: pve-g3-1-local
  volumeMode: Filesystem
  local:
    path: /var/mnt/homepage-drill/caddy
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - key: kubernetes.io/hostname
              operator: In
              values: [k8s-w-1]
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: homepage-drill-tailscale
spec:
  capacity:
    storage: 64Mi
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Delete
  storageClassName: pve-g3-1-local
  volumeMode: Filesystem
  local:
    path: /var/mnt/homepage-drill/tailscale
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - key: kubernetes.io/hostname
              operator: In
              values: [k8s-w-1]
YAML
kubectl --context "$CTX" apply -f "$WORK/scratch-pvs.yaml"
kubectl --context "$CTX" wait --for=jsonpath='{.status.phase}'=Available \
  pv/homepage-drill-config pv/homepage-drill-caddy pv/homepage-drill-tailscale \
  --timeout=120s
```

Create the target namespace, then recreate its Secrets before restoring. For
an in-cluster drill where the source namespace still exists, copy Secret objects
without printing their data:

```bash
CTX=homelab
SOURCE_NS=homepage
TARGET_NS=homepage-drill
kubectl --context "$CTX" create namespace "$TARGET_NS"
for secret in homepage-environment homepage-caddy; do
  kubectl --context "$CTX" -n "$SOURCE_NS" get secret "$secret" -o json \
    | jq --arg ns "$TARGET_NS" \
      'del(.metadata.uid,.metadata.resourceVersion,.metadata.creationTimestamp,.metadata.managedFields,.metadata.ownerReferences) | .metadata.namespace=$ns' \
    | kubectl --context "$CTX" apply -f -
done
```

For a recovery where the source namespace is unavailable, create the two
Homepage Secrets from protected local files populated from the existing Vault
values. Keep the files outside the repository with mode `0600`; the environment
file keys are the `HOMEPAGE_VAR_*` entries supplied by Vault through
`apps/homepage/values.ansible.yaml.j2`:

```bash
set -euo pipefail
CTX=homelab
TARGET_NS=homepage-drill
umask 077
HOMEPAGE_SECRETS_ENV_FILE="$HOME/.local/share/homepage-secrets.env"
CLOUDFLARE_TOKEN_FILE="$HOME/.local/share/homepage-cloudflare-token"
kubectl --context "$CTX" -n "$TARGET_NS" create secret generic homepage-environment \
  --from-env-file="$HOMEPAGE_SECRETS_ENV_FILE" --dry-run=client -o yaml \
  | kubectl --context "$CTX" apply -f -
kubectl --context "$CTX" -n "$TARGET_NS" create secret generic homepage-caddy \
  --from-file=cloudflare_api_token="$CLOUDFLARE_TOKEN_FILE" \
  --dry-run=client -o yaml | kubectl --context "$CTX" apply -f -
```

The PVCs restored from the backup carry production PV names. The resource
modifier below rewrites their `volumeName` fields to the scratch PVs; applying
the backup's PV objects encounters the already-existing production PV names,
while the restored claims bind only to the scratch PVs:

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
          resourceNameRegex: '^homepage-config$'
          namespaces: [homepage]
        patches:
          - operation: add
            path: /spec/volumeName
            value: homepage-drill-config
      - conditions:
          groupResource: persistentvolumeclaims
          resourceNameRegex: '^homepage-caddy$'
          namespaces: [homepage]
        patches:
          - operation: add
            path: /spec/volumeName
            value: homepage-drill-caddy
      - conditions:
          groupResource: persistentvolumeclaims
          resourceNameRegex: '^homepage-tailscale$'
          namespaces: [homepage]
        patches:
          - operation: add
            path: /spec/volumeName
            value: homepage-drill-tailscale
YAML
kubectl --context "$CTX" -n velero exec deployment/velero -- /velero restore create \
  homepage-drill-restore --from-backup "$BACKUP" \
  --namespace-mappings homepage:homepage-drill \
  --resource-modifier-configmap homepage-drill-restore-modifiers --wait
kubectl --context "$CTX" -n velero get restore homepage-drill-restore
kubectl --context "$CTX" -n velero get podvolumerestores \
  -l velero.io/restore-name=homepage-drill-restore \
  -o custom-columns=VOLUME:.spec.volume,PHASE:.status.phase,BYTES:.status.progress.totalBytes
kubectl --context "$CTX" -n homepage-drill get pvc -o wide
```

For this Homepage pod, expect completed PodVolumeRestores for `homepage-config`,
`caddy-state`, and `caddy-runtime`, with no `tailscale-state` restore. The
Tailscale state is excluded to prevent cloning a live tailnet identity. Once
the volume restores complete, drop the Tailscale and Caddy sidecars in the
scratch Deployment so the Homepage container can be evaluated by itself:

```bash
CTX=homelab
kubectl --context "$CTX" -n homepage-drill patch deployment homepage \
  --type=json \
  --patch='[{"op":"remove","path":"/spec/template/spec/containers/1"},{"op":"remove","path":"/spec/template/spec/containers/1"}]'
kubectl --context "$CTX" -n homepage-drill rollout status deployment/homepage --timeout=300s
kubectl --context "$CTX" -n homepage-drill get pods -o wide
```

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

Run cleanup only after verification is finished and the drill workload is down.
This deletes only `homepage-drill`, its three named scratch PVs, and the three
scratch directories. The Talos baseline file must be the saved `k8s-w-1`
configuration containing the three production `.keep` entries and no
`homepage-drill` entries:

```bash
CTX=homelab
W1_ADDR="$(kubectl --context "$CTX" get node k8s-w-1 -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')"
TALOSCONFIG="$HOME/.local/share/homelab-talos/base/talosconfig"
BASELINE="$HOME/.local/share/homelab-talos/k8s-w-1.yaml"
if grep -q '/var/mnt/homepage-drill' "$BASELINE"; then
  echo "Saved Talos baseline still contains drill paths; stop." >&2
  exit 1
fi
for path in /var/mnt/homepage/config/.keep /var/mnt/homepage/caddy/.keep \
  /var/mnt/homepage/tailscale/.keep; do
  grep -qF "$path" "$BASELINE" || { echo "Production path missing from baseline: $path" >&2; exit 1; }
done
kubectl --context "$CTX" -n homepage-drill scale deployment/homepage --replicas=0
kubectl --context "$CTX" -n homepage-drill wait --for=delete pod \
  -l app.kubernetes.io/name=homepage --timeout=180s
kubectl --context "$CTX" delete namespace homepage-drill --wait=true --timeout=300s
kubectl --context "$CTX" delete pv homepage-drill-config homepage-drill-caddy \
  homepage-drill-tailscale --ignore-not-found=true --wait=true
talosctl apply-config --nodes "$W1_ADDR" --endpoints "$W1_ADDR" \
  --talosconfig "$TALOSCONFIG" --mode no-reboot --file "$BASELINE"
kubectl --context "$CTX" -n velero apply -f - <<'YAML'
apiVersion: batch/v1
kind: Job
metadata:
  name: homepage-drill-storage-cleanup
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 300
  template:
    spec:
      nodeName: k8s-w-1
      automountServiceAccountToken: false
      restartPolicy: Never
      containers:
        - name: cleanup
          image: docker.io/amazon/aws-cli:2.34.0@sha256:97cc5f847898f54432492c128408c62e0df2153d9ad36573be8e5a03826123b0
          imagePullPolicy: IfNotPresent
          command:
            - /bin/sh
            - -ec
            - |
              test "$(ls -1A /scratch | sort | tr '\n' ' ')" = "caddy config tailscale "
              test -d /scratch/config
              test -d /scratch/caddy
              test -d /scratch/tailscale
              rm -rf -- /scratch/config /scratch/caddy /scratch/tailscale
              echo "Removed the three Homepage drill storage directories."
          securityContext:
            privileged: true
            runAsUser: 0
          volumeMounts:
            - name: scratch-root
              mountPath: /scratch
      volumes:
        - name: scratch-root
          hostPath:
            path: /var/mnt/homepage-drill
            type: Directory
YAML
kubectl --context "$CTX" -n velero wait --for=condition=Complete \
  job/homepage-drill-storage-cleanup --timeout=300s
kubectl --context "$CTX" -n velero logs job/homepage-drill-storage-cleanup
kubectl --context "$CTX" -n velero delete job/homepage-drill-storage-cleanup \
  configmap/homepage-drill-restore-modifiers --ignore-not-found=true
kubectl --context "$CTX" -n homepage rollout status deployment/homepage --timeout=300s
kubectl --context "$CTX" get pv homepage-config homepage-caddy homepage-tailscale -o wide
```

Confirm the drill namespace and PVs are absent, the scratch paths no longer
list on `k8s-w-1`, all three production PV claims remain Bound to their original
paths, and production Homepage is healthy. Do not run the cleanup block against
a real restored namespace whose scratch PVs are now serving production.


[Back to Kubernetes overview](README.md).
