# k8s-readonly - tailnet-only read-only Kubernetes API proxy

For Tux's Velero/PV audit, so Tux does not need an admin kubeconfig
and does not need kubectl on its VM. Tux reaches the proxy over the
tailnet and queries the API over HTTPS; the proxy pod's ServiceAccount
does the actual API auth, read-only.

## Chain

Tux (tailnet, tunnel proxy, approval on first connect to the new
node) -> Tailscale sidecar TCPForward 443 -> Caddy 8443 (TLS,
Cloudflare DNS-01, k8s-readonly.tail.davegallant.ca) -> kubectl proxy
127.0.0.1:8001 -> https://kubernetes.default.svc with the pod's
ServiceAccount token.

## Security boundary - read this before applying rbac.yaml

1. RBAC (`rbac.yaml`, hand-applied, NOT Argo-managed): get/list/watch
   only, on PVs, PVCs, namespaces, pods, services, nodes, events,
   workloads (apps/batch), and Velero backups/schedules/PVBs/restores.
   Deliberately EXCLUDED: secrets, serviceaccounts, pods/exec,
   pods/log, pods/attach, pods/proxy, nodes/proxy, and every write verb.
2. kubectl proxy default filter: NO --disable-filter, so the proxy
   itself rejects writes before they reach the API server.
3. Tailnet-only: no public URL, no Pangolin resource. Any tailnet
   member device can read cluster state via this proxy, by design
   (same as Homepage/Prowlarr tailnet-only access).
4. No Headscale ACL change: the sidecar joins UNTAGGED with a user
   auth key (member-owned), so the existing autogroup:member -> *:*
   rule covers muse -> k8s-readonly:443. Tagging the sidecar WOULD
   require an ACL update (explicit member -> tag:*:443 rule + a
   tagOwners entry, which is currently blocked - all tagOwners are
   [] and Headscale v0.29.3 rejects plain usernames and
   autogroup:member as owners). Do NOT tag this node.

## Why RBAC + namespace are hand-applied

The homelab AppProject has an empty clusterResourceWhitelist, so
Argo CD cannot create Namespaces, ClusterRoles, or
ClusterRoleBindings for a homelab-project app. The platform project
whitelists those kinds but does not include the bjw-s chart source,
so splitting is cleaner than expanding either project:
namespace.yaml + rbac.yaml by hand (reviewed, kubectl apply),
workload only via Argo CD (homelab project, bjw-s 5.3.0).
The homelab project destination for namespace k8s-readonly was
added in project.yaml for the workload sync.

## Storage - deliberately nothing to back up

tailscale-state and caddy-state are disposable local-path PVCs
(like Prowlarr's sidecars), NOT annotated for Velero, NOT backed
up, recreatable on re-auth / cert re-issue. There is no main data
volume, no new PV that needs a backup, no reboot, no storage
change. See [../../STORAGE.md](../../STORAGE.md) - this app is
the exception that proves the rule: no critical data, so no
Velero gate applies to its own volumes.

## Secrets (outside Git, outside Argo ownership)

- k8s-readonly-tailscale-auth: TS_AUTHKEY, one-use, UNTAGGED user
  auth key, bootstrap only, then deleted (Prowlarr pattern).
- k8s-readonly-caddy-external: cloudflare_api_token, for Caddy DNS-01.
Both via gitops-secrets.yml / Vault flow. Never print, copy, or
paste either value.

## Verification gates (Codex run, see prompt)

- kubectl image digest pinned and verified BEFORE sync (values file
  carries a placeholder tag until then - do NOT sync unpinned).
- bjw-s ServiceAccount field verified by helm-template render
  (pod.serviceAccountName in values must render as the pod's
  serviceAccountName: k8s-readonly, otherwise fix the field).
- RBAC negative tests BEFORE Tux access: auth can-i as the
  ServiceAccount must say YES for get persistentvolumes, NO for
  get secrets, NO for create pods, NO for pods/exec.
- Positive test from inside the pod: kubectl proxy serves
  /api/v1/persistentvolumes, /api/v1/persistentvolumeclaims,
  /apis/velero.io/v1/namespaces/velero/backups.
- Negative test via the proxy: POST to /api/v1/namespaces must fail
  (proxy filter + RBAC), GET /api/v1/secrets must fail (RBAC).
- Tux access test is Dave's step after sync: Dave tells Tux the
  tailnet hostname, Tux approves the new address once, then curls
  the proxy. If Tux cannot reach it, report the exact failure -
  do NOT widen the proxy (no public URL, no Pangolin, no ACL
  change) to work around a connectivity failure without Dave's
  explicit approval in that run.
