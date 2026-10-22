# Seerr on the Talos cluster (Argo CD)

Seerr runs from the bjw-s **app-template** chart (5.3.0, digest-pinned
images) as an Argo CD Application — no local chart. Desired state is
`values.production.yaml` in this directory; the Application definition
is `../argocd/applications/seerr.yaml`. Syncs are manual, pruning is
off, and deleting the Application preserves the workload.

Workload source of truth: `playbooks/seerr/docker-compose.yml`
(image `ghcr.io/seerr-team/seerr:v3.5.1`, port 5055, `./config:/app/config`
relative to `/root` on the LXC).

Exposure is **tailnet-only** (Dave's standing decision): the pod mirrors
the Kiwix shape — a userspace Tailscale sidecar TCP-forwards 443 to an
in-pod Caddy on 8443, which terminates a real certificate (Cloudflare
DNS-01) for `seerr.tail.davegallant.ca` and proxies to Seerr on
127.0.0.1:5055. No Pangolin/Newt tunnel, no public ingress.

Secrets stay in Vault and outside Argo's ownership:

- `seerr-caddy-external` (key `cloudflare_api_token`) — materialized by
  `playbooks/talos-cluster/gitops-secrets.yml` from
  `cloudflare_dns_api_token`.
- `seerr-tailscale-auth` (key `TS_AUTHKEY`) — a one-use Headscale
  preauth key created by hand at first registration (below), deleted
  once the identity persists in the `seerr-tailscale-state` PVC.

Backups: the values carry a Velero Schedule (`seerr-daily`, into the
velero namespace) in opt-in mode; the pod annotates
`backup.velero.io/backup-volumes: config`, so only the app config
volume is filesystem-backed-up. The tailscale identity volume is never
captured — restoring it would clone a live tailnet identity.

## Prerequisites (once)

1. `apps/argocd/project.yaml` includes the bjw-s chart repo, the
   `seerr` destination, and the PersistentVolumeClaim whitelist entry;
   re-apply it: `kubectl --context admin@homelab apply -f ansible/kubernetes/apps/argocd/project.yaml`
2. Namespace: `kubectl --context admin@homelab apply -f ansible/kubernetes/apps/seerr/storage.yaml`
3. Caddy secret: run `playbooks/talos-cluster/gitops-secrets.yml`.

## Staging

`values.production.yaml` ships with `replicas: 0`. Commit and push,
register the Application, and approve the first Sync:

```sh
kubectl --context admin@homelab apply -f ansible/kubernetes/apps/argocd/applications/seerr.yaml
```

Argo creates the ConfigMaps, PVCs (pending until first mount —
local-path is WaitForFirstConsumer), Service, and the Velero Schedule.
No pod starts; the LXC keeps serving.

## Cutover

1. Stop the LXC stack (outage starts; Seerr is a personal service):

   ```sh
   ssh root@seerr 'cd ~ && docker compose down'
   ```

2. Copy the config into the PVC with a throwaway pod:

   ```sh
   kubectl --context admin@homelab -n seerr apply -f - <<'EOF'
   apiVersion: v1
   kind: Pod
   metadata:
     name: datacopy
     namespace: seerr
   spec:
     restartPolicy: Never
     containers:
       - name: datacopy
         image: docker.io/library/busybox:1.37.0@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e
         command: ["sleep", "3600"]
         volumeMounts:
           - name: config
             mountPath: /data
     volumes:
       - name: config
         persistentVolumeClaim:
           claimName: seerr-config
   EOF
   kubectl --context admin@homelab -n seerr wait --for=condition=Ready pod/datacopy --timeout=120s
   ssh root@seerr 'tar -C /root/config -cf - .' | kubectl --context admin@homelab -n seerr exec -i datacopy -- tar -C /data -xf -
   kubectl --context admin@homelab -n seerr exec datacopy -- chown -R 1000:1000 /data
   kubectl --context admin@homelab -n seerr exec datacopy -- sh -c 'find /data -type f | wc -l; du -sb /data'
   ssh root@seerr 'find /root/config -type f | wc -l; du -sb /root/config'
   kubectl --context admin@homelab -n seerr delete pod datacopy
   ```

   File count and byte total must match the LXC side before continuing.

3. Retire the LXC's tailnet node so the sidecar takes the clean name:
   on the Headscale host, `headscale nodes list`, then
   `headscale nodes delete --identifier <old-seerr-id>`.

4. Create the one-use registration key and its Secret:

   ```sh
   # on the Headscale host:
   headscale preauthkeys create --user <user> --reusable=false --expiration 1h
   # locally, with the printed key:
   kubectl --context admin@homelab -n seerr create secret generic seerr-tailscale-auth --from-literal=TS_AUTHKEY=<key>
   ```

5. Remove the `replicas: 0` staging line from `values.production.yaml`,
   commit, push, and approve the Sync in Argo CD.

6. Verify:

   - Pod `3/3` Ready; app logs clean.
   - `https://seerr.tail.davegallant.ca` loads with the existing
     requests/settings present (proof the copied config is live).
   - Argo CD shows the Application Synced / Healthy.
   - Trigger one backup (`playbooks/talos-cluster/backup-now.yml`
     pattern) and confirm it completes with the config volume.
   - Delete the spent key Secret:
     `kubectl --context admin@homelab -n seerr delete secret seerr-tailscale-auth`

7. Leave the stopped LXC in place as the rollback target until the
   migration has soaked; retiring it is a separate, explicit step.

## Rollback

Before step 5 nothing has changed for users: `docker compose up -d` on
the LXC restores service (if step 3 already deleted its node, re-run
`tailscale up` on the LXC to re-register). After a successful step 6,
rollback is the same LXC restart plus re-pointing nothing — the
tailnet name follows whichever node registers as `seerr`, so bring the
cluster pod down first (`replicas: 0` commit + Sync) to free the name.
