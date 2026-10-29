# Forgejo Docker runner

## Design and trust boundary

- The official Forgejo runner chart is sourced from
  `https://code.forgejo.org/forgejo-helm/forgejo-runner.git`. The checked chart
  reports version `0.7.5` and runner app version `12.7.3`; the Application
  currently tracks `main`.
- Runner polling uses the internal Forgejo URL
  `http://forgejo.forgejo.svc.cluster.local:3000`.
- The runner uses the `docker` label and DinD. Only trusted repositories and
  maintainers should be able to send work to it. The actual registration scope,
  workflow triggers, and secret use still need review in Forgejo and the
  workflow repositories; those files are not in this repository.
- The privileged runner and DinD containers share a Kubernetes worker with
  production workloads. A dedicated runner VM outside this cluster remains the
  preferred isolation boundary. A tainted worker would reduce sharing but
  would not create a separate cluster boundary.
- Public web egress is required for external actions and package downloads.
  The proposed policy limits its ports and blocks private address ranges, but
  it does not restrict which public hostnames workflows can contact. Do not
  expose long-lived or broadly scoped credentials to jobs.

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
5. Confirm in Forgejo that the runner is registered only at the intended
   trusted scope, and review all workflow triggers and job secrets before
   treating this runner as safe for untrusted contributions.

Do not sync the policy or runner values until the rendered Argo diff has been
reviewed. Do not rotate the registration credential or change its scope as part
of this work without an explicit recovery plan.
