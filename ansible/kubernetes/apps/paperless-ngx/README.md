# Paperless-ngx on the Talos cluster (Argo CD)

Paperless-ngx runs from the bjw-s **app-template** chart (5.3.0) as
an Argo CD Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application
definition is `../argocd/applications/paperless-ngx.yaml`. Syncs are
manual, pruning is off, and deleting the Application preserves the
workload.

Workload source of truth: `playbooks/paperless-ngx/docker-compose.yml`
(app `docker.io/paperlessngx/paperless-ngx:3.3.3`, port 8000; broker
`docker.io/library/redis:8` in the same pod).

Exposure is **public via Pangolin** — the compose pairs the app with
a Newt sidecar, reproduced in-pod with the *same* Newt identity, so
the existing Pangolin route and public URL carry over unchanged. Do
not rewrite this app as tailnet-only; the compose is authoritative.
Expect a brief public outage at cutover while the Newt identity
moves from the LXC to the pod.

The compose sets no `PAPERLESS_DBHOST`, so the database is SQLite in
the `data` volume. State is four file volumes, all chart-managed
local-path PVCs at staging: `data` (SQLite DB + search index, 5Gi),
`media` (the documents themselves, 20Gi), `consume` (the ingest
drop folder, 5Gi), `export` (5Gi). `media` stays on a local volume
deliberately: NFS data is never Velero-backed-up, and the document
store is the one thing the backup must cover. Redis data is broker
state only — it is **not** copied; the broker starts empty. After
cutover, bind each copied volume through a repo-managed static local
PV and claim (a `<volume>-local-pv.yaml` beside this README, using
each dynamic claim's provisioned path and node), switch the values
to the `*-local` claims for the live mounts, and keep the original
claims mounted read-only under `/mnt/paperless-rollback-*` — the
Batch A/B post-cutover shape.

Before cutover, measure the LXC's four directories. If `media`
exceeds the authored sizes, grow the PVC sizes in the values first —
the local-path sizes are advisory, but the node's disk is not.

Secrets stay in Vault and outside Argo's ownership, both created by
`playbooks/talos-cluster/paperless-secret.yml`:
`paperless-newt-external` (Pangolin/Newt) and `paperless-external`
(`PAPERLESS_SECRET_KEY`, `PAPERLESS_ADMIN_USER`,
`PAPERLESS_ADMIN_PASSWORD`, `PAPERLESS_URL`).

Backups: Velero Schedule `paperless-ngx-daily` (in the values) with
pod annotation `backup.velero.io/backup-volumes: data-local,media-local,consume-local,export-local`
and a pre-backup hook that writes a consistent SQLite copy
(`db-backup.sqlite3`, via the SQLite online-backup API) into the
data volume first. The network policy is the house default-deny
CiliumNetworkPolicy, in the values as
`rawResources.defaultDenyNetworkPolicy`.

## Prerequisites (once)

1. `apps/argocd/project.yaml` updated (paperless-ngx destination)
   and applied via `playbooks/talos-cluster/argocd-project.yml`.
2. Namespace: `kubectl --context admin@homelab apply -f ansible/kubernetes/apps/paperless-ngx/storage.yaml`
3. Secrets: run `playbooks/talos-cluster/paperless-secret.yml`. Its
   asserts name every Vault key it needs; a failed assert means the
   Vault spelling differs — fix the playbook, not the Vault. Note
   `paperless_url` must resolve from the playbook's vars files; if
   it lives outside `group_vars/all/secrets.yaml`, add that vars
   file to the playbook.

## Staging

Values ship with `replicas: 0`. Commit, push, register the
Application, approve the first Sync — objects and PVCs appear, no
pod starts, the LXC keeps serving:

```sh
kubectl --context admin@homelab apply -f ansible/kubernetes/apps/argocd/applications/paperless-ngx.yaml
```

## Cutover

1. **Check the consume folder's writers first.** If anything outside
   the LXC (a scanner, another host, a sync job) drops files into
   `./consume`, that path changes at cutover — repoint it at the
   pod's consume volume (or pause the writer for the window) before
   continuing. An unwatched external writer is the one real data
   loss risk in this migration.
2. Stop the LXC stack (drops the public route until step 5, and
   checkpoints the SQLite WAL so the file copy below is consistent):

   ```sh
   ssh root@paperless-ngx 'cd ~ && docker compose down'
   ```

3. Copy `data`, `media`, `consume` and `export` into their PVCs
   with datacopy helper pods (busybox image as in the LubeLogger
   README), one per volume, tar-streamed from the LXC's directories
   (the claims are `paperless-ngx-data`, `paperless-ngx-media`,
   `paperless-ngx-consume`, `paperless-ngx-export`; confirm with
   `kubectl -n paperless-ngx get pvc`). Verify file count AND total
   bytes of regular files on both sides for each volume
   (`find <dir> -type f | wc -l` and the `stat -c %s` sum, as in the
   LubeLogger README); directory metadata is excluded. The `media`
   numbers must match exactly — those are the documents. Mismatch →
   debug and re-copy; if it will not verify, restart the LXC stack,
   leave Paperless serving there, and report.
4. Bind the static local PVs (above), remove `replicas: 0` from the
   values, commit, push, approve Sync.
5. Verify: pod `3/3` Ready; the public Paperless URL loads; log in
   and confirm the document count and a known document's thumbnail
   and OCR text; drop a test file in consume and watch it get
   ingested. Argo Synced/Healthy. Create and verify a Velero backup
   with Completed PodVolumeBackups for all four volumes (the script
   in the Navidrome README, with schedule `paperless-ngx-daily`,
   checking each volume).
6. Leave the stopped LXC as rollback target until soak completes.

Rollback: `docker compose up -d` on the LXC (its Newt sidecar
re-registers the public route); bring the cluster pod down via a
`replicas: 0` commit + Sync so the Newt identity is not claimed
twice. Any documents consumed by the cluster pod after cutover exist
only in the cluster volumes — copy `media`, `data` and `export`
back before rolling back, or accept losing them.
