# Gaswatch

Gaswatch checks GasBuddy hourly at minute 17 UTC in the `argo-workflows`
namespace. The CronWorkflow currently remains suspended pending the state and
credential handoff. It runs the Python source and pinned dependencies bundled
in this Helm chart. Argo does not clone or authenticate to Forgejo.

The `gaswatch-state` local-path PVC stores `gaswatch-state.json` and the
GasBuddy token cache. Its PV is pinned to one worker and marked
`volumeType: local` for Velero filesystem backup. The Argo Workflows daily
schedule includes the namespace at 02:55 UTC, excludes Kubernetes Secrets, and
retains backups for 14 days. Workflow failures use the namespace-wide Argo
Gotify exit handler; price alerts use a dedicated Gaswatch Gotify token.

The Vault bridge expects `gaswatch_location`, `gaswatch_latitude`,
`gaswatch_longitude`, `gaswatch_radius_km`, `gaswatch_fuel_grade`,
`gaswatch_max_price_age_hours`, `gaswatch_drop_cpl`,
`gaswatch_drop_lookback_hours`, `gaswatch_hysteresis_cpl`,
`gaswatch_quiet_hours`, `gaswatch_timeout_seconds`,
`gaswatch_favourite_station_ids`, and `gaswatch_gotify_token`. Copy the alert
tuning values and timeout from
the current Forgejo Actions variables; set `gaswatch_quiet_hours` to an empty
string if no quiet window is configured. Use a separate Gotify application
token for Gaswatch; Argo workflow-failure notifications keep their existing
global token. Provision the runtime Secret with:

```sh
just run talos-cluster/gitops-secrets --tags gaswatch-secrets
```

## Cutover

1. Confirm the Vault settings match the current Forgejo Actions configuration.
2. Stop the Forgejo hourly schedule and wait for any active run to finish.
3. Provision the runtime Secret and sync the Gaswatch Argo CD Application while
   its CronWorkflow remains suspended.
4. Copy the final `gaswatch-state.json` from the Gaswatch repo into the
   `gaswatch-state` PVC, preserving it byte-for-byte. Do not remove the tracked
   copy until a successful Argo run and a Velero backup are verified.
5. Unsuspend the CronWorkflow, verify one successful run and the state/cache
   files, then verify that a Velero backup contains the PVC data.
6. Remove the tracked state file from the Gaswatch repository after cutover is
   accepted.
7. Delete the Gaswatch Forgejo repository after confirming the homelab copy
   contains the required source and tests and the Argo schedule is healthy.

To roll back before deleting the Forgejo repo, suspend Argo first, copy the PVC
state back to the repository, then restore the Forgejo schedule. Do not run both
schedulers against the same state concurrently. After repository deletion,
restore the script and requirements from homelab Git and recover state from the
PVC or Velero backup; the old Forgejo scheduler is no longer available.

## Development

The original Gaswatch test suite is kept with this app. Run it from the homelab
repo root with:

```sh
PYTHONPATH=kubernetes/apps/gaswatch/chart/files uv run --no-project \
  --with-requirements kubernetes/apps/gaswatch/requirements-dev.txt \
  --python 3.13 python -m pytest -q kubernetes/apps/gaswatch/tests
```

The alert triggers when the cheapest valid observation is below the recent
lookback high by `GASWATCH_DROP_CPL`; it rearms after a rise of
`GASWATCH_HYSTERESIS_CPL`. Quiet hours defer notifications. Defaults are 4¢/L,
24 hours, and 2¢/L respectively. The GasBuddy token cache and alert history
share the PVC so restarts preserve both.
