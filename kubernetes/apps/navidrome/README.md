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
rewrite this app as tailnet-only; the compose is authoritative over
the Batch B plan's initial "expected tailnet" note. Expect a brief
public outage at cutover while the Newt identity moves from the LXC
to the pod.

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

## Prerequisites (once)

1. `apps/argocd/project.yaml` updated (navidrome destination;
   `cilium.io`/`CiliumNetworkPolicy` in the namespace resource
   whitelist) and applied via
   `playbooks/talos-cluster/argocd-project.yml` — the playbook
   kubectl-applies the repo file and asserts the policy permission
   is live. (The whitelist went live with the Cilium run; the
   Batch B edit adds the destination.)
2. Namespace + library volume:
   `kubectl --context admin@homelab apply -f kubernetes/apps/navidrome/storage.yaml`
3. Secrets: run `playbooks/talos-cluster/navidrome-secret.yml`.

## Staging

Values ship with `replicas: 0`. Commit, push, register the
Application, approve the first Sync — objects and PVCs appear, no pod
starts, the LXC keeps serving:

```sh
kubectl --context admin@homelab apply -f kubernetes/apps/argocd/applications/navidrome.yaml
```

Verify the `navidrome-music` PV is Bound and the library is visible
from a debug pod before scheduling the cutover.

## Cutover

1. Stop the LXC stack (this also drops the public route until step 4):

   ```sh
   ssh root@navidrome 'cd ~ && docker compose down'
   ```

2. Copy `./data` into the PVC with the datacopy helper pod (busybox
   image as in the LubeLogger README), tar-streamed from the LXC:

   ```sh
   kubectl --context admin@homelab -n navidrome apply -f - <<'EOF'
   apiVersion: v1
   kind: Pod
   metadata:
     name: datacopy
     namespace: navidrome
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
           claimName: navidrome
   EOF
   kubectl --context admin@homelab -n navidrome wait --for=condition=Ready pod/datacopy --timeout=120s
   ssh root@navidrome 'tar -C /root/data -cf - .' \
     | kubectl --context admin@homelab -n navidrome exec -i datacopy -- tar -C /data -xf -
   kubectl --context admin@homelab -n navidrome exec datacopy -- chown -R 1000:1000 /data
   ```

   Verify file count AND total bytes of regular files on both sides
   (`find <dir> -type f | wc -l` and the `stat -c %s` sum, as in the
   LubeLogger README) before continuing; directory metadata is
   excluded. Mismatch → debug and re-copy; if it will not verify,
   restart the LXC stack, leave Navidrome serving there, and report.

   Then bind the copied directory through the repo-managed static local PV and
   claim in `data-local-pv.yaml`, which use the dynamic claim's provisioned
   path and node. The values use `navidrome-data-local` for the app and keep
   the original `navidrome` claim mounted read-only at
   `/mnt/navidrome-rollback-data` — the Batch A post-cutover shape. Commit
   and push the values and PV/PVC, apply the manifest, and manually Sync while
   `replicas: 0` remains set. Confirm `navidrome-data-local` is Bound before
   continuing.

3. There is no Headscale gate for this app (it is public); the gate
   is the cutover approval itself.
4. Remove `replicas: 0` from the values, commit, push, approve Sync.
5. Verify: pod `2/2` Ready; the public Navidrome URL shows the
   existing library and users; Argo Synced/Healthy. Create and
   verify a Velero backup with its `data` PodVolumeBackup:

   ```sh
   set -euo pipefail
   kubectl --context admin@homelab -n velero exec deployment/velero -- \
     /velero backup create --from-schedule navidrome-daily --wait
   BACKUP="$(kubectl --context admin@homelab -n velero get backups.velero.io \
     -l velero.io/schedule-name=navidrome-daily -o json \
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

6. Leave the stopped LXC as rollback target until soak completes.

Rollback: `docker compose up -d` on the LXC (its Newt sidecar
re-registers the public route); bring the cluster pod down via a
`replicas: 0` commit + Sync so the Newt identity is not claimed
twice.
