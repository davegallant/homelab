# Mealie

Mealie runs on Talos as a single replica using SQLite in `/app/data`. The PVC
uses `local-path` with `volumeType: local`, is Velero-backed by the
`mealie-daily` Schedule, and pins the workload to `k8s-w-1`. Mealie and Newt
share a pod; Pangolin routes to the pod's HTTP service at `127.0.0.1:9000`.

Create a Mealie site in Pangolin and put its ID and secret in Ansible Vault as
`mealie_newt_id` and `mealie_newt_secret`. The shared `pangolin_endpoint` is
used for the endpoint. Run `just run talos-cluster/gitops-secrets` to provision
the namespace and `mealie-newt-external` Secret before syncing the Application.
The Pangolin resource target is HTTP at `127.0.0.1:9000`. The VPS playbook
manages the DNS-only A record and retries Traefik certificate issuance after
the hostname resolves publicly. `BASE_URL` is set to the public HTTPS URL.

The first scheduled Velero backup remains pending until the workload is
running. The schedule excludes Secrets; recreate Newt credentials from Vault.
Verify a Completed backup and a nonzero PodVolumeBackup before considering its
data protected. Read `kubernetes/STORAGE.md` for the required volume and backup
gates.
