# Tailnet gateway migration

Migrate one application at a time. This runbook does not authorize deployment,
certificate issuance, DNS/ACL changes, pruning or node reboots. Verify each gate
against live state. On failure, halt that step, preserve evidence and completed
work, and obtain direction before reversing state unless it is actively harming
workloads or data.

## Prerequisites

- Verify the intended API server and expected nodes. Inspect Gateway, listener,
  route, Envoy and fronting-pod health; configuration alone is not proof.
- Inspect the tracked Gateway chart, Cilium values, Argo project and application
  definition. Confirm the listener permits the app namespace and the project
  permits every rendered kind and destination. Use ReferenceGrant only when
  references cross namespaces; do not widen projects to clear a sync error.
- Verify a trusted production wildcard certificate, hostname/SAN, expiry and
  key/leaf match without printing private material. Never reuse an exposed
  staging key or accept staging trust as production proof.
- Record the app's Service, target port, backend bind address, sidecar resources,
  DNS answers, Headscale registration and required clients. Preserve source
  data and protected configuration backups before changing them.

## Per-application sequence

1. Keep the existing access path while adding the route and narrowly scoped
   backend policy. The backend must listen on pod IP, not only loopback.
2. Review the Argo diff and sync only the approved resources. Verify route
   Accepted/ResolvedRefs, ready endpoints and successful backend transport.
   A ready EndpointSlice does not prove the process accepts pod-IP connections.
3. Prove Gateway transport with the application's real Host/SNI. Forced-address
   requests may isolate this test, but do not establish normal client access.
4. After approval, remove that application's sidecars through its reviewed Argo
   change. Prune only approved obsolete resources for that app, without force.
   Deleting their PVCs or ConfigMaps while the Deployment still mounts them
   breaks the existing path. Preserve data pending separately approved cleanup.
5. Wait for the retired Headscale node to become offline before removing or
   expiring its colliding registration. Do not add an extra DNS record while an
   online node owns that name.
6. Preserve existing extra DNS records when adding the app's records. Validate
   a protected candidate with `headscale configtest` using a `.yaml` filename,
   update the repository template, then apply only the approved change. Verify
   Headscale health and unrelated clients after any required restart.
7. Verify ordinary DNS and trusted HTTPS from the operator and every required
   tagged client. Require the intended answer without stale sidecar addresses.
   Do not use `--resolve`, `--connect-to` or `-k` for this final proof.
8. Verify real app functions and unrelated routes before declaring completion.
   For API-only apps, use positive and negative API calls rather than a page.

## Client ACLs and diagnostics

Tagged clients do not inherit member permissions. Review the tracked Headscale
policy and tests; authorize a narrow client-to-gateway TCP 443 rule when needed,
retaining denial tests for other ports, UDP and management destinations. Do not
change node ownership or tags merely to bypass an access failure. Shared port
443 reachability does not authorize access to a single hostname behind it.

Use timestamped fronting logs and Hubble to distinguish ACL denial, backend
failure and route mismatch. Check DNS propagation before concluding failure.
For Envoy HTTP 500/IPCache failures, inspect its BPF mount and propagation against
Cilium values before changing the app. A repair or restart needs authorization.

## Application constraints

- Prowlarr: preserve in-pod Flaresolverr and in-cluster *arr traffic.
- Read-only API proxy: retain filtering and RBAC. Verify PV/PVC/Velero backup
  GETs succeed and Secret GETs/namespace POSTs fail; root 403 is expected.
- Homepage: outbound widget/API and TrueNAS WebSocket verification is separate
  from inbound routing.
- Public Newt services and Bedrock UDP require their existing exposure paths.

## Certificate renewal and evidence

Inspect actual served expiry; do not use a historical date as the renewal
inventory. Renew before the operational threshold of 30 days remaining. Use
production ACME DNS-01 with Vault-sourced credentials and protected temporary
files. Validate trust, SAN, expiry and key match before updating Vault and the
wildcard Secret. Verify Envoy serves the new fingerprint through ordinary
trusted hostname HTTPS. On failure preserve the last working production state;
never fall back to staging material.

Keep receipt files local and gitignored under `kubernetes/receipts/`. Record
which gates passed, failed or remain pending without secret values. Evidence
from a prior migration does not satisfy a new migration's gates.
