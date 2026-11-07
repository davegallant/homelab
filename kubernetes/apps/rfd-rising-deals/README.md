# RFD rising deals proof of concept

This suspended CronWorkflow ranks recent Hot Deals by feed upvotes per hour,
checks thread pages, and asks the existing in-cluster LiteLLM proxy to format a
digest. The schedule is noon America/Toronto, with overlapping runs forbidden.
It does not persist application state. The feed is cached and may lag the forum.

The production values enable Gotify for a manual delivery test, while the
CronWorkflow remains suspended. The job does not retry a Gotify POST, because
a timeout can leave delivery uncertain. Keep the schedule suspended until the
NanoClaw task has been paused and a cutover is approved. Override `sendGotify`
to `false` for a run that only prints the digest.

The namespace-scoped Secrets are provisioned from Vault using the
`rfd-rising-deals-secret` tag of `gitops-secrets.yml`. The Gotify token is the
same app token used by NanoClaw. The LiteLLM credential is the existing master
key; any workload able to read it has its privileges. LiteLLM and workflow
network policies must be synced before a run. Allow only reviewed operators to
submit workflows or read these Secrets.

Deploy by pushing the reviewed changes and syncing the Argo CD, Argo Workflows,
LiteLLM, and rfd-rising-deals Applications. Apply the platform AppProject and
provision the Secrets before syncing the workflow. Run a manual instance of the
suspended CronWorkflow, inspect its logs, and compare the five entries with the
source before enabling the schedule. The local tests are
`python3 -m unittest scripts.tests.test_rfd_rising_deals`.
