# Kubernetes backups and Homepage restore drill

Backup scope, UTC schedules, retention, and Secret inclusion are declared in
[velero-schedules](apps/velero-schedules/) and the Forgejo chart. Inspect those
sources and live Schedule objects before relying on coverage. A schedule is
not evidence that a backup or restore succeeded.

Velero resource archives are not encrypted. Restrict Garage and off-site
copies, especially backups including Secrets. Recreate external Secrets from
Ansible Vault. Verify off-site encryption and deletion retention independently.

Keep the Kopia repository password in Vault. Never replace its Kubernetes
Secret alone: existing repositories require a coordinated password change.
Rehearse against an isolated repository copy, preserve snapshot counts, and
verify restores and a fresh backup before resuming schedules.

## Recovery safeguards

Proxmox VM backups cover the Talos disks, including local PV data. Separate
off-host etcd snapshots protect cluster state. Protect the operator's Talos
credentials and Ansible Vault too. Isolate a full VM restore from the live
cluster until node identity and etcd membership are reconciled.

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

Require completed PodVolumeRestores matching the selected backup's volume
inventory and expected byte counts, plus a Running, Ready pod. Inspect the
saved Deployment before restore: remove identity-bearing sidecars and routes
from the drill rather than cloning production identities.

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
healthy, and production claims remain Bound to their original PVs.


[Back to Kubernetes overview](README.md).
