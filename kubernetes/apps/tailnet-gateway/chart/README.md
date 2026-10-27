# tailnet-gateway-routes chart — DRY start, NOT yet wired live

Status 2026-10-27: chart + values exist on disk only. The live Argo
Application `tailnet-gateway` still sources `kustomization.yaml`, which
does NOT list this chart. Nothing here is synced, and no live route,
policy, Gateway, listener, cert, DNS, or ACL has changed.

What this chart renders, per app in values.yaml: one HTTPRoute
(`<app>-gateway-production`, `<app>.tail.davegallant.ca` -> Service
`<app>:<port>`) and one CiliumNetworkPolicy (Gateway ingress identity
only, to that port, with that app's explicit selector labels).

Canonicalisation, deliberate: rendered routes always carry
`kind: Gateway`, `kind: Service`, and `matches: PathPrefix /`. That
matches 9 of 11 live routes exactly. Homepage and kiwix live routes omit
those fields; Gateway API defaults make the canonical form equivalent,
but Codex must prove that in Gate 1 (rendered diff + Argo diff + live
test), not assume it. Changedetection's policy name is preserved as
`changedetection-gateway-test` — renaming it is out of scope here.

Out of scope for this chart: Gateway itself, listener, lb-pool, l2-policy,
entry-policy, fronting pod, namespace, storage, and the comment-only
referencegrant file. Those stay in kustomize / platform files.

Next step is the Codex handoff (see /Users/dave/codex-prompt-gateway-dryout.md
as updated after this chart): helm template render + diff vs live,
server-side Argo dry-run, kiwix canary first, then remaining apps in
approved batches. No prune, no force, no push without Dave's go.
