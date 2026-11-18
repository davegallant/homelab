# Cilium upgrade runbook

Applies to any Cilium chart-pin change (`applications/cilium.yaml`) or
`values.yaml` change. Cilium is the CNI, the Gateway API front door
(192.168.1.185:443 via Envoy), the L2 announcer, and policy enforcement:
every node restart and every front-door flap rides on this rollout.
Read the whole runbook before syncing. Gates halt and preserve: on any
abort criterion, stop, capture state, and decide from evidence — do not
delete pods, force-sync, or re-sync blindly.

## History

- 2026-10-28: 1.20.4 broke Envoy xDS (no 443 listener); rolled back to
  1.20.3. Fix: `envoy.xdsMode: split` pinned explicitly in values.yaml.
  Never remove that pin; the 1.20.4+ chart renders no xDS mode when unset.
- 2026-11-17: 1.20.5 rollout stuck one node (k8s-w-1) in Init for 4+
  minutes; the 443 listener was dead for the whole hang, then recovered
  on its own. Root cause of the hang was never captured (events expired).
  This runbook's abort step requires capturing state first.

## Gate 0 — before merging

1. Render-diff the chart: `helm template` with `values.yaml` at the old
   and new chart versions. Confirm:
   - the rendered ConfigMap still has `envoy-xds-mode: "split"`;
   - no CRD changes (the chart ships no `crds/` dir — if one appears,
     stop and review separately);
   - `maxUnavailable: 1` still set on both DaemonSets (agent and Envoy);
   - the diff is version/digest bumps plus expected fixes only.
2. Skim the release notes for Gateway API, L2 announcer, xDS/Envoy, and
   WireGuard items.
3. Confirm kubectl works from your machine and no other cluster work is
   in flight. Confirm the previous chart version (rollback target) and
   that the PR touches only the two pins (`applications/cilium.yaml`
   targetRevision and the recovery-only `vars.yaml` pin) plus values
   changes you intend.
4. Expect a front-door flap: while the node holding the 192.168.1.185
   lease restarts its Envoy, Gateway routes go dark. One node at a time,
   minutes total. Do not start an upgrade you cannot watch to completion.

## Gate 1 — merge, then parent sync first

1. Merge the PR.
2. Sync the parent `argocd` app FIRST and let it finish. The parent owns
   the Application objects; the live cilium Application keeps the old
   pin until the parent sync lands.
3. Confirm the cilium app now shows OutOfSync against the new pin.
   Syncing the child before the parent finishes reconciles to the stale
   spec and succeeds as a no-op (2026-11-17).

## Gate 2 — child sync and rollout watch

1. Sync the `cilium` app: manual sync, no pruning, no force.
2. Watch the rollout node by node:

   ```sh
   kubectl -n cilium-system get pods -o wide -w
   ```

   Expected: one node at a time (`maxUnavailable: 1`); the agent and
   Envoy pods on that node restart; the operator, Hubble relay, and
   Hubble UI restart once. The 443 listener flaps while the lease
   holder's Envoy is down.

3. Abort criteria — halt and preserve on ANY of:
   - an agent pod stuck in Init, ContainerCreating, or CrashLoopBackOff
     for more than 10 minutes;
   - a node whose new agent is not Ready 10 minutes after its turn
     started;
   - 192.168.1.185:443 dead more than 10 minutes after all agents report
     Ready;
   - an agent's PolicyEnforcement value is not `default` after rollout.
4. On abort: capture state BEFORE touching anything:

   ```sh
   kubectl -n cilium-system describe pod <stuck-pod>
   kubectl -n cilium-system get events --sort-by=.lastTimestamp | tail -40
   kubectl -n cilium-system logs <stuck-pod> --all-containers
   kubectl get lease -A | grep -iE 'l2|cilium'
   ```

   Then decide rollback vs. wait from that evidence. Do not delete
   pods: the DaemonSet recreates the same new pod.

## Rollback

1. Revert the two pins to the previous version in a commit to main
   (`applications/cilium.yaml` targetRevision and `vars.yaml`).
2. Sync the parent `argocd` app, let it finish, then sync `cilium`.
   Watch Gate 2 the same way.
3. If the Argo UI is unreachable, trigger the sync directly (proven
   2026-10-28):

   ```sh
   kubectl -n argocd patch application cilium --type=merge \
     -p '{"operation":{"sync":{}}}'
   ```

   Never `helm upgrade` the Cilium release: Argo owns the resources via
   server-side apply and Helm cannot adopt them (proven 2026-10-28).
4. The bootstrap playbook (`cilium.yml`, steady + recovery) is the
   last-resort path only when Argo itself is unavailable. See README.

## Gate 3 — post-checks before calling it done

- All agents and Envoys Ready on the new image:

  ```sh
  kubectl -n cilium-system get daemonset cilium -o jsonpath='agent: {.spec.template.spec.containers[0].image}{"\n"}'
  kubectl -n cilium-system get daemonset cilium-envoy -o jsonpath='envoy: {.spec.template.spec.containers[0].image}{"\n"}'
  kubectl -n cilium-system get pods -o wide
  ```

- Operator Ready; Hubble relay and UI Running.
- The 443 listener answers:

  ```sh
  curl -sk -o /dev/null -w '%{http_code}\n' https://192.168.1.185:443/
  ```

  Any HTTP status proves the listener is back; `000` means it is still
  down.
- A Gateway app loads (Homepage, Grafana).
- GatewayClass accepted and Gateway API CRDs present (after any
  Gateway-relevant change). A ConfigMap-only change may leave the
  operator unchanged; restart the operator rollout if Gateway
  controller behavior looks stale (see README).
- Running agent PolicyEnforcement is `default`, not `never` (check the
  agent's effective config, not just the ConfigMap — see README).
- Cross-node pod traffic works (a flow between pods on different
  nodes); Hubble shows flows.
