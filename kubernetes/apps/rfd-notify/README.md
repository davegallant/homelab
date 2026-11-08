# RFD Notify

RFD Notify scans two pages of the RedFlagDeals Hot Deals API every five
minutes, except from 02:45 through 03:05 UTC for the backup window, and sends
matches from the maintained expression list to Gotify. It
runs the pinned upstream `ghcr.io/davegallant/rfd-notify:2` image in the
`argo-workflows` namespace. The workflow is initially suspended for a staged
state transfer and scheduler cutover.

The expression list is kept in the live `rfd-notify-config` ConfigMap in
`argo-workflows`; it is intentionally not stored in Git. Edit it with
`kubectl --context homelab -n argo-workflows edit configmap rfd-notify-config`.
The ConfigMap is included in the `argo-workflows-daily` Velero backup. New
workflow pods read the edited ConfigMap on startup. Match history remains the
upstream Python `shelve` database on the `rfd-notify-state` PVC. The PVC
uses `local-path` with `volumeType: local`; it binds to one worker and is
mounted by a restricted state-keeper Deployment so the existing
`argo-workflows-daily` Velero schedule at 02:55 UTC can consistently see it.
Velero backs up the volume data and excludes Secrets. Recreate the
`rfd-notify-runtime-external` Secret from Vault before restoring or running the
workflow. Provision it after the namespace exists with
`just run talos-cluster/gitops-secrets --tags rfd-notify-secrets` and the
intended `talos_kube_context` extra var.

The runtime Secret's `APPRISE_URL` is built from the
`rfd_notify_gotify_token` Vault value, also used by RFD rising-deals. Argo
Workflows failure notifications use a separate `argo_workflows_gotify_token`
Vault value. Gaswatch continues to use its separate token. Only the workflow
pod can egress to DNS,
`forums.redflagdeals.com`, and `gotify.davegallant.ca` over HTTPS.
Avoid manual workflow submissions from 02:40 through 03:10 UTC while Velero
backs up the namespace and state files.

## Migration and cutover

The source state is the `previous_matches` file from the latest
`rfd-notify-cron` commit. Disable all Forgejo triggers first and wait for any
active Forgejo run to finish. Then fetch and record the latest state commit:

```sh
REPO=/Users/dave/src/forgejo.davegallant.ca/dave/rfd-notify-cron
git -C "$REPO" fetch origin main
umask 077
SOURCE=$(mktemp /tmp/rfd-notify-state.XXXXXX)
git -C "$REPO" show origin/main:previous_matches > "$SOURCE"
git -C "$REPO" rev-parse origin/main
SOURCE_SHA=$(shasum -a 256 "$SOURCE" | awk '{print $1}')
```

Use this `SOURCE` file for the PVC copy. At migration review, source commit
`d85ae2c` contained 575 entries; the fetched state may have since advanced.
Sync the Argo Application with the CronWorkflow still suspended, provision the
runtime Secret, and inspect the claim before copying. The pinned image was
verified to open, update, and preserve the GNU dbm file as UID 10001; the
reviewed snapshot contained 575 entries.

Before copying data, confirm the claim is Bound with the `volumeType: local`
annotation. Inspect the bound PV and verify `spec.local.path` is set,
`spec.hostPath` is absent, and its node affinity is intentional:

```sh
kubectl --context homelab -n argo-workflows get pvc rfd-notify-state \
  -o jsonpath='{.status.phase}{" "}{.metadata.annotations.volumeType}{"\n"}'
PV=$(kubectl --context homelab -n argo-workflows get pvc rfd-notify-state -o jsonpath='{.spec.volumeName}')
kubectl --context homelab get pv "$PV" -o jsonpath='{.spec.local.path}{" "}{.spec.hostPath.path}{" "}{.spec.nodeAffinity.required.nodeSelectorTerms[0].matchExpressions[0].values[0]}{"\n"}'
```

To seed the volume, set `SOURCE` to the checked-out `previous_matches` file
and record its SHA256, then create a temporary restricted pod using the same
pinned image:

```sh
kubectl --context homelab -n argo-workflows apply -f - <<'YAML'
apiVersion: v1
kind: Pod
metadata:
  name: rfd-notify-state-seed
  namespace: argo-workflows
spec:
  restartPolicy: Never
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: seed
      image: ghcr.io/davegallant/rfd-notify:2@sha256:2c646a4305b665966674019887612a7deea46c1082544d0b24031cbdc6db7569
      command: [/venv/bin/python, -B, -c, "import time; time.sleep(1800)"]
      resources:
        requests: {cpu: 10m, memory: 32Mi}
        limits: {cpu: 100m, memory: 64Mi}
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: [ALL]
      volumeMounts:
        - name: state
          mountPath: /state
  volumes:
    - name: state
      persistentVolumeClaim:
        claimName: rfd-notify-state
YAML
kubectl --context homelab -n argo-workflows wait --for=condition=Ready pod/rfd-notify-state-seed --timeout=120s
kubectl --context homelab -n argo-workflows exec -i rfd-notify-state-seed -- \
  /venv/bin/python -c 'import sys; open("/state/previous_matches", "wb").write(sys.stdin.buffer.read())' < "$SOURCE"
kubectl --context homelab -n argo-workflows exec rfd-notify-state-seed -- \
  /venv/bin/python -c 'import shelve; s=shelve.open("/state/previous_matches", flag="r"); print("entries:", len(s)); s.close()'
PVC_SHA=$(kubectl --context homelab -n argo-workflows exec rfd-notify-state-seed -- \
  /venv/bin/python -c 'import hashlib; print(hashlib.sha256(open("/state/previous_matches", "rb").read()).hexdigest())')
test "$SOURCE_SHA" = "$PVC_SHA"
printf 'Source and PVC state hashes match.\n'
kubectl --context homelab -n argo-workflows wait \
  --for=condition=Available deployment/rfd-notify-state-keeper --timeout=120s
kubectl --context homelab -n argo-workflows delete pod rfd-notify-state-seed
rm -f "$SOURCE"
```

The copy command compares source and PVC SHA256 values before deleting the
seed pod. Confirm the state-keeper is Ready and the workflow remains suspended.
Submit one manual workflow and verify it completes
and persists state. Then create a namespace backup while the state-keeper is
mounted:

```sh
BACKUP=rfd-notify-state-migration-$(date -u +%Y%m%d%H%M%S)
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

Require a Completed backup and a Completed `PodVolumeBackup` with nonzero
bytes for `rfd-notify-state`. Only after those gates pass should the schedule
be enabled and synced. Preserve the Forgejo repository as rollback material
until the first scheduled Argo run and daily Velero backup are verified; never
run both schedules at once.

## Operations and recovery

Submit a one-off run with `argo submit --from cronwf/rfd-notify -n
argo-workflows`; inspect it with `argo logs <workflow-name> -n
argo-workflows`. Argo's global exit handler sends a Gotify notification for
Failed or Error workflows. Check the [Argo Workflows UI](https://argo-workflows.tail.davegallant.ca)
for schedule status and history.

The upstream notifier ignores Apprise's delivery result. A Gotify delivery
failure may therefore leave the Workflow successful and will not trigger the
global Argo failure notification.

For restore, provision the Secret from Vault, restore the `argo-workflows`
Velero backup's `rfd-notify-config` ConfigMap and `rfd-notify-state` volume to
a new local-path PVC with
`volumeType: local`, verify its worker binding, and then resume the CronWorkflow.
If rolling back, suspend the Argo CronWorkflow, copy the latest PVC state back
to Forgejo's `previous_matches`, verify the file opens, and only then restore
the Forgejo workflow and schedule.
