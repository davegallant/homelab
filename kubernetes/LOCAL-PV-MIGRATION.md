# Move a stateful workload between Talos workers

Use this runbook when a Kubernetes workload must move between workers and its
data lives on node-local PVs. The workload is stopped during the copy. The
source PVCs and PVs stay Bound as rollback material until separately approved
cleanup. This is a manual, app-specific operation; do not treat it as a pod
reschedule.

Read [Storage](STORAGE.md), [Argo CD management](apps/argocd/MANAGEMENT.md),
and [Backups](BACKUPS.md) first. Check
[Pod Security](SECURITY.md) and the app's own runbook for identity, route, and
backup requirements.

## Stop conditions

Stop and ask Dave if the source, destination, claim, required data, identity,
backup scope, or safe copy method is uncertain. Do not invent a workaround.
Do not reboot a node, relax Pod Security, change networking, copy Tailscale
identity, prune Argo resources, delete source PVs/PVCs, or roll back without
explicit approval. On any failed gate, keep the evidence and leave completed
steps in place.

## 1. Identify the complete workload state

Record the app, namespace, source and destination workers, downtime approval,
all Deployment/StatefulSet replicas, node selectors or affinity, sidecars,
Services and routes, every PVC, and every state path in the app container.
Include state held by companions such as Caddy or a database. Ask whether
identity-bearing state should be recreated instead of copied.

Check live PVs, not only chart values:

```sh
kubectl config current-context
kubectl get nodes -o wide
kubectl get pods -n "$NS" -o wide
kubectl get pvc -n "$NS" -o wide
kubectl get pv -o json | jq -r --arg ns "$NS" \
  '.items[] | select(.spec.claimRef.namespace == $ns) |
   [.metadata.name,.spec.claimRef.name,.spec.storageClassName,
    (.spec.local.path // .spec.hostPath.path // ""),
    (.spec.nodeAffinity.required.nodeSelectorTerms | tostring)] | @tsv'
```

For each source claim, record its PV type, node affinity, reclaim policy, and
on-disk path. **An annotation cannot convert an existing `hostPath` PV to
`local`.** Do not edit a bound source PV in place. Confirm destination memory,
CPU requests, disk bytes, and free inodes. Check the live Velero Schedule and
its completed backup/PVB history before choosing a destination.

Before stopping the source, take a fresh namespace backup using its current
Schedule settings. Require a Completed backup and nonzero PVB bytes for every
required source volume; inspect and record any warnings. This is the recovery
baseline for the cutover, not proof that the destination copy works.

```sh
kubectl get schedule "$SCHEDULE" -n velero -o yaml
kubectl exec -n velero deployment/velero -- /velero backup create "$BACKUP" \
  --from-schedule "$SCHEDULE" --wait
kubectl get backup "$BACKUP" -n velero -o yaml
kubectl get podvolumebackups.velero.io -n velero -o wide
```

## 2. Prepare new destination claims

Create new claim names; a bound source claim cannot be retargeted. For dynamic
local-path, add the `volumeType: local` annotation to every new PVC. Keep
`WaitForFirstConsumer` behavior and pin the production workload and destination
helper to the destination worker. For static local PVs, follow the app-specific
path and ensure the destination directory exists before binding; a missing
static local path is not created by kubelet.

Review the rendered manifests and exact Argo diff. Publish the reviewed values
to remote `main` because Argo reads the remote repository. Set the production
replica count to zero in the migration configuration and point it at the new
claims and destination worker. Sync the app manually with prune and force
disabled:

```sh
argocd app get "$APP" --refresh
argocd app diff "$APP"
argocd app sync "$APP" --prune=false
```

The CLI may return nonzero and say resources require pruning even when the
Argo operation succeeded. Check `.status.operationState.phase` and the live
resources. Never use prune to clear this state. Verify the old app pod is gone,
the Deployment has zero replicas, and all source claims remain Bound.

## 3. Provision and verify destination PVs

Create two temporary helpers: a source helper pinned to the source node with
read-only source mounts, and a destination helper pinned to the target node
with writable new-claim mounts. Use a digest-pinned image, no service-account
token, a read-only root filesystem, dropped capabilities, and the application
UID/GID where possible. Restricted namespaces may reject a helper that does
not comply; do not relax namespace policy to make it work.

The destination claims may remain Pending until the target helper mounts them.
After they bind, verify each PVC annotation and PV directly before copying:

```sh
kubectl get pvc -n "$NS" -o wide
kubectl get pv "$TARGET_PV" -o yaml
```

Require `spec.local`, the intended target node affinity, and the expected
reclaim policy. Stop if the volume is `hostPath`, bound to another node, or has
the wrong claim. Confirm the destination directories are empty before copying.

## 4. Freeze, inventory, and copy

Keep the source application at zero replicas. Capture a sorted manifest of
relative file path and byte size from each frozen source tree and save the
output outside Git. For regular filenames without newline characters, a
non-root helper can produce it with:

```sh
kubectl exec -n "$NS" "$SOURCE_HELPER" -- sh -c '
  find /source -type f | while IFS= read -r f; do
    printf "%s\t%s\n" "${f#/source/}" "$(stat -c %s "$f")"
  done | LC_ALL=C sort'
```

If Restricted Pod Security prevents reading root-owned source files, use the
documented Talos `copy` command to stream the node directory as a tar.gz
archive. This reads the source without changing its permissions or running a
privileged Pod:

