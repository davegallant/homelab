# Kubernetes workloads

This repository stores Kubernetes workloads as Helm charts and Ansible-managed
manifests. Homepage runs on Talos and is managed by the local Helm chart in
`ansible/kubernetes/apps/homepage/chart/`. Its source config remains in
`ansible/kubernetes/apps/homepage/config/`. The former Homepage LXC playbook
has been retired.

## Existing Secrets and future GitOps ownership

Argo CD bootstrap and the first BentoPDF handoff are documented in
[`apps/argocd/README.md`](apps/argocd/README.md). The bootstrap remains
available for recovery; all Helm releases, including Argo CD itself, are
managed by Applications that read GitHub `main` and require sync approval.
See [`apps/argocd/MANAGEMENT.md`](apps/argocd/MANAGEMENT.md) for the inventory,
external-resource workflow, and recovery safeguards.

The application charts can consume Secrets provisioned separately from Helm.
Empty `existingSecret` values preserve the current Vault-to-Helm deployment
path. Set the following values to use an existing Secret instead; the chart
then references it without rendering or requiring its secret values:

| Chart value | Required Secret keys |
|---|---|
| BentoPDF / SearXNG `newt.existingSecret` | `PANGOLIN_ENDPOINT`, `NEWT_ID`, `NEWT_SECRET` |
| SearXNG `settings.existingSecret` | `settings.yml` (complete application settings) |
| Miniflux `existingSecret` | `db-user`, `db-password`, `admin-username`, `admin-password`; `newt-id`, `newt-secret` when Newt is enabled |
| Homepage `homepage.existingSecret` | Existing `HOMEPAGE_VAR_*` environment keys |
| Homepage / Kiwix `caddy.existingSecret` | `cloudflare_api_token` |

Non-secret configuration such as hostnames, Miniflux's base URL and Pangolin
endpoint, and Homepage's rendered config files still needs to be supplied.
The one-use Tailscale auth Secret remains part of the registration workflow.

For a future ownership transfer, create Secrets under **new names** from
Vault before selecting them in values. Switching to the name of an existing
Helm-owned Secret without first transferring ownership can cause Helm to
delete that Secret on upgrade. Keep secret values out of Git. Let one tool
own each Secret; Argo CD can later own the charts while Ansible supplies
the external Secrets.

Changing an external Secret does not automatically roll pods. Restart
workloads after environment-variable changes; SearXNG also needs a restart
because its settings file uses a subPath mount. Its settings checksum is
only rendered when the chart manages the settings Secret. Credential
rotation for an existing PostgreSQL database must update the database role
as well as the Secret; changing `POSTGRES_PASSWORD` alone does not rotate it.

## Homepage

The pilot runs Homepage, Caddy, and a Tailscale sidecar in one Pod. Tailscale
Serve forwards tailnet TCP 443 to Caddy on loopback port 8443. Caddy keeps the
existing Cloudflare DNS-01 certificate flow; Homepage is allowed at
`homepage.{{ headscale_magic_dns_domain }}`. The Tailscale node registered as
`homepage-k8s` for staging. The first cutover was rolled back after widget API
requests failed to reach private tailnet services. The desired Tailscale
hostname is in `apps/homepage/vars.yaml`.

The userspace Tailscale sidecar handles inbound HTTPS and exposes a local
outbound HTTP proxy. Homepage's Node preloader in `apps/homepage/proxy-agent.cjs`
routes requests to private tailnet hosts through that proxy, including the
TrueNAS WebSocket upgrade. Configured non-tailnet widget URL hosts connect
directly. Plain Node proxy
environment variables alone do not fix Homepage v2.6.0 because it constructs
custom HTTP agents. A kernel-mode Tailscale sidecar was tried with scoped
`NET_ADMIN`, `NET_RAW`, and `/dev/net/tun`, but Talos's cluster-wide Pod Security
baseline rejected the Pod. No Pod Security exception was applied. The preloader
is specific to Homepage's Node networking; future workloads need their own
outbound proxy support or another reviewed route.

Homepage's `/app/config` is a writable local PVC because the application writes
logs and generated files there. Ansible-managed `services.yaml` and
`settings.yaml` are mounted over that PVC from a ConfigMap. The custom icon
directory is a binary ConfigMap mounted at `/app/public/icons`. Tailscale state
and Caddy certificate state have separate local PVCs. All three PVs and the Pod
are pinned to `k8s-w-1` on `pve-g3-1`.

