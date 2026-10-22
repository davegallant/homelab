# Homepage on Talos (Helm)

Homepage (app + userspace Tailscale sidecar + Caddy) packaged as a local
Helm chart and adopted in place from the original raw-manifest install.
Everything is driven by one playbook:

```sh
ansible-playbook playbooks/talos-cluster/homepage.yml -i inventory --vault-password-file .vault_pass
# (default action is verify: read-only production checks)
# -e homepage_action=rehearse   install the chart into homepage-drill and verify it there
# -e homepage_action=adopt      take Helm ownership of production in place, verify, back up
```

## Layout

- `chart/` -- the Helm chart: the three-container Deployment, Service,
  ServiceAccount, four ConfigMaps (managed config, node proxy, Caddy,
  Tailscale serve config), two Secrets (widget environment, Cloudflare
  token), and the `homepage-daily` Velero Schedule (into the `velero`
  namespace). Fixed resource names on purpose -- single-instance app,
  and the names/selectors must match the pre-Helm objects exactly or
  adoption becomes recreation.
- `chart/values.yaml` -- committed defaults: the exact image pins and
  resource values from the original manifests. Ansible-sourced values
  ship empty and the templates `required`-fail without them.
- `values.ansible.yaml.j2` -- the Vault/group_vars bridge: renders the
  MagicDNS and Headscale domains, the Tailscale hostname, the Cloudflare
  token, all 42 `HOMEPAGE_VAR_*` values, and the rendered
  `config/services.yaml` / `config/settings.yaml` / `proxy-agent.cjs`
  contents as a Helm values file. The playbook renders it into a
  protected temp dir (0600) and deletes it after the run. Never commit a
  rendered copy.
- `config/` -- the human-edited Homepage configuration (services,
  settings, icons). Still the source of truth; the bridge renders
  services/settings through Ansible templating exactly as before
  (Homepage's own `{{HOMEPAGE_VAR_*}}` placeholders survive via
  `{% raw %}` blocks in the sources).
- `icons-configmap.yaml.j2` -- the `homepage-icons` ConfigMap, applied by
  the playbook, NOT the chart: the 24 icons are ~660 KiB of binaries,
  and carrying them as Helm values would push the release record past
  the 1 MiB object limit.
- `storage.yaml` -- the StorageClass and the three static PVs/PVCs.
  Deliberately NOT chart-managed: the chart references the existing
  claims, and the playbook's adopt action asserts every pre-existing
  object (above all the PVCs) keeps its UID across the adoption.
- `tailscale-auth-secret.yaml.j2` + `vars.yaml` -- unchanged from the
  raw-manifest era; the playbook still renders the one-use auth Secret
  when (and only when) no tailnet identity exists yet.

## Design

- **Adopt, never recreate.** `helm upgrade --install --take-ownership
  --force-conflicts --server-side=true` takes ownership of the objects
  `apply-homepage.yml` created. The Deployment selector
  (`app.kubernetes.io/name: homepage`) and pod template labels are
  byte-identical to the original manifest; the only expected pod
  template change is the `checksum/config` annotation value (Helm's
  sha256 of the same concatenated config contents), so exactly one
  rollout is expected. The tailnet identity lives on the
  `homepage-tailscale` PVC and survives it; `TS_AUTH_ONCE` plus the
  persisted state means no new preauth key is needed in the normal case.
- **Prove it by render-diff, then adopt.** The conversion is proven by
  rendering the chart with the real bridge values and diffing against
  the live objects (only Helm ownership metadata and the
  `checksum/config` value may differ) -- not by a drill install: the
  drill namespace's objects are Velero-restored copies, not the
  production objects whose adoption matters, and the drill rig may
  need rebuilding to use at all. A `rehearse` action still exists for
  anyone who wants a full dress rehearsal; it installs into
  `homepage-drill` against the scratch PVs with
  `backup.enabled=false` (the drill must not hijack the production
  `homepage-daily` Schedule) and with NO preauth key: the drill sidecar
  stays logged out, and the playbook asserts it has no tailnet IP, so a
  rehearsal can never register a second `homepage` node. Known side
  effect: the drill Caddy obtains a duplicate certificate for the
  production hostname onto the scratch caddy PVC -- harmless, but
  don't loop rehearsals (Let's Encrypt duplicate-cert limits).
  Verification in the drill is a port-forward + Host header from the
  Mac. Never probe Homepage with Node from inside its own container --
  the proxy-agent preloader hijacks that process's outbound HTTP.
- **Verification is functional, not cosmetic.** Production verify =
  pod Ready + `tailscale ip` + hostname assert + a TLS-verified HTTPS
  request to the dashboard through the tailnet IP (the old
  verify-homepage.yml flow). Adopt additionally triggers a
  `homepage-daily` backup and applies the strict standard: backup
  Completed AND exactly two Completed PodVolumeBackups (config and
  caddy), with `tailscale-state` and ephemeral `caddy-runtime` excluded.
  Restoring `tailscale-state` would clone a live tailnet identity.
- **Backups**: the chart owns the `homepage-daily` Schedule now
  (Secrets excluded and `defaultVolumesToFsBackup: true`). The Deployment pod
  template excludes Tailscale identity state and the disposable Caddy runtime
  emptyDir, leaving only the config and Caddy state PVCs for file system backup.
  Once adoption succeeds, remove the Schedule handling from
  `apply-velero.yml` and retire `apps/velero/schedule.yaml` and
  `apps/velero/homepage-fsb-patch.yaml` -- two managers must not own
  the same Schedule.

## Retiring the old path (after a successful adopt)

Move to Trash (recoverable; git history is the deeper rollback):
`playbooks/talos-cluster/apply-homepage.yml`,
`playbooks/talos-cluster/verify-homepage.yml`, `deployment.yaml.j2`,
`configmap.yaml.j2`, `secrets.yaml.j2`, `namespace.yaml`,
`service.yaml`, `serviceaccount.yaml` (all now chart-owned), plus the
two velero files above. Keep: `storage.yaml`,
`tailscale-auth-secret.yaml.j2`, `vars.yaml`, `config/`,
`proxy-agent.cjs`, `icons-configmap.yaml.j2`,
`values.ansible.yaml.j2`, `chart/`.
