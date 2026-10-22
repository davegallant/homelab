# BentoPDF on Talos (Helm)

Migration of the `bento-pdf` LXC Compose stack (BentoPDF + Newt) to the
Talos cluster, packaged as a local Helm chart. Everything is driven by
one playbook:

```sh
ansible-playbook playbooks/talos-cluster/bentopdf.yml -i inventory --vault-password-file .vault_pass
# -e bentopdf_action=verify    re-run in-cluster verification only
# -e bentopdf_action=cutover   -e bentopdf_public_url=https://...   move the Pangolin identity
# -e bentopdf_action=rollback  -e bentopdf_public_url=https://...   back to the LXC
```

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
- **One owner for the Newt identity.** `newt.enabled` defaults to
  `false` (staging). Only the playbook's `cutover` action enables it,
  after stopping the LXC stack and proving no containers remain;
  `rollback` disables it (plus the stale-container prune) before
  restarting the LXC. Never flip it by hand outside those actions.
- **Backups**: the chart's `bentopdf-daily` Velero Schedule (Secrets
  excluded, `defaultVolumesToFsBackup: false`). Manifests-only is the
  *correct* outcome here -- the playbook asserts a completed backup
  with zero PodVolumeBackups, same as SearXNG.
- **Uniform Helm flags.** Every upgrade in bentopdf.yml uses
  `--take-ownership --force-conflicts --server-side=true` -- the
  consistency fix identified in the SearXNG review, applied from
  birth here.

## Before the first run (iteration checklist)

1. Confirm the app port: the chart assumes 8080 (upstream default for
   the pinned 2.8.10 image, nginx-unprivileged). Verify against the
   running LXC container (inspect / `docker compose port` or the
   Pangolin site's target) and the Pangolin target for BentoPDF
   (`bentopdf:8080` or `localhost:8080` both work unchanged in the
   pod). The playbook's port-forward check (`/` returns 200 with
   BentoPDF content) will catch a wrong port at stage time.
2. Confirm the Compose working directory on the `bento-pdf` host is
   `/root` (the playbook's cutover/rollback delegate there, mirroring
   the SearXNG playbook; main.yml installs the stack to
   `~/docker-compose.yml`).
3. Check whether Pangolin SSO protects this site. SearXNG's `/healthz`
   has a Bypass Auth rule; if BentoPDF's root is behind SSO, the
   cutover gate's 200 expectation will see a 302 to the auth portal
   instead -- which also proves the tunnel routes. Reconcile the gate
   with the site's actual posture before cutover, don't just loosen
   it blindly.
4. Sanity-check resource requests in `chart/values.yaml` against
   `docker stats` on the LXC; the shipped values are estimates for a
   static file server.
5. Run `just lint` (with the vault password helper set) and
   `helm lint`/`helm template` on the chart before the first stage
   run.