Edit the tracked `services.yaml`, `settings.yaml`, and icon files in
`ansible/kubernetes/apps/homepage/config/`; those remain Ansible-managed.
During migration, the remaining runtime config was streamed directly from the
former Homepage LXC into the PVC, excluding the managed files, icons, logs, and
Git metadata. Its contents never entered the repository or a local temporary
file. Edit imported files on the PVC with `kubectl cp`/`kubectl exec` until they
are added to the repo as Ansible-managed templates. Edit the Helm chart under
`ansible/kubernetes/apps/homepage/chart/` and the Ansible-to-Helm values bridge
at `ansible/kubernetes/apps/homepage/values.ansible.yaml.j2`. The playbook
validates the chart and values, then manages the deployed release. The default
`verify` action is read-only; `rehearse` installs into the drill namespace, and
`adopt` updates production and verifies its backup. Vault values are rendered
to a protected temporary file and removed after the run.

From `ansible/`, after the Talos cluster and its protected kubeconfig exist:

```sh
ansible-playbook playbooks/talos-cluster/homepage.yml \
  -i inventory \
  --vault-password-file .vault_pass
```

The playbook defaults to read-only verification. To adopt or rehearse, pass
`-e homepage_action=adopt` or `-e homepage_action=rehearse`. It prompts for the
expected kubectl context. On first registration,
it creates a one-use Headscale preauth key through the repo's `pangolin` SSH
connection, holds the value only in Ansible memory and a short-lived Kubernetes
Secret, and removes the Secret after Tailscale identity persists across a pod
restart. Later runs reuse the PVC-backed identity. Do not run this playbook
in CI or as part of the normal all-host playbook list.

The Homepage hostname has been moved to the Kubernetes tailnet node.
`verify-cutover.yml` confirms that it resolves to the Kubernetes tailnet IP
and returns HTTP 200 with valid TLS. The former LXC is retired from Ansible and
is no longer a supported rollback target. The verification playbook requires
the Vault password file and the protected Talos kubeconfig as `KUBECONFIG`.

From `ansible/`, verify the active Homepage hostname with:

```sh
KUBECONFIG="$HOME/.local/share/homelab-talos/kubeconfig" \
  ansible-playbook playbooks/talos-cluster/verify-cutover.yml \
  -i inventory --vault-password-file .vault_pass
```

## Capacity, backups, and observability

The pilot's VM layout is recorded in `cluster/README.md`. Keep the `pve-g3-2`
memory gate: inspect host availability and worker health before adding
workloads. `k8s-w-2` is at 2 GiB. Homepage's local data resides on `k8s-w-1`;
loss of that worker
means the dashboard is down until the worker returns or its data is restored
and deliberately relocated.

Proxmox `vzdump` is the first backup layer and includes all three Talos VMs;
that captures the worker's local PV data as part of its VM disk. A separate
off-host etcd snapshot is also taken through `snapshot-etcd.yml`. Keep secure
recovery of Talos credentials and Ansible Vault, and a tested procedure for
recovering the Homepage paths `/var/mnt/homepage/config`,
`/var/mnt/homepage/tailscale`, and `/var/mnt/homepage/caddy`. A full VM restore
must be isolated from the live cluster until node identity and etcd membership
are reconciled. The retired Homepage LXC is not a rollback target.

### Velero namespace restore

The Kubernetes layer is backed up by Velero with Kopia filesystem backups:
Talos cluster → Velero/node-agent → Garage on TrueNAS → covered by Dave's
existing TrueNAS-to-Drive sync. The `homepage-daily` schedule runs at 03:00,
keeps backups for 14 days, includes only `homepage`, and excludes Secrets.
Secrets are intentionally excluded because Velero's resource archive is not
encrypted. Recreate them from Vault before judging restored workloads.

Use direct `kubectl` and `talosctl` commands for recovery; no Ansible playbook
is required. Set the context and backup name first, and stop if the cluster,
backup, or Garage storage location is not healthy:

```bash
set -euo pipefail
CTX=homelab
BACKUP=homepage-daily-20261022020014
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
BACKUP=homepage-daily-20261022020014
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

#### Remove a completed drill

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

The Homepage pilot initially used `kubectl logs` and the Homepage file log.
The Alloy follow-up is prepared under `apps/alloy/`. It reads Kubernetes pod
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
the 2 GiB worker's free memory after rollout.

Apply these as two separately approved actions: first run the Grafana playbook
to admit the Talos node IPs to Loki; then run the Alloy playbook to create the
namespace, RBAC, ConfigMap, and DaemonSet. The Alloy playbook is manual; the
Grafana playbook is also part of the normal all-host CI run, so merging this
branch will reapply its firewall rule. From `ansible/`:

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
