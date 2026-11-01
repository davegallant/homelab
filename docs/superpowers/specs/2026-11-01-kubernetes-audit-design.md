# Kubernetes API Audit Design

## Intent

Keep security-relevant API audit metadata searchable in Loki while stopping
routine controller reads from filling the control-plane audit file. Audit
request and response bodies remain excluded.

## Approaches

- Keep the current all-request file policy and add a hostPath collector. This
  retains the firehose and requires a new hostPath exception; reject it.
- Send the current firehose to Loki over an audit webhook. This adds a new
  synchronous API dependency and preserves the excessive volume; reject it.
- Filter at the API server and send its audit stream to stdout for the existing
  Alloy pod-log pipeline. Choose this because it avoids new host access and
  ships only reviewed metadata.

## Design and constraints

Configure Talos's dedicated `KubeAuditPolicyConfig` and `KubeAPIServerConfig`
documents with ordered Metadata/None audit rules. Keep
human/admin requests, all mutations, Secret and ConfigMap access, RBAC and
admission objects, and pod/node access subresources. Omit health/metrics URLs
and routine read/watch requests from Kubernetes controller groups. Omit the
RequestReceived stage. Set the audit log path to stdout so Alloy's existing
Kubernetes pod-log source forwards records to Loki. Keep the existing Alloy
Restricted namespace and network policy. Preserve existing local audit files;
do not delete historical records as part of this change.

## Risks and verification

There is one control-plane node, so applying the audit configuration can briefly
interrupt Kubernetes API access. Validate the generated Talos machine config
before applying; after the API server returns, confirm readiness, audit metrics,
and a harmless denied request in Loki. Check that sampled audit lines contain
metadata only and that the local audit file stops growing. If any gate fails,
stop without continuing to another change.
