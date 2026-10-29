# Read-only Kubernetes API proxy

[Production values](values.production.yaml) define the filtered kubectl proxy;
[RBAC](rbac.yaml) defines its API permissions. Inbound traffic uses the shared
[tailnet gateway](../tailnet-gateway/README.md). The proxy uses its mounted
ServiceAccount token; it needs no application credential or persistent data.
Namespace and cluster RBAC are managed separately from the workload chart.

## Security and verification

Keep the default kubectl proxy filter enabled. Review RBAC and the rendered
ServiceAccount selection before syncing. Do not widen access to resolve a
connectivity failure without reviewing the security boundary.

Verify through ordinary trusted hostname HTTPS from each intended client:

- GET persistent volumes, persistent volume claims and Velero backups succeeds.
- GET Secrets and POST namespaces fails.
- ServiceAccount authorization denies Secret reads, Pod creation and exec.

A root-path 403 is expected; this service has no dashboard page. A route marked
Accepted or a successful forced-address request does not prove client DNS,
trusted TLS or API permissions. Repeat positive and negative API checks after
gateway, proxy, RBAC or network policy changes.
