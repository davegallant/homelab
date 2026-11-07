# Gaswatch

Gaswatch checks GasBuddy hourly at minute 17 UTC in the `argo-workflows`
namespace. The CronWorkflow currently remains suspended pending the state and
credential handoff. It runs Python 3.13 with the pinned dependencies from the
private Forgejo repository and commits source revision
`10ab68cbd02d3ab8d94a45f2032d30d8bfe0769c`.

The `gaswatch-state` local-path PVC stores `gaswatch-state.json` and the
GasBuddy token cache. Its PV is pinned to one worker and marked
`volumeType: local` for Velero filesystem backup. The Argo Workflows daily
schedule includes the namespace at 02:55 UTC, excludes Kubernetes Secrets, and
retains backups for 14 days. Workflow failures use the namespace-wide Argo
Gotify exit handler; price alerts use the existing RFD Gotify token.

The Vault bridge expects `gaswatch_location`, `gaswatch_latitude`,
`gaswatch_longitude`, `gaswatch_radius_km`, `gaswatch_fuel_grade`,
`gaswatch_max_price_age_hours`, `gaswatch_favourite_station_ids`, and the
existing `rfd_rising_deals_gotify_token`. Add the read-only repository token as
`gaswatch_forgejo_read_token`. Provision the two Kubernetes Secrets with:

```sh
just run talos-cluster/gitops-secrets --tags gaswatch-secrets
```

## Cutover

1. Confirm the Vault settings match the current Forgejo Actions configuration.
2. Stop the Forgejo hourly schedule and wait for any active run to finish.
3. Provision both Secrets and sync the Gaswatch Argo CD Application while its
   CronWorkflow remains suspended.
4. Copy the final `gaswatch-state.json` from the Gaswatch repo into the
   `gaswatch-state` PVC, preserving it byte-for-byte. Do not remove the tracked
   copy until a successful Argo run and a Velero backup are verified.
5. Unsuspend the CronWorkflow, verify one successful run and the state/cache
   files, then verify that a Velero backup contains the PVC data.
6. Remove the tracked state file from the Gaswatch repository after cutover is
   accepted.

To roll back, suspend Argo first, copy the PVC state back to the repository,
then restore the Forgejo schedule. Do not run both schedulers against the same
state concurrently.
