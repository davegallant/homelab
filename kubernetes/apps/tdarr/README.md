# Tdarr

Tdarr runs as an Argo CD application at `https://tdarr.tail.davegallant.ca`.
Its internal CPU worker mounts the same Cinema mergerfs export as Jellyfin,
at `/media`, using a separate read-write NFS claim. Jellyfin's existing claim
remains read-only.

The first deployment does not create a Tdarr library or scan files, and its
internal worker starts paused. Configure the library and processing rules in
the Tdarr UI and unpause the worker only when ready. A lossy re-encode can reduce quality, and completed transcodes
replace the original file; test a few copied files and inspect the results
before processing the live library. The `/temp` transcode cache is ephemeral
and is not a backup of source media.

Tdarr server state is stored on the Velero-backed local PVC. The daily backup
covers that state only; the NFS media share remains outside Velero.

Before syncing, provision the namespace and `tdarr-auth` Secret with
`just run talos-cluster/gitops-secrets`, then apply `storage.yaml`. Sync the
Argo CD Application definitions, sync `tailnet-gateway`, then sync `tdarr`
manually. Headscale DNS resolves the Gateway hostname to `100.100.0.8` after
the VPS playbook applies the tracked config.
