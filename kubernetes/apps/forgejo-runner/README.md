# Forgejo Docker runner

## Design and trust boundary

- The official Forgejo runner chart is sourced from
  `https://code.forgejo.org/forgejo-helm/forgejo-runner.git`. The checked chart
  reports version `0.7.5` and runner app version `12.7.3`; the Application
  currently tracks `main`.
- Runner polling uses the internal Forgejo URL
  `http://forgejo.forgejo.svc.cluster.local:3000`.
- The runner uses the `docker` label and DinD. Only trusted repositories and
  maintainers should be able to send work to it. Its registration is scoped to
  the `dave` user, which includes all repositories owned by that user. The two
  current private workflow repositories have no collaborators; workflows use
  `push`/schedule/manual triggers and do not use pull-request triggers.
- The `.runner` registration file is stored in Ansible Vault as
  `forgejo_runner_config` and provisioned by
  `ansible/playbooks/talos-cluster/forgejo-runner-secret.yml`. Keep a completed
  Forgejo Velero backup with Secrets included before changing registration.
- The runner and privileged DinD are intentionally in this Kubernetes cluster
  and share a worker with production workloads. Treat privileged DinD as a
  reviewed exception; a tainted worker would reduce sharing but would not
  create a separate cluster boundary.
- Public egress is limited to TCP 443 for the explicit FQDNs in
  `policy/network-policy.yaml`; direct public IPs and unlisted HTTPS hosts are
  denied. DNS queries to cluster DNS are visible through Cilium's DNS proxy.
  DNS query names are temporarily unrestricted while FQDN-based egress is
  validated. Do not expose long-lived or broadly scoped credentials to jobs.

## Apply and verify

Application definitions are managed by the `argocd` Application. The runner
workload and its namespace/network policy are separate Applications and require
manual sync. Review each Argo diff before syncing; no automatic sync or prune is
configured.

After approval and sync:

1. Confirm the namespace has `enforce: privileged` and `audit`/`warn: restricted`.
2. Confirm capacity for two concurrent jobs, the intended resource bounds, and
   no mounted service-account token.
3. Use Hubble to confirm DNS, Forgejo polling, checkout, and required public
   web traffic are allowed; confirm access to the Kubernetes API, NAS, node
   management addresses, and unrelated private services is denied.
4. Run two real trusted Docker workflows concurrently and verify both checkout
   and complete successfully.
   Runner registration alone does not prove job networking works.
5. Review all workflow triggers and job secrets before treating this runner as
   safe for untrusted contributions. User scope includes future repositories
   Dave owns, so review those workflows before enabling Actions for them.

Do not sync the policy or runner values until the rendered Argo diff has been
reviewed. Do not rotate the registration credential or change its scope as part
of this work without an explicit recovery plan.
