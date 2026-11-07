# Argo Workflows

The controller runs workflows only in the `argo-workflows` namespace. The UI
is available through the tailnet gateway at
https://argo-workflows.tail.davegallant.ca and uses client-token authentication.
Create a short-lived login token with `kubectl -n argo-workflows create token
argo-workflows-user --duration=1h` and enter it prefixed with `Bearer `.
The user can submit workflows that execute containers in this namespace; treat
the token as an execution credential.

The chart's CRD installer needs cluster-level CRD permissions during sync.
Its controller and server use namespace-scoped roles. Workflow resources live
in etcd, covered by cluster snapshots; no workflow archive or artifact store is
configured. New workflows must specify restricted Pod Security settings,
pinned images, resources, explicit network access, and backup coverage for any
persistent data. The namespace default egress permits DNS and Kubernetes API
access; grant other destinations narrowly for each workload.

The controller applies a default exit handler and sends a Gotify message only
when a workflow ends Failed or Error. Provision its credential from Ansible
Vault with `just run talos-cluster/gitops-secrets --tags
argo-workflows-gotify-secret`. Only the notifier pod has Cilium egress to
Gotify; workflow failure details are omitted from the message.

Provision the namespace from `namespace.yaml` before syncing the Application.
Sync the Application and tailnet-gateway through Argo CD. Verify the controller
and server are Ready, the route is accepted, and the UI and authenticated API
work through the tailnet URL. Recover workflow definitions from Git and etcd
snapshots; see [cluster recovery](../../cluster/README.md).

Gaswatch's `local-path` PVC is covered by the `argo-workflows-daily` Velero
Schedule at 02:55 UTC. The backup includes filesystem data and excludes
Secrets. The Gaswatch runbook documents its state transfer and rollback.
