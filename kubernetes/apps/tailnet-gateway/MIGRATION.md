# Tailnet Gateway migration guide v3

Snapshot: 2026-10-26/27. This updates the v2 guide in place. Migrate one
application per separately authorized run; stop at every failed gate and
preserve the evidence. Live status, certificate expiry and repository state
must be checked again before each migration.

Changedetection and k8s-readonly are now COMPLETE on the Gateway. Prowlarr is
next, Homepage is last. Do not re-learn the k8s-readonly halts for Prowlarr.

## What changed from v2

V2 corrected sidecar/DNS sequencing for an online node, but it did not know
three further gates that halted k8s-readonly in order, nor the backend and
prune fixes that finally proved it:

1. **Gateway listener gate:** the listener allowed only `changedetection`, so
a k8s-readonly route could not attach. Fixed by widening the listener, commit
`1de7324`, to exactly `changedetection, k8s-readonly, prowlarr, homepage`.
2. **Argo project gate:** the tailnet-gateway Application is project
`homelab-platform`, whose destinations were only `tailnet-gateway` and
`changedetection`, so a k8s-readonly route/policy was rejected. Fixed by
widening homelab-platform destinations, commit `fe9e1204`, to add
`k8s-readonly, prowlarr, homepage`. Apps themselves remain project `homelab`.
3. **Receipts gate:** receipts must not be committed. `.gitignore` now ignores
`kubernetes/receipts/`, the one tracked receipt was removed with
`git rm --cached` (local file preserved), and after commit `fe9e1204`
`git ls-files kubernetes/receipts/` is empty. All receipts stay local.
4. **Backend gate:** k8s-readonly was loopback-only, so Gateway transport
returned HTTP 503 upstream connection failure even though the route was
Accepted. A Caddy plain-HTTP fix failed and was rolled back. The proven fix
was proxy-direct: proxy `--address=0.0.0.0` port 8001, Service/route/policy
port 8001, Caddy untouched, commit `bbbe6456`.
5. **Prune gate:** a proxy-only Argo sync without prune left the Deployment
with all three containers and four sidecar ConfigMaps/PVCs OutOfSync, with
trash icons in Argo. The fix was `argocd app sync k8s-readonly --prune`, no
force, k8s-readonly only, which pruned exactly those four and left the
Deployment proxy-only, Synced/Healthy.

## What changed from v1

V1 required ordinary-DNS/browser proof before deleting a sidecar. That order
does not work when an online sidecar node owns the production MagicDNS name:
adding the Gateway extra record collides, and removing the sidecar before
changing DNS makes ordinary resolution fail. V2 uses a trusted `--connect-to`
transport proof while the sidecar remains live, removes the sidecar, waits for
its Headscale node to go offline, removes any remaining offline registration,
then changes DNS and performs ordinary browser proof. The guide now records
the `k8s-readonly` online-node collision that halted before any route or DNS
change.

## 1. Prerequisites

- Confirm the intended cluster, API server and node names. Gateway
  `tailnet-gateway/tailnet-gateway` must be Accepted and Programmed at
  `192.168.1.185`; the listener and relevant routes must be Accepted and have
  ResolvedRefs. The fronting pod must be Ready, with Tailscale node
  `tailnet-gateway` at `100.100.0.8` serving raw TCP 443 to
  `192.168.1.185:443`.
- Confirm Secret `tailnet-gateway/tailnet-gateway-wildcard` is
  `kubernetes.io/tls` and its public leaf fingerprint and expiry match the
  approved production certificate. The 2026-10-26 certificate is Let's Encrypt
  YE1, SHA-256 `511E99CD84024C77A71210CA5BA69C4D2F608B97092799F2B0AD86DAEFACD199`,
  expiring 2027-01-24 21:48:01 UTC. Prove the real hostname serves this trusted
  certificate before migrating. Inspect certificate metadata only; never print
  Secret data or private keys.
- Confirm the app and its backend endpoint are Ready, and record the existing
  sidecar path, route, DNS, ACL and browser results. Do not migrate until these
  gates are proven. See the production certificate and DNS proof receipts in §10.
