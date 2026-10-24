# Audiobookshelf on the Talos cluster (Argo CD)

Audiobookshelf runs from the bjw-s **app-template** chart (5.3.0) as
an Argo CD Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application
definition is `../argocd/applications/audiobookshelf.yaml`. Syncs are
manual, pruning is off, and deleting the Application preserves the
workload.

Workload source of truth: `playbooks/audiobookshelf/docker-compose.yml`
(image `ghcr.io/advplyr/audiobookshelf:2.37.1`, port 80,
`/mnt/media/Audiobooks:/audiobooks`, `/mnt/media/Podcasts:/podcasts`,
`./metadata:/metadata`, `./config:/config`).

Exposure is **public via Pangolin — this app stays public.** The
compose's Newt sidecar is reproduced in-pod with the *same* Newt
identity, so the existing Pangolin route and public URL carry over
unchanged. Never rewrite this app as tailnet-only. Expect a brief
public outage at cutover while the Newt identity moves from the LXC
to the pod.

The libraries are static NFS PVs (`storage.yaml`) onto the existing
TrueNAS exports (`/mnt/tank/media/Audiobooks`,
`/mnt/tank/media/Podcasts`), read-write like the LXC mounts; they
never move and are never Velero-backed-up (TrueNAS snapshots + Drive
sync). Verify the share paths against the LXC's `/mnt/media` mount
sources before applying `storage.yaml`. The app state lands on two
local-path PVCs: `config` (1Gi) and `metadata` (10Gi — cover cache
and backups grow). The image runs as root; copied state keeps its
LXC ownership (no chown to 1000 for this app).

Secrets stay in Vault and outside Argo's ownership:
`audiobookshelf-newt-external`, created by
`playbooks/talos-cluster/audiobookshelf-secret.yml`.

Backups: Velero Schedule `audiobookshelf-daily` (in the values,
opt-in mode) with pod annotation
`backup.velero.io/backup-volumes: config,metadata`. The network
policy is the house default-deny CiliumNetworkPolicy, in the values
as `rawResources.defaultDenyNetworkPolicy`.

## Prerequisites (once)

1. `apps/argocd/project.yaml` updated (audiobookshelf destination;
   `cilium.io`/`CiliumNetworkPolicy` in the namespace resource
   whitelist) and applied via
   `playbooks/talos-cluster/argocd-project.yml` — see the note in
   the Navidrome README.
2. Namespace + library volumes:
   `kubectl --context admin@homelab apply -f kubernetes/apps/audiobookshelf/storage.yaml`
3. Secrets: run `playbooks/talos-cluster/audiobookshelf-secret.yml`.

## Staging

Values ship with `replicas: 0`. Commit, push, register the
Application, approve the first Sync — objects and PVCs appear, no pod
starts, the LXC keeps serving:

```sh
kubectl --context admin@homelab apply -f kubernetes/apps/argocd/applications/audiobookshelf.yaml
```

Verify both library PVs are Bound and the libraries are visible from
a debug pod (file counts at the roots are enough — the trees are the
NAS's, unchanged) before scheduling the cutover.

## Cutover

1. Stop the LXC stack (this also drops the public route until step 4):

   ```sh
   ssh root@audiobookshelf 'cd ~ && docker compose down'
   ```

2. Copy `./config` and `./metadata` into their PVCs with one
   datacopy helper pod mounting both claims (busybox image as in
   the LubeLogger README):

   ```sh
   kubectl --context admin@homelab -n audiobookshelf apply -f - <<'EOF'
   apiVersion: v1
   kind: Pod
   metadata:
     name: datacopy
     namespace: audiobookshelf
   spec:
     restartPolicy: Never
     containers:
       - name: datacopy
         image: docker.io/library/busybox:1.37.0@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e
         command: ["sleep", "3600"]
         volumeMounts:
           - name: config
             mountPath: /config
           - name: metadata
             mountPath: /metadata
     volumes:
       - name: config
         persistentVolumeClaim:
           claimName: audiobookshelf-config
       - name: metadata
         persistentVolumeClaim:
           claimName: audiobookshelf-metadata
   EOF
   kubectl --context admin@homelab -n audiobookshelf wait --for=condition=Ready pod/datacopy --timeout=120s
   ssh root@audiobookshelf 'tar -C /root/config -cf - .' \
     | kubectl --context admin@homelab -n audiobookshelf exec -i datacopy -- tar -C /config -xf -
   ssh root@audiobookshelf 'tar -C /root/metadata -cf - .' \
     | kubectl --context admin@homelab -n audiobookshelf exec -i datacopy -- tar -C /metadata -xf -
   kubectl --context admin@homelab -n audiobookshelf delete pod datacopy
   ```

   Verify file count AND total bytes of regular files for each dir
   on both sides before continuing; directory metadata is excluded.
   Preserve ownership exactly as copied (the app runs as root).
   Mismatch → debug and re-copy; if it will not verify, restart the
   LXC stack, leave Audiobookshelf serving there, and report.

   Then bind the copied directories through repo-managed static
   local PVs (write `config-local-pv.yaml` / `metadata-local-pv.yaml`
   from the dynamic claims' provisioned paths and node, following
   `seerr/config-local-pv.yaml`) and add the `-local` claims to the
   values with the originals kept mounted read-only under
   `/mnt/audiobookshelf-rollback-*` — the Batch A post-cutover shape.

3. There is no Headscale gate for this app (it is public); the gate
   is the cutover approval itself.
4. Remove `replicas: 0` from the values, commit, push, approve Sync.
5. Verify: pod `2/2` Ready; the public Audiobookshelf URL shows the
   existing libraries, users, and progress; Argo Synced/Healthy.
   Create and verify a Velero backup whose PodVolumeBackups cover
   BOTH `config` and `metadata` (adapt the script in the Navidrome
   README: schedule `audiobookshelf-daily`, expect two Completed
   PodVolumeBackups, one per volume).
6. Leave the stopped LXC as rollback target until soak completes.

Rollback: `docker compose up -d` on the LXC (its Newt sidecar
re-registers the public route); bring the cluster pod down via a
`replicas: 0` commit + Sync so the Newt identity is not claimed
twice.
