# FreshRSS

FreshRSS is served at `https://freshrss.tail.davegallant.ca` through the
tailnet Gateway. The official image starts as root to configure Apache, PHP,
permissions and its refresh cron, then changes Apache workers to `www-data`.
Its namespace therefore uses Pod Security `baseline`; privilege escalation
is disabled and the pod has RuntimeDefault seccomp. Runtime default
capabilities remain enabled so Apache can change worker identity. SQLite and instance data live in the
local-path PVC at `/var/www/FreshRSS/data`, annotated for Velero filesystem
backups.

After the first sync, complete the FreshRSS setup wizard through the tailnet
URL. No administrator password is stored in Git.
