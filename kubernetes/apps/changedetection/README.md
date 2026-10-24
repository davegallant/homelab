# ChangeDetection on the Talos cluster (Argo CD)

ChangeDetection runs from the bjw-s **app-template** chart (5.3.0) as
an Argo CD Application — no local chart. Desired state is
`values.production.yaml`; the Application definition is
`../argocd/applications/changedetection.yaml`. Syncs are manual,
pruning is off, and deleting the Application preserves the workload.

Workload source of truth: `playbooks/changedetection/docker-compose.yml`
(image `docker.io/dgtlmoon/changedetection.io:0.60.9` digest-pinned,
port 5000, `./changedetection:/datastore` — `/root/changedetection`
on the LXC). The LXC runs without the optional browser sidecar;
parity is kept — no browser container here either. (`HIDE_REFERER=true`
carried over.)

Exposure is **tailnet-only**: userspace Tailscale sidecar → in-pod
Caddy (8443, Cloudflare DNS-01) → ChangeDetection on 127.0.0.1:5000,
at `changedetection.tail.davegallant.ca`.

The Cilium default-deny policy is in `values.production.yaml` under
`rawResources.defaultDenyNetworkPolicy`. It allows same-namespace traffic,
cluster DNS and cluster entities, allows ChangeDetection's internet fetches,
and explicitly denies the LAN, service, and pod CIDR ranges.

Secrets stay in Vault and outside Argo's ownership:
`changedetection-caddy-external` (from `gitops-secrets.yml`) and the
bootstrap-only one-use `changedetection-tailscale-auth`.

Backups: Velero Schedule `changedetection` (in the values,
opt-in mode) with pod annotation
`backup.velero.io/backup-volumes: datastore`.

## Prerequisites (once)

1. `apps/argocd/project.yaml` updated (bjw-s repo, `changedetection`
   destination, PersistentVolumeClaim whitelist) and re-applied.
2. Namespace: `kubectl --context admin@homelab apply -f kubernetes/apps/changedetection/storage.yaml`
3. Caddy secret: run `playbooks/talos-cluster/gitops-secrets.yml`.

## Staging

Values ship with `replicas: 0`. Commit, push, register the
Application, approve the first Sync — objects and PVCs appear, no pod
starts, the LXC keeps serving:

```sh
kubectl --context admin@homelab apply -f kubernetes/apps/argocd/applications/changedetection.yaml
```

## Cutover

1. Stop the LXC stack:

   ```sh
   ssh root@changedetection 'cd ~ && docker compose down'
   ```

2. Copy the datastore into the PVC:

   ```sh
   kubectl --context admin@homelab -n changedetection apply -f - <<'EOF'
   apiVersion: v1
   kind: Pod
   metadata:
     name: datacopy
     namespace: changedetection
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
           claimName: changedetection-datastore
   EOF
   kubectl --context admin@homelab -n changedetection wait --for=condition=Ready pod/datacopy --timeout=120s
   ssh root@changedetection 'tar -C /root/changedetection -cf - .' | kubectl --context admin@homelab -n changedetection exec -i datacopy -- tar -C /data -xf -
   kubectl --context admin@homelab -n changedetection exec datacopy -- chown -R 1000:1000 /data
   kubectl --context admin@homelab -n changedetection exec datacopy -- sh -c 'find /data -type f | wc -l; find /data -type f -exec stat -c %s {} \; | awk "{total += \$1} END {print total+0}"'
   ssh root@changedetection 'find /root/changedetection -type f | wc -l; find /root/changedetection -type f -exec stat -c %s {} \; | awk "{total += \$1} END {print total+0}"'
   kubectl --context admin@homelab -n changedetection delete pod datacopy
   ```

   File count and the sum of regular-file byte sizes must match before
   continuing. Directory metadata is excluded because the LXC and PVC
   filesystems can report different directory sizes.

3. Retire the LXC's tailnet node on the Headscale host
   (`headscale nodes delete --identifier <old-changedetection-id>`).
4. Create the one-use key + Secret (`changedetection-tailscale-auth`,
   key `TS_AUTHKEY`) as in the Seerr README.
5. Remove `replicas: 0` from the values, commit, push, approve Sync.
6. Verify: pod `3/3` Ready;
   `https://changedetection.tail.davegallant.ca` shows the existing
   watches; trigger one watch check to confirm fetching works; Argo
   Synced/Healthy. Create and verify a Velero backup with its datastore
   PodVolumeBackup:

   ```sh
   set -euo pipefail
   kubectl --context admin@homelab -n velero exec deployment/velero -- \
     /velero backup create --from-schedule changedetection --wait
   BACKUP="$(kubectl --context admin@homelab -n velero get backups.velero.io \
     -l velero.io/schedule-name=changedetection -o json \
     | jq -r '.items | sort_by(.metadata.creationTimestamp) | last | .metadata.name')"
   kubectl --context admin@homelab -n velero wait \
     --for=jsonpath='{.status.phase}'=Completed "backup/$BACKUP" --timeout=600s
   PVBS="$(kubectl --context admin@homelab -n velero \
     get podvolumebackups.velero.io -l "velero.io/backup-name=$BACKUP" -o json)"
   PVB="$(jq -er --arg volume datastore '
     .items as $items
     | if ($items | length) == 1 and $items[0].spec.volume == $volume
        and $items[0].status.phase == "Completed"
       then $items[0].metadata.name
       else error("expected one Completed datastore PodVolumeBackup") end' <<<"$PVBS")"
   printf 'Verified backup %s; PodVolumeBackup %s: Completed\n' "$BACKUP" "$PVB"
   ```

   Delete the spent `changedetection-tailscale-auth` Secret.
7. Leave the stopped LXC as rollback target until soak completes.

Rollback: `docker compose up -d` on the LXC (re-register its
tailscale first if step 3 already deleted the node); bring the
cluster pod down via a `replicas: 0` commit + Sync to free the name.
