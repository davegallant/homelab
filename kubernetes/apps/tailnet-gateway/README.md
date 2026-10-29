# Tailnet gateway

The tracked chart, production values, routes and Cilium policies define the
intended inbound path. Use [the migration runbook](MIGRATION.md) when moving
an application. Inspect live Gateway conditions, attached routes, DNS and TLS
before treating a hostname as migrated; files alone do not establish deployment.

Keep public Newt services and UDP services on their separately managed paths.
Homepage outbound widget/API and TrueNAS WebSocket checks are separate from
inbound Gateway verification.
