# RFD rising deals

The CronWorkflow ranks recent Hot Deals by feed upvotes per hour, checks thread
pages, and asks the existing in-cluster LiteLLM proxy to format a digest. It
runs daily at noon America/Toronto, with overlapping runs forbidden. It does
not persist application state. The feed is cached and may lag the forum.

Production runs send the digest to Gotify. The workflow makes one Gotify POST
and does not retry failed runs, because a timeout can leave delivery uncertain
and a retry could send a duplicate. Override `sendGotify` to `false` for a run
that only prints the digest. The chart defaults to a suspended schedule;
production values explicitly enable it.

The namespace-scoped Secrets are provisioned from Vault using the
`rfd-rising-deals-secret` tag of `gitops-secrets.yml`. The shared RFD Gotify
token is stored as `rfd_notify_gotify_token` and is also used by RFD Notify and
Argo Workflows failure notifications; Gaswatch has its own token. The LiteLLM
credential is the existing master key; any workload able to read it has its
privileges. LiteLLM and workflow network policies must be synced before a run.
Allow only reviewed operators to submit workflows or read these Secrets.

Deploy through Argo CD after provisioning the namespace Secrets and syncing
the platform AppProject, Argo Workflows, LiteLLM, and rfd-rising-deals
Applications. To verify a scheduled delivery, inspect the Workflow logs and
compare the five entries with the source feed and thread pages. The local tests
are `python3 -m unittest scripts.tests.test_rfd_rising_deals`.
