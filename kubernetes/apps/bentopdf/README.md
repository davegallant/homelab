# BentoPDF on Talos (Argo CD)

## Current operations

Argo CD manages the production resources. Follow [release management](../argocd/MANAGEMENT.md)
for updates, external Secrets, and recovery. Use the tracked production values
and Application definition for desired state. Do not run Helm mutations against
resources owned by Argo CD.

## Layout

- `chart/` -- the Helm chart: app Deployment (optional Newt sidecar),
  app Service, the Newt Secret, and the Velero Schedule (into the
  `velero` namespace). Fixed resource names (`bentopdf`,
  `bentopdf-daily`) on purpose -- single-instance internal app, no
  fullname templating. Same shape as the SearXNG chart minus Valkey
  and settings: this app has neither.
- `chart/values.yaml` -- committed defaults; the image is the exact
  version+digest pin from the LXC Compose file. Secret-bearing values
  ship empty and the chart refuses to render them without the bridge
  (`required` on the Newt Secret).
- `values.secrets.yaml.j2` -- Ansible template that injects the Vault
  values (`pangolin_endpoint`, `bentopdf_newt_id`,
  `bentopdf_newt_secret` -- all pre-existing; no new Vault entries)
  as a Helm values file, rendered by the playbook into a protected
  temp dir and deleted after the run. Never commit a rendered copy.

## Design

- **Fully stateless, no PVs, no node pinning.** BentoPDF is a static
  site (all PDF processing happens in the visitor's browser); the
  Compose stack mounts nothing and the chart mirrors that. The
  workload schedules on either worker.
- **Exposure is Pangolin/Newt, not the tailnet.** The Compose stack
  publishes no ports; traffic arrives through the Newt tunnel. In the
  pod, Newt shares the app container's network namespace, so the
  existing Pangolin site keeps working: a target of `bentopdf:8080`
  resolves to the Service and `localhost:8080` reaches the app
  directly. The image's nginx-unprivileged listens on 8080 by
  default (`PORT` env upstream; the Compose stack sets no override).
- **Newt identity:** the production values enable the existing Pangolin
  identity in the pod. Keep its Secret Ansible-managed and out of Git.
- **Backups**: the chart's `bentopdf-daily` Velero Schedule (Secrets
  excluded, `defaultVolumesToFsBackup: false`). Manifests-only is the
  *correct* outcome here -- the playbook asserts a completed backup
  with zero PodVolumeBackups, same as SearXNG.
- **Uniform Helm flags.** Every upgrade in bentopdf.yml uses
  `--take-ownership --force-conflicts --server-side=true` -- the
  consistency fix identified in the SearXNG review, applied from
  birth here.
