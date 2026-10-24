# Maloja on the Talos cluster (Argo CD)

Maloja runs from the bjw-s **app-template** chart (5.3.0) as an Argo
CD Application — no local chart. Desired state is
`values.production.yaml`; the Application definition is
`../argocd/applications/maloja.yaml`. Syncs are manual, pruning is
off, and deleting the Application preserves the workload.

Workload source of truth: `playbooks/maloja/docker-compose.yml`
(image `docker.io/krateng/maloja:3.2.9` digest-pinned, port 42010,
bind mount `$PWD/data:/data` — `/root/data` on the LXC). Environment
is carried over verbatim, including `MALOJA_FORCE_PASSWORD=stub`
(already committed in the LXC playbook; not a real credential —
access control is the tailnet itself).

Exposure is **tailnet-only**: userspace Tailscale sidecar → in-pod
Caddy (8443, Cloudflare DNS-01) → Maloja on 127.0.0.1:42010, at
`maloja.tail.davegallant.ca`.

Secrets stay in Vault and outside Argo's ownership:
`maloja-caddy-external` (from `gitops-secrets.yml`) and the
bootstrap-only one-use `maloja-tailscale-auth`.

Backups: Velero Schedule `maloja` (in the values, opt-in mode)
with pod annotation `backup.velero.io/backup-volumes: data-local`.
The local-path provisioner creates hostPath-backed PVs, which Velero does
not support for PodVolumeBackup. After verifying the copied data, the
`maloja-data-local` claim points to the same directory via a static local
PV. Its worker and path are specific to this staged copy and must be taken
from the bound `maloja-data` PV during a fresh migration; the original PVC
stays present for rollback.

## Prerequisites (once)

1. `apps/argocd/project.yaml` updated (bjw-s repo, `maloja`
   destination, PersistentVolumeClaim whitelist) and re-applied.
2. Namespace: `kubectl --context admin@homelab apply -f kubernetes/apps/maloja/storage.yaml`
3. Caddy secret: run `playbooks/talos-cluster/gitops-secrets.yml`.

## Staging

Values ship with `replicas: 0`. Commit, push, register the
Application, approve the first Sync — objects and PVCs appear, no pod
starts, the LXC keeps serving:

```sh
kubectl --context admin@homelab apply -f kubernetes/apps/argocd/applications/maloja.yaml
```

## Cutover

1. Stop the LXC stack:

   ```sh
   ssh root@maloja 'cd ~ && docker compose down'
   ```

2. Copy the data directory into the PVC:

   ```sh
   kubectl --context admin@homelab -n maloja apply -f - <<'EOF'
   apiVersion: v1
   kind: Pod
   metadata:
     name: datacopy
     namespace: maloja
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
           claimName: maloja-data
   EOF
   kubectl --context admin@homelab -n maloja wait --for=condition=Ready pod/datacopy --timeout=120s
   ssh root@maloja 'tar -C /root/data -cf - .' | kubectl --context admin@homelab -n maloja exec -i datacopy -- tar -C /data -xf -
   kubectl --context admin@homelab -n maloja exec datacopy -- chown -R 1000:1000 /data
   kubectl --context admin@homelab -n maloja exec datacopy -- sh -c 'find /data -type f | wc -l; find /data -type f -exec stat -c %s {} \; | awk "{total += \$1} END {print total+0}"'
   ssh root@maloja 'find /root/data -type f | wc -l; find /root/data -type f -exec stat -c %s {} \; | awk "{total += \$1} END {print total+0}"'
   kubectl --context admin@homelab -n maloja delete pod datacopy
   ```

   File count and the sum of regular-file byte sizes must match before
   continuing. Directory metadata is excluded because the LXC and PVC
   filesystems can report different directory sizes.

   Apply the repo-managed local PV for the copied directory:

   ```sh
   kubectl --context admin@homelab apply -f kubernetes/apps/maloja/data-local-pv.yaml
   ```

   Commit and push the values update while `replicas: 0` remains set, then
   manually Sync Maloja. Confirm `maloja-data-local` is Bound before
   continuing; the active app will use this claim after the final flip.

3. Retire the LXC's tailnet node on the Headscale host
   (`headscale nodes delete --identifier <old-maloja-id>`).
4. Create the one-use key + Secret (`maloja-tailscale-auth`, key
   `TS_AUTHKEY`) as in the Seerr README.
5. Remove `replicas: 0` from the values, commit, push, approve Sync.
6. Verify: pod `3/3` Ready; `https://maloja.tail.davegallant.ca`
   shows the existing scrobble history; Argo Synced/Healthy. Create
   and verify a Velero backup with its data PodVolumeBackup:

   ```sh
   set -euo pipefail
   kubectl --context admin@homelab -n velero exec deployment/velero -- \
     /velero backup create --from-schedule maloja --wait
   BACKUP="$(kubectl --context admin@homelab -n velero get backups.velero.io \
     -l velero.io/schedule-name=maloja -o json \
     | jq -r '.items | sort_by(.metadata.creationTimestamp) | last | .metadata.name')"
   kubectl --context admin@homelab -n velero wait \
     --for=jsonpath='{.status.phase}'=Completed "backup/$BACKUP" --timeout=600s
   PVBS="$(kubectl --context admin@homelab -n velero \
     get podvolumebackups.velero.io -l "velero.io/backup-name=$BACKUP" -o json)"
   PVB="$(jq -er --arg volume data-local '
     .items as $items
     | if ($items | length) == 1 and $items[0].spec.volume == $volume
        and $items[0].status.phase == "Completed"
       then $items[0].metadata.name
       else error("expected one Completed data-local PodVolumeBackup") end' <<<"$PVBS")"
   printf 'Verified backup %s; PodVolumeBackup %s: Completed\n' "$BACKUP" "$PVB"
   ```

   Delete the spent `maloja-tailscale-auth` Secret. Send a test
   scrobble from a client to confirm ingestion works.
7. Leave the stopped LXC as rollback target until soak completes.

Rollback: `docker compose up -d` on the LXC (re-register its
tailscale first if step 3 already deleted the node); bring the
cluster pod down via a `replicas: 0` commit + Sync to free the name.
