# RFD enrichment

The `rfd-enrich` CronWorkflow refreshes RFD data every 15 minutes in the
`argo-workflows` namespace. It runs the pinned `ghcr.io/davegallant/rfd-enricher`
image and uses the in-cluster LiteLLM endpoint with `gpt-6-luna`. The workflow
has no persistent volume; its refresh credentials are provisioned from Ansible
Vault into the namespace Secret `rfd-enrich-runtime-external`.

Failed enrichment attempts are retried up to three times (four attempts total),
within the workflow's 10-minute deadline.

Provision the Secret with `just run talos-cluster/gitops-secrets --tags
rfd-enrich-secrets`. The workflow pod's Cilium policy allows DNS, the RFD API
over HTTPS, and LiteLLM on TCP 4000. Keep the runtime Secret and workflow
submission access limited to trusted operators.

Submit a one-off refresh with `argo submit --from cronwf/rfd-enrich -n
argo-workflows`. Inspect its output with `argo logs <workflow-name> -n
argo-workflows`. Scheduled runs and their history are visible in the Argo
Workflows UI at https://argo-workflows.tail.davegallant.ca.