- **New in v3, check before any route:** (a) Gateway listener
  `allowedRoutes.namespaces` must include the app namespace, not just
  `changedetection`; (b) Argo project `homelab-platform` destinations must
  include the app namespace, not just `tailnet-gateway` and `changedetection`;
  (c) the app backend must listen on pod IP, not loopback only — see §7 for
  k8s-readonly, and verify the same for Prowlarr/Homepage before assuming a
  plain Service route will work; (d) receipts are gitignored, see §6.

## 2. Mandatory per-application sequence

Follow these gates in order for each separately authorized application. Do not
change DNS before sidecar deletion when its online Headscale node owns the
application hostname.

1. Record the app's current behavior, dependencies, sidecar resources, Service
   and backend port, DNS answers, Headscale node/IP/status, ACL coverage, and
   production proof. Confirm the cluster, Gateway, production certificate,
   fronting pod and backend are healthy. Inventory hostname collisions before
   editing either route or DNS. Add a test route only when the app's plan calls
   for one.
2. Add the production HTTPRoute to the live Gateway source with the exact
   Service and port recorded above. Keep the sidecar live and leave Headscale
   DNS unchanged. Commit/push only that route change, then manually sync only
   the `tailnet-gateway` Argo Application with no force and no prune, unless
   the run explicitly authorizes prune for a later sidecar-removal step.
   Verify route Accepted/ResolvedRefs and record the sync result. If Argo
   rejects the sync with a namespace/project error, halt — see §2a, do not
   work around it with a cross-namespace route.
3. With the sidecar still live, prove the production HTTP path through the
   fronting node using trusted `curl --connect-to`, preserving the production
   URL hostname for Host/SNI and certificate validation. Record curl exit,
   HTTP status, TLS verification, production fingerprint, and an app page/API
   marker. **This is transport proof only; `--connect-to` is not browser proof**
   because ordinary DNS is bypassed. If it fails, halt and preserve evidence.
   If it fails with HTTP 503 upstream connection failure, check §7 backend
   loopback first, not DNS or ACL.
4. Only after transport proof passes, remove only that app's inbound sidecar
   containers and their sidecar-only resources. Keep its app container, Service,
   data, unrelated sidecars and outbound dependencies. **Sync the app
   Application with prune explicitly authorized for that app only, if removed
   resources must be pruned** — a sync without prune will leave the old
   containers/ConfigMaps/PVCs OutOfSync with trash icons, as k8s-readonly did.
   Wait for the app pod to become Ready and stable for 60 seconds. Confirm
   that the sidecar's Headscale node has gone offline. If it remains online,
   halt; do not delete an online node.
5. If the now-offline sidecar node is still registered and collides with the
   app hostname, delete or expire that stale/offline registration and verify it
   is absent. Never remove an online node before sidecar deletion. If node
   ownership, status or collision is ambiguous, halt and preserve state.
6. Only after the sidecar node is absent, add the Headscale extra A record for
   the production hostname (and test hostname, if used) to `100.100.0.8`. Back
   up the live Headscale config first, validate a `.yaml` candidate with
   `headscale configtest`, install only the approved DNS change and restart only
   Headscale if required. Verify Headscale health and that other nodes remain
   healthy. Never apply a config that omits required live records. **Preserve
   existing extra records in the candidate** — the k8s-readonly candidate
   preserved both changedetection records and added only its own record.
7. Check MagicDNS and system DNS on the Mac and every relevant tagged client.
   Check ACL access first for tagged clients; if an ACL is missing, halt for its
   separately authorized narrow update. Then make ordinary trusted HTTPS
   requests with no `--connect-to`, `--resolve` or `-k`. Record exit, status,
   TLS verification, remote IP, fingerprint and app marker from the Mac and
   tagged client. This is the browser-equivalent proof. For grafana, if SSH as
   user `dave` is denied by tailnet policy, try already-available `root@grafana`
   access before changing any ACL — that is how k8s-readonly grafana proof
   passed, with no ACL change.
8. Re-prove ordinary HTTPS and app API behavior in the final state. Confirm
   sidecar resources are gone, the app and fronting pods are Ready, and the
   Gateway route remains Accepted/ResolvedRefs. For changedetection, verify
   both production and test hostnames still work. Stop after this one app; do
   not migrate another app in the same run.

