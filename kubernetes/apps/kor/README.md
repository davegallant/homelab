# Kor

Kor scans for potentially unused Kubernetes resources every Monday at 01:00 UTC.
It runs as a read-only CronJob in the dedicated `kor` namespace. Results are
available in the completed Job's pod logs; two successful and two failed Jobs
are retained. Findings require review before any deletion. The service account
can read Secrets cluster-wide as required to detect unused Secrets.

There is no web endpoint, persistent storage, secret, or backup requirement.
The job can access only the Kubernetes API through its Cilium policy. To inspect
a run, list Jobs in `velero` and use `kubectl logs job/<job-name> -n velero`.
To run on demand, create a Job from `cronjob/kor` after deployment. Deploy and
roll back through the manually synced Argo CD application.
