# Speedtest Tracker on the Talos cluster (Argo CD)

Speedtest Tracker runs from the bjw-s **app-template** chart (5.3.0)
as an Argo CD Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application
definition is `../argocd/applications/speedtest-tracker.yaml`. Syncs
are manual, pruning is off, and deleting the Application preserves
the workload.

The Kubernetes workload is defined by `values.production.yaml`. The former
LXC Compose stack used Speedtest Tracker 1.15.1, PostgreSQL 18.6, and
Apprise 2.0.1; its playbook was retired after cutover.

Exposure is **tailnet-only**, mirroring the RomM pod: a userspace
Tailscale sidecar TCP-forwards 443 to an in-pod Caddy (8443), which
terminates a real certificate (Cloudflare DNS-01) and proxies to
the app on `127.0.0.1:80`. This replaces the LXC's `tailnet_caddy`
role; the tailnet URL (`speedtest-tracker.tail.davegallant.ca`) is
unchanged. The pod registers as a *new* tailnet node named
`speedtest-tracker` — see cutover step 4.

State: the Postgres database (the speedtest history — the point of
the app) moves by logical dump/restore at cutover (the Miniflux
pattern); the app `/config` and the Apprise directories move by file
copy. Volumes at staging are chart-managed local-path PVCs:
`config` (1Gi), `db-data` (2Gi), `apprise` (1Gi, subPaths for
`/config`, `/plugin`, `/attach`), plus the sidecar state volumes.
After cutover, bind the copied volumes through repo-managed static
local PVs and claims (`*-local-pv.yaml` files beside this README,
using each dynamic claim's provisioned path and node), switch the
values to the `*-local` claims for the live mounts, and keep the
original claims mounted read-only under
`/mnt/speedtest-rollback-*` — the Batch A/B post-cutover shape.

The LXC's `./web:/etc/ssl/web` directory was empty and no files in
`speedtest-app` referenced it. Caddy terminates TLS and the app is
reached over plain HTTP on localhost, so the unused `web-certs`
volume is dropped during cutover.

Secrets stay in Vault and outside Argo's ownership:
`speedtest-tracker-external` (`DB_USERNAME`, `DB_PASSWORD`,
`APP_KEY`, `POSTGRES_USER`, `POSTGRES_PASSWORD`) from
`playbooks/talos-cluster/speedtest-secret.yml`;
`speedtest-tracker-caddy-external` (Cloudflare token) from
`playbooks/talos-cluster/gitops-secrets.yml` (this app is in its
`gitops_caddy_secret_namespaces` list); and the bootstrap-only
`speedtest-tracker-tailscale-auth` (`TS_AUTHKEY`), created by the
executor from a one-use Headscale pre-auth key (headscale CLI on
the Pangolin VPS) — no operator step.

Backups: Velero Schedule `speedtest-tracker-daily` (in the values)
with pod annotation `backup.velero.io/backup-volumes: config-local,db-data-local,apprise-local`
and a pre-backup hook that writes a `pg_dump` into the database
volume first. The network policy is the house default-deny
CiliumNetworkPolicy, in the values as
`rawResources.defaultDenyNetworkPolicy` — world egress is
load-bearing (the speedtests themselves).

## Prerequisites (once)

1. `apps/argocd/project.yaml` updated (speedtest-tracker
   destination) and applied via
   `playbooks/talos-cluster/argocd-project.yml`.
2. Namespace: `kubectl --context admin@homelab apply -f kubernetes/apps/speedtest-tracker/storage.yaml`
3. Secrets: run `playbooks/talos-cluster/speedtest-secret.yml`
   (asserts name its Vault keys: `speedtest_tracker_db_username`,
   `speedtest_tracker_db_password`, `speedtest_tracker_app_key`)
   and `playbooks/talos-cluster/gitops-secrets.yml` for the Caddy
   credential.

## Staging

Values ship with `replicas: 0`. Commit, push, register the
Application, approve the first Sync — objects and PVCs appear, no
pod starts, the LXC keeps serving:

```sh
kubectl --context admin@homelab apply -f kubernetes/apps/argocd/applications/speedtest-tracker.yaml
```

The executor creates the bootstrap Tailscale auth Secret from a
one-use Headscale pre-auth key (headscale CLI on the Pangolin VPS
over SSH; no operator gate). Once the pod has registered, the
LXC's stale tailnet node is deleted so the hostname is unique on
the tailnet (cutover step 4).

## Cutover

1. With the LXC stack still running, capture the source count and
   take the dump (user/password per the compose):

   ```sh
   ssh root@speedtest-tracker 'docker exec speedtest-db psql -U <db-user> -d speedtest_tracker -Atc "select count(*) from results;"'
   ssh root@speedtest-tracker 'docker exec speedtest-db pg_dump -U <db-user> speedtest_tracker' > /tmp/speedtest.sql
   ```

2. Stop the LXC stack:

   ```sh
   ssh root@speedtest-tracker 'cd ~ && docker compose down'
   ```

3. Restore the database into the cluster (one-shot Postgres pod
   mounting the `speedtest-tracker-db-data` claim, as in the Umami
   README) and verify the step-1 count matches. Copy `./speedtest-app`
   into the `config` claim and the Apprise `./apprise-config`,
   `./plugin`, `./attach` directories into the `apprise` claim's
   subPaths with datacopy helper pods. The empty, unused `./web`
   directory is deliberately not copied; Caddy terminates TLS.
   Verify file counts and bytes for the file copies (LubeLogger
   README method).
   Anything unverifiable → restart the LXC stack, leave Speedtest
   Tracker serving there, and report.
4. Headscale (executor, no operator gate): the pod's Tailscale
   sidecar registers as `speedtest-tracker` with the one-use
   pre-auth key. Verify the new node is online, then delete the
   LXC's stale `speedtest-tracker` node so the name and its DNS
   settle on the pod. List nodes before and after; touch only
   nodes named `speedtest-tracker`; no ACL/policy changes.
5. Bind the static local PVs (above), remove `replicas: 0` from the
   values, commit, push, approve Sync.
6. Verify: pod `5/5` Ready; the tailnet URL loads over HTTPS with a
   valid certificate; history shows the pre-cutover results; trigger
   a manual speedtest from the UI and confirm a fresh result lands
   (this proves the pod's world egress and the Ookla path — results
   now measure from the pod's node, which is expected). Argo
   Synced/Healthy. Create and verify a Velero backup with Completed
   PodVolumeBackups for the annotated volumes (the script in the
   Navidrome README, schedule `speedtest-tracker-daily`).
7. Leave the stopped LXC as rollback target until soak completes.

### Worker placement before retry

Before creating or provisioning any Speedtest claims, cordon
`k8s-w-2` so local-path claims are first-consumer provisioned on
`k8s-w-1`. Local-path volumes are tied to their first worker; the
first attempt provisioned on `k8s-w-2`, where the pod could not
schedule. Keep `k8s-w-2` cordoned through claim creation, data
restore/copy, static PV binding, and the scheduling gate. If the pod
still cannot schedule on `k8s-w-1`, park Speedtest at zero replicas,
restart the LXC, and uncordon `k8s-w-2` after confirming the LXC serves.

Rollback: `docker compose up -d` on the LXC and re-register its
tailnet node; bring the cluster pod down via a `replicas: 0` commit
+ Sync so the `speedtest-tracker` tailnet name is not claimed
twice. Speedtests recorded by the cluster pod after cutover live
only in its database — restore them back first, or accept the gap.

## Batch C execution status (2026-10-23)

Speedtest Tracker remains on the LXC. The cutover database copy
verified at 14,391 results, and the config copy matched at 46 files
and 4,417,588 bytes. Activation was parked because the local volumes
are pinned to `k8s-w-2`, where the pod could not fit its memory
request. The LXC stack was restarted; it now has 14,392 results after
a scheduled run. Headscale still has only the LXC's
`speedtest-tracker` node; the unused one-time auth key was revoked.
No Kubernetes backup or test run was recorded.

## Retry status (2026-10-23)

The stranded `k8s-w-2` attempt was removed after confirming the LXC stack was
running. `k8s-w-2` was cordoned before the retry's claims were provisioned or
any data moved. The database, config, and Apprise PVCs mounted by the
migration helper provisioned on `k8s-w-1`; the caddy and Tailscale state PVCs
remain pending because the workload pod never scheduled. The database restore
matched at 14,392 results, and app configuration matched at 46 files and
4,446,440 bytes. The Apprise `config`, `plugin`, and `attach` directories each
matched at 0 files and 0 bytes. The unused `./web` directory was not copied.

The static database, config, and Apprise PVs are bound to those `k8s-w-1`
paths. The K8s pod could not pass the scheduling gate: `k8s-w-1` had about
155m free CPU request capacity, while the pod requests 275m. The pod never
started, so no K8s URL check, manual speedtest, or Velero backup with completed
PodVolumeBackups was recorded. The deployment is parked at zero replicas,
`k8s-w-2` is uncordoned, and the LXC was restarted and verified serving at
14,392 results; its tailnet URL returned HTTP 302. The unused one-time
Headscale key and Kubernetes bootstrap Secret were deleted. The existing LXC
Headscale node remains online; no ACL or policy changes were made.

## Activation gate retry (2026-10-23)

The final dump included the LXC's additional scheduled result: both
the stopped LXC source and the restored cluster database had 14,393
results. The pod scheduled on `k8s-w-1`, and its app, database,
Apprise, and Caddy containers became Ready. The Tailscale container
crash-looped with `error initializing kube client` because
`TS_KUBE_SECRET` was set to the literal string `false` while the pod
has `automountServiceAccountToken: false`. The pod never registered
a new Headscale node. The activation gate failed, so the deployment
was returned to zero replicas and the LXC Compose stack was restarted;
the LXC app returned HTTP 200 and the tailnet URL returned HTTP 302.

The bootstrap Secret and unused one-use preauth key were deleted. The
original LXC Headscale node remains online, no other Headscale nodes or
ACLs were changed, and the CiliumNetworkPolicy remains Valid. No manual
speedtest or Velero backup was recorded. The copied database, config,
and Apprise data and static `k8s-w-1` PV bindings remain available for
the next attempt.


## Retry 3 status (2026-10-23)

The `TS_KUBE_SECRET: ""` fix synced. The pod scheduled on `k8s-w-1`,
but the Tailscale sidecar rejected the one-use Headscale key with
`hash length mismatch, expected 64 chars, got 65`: the Secret file included
a trailing newline. The gate failed before a new Headscale node registered;
the old LXC node was not changed. The deployment is parked at zero replicas,
the failed bootstrap Secret was deleted, and Headscale key ID 59 was expired.
The LXC Compose stack remains running (`speedtest-tracker`, `speedtest-db`,
`apprise`). No tailnet URL, manual test, or Velero backup gate was passed.
Data and the static `k8s-w-1` PV bindings were not changed.

## Retry 4 completion (2026-10-23)

The bootstrap key was created with the repository-documented pipeline:
extract the JSON `key` using `jq -sr` and strip `\r\n` before piping it
into `kubectl --from-file`. The resulting Secret value was 88 bytes; the
sidecar accepted it, and one-use key ID 60 registered the pod as Headscale
node ID 61. The prior malformed key ID 59 was expired.

The pod is `5/5` Ready on `k8s-w-1` with zero restarts. The old LXC Headscale
node ID 1 was deleted after both nodes were online; the pod node was renamed
from `speedtest-tracker-1` to `speedtest-tracker` so the existing tailnet
hostname and DNS resolve to `100.100.0.58`. No other nodes or ACLs changed.
The HTTPS dashboard answered at the established tailnet URL. A manual UI
speedtest completed as result 14425 (346.05 Mbps down, 521.78 Mbps up,
13 ms ping). The cluster and LXC each had 14,394 results immediately before
the LXC stack was stopped. The config copy remains verified at 46 files and
4,446,440 bytes; the three Apprise directories were empty on both sides.

Argo CD is Synced/Healthy and the CiliumNetworkPolicy is Valid. Velero backup
`speedtest-tracker-daily-20261023171535` completed, with Completed
PodVolumeBackups for `apprise-local`, `config-local`, and `db-data-local`.
The LXC Compose stack was stopped on Proxmox CT 103 (`pve-g3-2`); its data
remains on disk. Its Ansible playbook and import from `playbooks/main.yml`
were removed so daily CI no longer starts the retired stack.
