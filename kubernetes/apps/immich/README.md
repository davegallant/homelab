# Immich CPU test deployment

Disposable test data only. The production Immich LXC remains authoritative.
There is no gateway route, GPU access, production library mount, or backup
schedule. Do not use this deployment for production data.

The app-template 5.3.0 deployment runs server, machine learning, Valkey,
and Postgres together in a single pod. It requests 875m CPU and 1856Mi
memory, pinned to k8s-w-2 because k8s-w-1 lacked request capacity during
planning. Recheck capacity before sync. This topology has a single failure
domain and cannot scale the server and ML separately. A production decision
must revisit topology, Postgres management and backups, and library storage.

Three local-path claims hold the library, Postgres, and ML model cache; each
must render with `volumeType: local` and provision a local PV. These volumes
are disposable and have no Velero schedule. Postgres is never on NFS.

Create the baseline-labeled namespace and provision `immich-external` with
`ansible/playbooks/talos-cluster/immich-secret.yml`. The playbook derives a
distinct test database password from the Vault credential; changing that Vault
credential requires coordinating the test database password before rerunning
the playbook. Both DB_PASSWORD and POSTGRES_PASSWORD are supplied.

Apply the AppProject destination and Application definition after publishing
the sources. Review the server-side Argo dry run, sync only Immich without
prune or force, and verify PVC annotations and PV types, pod readiness, UI,
test uploads, CPU video transcode, and CPU ML jobs. Cleanup requires a separate
decision. No production cutover is authorized by this test.
