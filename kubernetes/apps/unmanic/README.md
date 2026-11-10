# Unmanic

Unmanic is exposed only over the tailnet at `https://unmanic.tail.davegallant.ca`.
It mounts Cinema's full `/mnt/pool` NFS export read-only at `/mnt`, the same
source mount Jellyfin uses. Movies and TV are visible to Unmanic but cannot be
modified by it. Library scanning and event monitoring stay disabled; only
explicitly submitted files are processed. Mover2 output goes to a separate
writable `/processed` subpath.

The UI and worker run in one container. Library configuration and plugin state
live on a 2 GiB local-path PVC pinned to `k8s-w-1` and are included in the daily
Velero backup. Worker cache is ephemeral, limited to 24 GiB; the container's
ephemeral-storage limit is 26 GiB. Monitor worker disk headroom during large
transcodes. The read-only source PV and writable
output PV both use `Retain` and are not part of Velero backups. The output PV is
mounted only at `/processed/unmanic-processed`; it is not a library path. The
original movie remains in Jellyfin's library, untouched.

Unmanic requests one Intel GPU share and uses Quick Sync for HEVC encoding.
The Intel GPU device plugin allows two containers per worker GPU for batch
transcoding; this can contend with Jellyfin's real-time transcodes.

No credentials or external Secrets are required. The pod runs as UID/GID 1000,
with a restricted security context and a Cilium policy allowing only tailnet
Gateway ingress, cluster DNS, and NFS to `192.168.1.83:2049`.

## Safe transcode and cutover

Unmanic's postprocessor can replace its input, and the media pool has no
verified restore copy. The full pool is therefore mounted read-only at `/mnt`.
Set the Unmanic library root to `/mnt`, with scanning and event monitoring off.
Do not add a writable media mount or configure `/processed` as a library.

The flow uses Unmanic's Mover2 file-movement plugin to send completed outputs
to `/processed`; keep “Remove source files” and “Force processing of all files”
off. The input mount is read-only so a Mover2/plugin failure cannot replace the
input. The output path is a separate writable NFS subdirectory, and it is not
configured as an Unmanic library.

Unmanic can queue a specific file through its API (`/api/v2/pending/test` to
check eligibility, `/api/v2/pending/create` to queue it), so keep scanning and
event monitoring off and submit only selected files. Mover2 does not check the
output checksum and Unmanic may replace an existing destination; clear or use a
unique review destination before retrying the same file.

Submit only the selected absolute source path through Unmanic's API. For each
result under `/processed`, use `scripts/media-cutover.py` from an environment
with `ffmpeg`, `ffprobe`, and both files available:

1. Run `python3 scripts/media-cutover.py validate ORIGINAL CANDIDATE --report
   CANDIDATE.validation.json`. Validation requires HEVC video, matching stream
   counts and non-video track metadata, unchanged resolution/color/frame rate,
   duration within one second, at least 10% size reduction, and a successful
   full video/audio decode. It writes hashes to the report. A passing report
   still requires visual playback review; it cannot prove subjective quality.
2. After review, run `python3 scripts/media-cutover.py promote ORIGINAL
   CANDIDATE --report CANDIDATE.validation.json --backup ORIGINAL.pre-hevc`.
   Promotion rechecks both hashes, refuses hard-linked or symlinked originals,
   creates and verifies a same-directory original backup, then replaces the
   media path. It never overwrites an existing backup. Keep the
   backup through playback and restore checks; clean it up only as a separate,
   deliberate step.

The candidate itself is retained after promotion. This gives rollback material
and means the reported disk savings are not realized until the review copy and
the retained original backup are deliberately removed. No batch or automatic
promotion is configured. Radarr may hardlink torrent data into Movies, so the
promotion helper refuses hard-linked sources; check seeding/library links
before any manual alternative. A disposable same-folder rename test on the
NFS/mergerfs test path succeeded, but the replacing client got one transient
`ESTALE` on its immediate read; later reads from Unmanic and Jellyfin returned
the new content. Keep this as a pilot until a disposable video is tested through
Mover2.

Provision `namespace.yaml` and `storage.yaml`, sync the Argo CD Application,
then sync `tailnet-gateway` and `velero-schedules`. Validate the UI at the
tailnet URL and ensure the library path is `/mnt`. Configure one worker and
submit one file only. Keep library scanning disabled.

To recover settings, restore the `unmanic` Velero backup to a compatible local
volume and schedule the pod onto `k8s-w-1`. Media and processed candidates are
outside Velero. Deleting the app does not remove NFS files because both PVs
have reclaim policy `Retain`.