```sh
talosctl -n "$SOURCE_NODE_IP" -e "$SOURCE_NODE_IP" \
  copy "$SOURCE_PV_PATH" - | tar -tvzf -
```

For a file-level manifest from that archive, Python's standard library can
read the archive stream without saving data locally:

```sh
talosctl -n "$SOURCE_NODE_IP" -e "$SOURCE_NODE_IP" \
  copy "$SOURCE_PV_PATH" - |
python3 -c 'import sys,tarfile; t=tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz"); [print(f"{m.name}\t{m.size}") for m in t if m.isfile()]' |
LC_ALL=C sort
```

Copy each approved data tree as a stream. For helper-readable source data:

```sh
kubectl exec -n "$NS" "$SOURCE_HELPER" -- \
  tar -czf - -C /source . |
kubectl exec -i -n "$NS" "$TARGET_HELPER" -- \
  tar -xzf - -C /target
```

For a root-owned tree read via Talos, stream its archive directly to the
destination helper:

```sh
talosctl -n "$SOURCE_NODE_IP" -e "$SOURCE_NODE_IP" \
  copy "$SOURCE_PV_PATH" - |
kubectl exec -i -n "$NS" "$TARGET_HELPER" -- \
  tar -xzf - -C /target
```

Do not print file contents or put secrets in command output. A non-root tar
extraction can change file ownership to the helper UID while preserving file
modes. Verify the resulting owner, group, modes, symlinks, and any app-specific
ACLs before starting the app. Stop if the application requires ownership or
metadata that the documented copy path cannot preserve; do not change source
permissions as an unreviewed workaround.

Generate the same per-file manifest from the destination and require an empty
diff for every copied tree. Do not substitute `du` or compare against a live,
changing source. If a path, size, or file type differs, keep the app frozen and
investigate before proceeding.

For two helper-readable trees mounted at `/source` and `/target`, compare the
relative path/size output directly:

```sh
diff -u \
  <(kubectl exec -n "$NS" "$SOURCE_HELPER" -- sh -c 'find /source -type f | while IFS= read -r f; do printf "%s\t%s\n" "${f#/source/}" "$(stat -c %s "$f")"; done | LC_ALL=C sort') \
  <(kubectl exec -n "$NS" "$TARGET_HELPER" -- sh -c 'find /target -type f | while IFS= read -r f; do printf "%s\t%s\n" "${f#/target/}" "$(stat -c %s "$f")"; done | LC_ALL=C sort')
```

For a source readable only through Talos, compare its archive manifest with
the destination helper manifest using the same `diff -u <(source) <(target)`
form. Ensure both outputs use the same relative path root before relying on an
empty diff.

## 5. Start and verify on the destination

After all manifest and ownership gates pass, update the reviewed production
values to one replica on the destination, still using only the new claims.
Push the reviewed commit, inspect the exact Argo diff, and sync with
`--prune=false` and without force. Verify:

- the app pod is Running and Ready on the destination node;
- every mounted PVC is the intended destination claim and remains Bound to a
  `local` PV on that node;
- the real service route returns the expected response and app-specific
  integrations work;
- no source app pod remains active on the source node.

Take a fresh post-cutover Velero backup only after the destination pod is
Running and mounting the volumes. Copy the current Schedule's namespace,
resource filters, storage location, volume settings, and TTL. Verify the
Backup is Completed and each required volume has a Completed PVB with nonzero
bytes. Inspect warnings with `velero backup describe --details`; a Completed
phase alone is insufficient. Do not count a backup taken at zero replicas as
volume proof.

## 6. Retain source and record the result

Keep original source PVCs and PVs Bound. With prune disabled, Argo may report
OutOfSync because those old claims are no longer desired; this is expected
while rollback material is retained. Do not resolve it with pruning or bulk
deletion. Remove only explicitly named temporary helpers or sidecars after
Dave authorizes that teardown. Source PVC/PV cleanup, rollback, or another
worker move requires its own explicit approval.

Record the source and target claim/PV names, file-manifest diff, ownership and
mode checks, cutover result, Argo operation phase and health, backup/PVB byte
counts and warnings, exact commands, and every unresolved item in a local
receipt outside Git.

## Beszel W1-to-W2 example

The 2026-11-01 pilot used new `local-path` claims named
`beszel-data-w2`, `beszel-caddy-state-w2`, and
`beszel-tailscale-state-w2`, each annotated `volumeType: local` and verified
with W2 node affinity before copy. The app was frozen on W1; the Beszel data
and Caddy trees had exact path/size matches on W2. Caddy's root-owned mode
`0700` tree was read using Talos `copy` and extracted by the non-root target
helper. Tailscale identity was not copied; the new Tailscale claim is empty
and the existing Gateway route was preserved.

After cutover, the app ran Ready on W2 and the existing route returned HTTP
200. Fresh backup `beszel-pilot-post-w2-20261101` completed with nonzero PVBs
for `data` (31,435,036 bytes) and `caddy-state` (6,527 bytes). It had one
warning because Velero skipped the completed pre-migration Caddy proof Pod;
the live W2 app Pod's two PVBs both completed. The original W1 PVCs remain
Bound as rollback material. The final values commit is
[669cf78a](https://github.com/davegallant/homelab/commit/669cf78ad997324b55c6681baf82d8dfd24825b6).
