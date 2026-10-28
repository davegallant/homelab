# Tailnet gateway routes chart

The `tailnet-gateway` Argo CD Application renders this chart alongside the
gateway platform resources. Each entry in `values.yaml` produces an HTTPRoute
and a CiliumNetworkPolicy for the named application's Service and port.
Routes default to `<name>.tail.davegallant.ca`; `hostname` overrides that
name, and `additionalHostnames` adds aliases to the same route. Immich uses
both its production and temporary Kubernetes hostnames.

Apply changes through the manually synced Argo CD Application. Follow the
gates in [the migration runbook](../MIGRATION.md) when moving a hostname,
including route, certificate, backend, DNS and client checks. Preserve the
existing policies and unrelated hostnames; do not prune or force a sync.
