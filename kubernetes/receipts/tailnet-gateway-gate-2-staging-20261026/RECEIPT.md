# Tailnet Gateway Gate 2 staging — 2026-10-26

**Verdict: HALTED at certificate approval gate, before any certificate request
or Gateway programming.** The initial staging resources synced successfully.
No Gateway, route, TLS Secret, PVC, or fronting Deployment exists. The existing
changedetection sidecar remains live and returned HTTP 200 after the sync.

## Baseline

- Kubernetes context `homelab`, API `https://192.168.1.210:6443`; all three
  expected nodes are Ready.
- Argo baseline was 34/34 Applications Synced/Healthy.
- GatewayClass `cilium` was Accepted. `k8s-w-1` CiliumNode InternalIP was
  `192.168.1.211`, generation 13, resourceVersion `1163739`.
- Changedetection sidecar URL was unchanged and returned HTTP 200 before and
  after staging. Backend Service is `changedetection:5000`.
- qBittorrent pod was 3/3 Ready; its scheduled egress monitor passed. The
  zero-torrents condition was not independently verified through available
  read-only checks. No torrent or monitor job was started by this run.

## Commits and push

- [`b2b5a39f1ab34f0fe15a19c3b669660949ab00b6`](https://github.com/davegallant/homelab/commit/b2b5a39f1ab34f0fe15a19c3b669660949ab00b6)
  publishes the Gateway source, initial stage-only Kustomization, Gate 2
  policies, and staging-only Secret workflow.
- [`3827f376537edecacd2f4517b3ce96b47e6738fb`](https://github.com/davegallant/homelab/commit/3827f376537edecacd2f4517b3ce96b47e6738fb)
  publishes the project permission required for the cluster-scoped entry policy.
- `origin/main` resolved to `3827f376537edecacd2f4517b3ce96b47e6738fb` after
  push.

## Sync and staging resources

The `tailnet-gateway` Application was created and manually synced alone with
prune and force disabled. Argo resolved revision
`3827f376537edecacd2f4517b3ce96b47e6738fb`; operation Succeeded, sync
Synced, health Healthy. All five rendered resources are Synced:

- Namespace `tailnet-gateway`.
- CiliumLoadBalancerIPPool `tailnet-gateway`: block `.185`, pool conflict
  False, 1 IP available, 0 used. No Gateway Service exists yet, so no address
  has been assigned or announced.
- CiliumL2AnnouncementPolicy `tailnet-gateway`: selects LoadBalancer IPs on
  `ens18`; no announcement status exists before a Service is created.
- CiliumClusterwideNetworkPolicy `tailnet-gateway-entry`: Valid=True.
- CiliumNetworkPolicy `changedetection-gateway-test`: Valid=True.

The initial Kustomization excludes Gateway, HTTPRoute, PVC, and fronting
Deployment. No other Argo Application was synced.

## Certificate gate and remaining evidence

The namespace exists, but `CERT-WORKFLOW.md` still lacks an approved staging
issuer, ACME account/contact, pinned Lego version, and protected runner
details. No ACME request, Cloudflare operation, Vault write, or Secret apply
was made. `tailnet-gateway-wildcard` is absent. Per the prompt, execution
halted here before Gateway programming.

Gateway and HTTPRoute are absent. No Gateway IP, L2 announcement, route/backend
response, or fronting tailnet proof is claimed. The staging certificate is
untrusted; no trusted HTTPS claim is made. The sidecar URL still returns
HTTP 200. Full `just lint` failed on captured Gate 1 receipt YAML; targeted
yamllint, Ansible lint, diff checks, Kustomize render, and server-side dry-run
of the initial staging manifests passed.
