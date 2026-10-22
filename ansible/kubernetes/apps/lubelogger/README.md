# LubeLogger on the Talos cluster (Argo CD)

LubeLogger runs from the bjw-s **app-template** chart (5.3.0) as an
Argo CD Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application definition
is `../argocd/applications/lubelogger.yaml`. Syncs are manual, pruning
is off, and deleting the Application preserves the workload.

Workload source of truth: `playbooks/lubelogger/docker-compose.yml`
(image `ghcr.io/hargata/lubelogger:v1.4.5`, port 8080). The compose
file's **eight named volumes** are consolidated into one local-path
PVC (`lubelogger-data`, 2Gi) mounted by subPath: `config`, `data`,
`translations`, `documents`, `images`, `temp`, `log`, and `keys`
(the ASP.NET DataProtection keys — losing them invalidates protected
data, so they are copied and backed up with everything else).

Exposure is **tailnet-only**: the pod mirrors the Kiwix shape —
userspace Tailscale sidecar → in-pod Caddy (8443, Cloudflare DNS-01)
→ LubeLogger on 127.0.0.1:8080, at `lubelogger.tail.davegallant.ca`.

Secrets stay in Vault and outside Argo's ownership:
`lubelogger-caddy-external` (from `gitops-secrets.yml`) and the
bootstrap-only one-use `lubelogger-tailscale-auth`.

Backups: Velero Schedule `lubelogger` (in the values, opt-in
mode) with pod annotation `backup.velero.io/backup-volumes: data-local`.
The copied local-path directory is exposed through a static local PV so
Velero can make a filesystem backup. The original claim stays mounted
read-only for rollback.

## Prerequisites (once)

1. `apps/argocd/project.yaml` updated (bjw-s repo, `lubelogger`
   destination, PersistentVolumeClaim whitelist) and re-applied.
2. Namespace: `kubectl --context admin@homelab apply -f ansible/kubernetes/apps/lubelogger/storage.yaml`
3. Caddy secret: run `playbooks/talos-cluster/gitops-secrets.yml`.

## Staging

Values ship with `replicas: 0`. Commit, push, register the
Application, approve the first Sync — objects and PVCs appear, no pod
starts, the LXC keeps serving:

```sh
kubectl --context admin@homelab apply -f ansible/kubernetes/apps/argocd/applications/lubelogger.yaml
```

## Cutover

1. Stop the LXC stack:

   ```sh
   ssh root@lubelogger 'cd ~ && docker compose down'
   ```

2. Copy the eight volumes into the PVC. Volume names below assume the
   compose project is `root` (compose file in `/root`); confirm with
   `docker volume ls` on the LXC first and adjust the prefix if not.

   ```sh
   kubectl --context admin@homelab -n lubelogger apply -f - <<'EOF'
   apiVersion: v1
   kind: Pod
   metadata:
     name: datacopy
     namespace: lubelogger
   spec:
     restartPolicy: Never
     containers:
       - name: datacopy
         image: docker.io/library/busybox:1.37.0@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e
         command: ["sleep", "3600"]
         volumeMounts:
           - name: data
             mountPath: /data
     volumes:
       - name: data
         persistentVolumeClaim:
           claimName: lubelogger-data
   EOF
   kubectl --context admin@homelab -n lubelogger wait --for=condition=Ready pod/datacopy --timeout=120s
   kubectl --context admin@homelab -n lubelogger exec datacopy -- mkdir -p /data/config /data/data /data/translations /data/documents /data/images /data/temp /data/log /data/keys
   for v in config data translations documents images temp log keys; do
     ssh root@lubelogger "tar -C /var/lib/docker/volumes/root_${v}/_data -cf - ." \
       | kubectl --context admin@homelab -n lubelogger exec -i datacopy -- tar -C /data/${v} -xf -
   done
   kubectl --context admin@homelab -n lubelogger exec datacopy -- chown -R 1000:1000 /data
   kubectl --context admin@homelab -n lubelogger exec datacopy -- sh -c '
   for v in config data translations documents images temp log keys; do
     dir="/data/$v"
     printf "%s PVC files: " "$v"
     find "$dir" -type f | wc -l
     printf "%s PVC bytes: " "$v"
     find "$dir" -type f -exec stat -c %s {} \; | awk "{total += \$1} END {print total+0}"
   done'
   ssh root@lubelogger '
   for v in config data translations documents images temp log keys; do
     dir="/var/lib/docker/volumes/root_${v}/_data"
     printf "%s LXC files: " "$v"
     find "$dir" -type f | wc -l
     printf "%s LXC bytes: " "$v"
     find "$dir" -type f -exec stat -c %s {} \; | awk "{total += \$1} END {print total+0}"
   done'
   kubectl --context admin@homelab -n lubelogger delete pod datacopy
   ```

   Compare file count and the sum of regular-file byte sizes for each
   corresponding PVC subdirectory and LXC volume before continuing.
   Directory metadata is excluded because the LXC and PVC filesystems
   can report different directory sizes.

   Bind the copied directory through the repo-managed static local PV;
   this keeps the data on the worker selected by the helper pod and makes
   it eligible for Velero filesystem backups:

   ```sh
   kubectl --context admin@homelab apply -f ansible/kubernetes/apps/lubelogger/data-local-pv.yaml
   ```

   The application values retain `lubelogger-data` read-only and mount
   `lubelogger-data-local` read-write at the same eight subpaths.

3. Retire the LXC's tailnet node on the Headscale host
   (`headscale nodes delete --identifier <old-lubelogger-id>`).
4. Create the one-use key + Secret
   (`lubelogger-tailscale-auth`, key `TS_AUTHKEY`) as in the Seerr
   README.
5. Remove `replicas: 0` from the values, commit, push, approve Sync.
6. Verify: pod `3/3` Ready; `https://lubelogger.tail.davegallant.ca`
   shows the existing vehicles/records; Argo Synced/Healthy. Create
   and verify a Velero backup with its data PodVolumeBackup:

   ```sh
   set -euo pipefail
   kubectl --context admin@homelab -n velero exec deployment/velero -- \
     /velero backup create --from-schedule lubelogger --wait
   BACKUP="$(kubectl --context admin@homelab -n velero get backups.velero.io \
     -l velero.io/schedule-name=lubelogger -o json \
     | jq -r '.items | sort_by(.metadata.creationTimestamp) | last | .metadata.name')"
   kubectl --context admin@homelab -n velero wait \
     --for=jsonpath='{.status.phase}'=Completed "backup/$BACKUP" --timeout=600s
   PVBS="$(kubectl --context admin@homelab -n velero \
     get podvolumebackups.velero.io -l "velero.io/backup-name=$BACKUP" -o json)"
   PVB="$(jq -er --arg volume data '
     .items as $items
     | if ($items | length) == 1 and $items[0].spec.volume == $volume
        and $items[0].status.phase == "Completed"
       then $items[0].metadata.name
       else error("expected one Completed data PodVolumeBackup") end' <<<"$PVBS")"
   printf 'Verified backup %s; PodVolumeBackup %s: Completed\n' "$BACKUP" "$PVB"
   ```

   Delete the spent `lubelogger-tailscale-auth` Secret.
7. Leave the stopped LXC as rollback target until soak completes.

Rollback: `docker compose up -d` on the LXC (re-register its
tailscale first if step 3 already deleted the node); bring the
cluster pod down via a `replicas: 0` commit + Sync to free the name.