The changedetection evidence explains the sequence. The production route was
added in [commit 6230ec5](https://github.com/davegallant/homelab/commit/6230ec5edd97c85a6bf54cd470d19158ca20eda2),
and its trusted `--connect-to` HTTP 200 passed while the sidecar was still
live. Sidecar removal was isolated in
[commit 109e171](https://github.com/davegallant/homelab/commit/109e1718cc6cbe4a9be858bda24c1c060aefb237).
After removal, normal DNS still selected retired node 57 at `.54` and timed
out; a request to the Gateway's own hostname returned 404 because that Host/SNI
matched no app route. The forced request proved transport, not browser access.
Node 57 was confirmed offline and removed before adding the DNS records. After
the tagged-client ACL was corrected, ordinary DNS and trusted HTTPS returned
200 from both Mac and Grafana. See the receipts in §10.

**Online-node collision example:** `k8s-readonly` was still online as Headscale
node 68 at `100.100.0.1`; its hostname resolved there. Pointing that same
hostname to Gateway `100.100.0.8` would collide. The migration correctly halted
at baseline before route or DNS changes; the sidecar remained live at that
time (it was later removed in v7, see §7). Do not try to work around this by
adding the record early or deleting the online node.
See the k8s-readonly receipt, `kubernetes/receipts/tailnet-gateway-k8s-readonly-migration-20261026/RECEIPT.md`, local only.

## 2a. Gateway listener and Argo project gates (new in v3)

These are one-time, separately authorized platform changes, not per-app route
changes. Do not skip them for Prowlarr/Homepage — they are already done for
all four namespaces, verify them, do not re-apply blindly.

- **Gateway listener:** `kubernetes/apps/tailnet-gateway/gateway.yaml`,
  `allowedRoutes.namespaces` was Selector `kubernetes.io/metadata.name=
  changedetection` only. k8s-readonly route could not attach, v2 halted before
  Step 2, no route/DNS/Argo/sidecar change. Fix, commit
  `1de7324fa63a2cc15619852399c0eaf5726f752f`, gateway.yaml only:
  matchExpressions key `kubernetes.io/metadata.name` operator In values
  `[changedetection, k8s-readonly, prowlarr, homepage]`, exactly those four,
  not All. Gateway Accepted/Programmed gen2, listener
  Accepted/Programmed/ResolvedRefs gen2, changedetection routes Accepted,
  trusted HTTPS 200 Mac prod+test, Argo Gateway-only sync Sync OK,
  Application overview remained OutOfSync for 3 resources, left untouched.
  Grafana proof was unavailable in that run, SSH denied as user `dave`.
- **Argo project:** Argo Application `tailnet-gateway` is project
  `homelab-platform`, AppProject `kubernetes/apps/argocd/platform-project.yaml`.
  Destinations were `tailnet-gateway` + `changedetection` only, namespace
  whitelist already included HTTPRoute + CiliumNetworkPolicy, type allowed,
  destination namespace not allowed. v3 halted Step 2, Argo dry-run rejected
  `namespace k8s-readonly is not permitted in project 'homelab-platform'`,
  no route/policy applied, sidecar live, node 68 online, DNS unchanged,
  source commit `18435e1` already pushed. Fix, commit
  `fe9e1204bdcdbdfcd1e63d2efe45c9ea6c69d4ad`, platform-project.yaml +
  .gitignore + `git rm --cached` one tracked receipt only: destinations added
  `k8s-readonly, prowlarr, homepage` to existing 10, no existing destination
  removed, source/cluster/namespace allowlists unchanged, apps remain project
  `homelab` (changedetection/homepage/k8s-readonly/prowlarr checked),
  tailnet-gateway remains `homelab-platform`, AppProject applied directly
  with `kubectl apply -f platform-project.yaml` (not an Argo Application,
  argocd Helm app not synced), changedetection trusted HTTP 200 Mac after,
  Argo dry-run for `18435e1` then Phase Succeeded, route/policy created
  dry-run, not applied in that run, tailnet-gateway OutOfSync pending migration.
- **Do not move apps to homelab-platform.** Widening destinations only allows
  the tailnet-gateway Application to deploy route/policy resources into those
  namespaces. App Applications stay `homelab`, their Deployments/Services still
  sync via `homelab`. Moving an app would change its sync policy and
  whitelists and lose the manual-approval separation.
- **Tailnet-gateway OutOfSync, Healthy, routes live, does not block traffic.**
  Last full sync was to `bbbe645`, target main later moved to `8f6f1aa`,
  Application OutOfSync, Healthy, routes Accepted, Gateway Accepted,
  changedetection + k8s-readonly transport proved. Do not click Sync on
  tailnet-gateway just to clear the badge without checking Diff first; a full
  sync later, after checking Diff, with no prune/force unless Diff shows only
  expected resources, is a separate cleanup.

## 3. DNS and browser proof

Headscale extra A records for an app's production and test hostnames must point
only to `100.100.0.8`. Follow §2: keep an online sidecar node in place through
transport proof and sidecar deletion; wait for it to go offline, then remove or
expire the colliding offline registration and verify it is absent **before**
adding the extra record. The retired changedetection node 57 at
`100.100.0.54` was offline and deleted after sidecar removal. Node 68 for
k8s-readonly at `100.100.0.1` was still online, so its proposed `.8` record was
a collision and the run halted without route or DNS changes.

Back up the live Headscale config before editing. Add production and test A
records to `100.100.0.8`, validate the candidate using a filename ending in
`.yaml` with `headscale configtest`, and restart only Headscale if required.
Verify Headscale health and that other nodes remain healthy. Keep the
repository template aligned with the approved live DNS state before any
configuration reapply. **Preserve existing extra records:** k8s-readonly
candidate preserved both changedetection records and added only
`k8s-readonly.tail.davegallant.ca A 100.100.0.8`, backup
`config.yaml.pre-k8s-readonly-v7-20261027` SHA-256 `4341681a…`, candidate
SHA-256 `d5463a6b…`, configtest passed, installed mode `0640`, restarted only
headscale, health succeeded, grafana 14 + gateway 71 online, node 68 absent.

Check `dig @100.100.100.100 <hostname> A` and the system resolver on the Mac
and every relevant tagged client, for both production and test names. Require
only `100.100.0.8`, not the old sidecar address or multiple answers. The Mac
cached NXDOMAIN for about 55 seconds after the 2026-10-26 restart; allow for
propagation and record observations before concluding failure. Browser proof is
ordinary trusted `curl https://<hostname>/` from the Mac and tagged clients,
without `--connect-to`, `--resolve`, or `-k`. A `--connect-to` success proves
the forced transport path only; it does not prove ordinary DNS or browser
access. For API-only apps like k8s-readonly, browser-equivalent proof is the
API pattern, not a page — see §7.

Changedetection illustrates why: MagicDNS returned the retired `.54` and the
production browser request timed out; the Gateway hostname resolved to
`100.100.0.8` and returned 404 because its Host/SNI matched no changedetection
route. A `--connect-to` request returned 200 with the app Host/SNI and proved
the data path, but **that is not browser proof**. Node 57 was removed only after
the sidecar had been deleted and the node was offline. An initial DNS attempt
returned trusted 200 from the Mac but timed out from Grafana; DNS was rolled
back. After the explicit Grafana-to-Gateway ACL was applied, normal requests
returned trusted 200 from both clients. The separate `k8s-readonly` example
stopped before DNS because its same-name node was still online at `.1`. See the
browser, node 57, ACL, DNS and k8s-readonly receipts in §10.

## 4. Tagged-client ACLs

Tagged clients do not inherit `autogroup:member`; the untagged Dave-owned Mac
was covered, while Grafana (`100.100.0.14`, tagged) was not. When a tagged client
needs this path, use an explicitly authorized narrow TCP rule from that client
IP to `100.100.0.8:443`. Update the tests in
`ansible/playbooks/vps/policy.headscale.hujson`, validate the candidate
before applying, and retain denial checks for other Dave-owned destinations,
other ports and UDP. Current explicit tests cover selected addresses; review
other existing and new Dave-owned nodes rather than assuming future nodes are
covered. Do not expand access by changing ownership or tags.

Capture timestamped fronting logs while probing; a Grafana `Drop ... no rules
matched` identified the 2026-10-26 ACL failure. After the approved policy update,
verify connectivity, trusted application HTTPS and absence of new matching drops.
See the Grafana diagnostic and ACL apply receipts in §10.

**Grafana SSH access, not ACL:** for k8s-readonly, SSH as user `dave` to grafana
was denied by tailnet policy, and SSH as `root@grafana` (already available)
passed ordinary DNS + trusted API proof with no ACL/policy change. Record
which user was used; do not claim dave@grafana works, and do not change ACL
just to make dave@grafana work if root access is already available and approved
for that proof.

## 5. Envoy BPF mount

With Cilium 1.20.3, `bpf.autoMount.enabled=false` remains set. Envoy needs
explicit `extraVolumes` and `extraVolumeMounts` for `/sys/fs/bpf`, with
`HostToContainer` propagation, as in
[the BPF mount commit](https://github.com/davegallant/homelab/commit/c4540f809cf51b0fc35f7b035891787a32cc8ffd).
Without that mount Envoy could not open IPCache and returned an empty HTTP 500
while the backend itself returned 200. Verify the mount and IPCache access,
policy publication, Envoy readiness and an application request before blaming
the backend. A repair or restart requires its own authorization. See the
HTTP 500, Envoy diagnostic and BPF mount receipts in §10.

## 6. Certificate, Vault and receipts in Git

Production issuance used a fresh private key; the staging key was exposed in
earlier diagnostic output and must never be reused. After
[Vault cleanup](https://github.com/davegallant/homelab/commit/e01fcd3a56dae798800619125aaef4456cce0691),
the task references only `tailnet_gateway_production_tls_crt` and
`tailnet_gateway_production_tls_key`; there is no environment selector or
staging fallback. Keep keys and credentials out of Git, logs and receipts.

**Repository state as of 2026-10-26:** commit
[e01fcd3](https://github.com/davegallant/homelab/commit/e01fcd3a56dae798800619125aaef4456cce0691)
contains the production-only Vault TLS task and the already-applied ACL policy.
The Headscale DNS template remains local, uncommitted and unpushed; fronting
auth Vault/include changes are also local. Before any Pangolin config reapply,
first preserve the live extra DNS records in the template, review and commit/push
the required Vault task, policy and DNS template changes, and verify the exact
candidate includes the desired records. The current template does not represent
the live changedetection DNS records, so reapplying it without this work could
remove them. Do not silently include unrelated work.

**Receipts in Git (new in v3):** receipts under `kubernetes/receipts/` are
**not** committed. `.gitignore` ignores `kubernetes/receipts/` only, added in
commit `fe9e1204`. The one previously tracked receipt,
`kubernetes/receipts/tailnet-gateway-gate-2-staging-20261026/RECEIPT.md`, was
removed with `git rm --cached`, local file preserved, not deleted. After that
commit `git ls-files kubernetes/receipts/` is empty; all receipts, including
this guide's own receipt if one is written, stay local and gitignored. Do not
commit a receipt, do not use plain `git rm` for receipts, do not remove
existing .gitignore entries, do not ignore other source files. Guide-only
commits must stay guide-only; receipt files must not be added to them.

## 7. Application-specific notes

- **Prowlarr:** retain its in-pod Flaresolverr; migrate inbound access only.
  Before migrating, verify its backend listens on pod IP, not loopback only,
  and record its Service/port, sidecar resources, Headscale node, and
  in-cluster *arr traffic (which must not change — *arr ↔ Prowlarr is
  in-cluster, not via Gateway).
- **k8s-readonly — COMPLETE, do not redo:** retain the filtered kubectl proxy
  on `0.0.0.0:8001` (changed from loopback in v6), Service ClusterIP
  `10.97.205.32` port/targetPort `8001`, and its RBAC and filtering protections.
  The old sidecar certificate fingerprint began `4279B76D` and expired
  2027-01-23; it was the sidecar certificate, not the Gateway production
  certificate, and it will expire unrenewed. Its node 68 at `100.100.0.1` was
  online at baseline, so the `.8` DNS collision halted the first migration.
  **Backend lesson:** the original chain was loopback-only — Tailscale
  TCPForward 443 → Caddy `127.0.0.1:8443` TLS Cloudflare → proxy
  `127.0.0.1:8001` — so Envoy via Service to pod IP got HTTP 503 upstream
  remote connection failure even though route was Accepted and EndpointSlice
  was ready. A Caddy plain-HTTP fix, site `http://…:8443` bind `0.0.0.0`
  TLS removed, commit `4f7a0fe`, failed: Caddy exited code 1, restarted 3x,
  sidecar reset, rollback commit `26bdb6a` restored Caddyfile, sidecar
  recovered. The proven fix was proxy-direct, commit `bbbe6456`: proxy
  `--address=0.0.0.0` port 8001, Service port/targetPort 8001 (app-template
  `targetPort` defaults to port), backend policy + route port 8001, Caddy
  untouched loopback TLS, Gateway transport API 200/200/200/403/403, sidecar
  still `.1` same pattern, pod Ready 60s zero restarts. **k8s-readonly has no
  browser page:** root returns 403 expected, proof is API pattern GET PVs
  200, GET PVCs 200, GET Velero backups 200, dry-run POST namespace 403,
  GET secrets 403, no title/marker. Final migration v7: prune sync by Dave,
  `argocd app sync k8s-readonly --prune`, no force, Deployment proxy-only,
  ConfigMaps/PVCs caddy+tailscale absent, Caddy gone for k8s-readonly,
  node 68 deleted, DNS `k8s-readonly A 100.100.0.8` preserving changedetection
  records, Mac + grafana (root@grafana) ordinary DNS trusted API proof
  200/200/200/403/403, root 403, prod fingerprint, changedetection still 200.
- **Homepage:** migrate last. Keep its outbound proxy-agent at
  `127.0.0.1:1055` and verify real widget/API calls, including the TrueNAS
  WebSocket. Its outbound proxy is separate from inbound Gateway access.
- **Audiobookshelf** stays public. **Bedrock** stays on its LXC; this L7 Gateway
  does not replace its UDP path. **Forgejo** stays public through Newt.
  **qBittorrent** remains untouched.

## 8. Rollback rules

HALT AND PRESERVE at a failed gate. Do not automatically roll back completed
steps; request Dave's explicit in-the-moment authorization unless a previously
approved gate specifies a rollback or the frozen state actively harms workloads
or data. Record the exact condition, evidence and remaining state.

- **DNS:** when the gate explicitly authorizes DNS rollback, remove the new
  extra records by restoring the protected config backup, restart Headscale if
  needed, verify health and that DNS returns to its prior state, and freeze.
  Do not restore deleted nodes or application sidecars without separate approval.
- **ACL:** when explicitly authorized, restore the backed-up policy, validate
  and apply it through the approved policy workflow, verify the resulting
  access and record the result. Keep DNS and other state intact.
- **Secret:** never roll back to the exposed staging certificate or key. Keep
  the last-working production Secret intact and ask Dave for a separately
  approved recovery if production verification fails.
- **Prune:** when explicitly authorized for one app only, sync that app with
  prune, no force, no other Application. Prune only resources removed from Git
  for that app; do not prune other Applications to clear a badge. Manual
  `kubectl delete` of ConfigMaps/PVCs alone does not update the Deployment
  and will break a live sidecar — use Argo prune sync instead.
- **Caddy/proxy backend:** if a backend fix breaks the live sidecar, use the
  prompt's sole rollback exception only: restore the previously committed
  config and re-sync only that app, as v5 did with commit `26bdb6a`. Do not
  proceed to deletion/DNS after a backend rollback.

## 9. Renewal

The production certificate recorded here expires **2027-01-24 21:48:01 UTC**;
check expiry daily and renew when 30 days or less remain. This is an operational
requirement, not a claim that automated monitoring already exists. Use the
production Lego workflow (v5.5.2 was used on 2026-10-26), production ACME and
Cloudflare DNS-01 with the Cloudflare credential sourced only from Ansible
Vault in protected temporary files. Never print credential, certificate or key
material. Use a fresh key. Validate hostname/SAN, chain trust, expiry and
key/leaf match before updating Vault.

After validation and authorization, update Vault and apply only the wildcard
TLS Secret. Check the public fingerprint and verify Envoy reload by comparing
the fingerprint actually served on trusted normal-hostname HTTPS. On failure,
leave the last-working Secret untouched and alert Dave; if a replacement has
already occurred, halt and seek a separately authorized recovery rather than
reverting to staging. See the production certificate cutover receipt for
protected state and issuance details.

## 10. Receipts index

These are the historical receipts in work order; later gates can supersede
an earlier failure. Receipts under `kubernetes/receipts/` are gitignored and
local only, not included in guide-only commits, so this index deliberately
has no links — the file names below are local paths, not GitHub links.
File names are under `kubernetes/receipts/` on a machine with local receipts.

1. Gate 0 — `tailnet-gateway-gate-0-20261026/RECEIPT.md` — FAIL, prerequisites open.
2. Gate 0b — `tailnet-gateway-gate-0b-20261026/RECEIPT.md` — HALTED, allocation confirmation required; `.185` later confirmed.
3. Gate 1 — `tailnet-gateway-gate-1-20261026/RECEIPT.md` — FAIL, Argo permissions.
4. Gate 1 retry — `tailnet-gateway-gate-1-retry-20261026/RECEIPT.md` — FAIL, cross-application gate.
5. Argo diagnosis — `tailnet-gateway-argo-diagnosis-20261026/RECEIPT.md` — FAIL, connectivity did not converge.
6. Cilium operator logs — `tailnet-gateway-cilium-operator-logs-20261026/RECEIPT.md` — COMPLETE, read-only inspection; no repair applied.
7. Cilium operator restart — `tailnet-gateway-cilium-operator-restart-20261026/RECEIPT.md` — FAIL, connectivity did not converge.
8. Cilium agent w1 restart — `tailnet-gateway-cilium-agent-w1-restart-20261026/RECEIPT.md` — PASS, address and health converged.
9. Gate 1 reverify — `tailnet-gateway-gate-1-reverify-20261026/RECEIPT.md` — PASS.
10. Gate 2 staging — `tailnet-gateway-gate-2-staging-20261026/RECEIPT.md` — HALTED at certificate approval, before certificate request.
11. Staging certificate — `tailnet-gateway-gate-2-cert-staging-20261026/RECEIPT.md` — FAIL, prerequisites not met.
12. Staging certificate v2 — `tailnet-gateway-gate-2-cert-staging-v2-20261026/RECEIPT.md` — FAIL, DNS-01 propagation.
13. Staging certificate v3 — `tailnet-gateway-gate-2-cert-staging-v3-20261026/RECEIPT.md` — FAIL, Secret assertion.
14. Secret assertion fix — `tailnet-gateway-secret-fix-apply-20261026/RECEIPT.md` — PASS for staging Secret assertion.
15. Gateway and fronting — `tailnet-gateway-gateway-fronting-20261026/RECEIPT.md` — FAIL, fronting auth absent.
16. Fronting auth — `tailnet-gateway-fronting-auth-20261026/RECEIPT.md` — FAIL, Vault storage.
17. Fronting auth v2 — `tailnet-gateway-fronting-auth-v2-20261026/RECEIPT.md` — FAIL, auth rejected.
18. Fronting auth v3 — `tailnet-gateway-fronting-auth-v3-20261026/RECEIPT.md` — FAIL, HTTP 500.
19. HTTP 500 diagnostic — `tailnet-gateway-http500-diagnostic-20261026/RECEIPT.md` — FAIL gate, Envoy-generated 500 established.
20. Envoy state diagnostic — `tailnet-gateway-envoy-state-diagnostic-20261026/RECEIPT.md` — FAIL gate, root cause identified; live fix unverified.
21. Envoy BPF mount — `tailnet-gateway-envoy-bpf-mount-apply-20261026/RECEIPT.md` — PASS for staging fronting path.
22. Production certificate cutover — `tailnet-gateway-prod-cert-cutover-20261026/RECEIPT.md` — PASS, trusted test route via forced transport.
23. Changedetection migration — `tailnet-gateway-changedetection-full-migration-20261026/RECEIPT.md` — PASS for the forced transport gate; subsequent ordinary DNS proof failed until DNS/ACL work.
24. Browser URL diagnostic — `tailnet-gateway-browser-url-diagnostic-20261026/RECEIPT.md` — FAIL, stale DNS identified.
25. Node 57 and live DNS attempt — `headscale-delete-node57-extra-record-live-20261026/RECEIPT.md` — FAIL, Grafana timed out and DNS was rolled back; node 57 remained deleted.
26. Grafana TCP 443 diagnostic — `grafana-fronting-tcp443-diagnostic-20261026/RECEIPT.md` — PASS, ACL drop cause proven.
27. Grafana ACL apply — `headscale-acl-grafana-fronting-apply-20261026/RECEIPT.md` — PASS, narrow ACL and trusted IP/TLS proof.
28. DNS reapply and browser proof — `headscale-dns-reapply-browser-proof-20261026/RECEIPT.md` — PASS, normal HTTPS from Mac and Grafana.
29. Vault selector cleanup — `tailnet-gateway-vault-selector-cleanup-20261026/RECEIPT.md` — PASS, production-only Vault/task cleanup committed.
30. Migration guide v1 — `tailnet-gateway-migration-guide-20261026/RECEIPT.md` — PASS, guide-only commit `aa06bea`; its sidecar/DNS sequencing is corrected here.
31. k8s-readonly migration — `tailnet-gateway-k8s-readonly-migration-20261026/RECEIPT.md` — FAIL, halted at baseline because online node 68 at `.1` collides with the proposed `.8` record; no route or DNS change and sidecar remains live.
32. Migration guide v2 — `tailnet-gateway-migration-guide-v2-20261026/RECEIPT.md` — PASS, guide-only commit `1cc0281`, 31-receipt index, correct sequencing route/transport/sidecar/node/DNS/browser.
33. k8s-readonly migration v2 — `tailnet-gateway-k8s-readonly-migration-v2-20261026/RECEIPT.md` — FAIL, halted before Step 2, Gateway listener allowed only `changedetection`, route could not attach, no ReferenceGrant, no changes.
34. Gateway listener widen — `tailnet-gateway-listener-widen-20261026/RECEIPT.md` — PASS, commit `1de7324`, listener In `[changedetection, k8s-readonly, prowlarr, homepage]`, Gateway gen2, changedetection trusted 200 Mac, Argo Gateway-only Sync OK, OutOfSync 3 resources left untouched, grafana SSH denied as dave.
35. k8s-readonly migration v3 — `tailnet-gateway-k8s-readonly-migration-v3-20261026/RECEIPT.md` — FAIL, halted Step 2, Argo rejected `namespace k8s-readonly is not permitted in project 'homelab-platform'`, commit `18435e1` route+policy source only, no live apply, sidecar live, node 68 online.
36. Homelab-platform destinations widen — `tailnet-gateway-platform-project-widen-20261026/RECEIPT.md` — PASS, commit `fe9e1204`, platform-project.yaml + .gitignore + `git rm --cached` one tracked receipt, destinations added k8s-readonly/prowlarr/homepage, apps remain homelab, dry-run for `18435e1` succeeded, route/policy not applied.
37. k8s-readonly migration v4 — `tailnet-gateway-k8s-readonly-migration-v4-20261026/RECEIPT.md` — FAIL, halted Step 3 transport, route+policy applied, all five API requests HTTP 503 upstream remote connection failure, route Accepted, EndpointSlice ready, sidecar live, node 68 online, DNS unchanged.
38. k8s-readonly backend fix v5 — `tailnet-gateway-k8s-readonly-backend-fix-v5-20261026/RECEIPT.md` — FAIL, Caddy plain-HTTP fix commit `4f7a0fe` exited code 1 restarted 3x sidecar reset, rollback commit `26bdb6a` Caddyfile restored sidecar recovered, Gateway transport not run.
39. k8s-readonly proxy-direct v6 — `tailnet-gateway-k8s-readonly-proxy-direct-v6-20261026/RECEIPT.md` — PASS, commit `bbbe6456`, proxy `--address=0.0.0.0` port 8001, Service/route/policy port 8001, Caddy untouched, Gateway transport API 200/200/200/403/403, sidecar still `.1` same pattern.
40. k8s-readonly migration v7 — `tailnet-gateway-k8s-readonly-migration-v7-20261026/RECEIPT.md` — PASS, prune sync by Dave to `8f6f1aa`, Deployment proxy-only, ConfigMaps/PVCs caddy+tailscale absent, node 68 deleted, DNS `k8s-readonly A 100.100.0.8` preserving changedetection records, Mac + grafana (root@grafana) ordinary DNS trusted API 200/200/200/403/403, root 403, changedetection still 200, receipt local gitignored not committed.
