# Umami on the Talos cluster (Argo CD)

Umami runs from the bjw-s **app-template** chart (5.3.0) as an Argo CD
Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application definition
is `../argocd/applications/umami.yaml`. Syncs are manual, pruning is
off, and deleting the Application preserves the workload.

Workload source of truth: `playbooks/umami/docker-compose.yml`
(app `ghcr.io/umami-software/umami:3.4.0`, port 3000; database
`docker.io/postgres:18.6` as a second container in the same pod).

Exposure is **public via Pangolin** — the compose pairs the app with a
Newt sidecar, reproduced in-pod with the *same* Newt identity, so the
existing Pangolin route and public URL carry over unchanged. Do not
rewrite this app as tailnet-only; the compose is authoritative.
Expect a brief public outage at cutover while the Newt identity moves
from the LXC to the pod.

The only state is the Postgres database. The app container is
stateless; analytics data moves by logical dump/restore at cutover
(the Miniflux pattern), never by copying the Postgres data directory.
In the values, `db-data` is a chart-managed local-path PVC (2Gi)
mounted by the `db` container at `/var/lib/postgresql`. After
cutover, bind the copied data through a repo-managed static local PV
and claim (a `db-data-local-pv.yaml` beside this README, using the
dynamic claim's provisioned path and node), switch the values to the
`db-data-local` claim for the live mount, and keep the original claim
mounted read-only at `/mnt/umami-rollback-db-data` — the Batch A/B
post-cutover shape.

Secrets stay in Vault and outside Argo's ownership, both created by
`playbooks/talos-cluster/umami-secret.yml`: `umami-newt-external`
(Pangolin/Newt) and `umami-external` (`DATABASE_URL` — assembled by
the playbook with host `127.0.0.1`, since the database is the
neighbouring container — plus `APP_SECRET`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`).

Backups: Velero Schedule `umami-daily` (in the values) with pod
annotation `backup.velero.io/backup-volumes: db-data-local` and a pre-backup
hook that writes a `pg_dump` into the volume, so the filesystem
backup carries a restorable copy. The network policy is the house
default-deny CiliumNetworkPolicy, in the values as
`rawResources.defaultDenyNetworkPolicy`.

## Prerequisites (once)

1. `apps/argocd/project.yaml` updated (umami destination) and applied
   via `playbooks/talos-cluster/argocd-project.yml` — the playbook
   kubectl-applies the repo file and asserts the Cilium policy
   permission is live.
2. Namespace: `kubectl --context admin@homelab apply -f ansible/kubernetes/apps/umami/storage.yaml`
3. Secrets: run `playbooks/talos-cluster/umami-secret.yml`. Its
   asserts name every Vault key it needs (`umami_db_user`,
   `umami_db_password`, `umami_app_secret`, `umami_newt_id`,
   `umami_newt_secret`, `pangolin_endpoint`); a failed assert means
   the Vault spelling differs — fix the playbook, not the Vault.

## Staging

Values ship with `replicas: 0`. Commit, push, register the
Application, approve the first Sync — objects and the PVC appear, no
pod starts, the LXC keeps serving:

```sh
kubectl --context admin@homelab apply -f ansible/kubernetes/apps/argocd/applications/umami.yaml
```

## Cutover

1. With the LXC stack still running, capture the source counts and
   take the dump (user/password per the compose's `POSTGRES_USER` /
   `POSTGRES_PASSWORD`):

   ```sh
   ssh root@umami 'docker exec umami-db psql -U <db-user> -d umami -Atc "select count(*) from website; select count(*) from website_event;"'
   ssh root@umami 'docker exec umami-db pg_dump -U <db-user> umami' > /tmp/umami.sql
   ```

2. Stop the LXC stack (this also drops the public route until step 5):

   ```sh
   ssh root@umami 'cd ~ && docker compose down'
   ```

3. The gate for continuing: a complete dump file from step 1 and
   its counts recorded. A truncated or empty dump means stop here,
   restart the LXC stack, and report.

4. Restore into the cluster: start a one-shot Postgres pod mounting
   the `umami` claim (the chart names a lone PVC after the release,
   so the claim is `umami`, not `umami-db-data` — it would take the
   key-based name if a second chart PVC were ever added; bind by
   provisioned path at cutover, not by name), let it initialise an
   empty database, load the dump with `psql`, then delete the pod.
   Verify the step-1 counts match in the cluster database before
   continuing. Mismatch → debug and re-restore; if it will not
   verify, restart the LXC stack, leave Umami serving there, and
   report.
5. Bind the static local PV (above), remove `replicas: 0` from the
   values, commit, push, approve Sync.
6. Verify: pod `3/3` Ready; the public Umami URL loads and shows the
   existing websites; Argo Synced/Healthy. Create and verify a Velero
   backup with its `db-data-local` PodVolumeBackup (the script in the
   Navidrome README, with schedule `umami-daily` and volume
   `db-data-local`).
7. Leave the stopped LXC as rollback target until soak completes.

Rollback: `docker compose up -d` on the LXC (its Newt sidecar
re-registers the public route); bring the cluster pod down via a
`replicas: 0` commit + Sync so the Newt identity is not claimed
twice.
