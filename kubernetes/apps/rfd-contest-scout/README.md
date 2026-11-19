# RFD Contest Scout

RFD Contest Scout reads the RedFlagDeals Contests forum RSS feed once a day at
08:00 America/Toronto and sends a Gotify digest of up to 12 Ontario-eligible
contests that are new or within three days of expiry. Expired contests are
dropped. Dave enters contests himself; the scout does not enter or open
threads.

The CronWorkflow runs in the `argo-workflows` namespace. Its script is in the
`rfd-contest-scout-script` ConfigMap, rendered from `chart/files/scout.py`, and
it runs on the pinned `python:3.14.5-alpine3.22` digest already used by
`rfd-rising-deals`. There is no separate image to build.

The schedule starts suspended (`suspend: true` in `values.production.yaml`).

## Behaviour

- Source: the RSS feed at `forums.redflagdeals.com/feed/forum/34`. The RFD
  forum HTML sits behind a proof-of-work browser challenge, so there is no HTML
  fallback. The feed has no reply count.
- Ranking: expiry soonest first (unknown expiry last), then `[Once]` before
  other frequencies, then newest. Reply count is not used.
- Eligibility: titles that restrict a contest to another province are dropped,
  for example `[AB and SK Only]` or `(BC only)`. `(No QC)` notes do not exclude
  Ontario; they are shown in the digest.
- Dedupe: `/state/contest-scout.db` (SQLite, WAL) records each thread. A thread
  is announced once, and once more as a reminder within three days of expiry.
  State is written only after Gotify returns 2xx, so a failed send is retried on
  the next run.
- Delivery: one Gotify message per run, using the `gotifys://` APPRISE_URL form
  that rfd-notify uses. The script calls the Gotify REST API directly and only
  accepts the `gotify.davegallant.ca` host.

A run with no new or ending contests exits 0 and sends nothing. A failed run
exits non-zero, and Argo's global exit handler sends the Argo failure
notification.

## Storage and backup

The `rfd-contest-scout-state` PVC uses `local-path` with `volumeType: local`,
which binds to one worker. `local-path` uses `WaitForFirstConsumer`, so the claim
stays Pending until a pod mounts it. The `rfd-contest-scout-state-keeper`
Deployment mounts the claim so Velero can see it.

The `argo-workflows-daily` Velero schedule (02:55 UTC) covers the whole
`argo-workflows` namespace, so this claim is included with no change to the
schedule. Velero excludes Secrets. The scout's backup window (08:00 Toronto)
does not overlap it.

## Secrets

The runtime Secret `rfd-contest-scout-runtime-external` in `argo-workflows` holds
`APPRISE_URL`, built from the existing Vault value `rfd_notify_gotify_token`. It
uses the same Gotify application as RFD Notify, so Contest Scout digests arrive
in that app and no new Vault value is needed. Argo failure notifications still
use `argo_workflows_gotify_token`.

Provision it after the namespace exists:

```sh
just run talos-cluster/gitops-secrets --tags rfd-contest-scout-secret -e talos_kube_context=homelab
```

Only the workflow pod can reach DNS, `forums.redflagdeals.com`, and
`gotify.davegallant.ca` over HTTPS (`rfd-contest-scout-egress`).

## Runbook

1. Confirm `rfd_notify_gotify_token` is in Vault (see Secrets).
2. Render and check locally, then server dry-run. Do not push or sync until
   Dave approves.
3. After approval, push to `main`. Sync the parent `argocd` Application first:
   it renders `kubernetes/apps/argocd/applications/`, which creates the
   `rfd-contest-scout` Application object. Then sync `rfd-contest-scout`. Never
   sync the child first. Sync is manual; this app has no automated sync.
4. Verify the claim is Bound with the annotation, and the PV is `local`:

   ```sh
   kubectl --context homelab -n argo-workflows get pvc rfd-contest-scout-state \
     -o jsonpath='{.status.phase}{" "}{.metadata.annotations.volumeType}{"\n"}'
   PV=$(kubectl --context homelab -n argo-workflows get pvc rfd-contest-scout-state -o jsonpath='{.spec.volumeName}')
   kubectl --context homelab get pv "$PV" -o jsonpath='{.spec.local.path}{" "}{.spec.hostPath.path}{" "}{.spec.nodeAffinity.required.nodeSelectorTerms[0].matchExpressions[0].values[0]}{"\n"}'
   ```

   `spec.local.path` must be set and `spec.hostPath` must be empty.
5. Confirm the CronWorkflow is suspended and the state-keeper is Available.
6. Run once manually, and only after Dave's go:

   ```sh
   argo submit --from cronwf/rfd-contest-scout -n argo-workflows
   argo logs <workflow-name> -n argo-workflows
   ```

   A Succeeded workflow does not prove delivery. Check that the Gotify
   application shared with RFD Notify received the Contest Scout message. Check the logs for
   `delivered N contests via Gotify`.
7. Verify a Velero backup with the state-keeper mounted, and require a
   Completed backup and a Completed PodVolumeBackup for
   `rfd-contest-scout-state` with nonzero bytes:

   ```sh
   BACKUP=rfd-contest-scout-gate-$(date -u +%Y%m%d%H%M%S)
   kubectl --context homelab -n velero exec deployment/velero -- \
     /velero backup create "$BACKUP" \
     --include-namespaces argo-workflows \
     --exclude-resources secrets \
     --include-cluster-resources=false \
     --default-volumes-to-fs-backup \
     --snapshot-volumes=false \
     --ttl 336h --wait
   kubectl --context homelab -n velero get backup "$BACKUP"
   kubectl --context homelab -n velero get podvolumebackups \
     -l velero.io/backup-name="$BACKUP" \
     -o custom-columns=NAME:.metadata.name,PHASE:.status.phase,BYTES:.status.progress.bytesDone
   ```

8. Only after steps 4 to 7 pass, set `suspend: false` in
   `values.production.yaml` as a separate reviewed change, and sync again.

## Operations

Inspect runs in the Argo Workflows UI at
https://argo-workflows.tail.davegallant.ca. Avoid manual submissions between
02:40 and 03:10 UTC while Velero backs up the namespace.

Rollback: suspend the CronWorkflow. Keep the PVC; it is backup material. Do not
delete the claim without Dave's go.

## Open items

- NanoClaw's Contest Scout is still live on the NanoClaw host and is not part
  of this app. Until it is retired, Dave may receive two digests.
- The NanoClaw title rules keep some titles such as `(BC best)`. This port keeps
  that behaviour; it has not been reviewed.
