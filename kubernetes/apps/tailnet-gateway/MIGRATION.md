# Tailnet Gateway migration guide

Snapshot: 2026-10-26. Migrate one application per separately authorized run;
stop at every failed gate and preserve the evidence. Live status, certificate
expiry and repository state must be checked again before each migration.

## 1. Prerequisites

- Confirm the intended cluster, API server and node names. Gateway
  `tailnet-gateway/tailnet-gateway` is Accepted and Programmed at
  `192.168.1.185`; the listener and relevant routes must be Accepted and have
  ResolvedRefs. The fronting pod must be Ready, with Tailscale node
  `tailnet-gateway` at `100.100.0.8` serving raw TCP 443 to
  `192.168.1.185:443`.
- Confirm Secret `tailnet-gateway/tailnet-gateway-wildcard` is
  `kubernetes.io/tls` and its public leaf fingerprint and expiry match the
  approved production certificate. The 2026-10-26 certificate is Let's Encrypt
  YE1, SHA-256 `511E99CD84024C77A71210CA5BA69C4D2F608B97092799F2B0AD86DAEFACD199`,
  expiring 2027-01-24 21:48:01 UTC. Confirm trusted HTTPS with the real hostname.
  Inspect certificate metadata only; do not print Secret data or private keys.
- Confirm the app and its backend endpoint are Ready, and record the existing
  sidecar path, route, DNS, ACL and browser results. Do not migrate until these
  gates are proven. See the production certificate and DNS proof receipts in §10.

## 2. Per-application gates

1. Record the app's existing behavior and dependencies. Prepare the production
   HTTPRoute with the correct hostname, service and port, and permit Gateway
   ingress through the app's existing network policy where needed. Add and prove
   a test route first when appropriate. Obtain authorization for each live step.
2. Before removing a sidecar, prove the **production hostname** resolves to the
   Gateway and returns the expected application content over trusted HTTPS from
   the Mac and relevant tagged clients. Use normal hostname resolution and
   `curl` without `--connect-to`, `--resolve` or `-k`; record exit status, HTTP
   status, TLS verification, page or API marker and served certificate fingerprint.
   Test actual application APIs where applicable, not only a root page.
3. Only after that browser-equivalent proof passes, remove the app's inbound
   sidecar and its obsolete resources under a separately authorized change.
   Preserve the app's data, other sidecars and outbound dependencies.
4. Repeat DNS, trusted HTTPS and app-specific proof after removal. Confirm the
   app and fronting are Ready and the route remains Accepted/ResolvedRefs.
   Stop after one app; do not migrate another app in the same run.

