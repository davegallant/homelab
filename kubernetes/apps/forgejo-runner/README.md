# Forgejo Docker runner

## Current state

The runner is active in the `forgejo-runner` namespace. A read-only check on
2026-10-28 found its Argo CD Application Synced and Healthy, with the runner and
DinD containers Running on `k8s-w-2`. The pod does not use Kubernetes
`hostNetwork`; the Forgejo Runner configuration sets Docker job containers to
`network: host`, which shares the runner pod's network namespace. This is not
the Talos node's host network.

The live namespace still has Pod Security `enforce`, `audit`, and `warn` all
set to `privileged`. The live runner and DinD containers are both privileged:
the upstream chart applies one `securityContext` value to both containers.
`runner.config.file.container.privileged: false` applies to nested job
containers and does not make the runner or DinD containers unprivileged.

The live runner service account cannot read Secrets, list Pods, or create Pods.
Its token is currently mounted automatically, though, and can be disabled with
`serviceAccount.automount: false`. The `forgejo-runner-config` Secret exists;
its contents have not been read. Its Forgejo registration scope (repository,
organization, user, or instance) is therefore not established here.

The Forgejo Cilium policy allows runner-namespace ingress to Forgejo on TCP
3000. No Cilium policy currently selects runner pods, so their egress is
unrestricted. The local policy manifest narrows egress to cluster DNS, Forgejo
on TCP 3000, and public IPv4 TCP 80/443, excluding private, loopback,
link-local, and shared-address ranges. The runner namespace labels, service
account setting, resource bounds, concurrency cap, and egress policy in Git
are pending manual Argo CD sync; none of those edits has been applied live.

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
2. Confirm one runner job at a time, the intended resource bounds, and no
   mounted service-account token.
3. Use Hubble to confirm DNS, Forgejo polling, checkout, and required public
   web traffic are allowed; confirm access to the Kubernetes API, NAS, node
   management addresses, and unrelated private services is denied.
4. Run a real trusted Docker workflow and verify checkout and job completion.
   Runner registration alone does not prove job networking works.
5. Confirm in Forgejo that the runner is registered only at the intended
   trusted scope, and review all workflow triggers and job secrets before
   treating this runner as safe for untrusted contributions.

Do not sync the policy or runner values until the rendered Argo diff has been
reviewed. Do not rotate the registration credential or change its scope as part
of this work without an explicit recovery plan.