The earlier changedetection route commit
[6230ec5](https://github.com/davegallant/homelab/commit/6230ec5edd97c85a6bf54cd470d19158ca20eda2)
and sidecar removal
[109e171](https://github.com/davegallant/homelab/commit/109e1718cc6cbe4a9be858bda24c1c060aefb237)
preceded normal DNS proof. The migration receipt's forced connection passed,
but the subsequent ordinary hostname request timed out. The later DNS and ACL
work finally proved browser access; future migrations must meet the stricter
pre-removal gate above.

## 3. DNS and browser proof

Headscale extra A records for the app's production and test hostnames must point
only to `100.100.0.8`. Before changing them, inventory stale registrations and
collisions, back up the live Headscale config, and obtain explicit approval for
any node deletion. Delete a stale node first **only when it collides and deletion
is authorized**: changedetection's retired node 57 was `100.100.0.54`. Validate
the `.yaml` candidate with Headscale configtest, confirm the Ansible template
matches it, then install the approved configuration and restart only Headscale
when needed. Check Headscale health and affected nodes after restart.

Check `dig @100.100.100.100 <hostname> A` and the system resolver on the Mac
and every relevant tagged client, for both production and test names. Require
only `100.100.0.8`, not the old sidecar address or multiple answers. The Mac
cached NXDOMAIN for about 55 seconds after the 2026-10-26 restart; allow for
propagation and record observations before concluding failure. Then use normal
trusted `curl https://<hostname>/` on both clients, without `--connect-to`,
`--resolve`, or `-k`.

Changedetection illustrates why: MagicDNS returned the retired `.54` and the
production browser request timed out; visiting the gateway's own hostname
returned 404 because its Host/SNI did not match the route. A `--connect-to`
request returned 200 with the app Host/SNI and proved the data path, but
**`--connect-to` proof is not browser proof**. Only after DNS and ACL fixes did
normal requests return trusted 200 from both clients. See the browser diagnostic,
node 57 rollback and DNS reapply receipts in §10.

## 4. Tagged-client ACLs

Tagged clients do not inherit `autogroup:member`; the untagged Dave-owned Mac
was covered, while Grafana (`100.100.0.14`, tagged) was not. When a tagged client
needs this path, use an explicitly authorized narrow TCP rule from that client
IP to `100.100.0.8:443`. Update the tests in
`ansible/playbooks/pangolin/policy.headscale.hujson`, validate the candidate
before applying, and retain denial checks for other Dave-owned destinations,
other ports and UDP. Current explicit tests cover selected addresses; review
other existing and new Dave-owned nodes rather than assuming future nodes are
covered. Do not expand access by changing ownership or tags.

Capture timestamped fronting logs while probing; a Grafana `Drop ... no rules
matched` identified the 2026-10-26 ACL failure. After the approved policy update,
verify connectivity, trusted application HTTPS and absence of new matching drops.
See the Grafana diagnostic and ACL apply receipts in §10.

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

## 6. Certificate and Vault

Production issuance used a fresh private key; the staging key was exposed in
earlier diagnostic output and must never be reused. After
[Vault cleanup](https://github.com/davegallant/homelab/commit/e01fcd3a56dae798800619125aaef4456cce0691),
the task references only `tailnet_gateway_production_tls_crt` and
`tailnet_gateway_production_tls_key`; there is no environment selector or
staging fallback. Keep keys and credentials out of Git, logs and receipts.

**Repository gap as of 2026-10-26:** the Headscale DNS template remains local,
uncommitted and unpushed; fronting auth Vault/include changes are also local.
The Vault task and already-applied policy were committed by the cleanup above.
Before any Pangolin config reapply, review, commit and push the authorized Vault
task, policy and DNS template changes, and confirm the desired extra records
are present in the version to be applied. Otherwise a reapply can remove the
live DNS records. Do not silently include unrelated work.

## 7. Application-specific notes

- **Prowlarr:** retain its in-pod Flaresolverr; migrate inbound access only.
- **k8s-readonly:** retain the filtered kubectl proxy on loopback
  `127.0.0.1:8001` and its RBAC and filtering protections.
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

## 9. Renewal

The production certificate recorded here expires **2027-01-24 21:48:01 UTC**;
check expiry daily and renew when 30 days or less remain. This is an operational
requirement, not a claim that automated monitoring already exists. Use the
production Lego workflow (v5.5.2 was used on 2026-10-26), production ACME and
Cloudflare DNS-01 with the Cloudflare credential sourced only from Ansible
Vault in protected temporary files. Never print credential, certificate or key
material. Use fresh key material and validate hostname/SAN, chain trust, expiry
and key/leaf match before updating Vault.

Apply only the wildcard TLS Secret after validation and authorization. Check its
public fingerprint and verify Envoy reload by comparing the fingerprint actually
served on trusted normal-hostname HTTPS. On failure, leave the last-working
Secret untouched and alert Dave; if a replacement has already occurred, halt and
seek a separately authorized recovery rather than reverting to staging. See the
production certificate cutover receipt for protected state and issuance details.

## 10. Receipts index

These are historical results, in work order; later gates can supersede an earlier
failure. Most receipt directories were untracked in the local workspace when
this guide was written and are not included in the guide-only commit. Preserve
or separately commit them if the evidence must be available to other clones.
Paths below are relative to this guide.

1. [Gate 0](../../receipts/tailnet-gateway-gate-0-20261026/RECEIPT.md) — FAIL, prerequisites open.
2. [Gate 0b](../../receipts/tailnet-gateway-gate-0b-20261026/RECEIPT.md) — halted on allocation; Dave later confirmed `.185`.
3. [Gate 1](../../receipts/tailnet-gateway-gate-1-20261026/RECEIPT.md) — FAIL, Argo permissions.
4. [Gate 1 retry](../../receipts/tailnet-gateway-gate-1-retry-20261026/RECEIPT.md) — FAIL, cross-application gate.
5. [Argo diagnosis](../../receipts/tailnet-gateway-argo-diagnosis-20261026/RECEIPT.md) — FAIL, connectivity did not converge.
6. [Cilium operator logs](../../receipts/tailnet-gateway-cilium-operator-logs-20261026/RECEIPT.md) — read-only diagnosis completed.
7. [Cilium operator restart](../../receipts/tailnet-gateway-cilium-operator-restart-20261026/RECEIPT.md) — FAIL, connectivity did not converge.
8. [Cilium agent w1 restart](../../receipts/tailnet-gateway-cilium-agent-w1-restart-20261026/RECEIPT.md) — PASS, address and health converged.
9. [Gate 1 reverify](../../receipts/tailnet-gateway-gate-1-reverify-20261026/RECEIPT.md) — PASS.
10. [Gate 2 staging](../../receipts/tailnet-gateway-gate-2-staging-20261026/RECEIPT.md) — halted at certificate approval.
11. [Staging certificate](../../receipts/tailnet-gateway-gate-2-cert-staging-20261026/RECEIPT.md) — FAIL, prerequisite check.
12. [Staging certificate v2](../../receipts/tailnet-gateway-gate-2-cert-staging-v2-20261026/RECEIPT.md) — FAIL, DNS-01 propagation.
13. [Staging certificate v3](../../receipts/tailnet-gateway-gate-2-cert-staging-v3-20261026/RECEIPT.md) — FAIL, Secret assertion.
14. [Secret assertion fix](../../receipts/tailnet-gateway-secret-fix-apply-20261026/RECEIPT.md) — PASS for staging Secret.
15. [Gateway and fronting](../../receipts/tailnet-gateway-gateway-fronting-20261026/RECEIPT.md) — FAIL, fronting auth absent.
16. [Fronting auth](../../receipts/tailnet-gateway-fronting-auth-20261026/RECEIPT.md) — FAIL, Vault storage.
17. [Fronting auth v2](../../receipts/tailnet-gateway-fronting-auth-v2-20261026/RECEIPT.md) — FAIL, auth rejected.
18. [Fronting auth v3](../../receipts/tailnet-gateway-fronting-auth-v3-20261026/RECEIPT.md) — FAIL, HTTP 500.
19. [HTTP 500 diagnostic](../../receipts/tailnet-gateway-http500-diagnostic-20261026/RECEIPT.md) — FAIL gate, Envoy-generated 500 established.
20. [Envoy state diagnostic](../../receipts/tailnet-gateway-envoy-state-diagnostic-20261026/RECEIPT.md) — FAIL gate, root cause identified; live fix unverified.
21. [Envoy BPF mount](../../receipts/tailnet-gateway-envoy-bpf-mount-apply-20261026/RECEIPT.md) — PASS for staging fronting path.
22. [Production certificate cutover](../../receipts/tailnet-gateway-prod-cert-cutover-20261026/RECEIPT.md) — PASS, trusted test route via forced connection.
23. [Changedetection migration](../../receipts/tailnet-gateway-changedetection-full-migration-20261026/RECEIPT.md) — PASS under its forced-path gate; normal hostname later failed.
24. [Browser URL diagnostic](../../receipts/tailnet-gateway-browser-url-diagnostic-20261026/RECEIPT.md) — FAIL, stale DNS identified.
25. [Node 57 and live DNS attempt](../../receipts/headscale-delete-node57-extra-record-live-20261026/RECEIPT.md) — FAIL, Grafana timed out; DNS rolled back.
26. [Grafana TCP 443 diagnostic](../../receipts/grafana-fronting-tcp443-diagnostic-20261026/RECEIPT.md) — PASS, ACL drop cause proven.
27. [Grafana ACL apply](../../receipts/headscale-acl-grafana-fronting-apply-20261026/RECEIPT.md) — PASS, narrow ACL and IP/TLS proof.
28. [DNS reapply and browser proof](../../receipts/headscale-dns-reapply-browser-proof-20261026/RECEIPT.md) — PASS, normal HTTPS from Mac and Grafana.
29. [Vault selector cleanup](../../receipts/tailnet-gateway-vault-selector-cleanup-20261026/RECEIPT.md) — PASS, production-only material and task committed.
