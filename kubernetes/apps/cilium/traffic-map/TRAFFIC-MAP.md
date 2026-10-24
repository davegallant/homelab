# Kubernetes workload traffic map

## Cross-node answer

Workload-to-workload traffic includes **0 cross-node** and **14,543 same-node** events. Workload-to-platform pod traffic includes 32,235 cross-node and 7,219 same-node events. Hubble recorded 294,252 total events (268,792 forwarded, 25,460 dropped); 76,805 were platform-only and 217,447 involved a workload endpoint and a platform/host endpoint. These are event counts, not unique connections; Hubble may emit several observations for a packet/flow.

## Capture and limits

- Capture file: [`hubble-flows-20261024T2226Z.jsonl.gz`](hubble-flows-20261024T2226Z.jsonl.gz) (gzip-compressed JSONL from `hubble --port-forward --kube-namespace cilium-system observe --follow --all-namespaces --output json --print-node-name`; no verdict filter).
- Capture event times: `2026-10-24T22:26:19.393085795Z` through `2026-10-24T22:56:36.006150735Z` (30 minutes 16.6 seconds between first and last events). Hubble Relay was healthy with 3/3 nodes connected when the capture began.
- Pod placement was joined by endpoint IP against the inventories saved at capture start and end. Host endpoint IPs were mapped to nodes using the saved CiliumNode address inventory. Non-pod source IPs are retained in parentheses; events without a pod identity are not assigned to a workload.
- A 30-minute sample misses infrequent and scheduled traffic, including hourly RSS syncs and nightly jobs. This is a sample map, not a complete inventory.
- Reply events are folded into their initiating source→destination direction; the port is the destination service port. Counts below are captured Hubble events grouped by endpoints, port, protocol, verdict, and drop reason, not unique connections.
- The table includes platform and workload traffic. The flat diagram omits platform-only traffic (DNS, monitoring scrapes, Cilium/Hubble and controller traffic) to keep workload edges legible; the source capture and table retain those observations.

## Flow table

The complete aggregate has 1,320 rows in the compressed CSV table. The Markdown preview below shows the 100 most frequent; every dropped event and reason remains in the full table.

- [Complete aggregated flow table (CSV, gzip)](FLOW-TABLE.csv.gz)

| Source pod / namespace / node (endpoint IP if not a pod) | Destination pod / namespace / IP / node | Port | Protocol | Events | Verdict | Drop reason | Placement |
|---|---|---:|---|---:|---|---|---|
| `host/host (10.245.1.169)` / `k8s-w-2` | `paperless-ngx/paperless-ngx-6c49ccfb5b-z96fh` / `10.245.1.131` / `k8s-w-2` | 8000 | tcp | 4,194 | FORWARDED | — | not pod-to-pod |
| `invidious/invidious-79f79999cb-m7h45` / `k8s-w-1` | `kube-system/coredns-58854787cc-2gsdj` / `10.245.0.167` / `k8s-cp-1` | 53 | udp | 4,030 | FORWARDED | — | cross-node |
| `argocd/argocd-application-controller-0` / `k8s-cp-1` | `kube-system/coredns-58854787cc-fhvnk` / `10.245.1.126` / `k8s-w-2` | 53 | udp | 3,853 | FORWARDED | — | cross-node |
| `host/host (10.245.2.92)` / `k8s-w-1` | `prowlarr/prowlarr-75d9d4b55-vk4m7` / `10.245.2.86` / `k8s-w-1` | 9696 | tcp | 3,714 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `sonarr/sonarr-cc778df89-44fjp` / `10.245.2.118` / `k8s-w-1` | 8989 | tcp | 3,710 | FORWARDED | — | not pod-to-pod |
| `invidious/invidious-79f79999cb-m7h45` / `k8s-w-1` | `kube-system/coredns-58854787cc-fhvnk` / `10.245.1.126` / `k8s-w-2` | 53 | udp | 3,705 | FORWARDED | — | cross-node |
| `host/host (10.245.2.92)` / `k8s-w-1` | `lidarr/lidarr-7b45c964b-8xjfq` / `10.245.2.225` / `k8s-w-1` | 8686 | tcp | 3,697 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `radarr/radarr-55595558c-vqdmf` / `10.245.2.85` / `k8s-w-1` | 7878 | tcp | 3,696 | FORWARDED | — | not pod-to-pod |
| `navidrome/navidrome-7784c894b6-6x92z` / `k8s-w-2` | `kube-system/coredns-58854787cc-2gsdj` / `10.245.0.167` / `k8s-cp-1` | 53 | udp | 3,607 | FORWARDED | — | cross-node |
| `paperless-ngx/paperless-ngx-6c49ccfb5b-z96fh` / `k8s-w-2` | `kube-system/coredns-58854787cc-2gsdj` / `10.245.0.167` / `k8s-cp-1` | 53 | udp | 3,573 | FORWARDED | — | cross-node |
| `—/unknown (169.254.42.1)` / `—` | `navidrome/navidrome-7784c894b6-6x92z` / `10.245.1.191` / `k8s-w-2` | 4533 | tcp | 3,408 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `invidious/invidious-79f79999cb-m7h45` / `10.245.2.99` / `k8s-w-1` | 3000 | tcp | 3,335 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.0.125)` / `k8s-cp-1` | `cilium-system/hubble-ui-5c9c65987-vb4lb` / `10.245.0.197` / `k8s-cp-1` | 8081 | tcp | 3,304 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `argocd/argocd-server-6db89f9768-9qgr2` / `10.245.2.246` / `k8s-w-1` | 8080 | tcp | 3,301 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.0.125)` / `k8s-cp-1` | `argocd/argocd-repo-server-7b956fcd68-5tr56` / `10.245.0.8` / `k8s-cp-1` | 8084 | tcp | 3,283 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.0.125)` / `k8s-cp-1` | `cilium-system/hubble-relay-565bdb4485-fdj8l` / `10.245.0.228` / `k8s-cp-1` | 4222 | tcp | 3,168 | FORWARDED | — | not pod-to-pod |
| `—/unknown (169.254.42.1)` / `—` | `paperless-ngx/paperless-ngx-6c49ccfb5b-z96fh` / `10.245.1.131` / `k8s-w-2` | 8000 | tcp | 3,136 | FORWARDED | — | not pod-to-pod |
| `—/unknown (169.254.42.1)` / `—` | `invidious/invidious-79f79999cb-m7h45` / `10.245.2.99` / `k8s-w-1` | 3000 | tcp | 3,114 | FORWARDED | — | not pod-to-pod |
| `paperless-ngx/paperless-ngx-6c49ccfb5b-z96fh` / `k8s-w-2` | `paperless-ngx/paperless-ngx-6c49ccfb5b-z96fh` / `10.245.1.131` / `k8s-w-2` | 8000 | tcp | 2,905 | FORWARDED | — | same-node |
| `host/host (10.245.1.169)` / `k8s-w-2` | `kube-system/metrics-server-76f6c7c7b6-vkqqh` / `10.245.1.114` / `k8s-w-2` | 10250 | tcp | 2,674 | FORWARDED | — | not pod-to-pod |
| `navidrome/navidrome-7784c894b6-6x92z` / `k8s-w-2` | `navidrome/navidrome-7784c894b6-6x92z` / `10.245.1.191` / `k8s-w-2` | 4533 | tcp | 2,647 | FORWARDED | — | same-node |
| `argocd/argocd-application-controller-0` / `k8s-cp-1` | `argocd/argocd-repo-server-7b956fcd68-5tr56` / `10.245.0.8` / `k8s-cp-1` | 8081 | tcp | 2,350 | FORWARDED | — | same-node |
| `—/unknown (169.254.42.1)` / `—` | `bentopdf/bentopdf-58c84696cc-bpj8t` / `10.245.1.214` / `k8s-w-2` | 8080 | tcp | 2,291 | FORWARDED | — | not pod-to-pod |
| `argocd/argocd-application-controller-0` / `k8s-cp-1` | `kube-system/coredns-58854787cc-2gsdj` / `10.245.0.167` / `k8s-cp-1` | 53 | udp | 2,240 | FORWARDED | — | same-node |
| `audiobookshelf/audiobookshelf-7ffbf68d98-h5k6h` / `k8s-w-1` | `kube-system/coredns-58854787cc-2gsdj` / `10.245.0.167` / `k8s-cp-1` | 53 | udp | 2,228 | FORWARDED | — | cross-node |
| `host/host (10.245.1.169)` / `k8s-w-2` | `alloy/alloy-cv6wg` / `10.245.1.209` / `k8s-w-2` | 12345 | tcp | 2,197 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `alloy/alloy-sdtfx` / `10.245.2.51` / `k8s-w-1` | 12345 | tcp | 2,195 | FORWARDED | — | not pod-to-pod |
| `paperless-ngx/paperless-ngx-6c49ccfb5b-z96fh` / `k8s-w-2` | `kube-system/coredns-58854787cc-fhvnk` / `10.245.1.126` / `k8s-w-2` | 53 | udp | 2,192 | FORWARDED | — | same-node |
| `host/host (10.245.2.92)` / `k8s-w-1` | `kiwix/kiwix-d9d58c8d4-vtcnx` / `10.245.2.18` / `k8s-w-1` | 8080 | tcp | 2,189 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.0.125)` / `k8s-cp-1` | `alloy/alloy-j8m77` / `10.245.0.185` / `k8s-cp-1` | 12345 | tcp | 2,187 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `romm/romm-5d775db57f-6lsxd` / `10.245.2.30` / `k8s-w-1` | 8080 | tcp | 2,187 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.1.169)` / `k8s-w-2` | `lubelogger/lubelogger-58d8f56f67-lgtjm` / `10.245.1.184` / `k8s-w-2` | 8080 | tcp | 2,182 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.1.169)` / `k8s-w-2` | `seerr/seerr-5bc6f4466d-t5g8x` / `10.245.1.58` / `k8s-w-2` | 5055 | tcp | 2,182 | FORWARDED | — | not pod-to-pod |
| `navidrome/navidrome-7784c894b6-6x92z` / `k8s-w-2` | `kube-system/coredns-58854787cc-fhvnk` / `10.245.1.126` / `k8s-w-2` | 53 | udp | 2,182 | FORWARDED | — | same-node |
| `umami/umami-865c4f696d-gdngv` / `k8s-w-1` | `kube-system/coredns-58854787cc-fhvnk` / `10.245.1.126` / `k8s-w-2` | 53 | udp | 2,168 | FORWARDED | — | cross-node |
| `host/host (10.245.2.92)` / `k8s-w-1` | `miniflux/miniflux-577f9dd8d-r9pjx` / `10.245.2.223` / `k8s-w-1` | 8080 | tcp | 2,106 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `audiobookshelf/audiobookshelf-7ffbf68d98-h5k6h` / `10.245.2.127` / `k8s-w-1` | 80 | tcp | 2,105 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `umami/umami-865c4f696d-gdngv` / `10.245.2.109` / `k8s-w-1` | 3000 | tcp | 2,105 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.1.169)` / `k8s-w-2` | `navidrome/navidrome-7784c894b6-6x92z` / `10.245.1.191` / `k8s-w-2` | 4533 | tcp | 2,081 | FORWARDED | — | not pod-to-pod |
| `invidious/invidious-79f79999cb-m7h45` / `k8s-w-1` | `invidious/invidious-79f79999cb-m7h45` / `10.245.2.99` / `k8s-w-1` | 3000 | tcp | 2,080 | FORWARDED | — | same-node |
| `umami/umami-865c4f696d-gdngv` / `k8s-w-1` | `kube-system/coredns-58854787cc-2gsdj` / `10.245.0.167` / `k8s-cp-1` | 53 | udp | 2,059 | FORWARDED | — | cross-node |
| `—/unknown (169.254.42.1)` / `—` | `umami/umami-865c4f696d-gdngv` / `10.245.2.109` / `k8s-w-1` | 3000 | tcp | 2,030 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.1.169)` / `k8s-w-2` | `searxng/searxng-59cdbdd555-tn2tl` / `10.245.1.4` / `k8s-w-2` | 8080 | tcp | 2,001 | FORWARDED | — | not pod-to-pod |
| `audiobookshelf/audiobookshelf-7ffbf68d98-h5k6h` / `k8s-w-1` | `kube-system/coredns-58854787cc-fhvnk` / `10.245.1.126` / `k8s-w-2` | 53 | udp | 1,996 | FORWARDED | — | cross-node |
| `miniflux/miniflux-577f9dd8d-r9pjx` / `k8s-w-1` | `kube-system/coredns-58854787cc-2gsdj` / `10.245.0.167` / `k8s-cp-1` | 53 | udp | 1,882 | FORWARDED | — | cross-node |
| `host/host (10.245.1.169)` / `k8s-w-2` | `bentopdf/bentopdf-58c84696cc-bpj8t` / `10.245.1.214` / `k8s-w-2` | 8080 | tcp | 1,825 | FORWARDED | — | not pod-to-pod |
| `bentopdf/bentopdf-58c84696cc-bpj8t` / `k8s-w-2` | `kube-system/coredns-58854787cc-2gsdj` / `10.245.0.167` / `k8s-cp-1` | 53 | udp | 1,810 | FORWARDED | — | cross-node |
| `miniflux/miniflux-577f9dd8d-r9pjx` / `k8s-w-1` | `kube-system/coredns-58854787cc-fhvnk` / `10.245.1.126` / `k8s-w-2` | 53 | udp | 1,788 | FORWARDED | — | cross-node |
| `host/host (10.245.2.92)` / `k8s-w-1` | `speedtest-tracker/speedtest-tracker-5869d7b77-p5vpb` / `10.245.2.155` / `k8s-w-1` | 80 | tcp | 1,779 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `homepage/homepage-84996664c-gpj89` / `10.245.2.233` / `k8s-w-1` | 3000 | tcp | 1,774 | FORWARDED | — | not pod-to-pod |
| `searxng/searxng-59cdbdd555-tn2tl` / `k8s-w-2` | `kube-system/coredns-58854787cc-2gsdj` / `10.245.0.167` / `k8s-cp-1` | 53 | udp | 1,759 | FORWARDED | — | cross-node |
| `host/host (10.245.2.92)` / `k8s-w-1` | `maloja/maloja-7b87fc7cf9-vx9m8` / `10.245.2.168` / `k8s-w-1` | 42010 | tcp | 1,735 | FORWARDED | — | not pod-to-pod |
| `—/unknown (169.254.42.1)` / `—` | `miniflux/miniflux-577f9dd8d-r9pjx` / `10.245.2.223` / `k8s-w-1` | 8080 | tcp | 1,715 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.1.169)` / `k8s-w-2` | `changedetection/changedetection-bb8d64ff7-zt2cv` / `10.245.1.134` / `k8s-w-2` | 5000 | tcp | 1,707 | FORWARDED | — | not pod-to-pod |
| `—/unknown (169.254.42.1)` / `—` | `audiobookshelf/audiobookshelf-7ffbf68d98-h5k6h` / `10.245.2.127` / `k8s-w-1` | 80 | tcp | 1,707 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `prowlarr/prowlarr-75d9d4b55-vk4m7` / `10.245.2.86` / `k8s-w-1` | 8191 | tcp | 1,701 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `speedtest-tracker/speedtest-tracker-5869d7b77-p5vpb` / `10.245.2.155` / `k8s-w-1` | 5432 | tcp | 1,701 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `speedtest-tracker/speedtest-tracker-5869d7b77-p5vpb` / `10.245.2.155` / `k8s-w-1` | 8000 | tcp | 1,701 | FORWARDED | — | not pod-to-pod |
| `argocd/argocd-server-6db89f9768-9qgr2` / `k8s-w-1` | `argocd/argocd-redis-68444c4c6-fqxbq` / `10.245.1.154` / `k8s-w-2` | 6379 | tcp | 1,696 | FORWARDED | — | cross-node |
| `host/host (10.245.1.169)` / `k8s-w-2` | `searxng/valkey-74fdbcc587-frhck` / `10.245.1.185` / `k8s-w-2` | 6379 | tcp | 1,694 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `invidious/invidious-79f79999cb-m7h45` / `10.245.2.99` / `k8s-w-1` | 8282 | tcp | 1,682 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `invidious/invidious-79f79999cb-m7h45` / `10.245.2.99` / `k8s-w-1` | 5432 | tcp | 1,670 | FORWARDED | — | not pod-to-pod |
| `—/unknown (169.254.42.1)` / `—` | `searxng/searxng-59cdbdd555-tn2tl` / `10.245.1.4` / `k8s-w-2` | 8080 | tcp | 1,666 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.0.125)` / `k8s-cp-1` | `argocd/argocd-application-controller-0` / `10.245.0.63` / `k8s-cp-1` | 8082 | tcp | 1,651 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.1.169)` / `k8s-w-2` | `monitoring/kube-state-metrics-68d86ff87-dk4zj` / `10.245.1.140` / `k8s-w-2` | 8080 | tcp | 1,643 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.1.169)` / `k8s-w-2` | `monitoring/kube-state-metrics-68d86ff87-dk4zj` / `10.245.1.140` / `k8s-w-2` | 8081 | tcp | 1,642 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `romm/romm-5d775db57f-6lsxd` / `10.245.2.30` / `k8s-w-1` | 3306 | tcp | 1,629 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `umami/umami-865c4f696d-gdngv` / `10.245.2.109` / `k8s-w-1` | 5432 | tcp | 1,596 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.1.169)` / `k8s-w-2` | `paperless-ngx/paperless-ngx-6c49ccfb5b-z96fh` / `10.245.1.131` / `k8s-w-2` | 6379 | tcp | 1,579 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.0.125)` / `k8s-cp-1` | `kube-system/coredns-58854787cc-2gsdj` / `10.245.0.167` / `k8s-cp-1` | 8181 | tcp | 1,468 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.1.169)` / `k8s-w-2` | `kube-system/coredns-58854787cc-fhvnk` / `10.245.1.126` / `k8s-w-2` | 8080 | tcp | 1,459 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.0.125)` / `k8s-cp-1` | `kube-system/coredns-58854787cc-2gsdj` / `10.245.0.167` / `k8s-cp-1` | 8080 | tcp | 1,458 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.1.169)` / `k8s-w-2` | `kube-system/coredns-58854787cc-fhvnk` / `10.245.1.126` / `k8s-w-2` | 8181 | tcp | 1,457 | FORWARDED | — | not pod-to-pod |
| `miniflux/miniflux-577f9dd8d-r9pjx` / `k8s-w-1` | `miniflux/miniflux-577f9dd8d-r9pjx` / `10.245.2.223` / `k8s-w-1` | 8080 | tcp | 1,444 | FORWARDED | — | same-node |
| `umami/umami-865c4f696d-gdngv` / `k8s-w-1` | `umami/umami-865c4f696d-gdngv` / `10.245.2.109` / `k8s-w-1` | 3000 | tcp | 1,251 | FORWARDED | — | same-node |
| `lidarr/lidarr-7b45c964b-8xjfq` / `k8s-w-1` | `—/world (192.168.1.52)` / `192.168.1.52` / `—` | 41641 | udp | 1,212 | DROPPED | POLICY_DENY | not pod-to-pod |
| `radarr/radarr-55595558c-vqdmf` / `k8s-w-1` | `—/world (192.168.1.52)` / `192.168.1.52` / `—` | 41641 | udp | 1,210 | DROPPED | POLICY_DENY | not pod-to-pod |
| `sonarr/sonarr-cc778df89-44fjp` / `k8s-w-1` | `—/world (192.168.1.52)` / `192.168.1.52` / `—` | 41641 | udp | 1,210 | DROPPED | POLICY_DENY | not pod-to-pod |
| `bentopdf/bentopdf-58c84696cc-bpj8t` / `k8s-w-2` | `bentopdf/bentopdf-58c84696cc-bpj8t` / `10.245.1.214` / `k8s-w-2` | 8080 | tcp | 1,209 | FORWARDED | — | same-node |
| `searxng/searxng-59cdbdd555-tn2tl` / `k8s-w-2` | `searxng/searxng-59cdbdd555-tn2tl` / `10.245.1.4` / `k8s-w-2` | 8080 | tcp | 1,181 | FORWARDED | — | same-node |
| `searxng/searxng-59cdbdd555-tn2tl` / `k8s-w-2` | `kube-system/coredns-58854787cc-fhvnk` / `10.245.1.126` / `k8s-w-2` | 53 | udp | 1,156 | FORWARDED | — | same-node |
| `seerr/seerr-5bc6f4466d-t5g8x` / `k8s-w-2` | `—/world (192.168.1.52)` / `192.168.1.52` / `—` | 41641 | udp | 1,110 | DROPPED | POLICY_DENY | not pod-to-pod |
| `seerr/seerr-5bc6f4466d-t5g8x` / `k8s-w-2` | `—/world (204.244.250.128)` / `204.244.250.128` / `—` | 9930 | udp | 1,110 | DROPPED | POLICY_DENIED | not pod-to-pod |
| `audiobookshelf/audiobookshelf-7ffbf68d98-h5k6h` / `k8s-w-1` | `audiobookshelf/audiobookshelf-7ffbf68d98-h5k6h` / `10.245.2.127` / `k8s-w-1` | 80 | tcp | 1,104 | FORWARDED | — | same-node |
| `bentopdf/bentopdf-58c84696cc-bpj8t` / `k8s-w-2` | `kube-system/coredns-58854787cc-fhvnk` / `10.245.1.126` / `k8s-w-2` | 53 | udp | 1,098 | FORWARDED | — | same-node |
| `—/remote-node (10.245.0.125)` / `—` | `kube-system/metrics-server-76f6c7c7b6-vkqqh` / `10.245.1.114` / `k8s-w-2` | 10250 | tcp | 1,014 | FORWARDED | — | not pod-to-pod |
| `host/host (10.245.2.92)` / `k8s-w-1` | `velero/velero-5946d984b8-8bvrw` / `10.245.2.71` / `k8s-w-1` | 8085 | tcp | 928 | FORWARDED | — | not pod-to-pod |
| `seerr/seerr-5bc6f4466d-t5g8x` / `k8s-w-2` | `—/world (72.11.149.242)` / `72.11.149.242` / `—` | 443 | tcp | 896 | FORWARDED | — | not pod-to-pod |
| `argocd/argocd-application-controller-0` / `k8s-cp-1` | `argocd/argocd-redis-68444c4c6-fqxbq` / `10.245.1.154` / `k8s-w-2` | 6379 | tcp | 819 | FORWARDED | — | cross-node |
| `seerr/seerr-5bc6f4466d-t5g8x` / `k8s-w-2` | `kube-system/coredns-58854787cc-2gsdj` / `10.245.0.167` / `k8s-cp-1` | 53 | udp | 740 | FORWARDED | — | cross-node |
| `cilium-system/hubble-relay-565bdb4485-fdj8l` / `k8s-cp-1` | `monitoring/node-exporter-27k62` / `192.168.1.210` / `k8s-cp-1` | 4244 | tcp | 726 | FORWARDED | — | same-node |
| `seerr/seerr-5bc6f4466d-t5g8x` / `k8s-w-2` | `—/world (204.244.250.128)` / `204.244.250.128` / `—` | 56858 | udp | 716 | DROPPED | POLICY_DENIED | not pod-to-pod |
| `romm/romm-5d775db57f-6lsxd` / `k8s-w-1` | `host/host (10.245.2.92)` / `10.245.2.92` / `k8s-w-1` | 5351 | udp | 640 | DROPPED | POLICY_DENIED | not pod-to-pod |
| `maloja/maloja-7b87fc7cf9-vx9m8` / `k8s-w-1` | `host/host (10.245.2.92)` / `10.245.2.92` / `k8s-w-1` | 5351 | udp | 632 | DROPPED | POLICY_DENIED | not pod-to-pod |
| `seerr/seerr-5bc6f4466d-t5g8x` / `k8s-w-2` | `host/host (10.245.1.169)` / `10.245.1.169` / `k8s-w-2` | 5351 | udp | 632 | DROPPED | POLICY_DENIED | not pod-to-pod |
| `speedtest-tracker/speedtest-tracker-5869d7b77-p5vpb` / `k8s-w-1` | `host/host (10.245.2.92)` / `10.245.2.92` / `k8s-w-1` | 5351 | udp | 632 | DROPPED | POLICY_DENIED | not pod-to-pod |
| `changedetection/changedetection-bb8d64ff7-zt2cv` / `k8s-w-2` | `host/host (10.245.1.169)` / `10.245.1.169` / `k8s-w-2` | 5351 | udp | 624 | DROPPED | POLICY_DENIED | not pod-to-pod |
| `homepage/homepage-84996664c-gpj89` / `k8s-w-1` | `host/host (10.245.2.92)` / `10.245.2.92` / `k8s-w-1` | 5351 | udp | 624 | DROPPED | POLICY_DENIED | not pod-to-pod |
| `lubelogger/lubelogger-58d8f56f67-lgtjm` / `k8s-w-2` | `host/host (10.245.1.169)` / `10.245.1.169` / `k8s-w-2` | 5351 | udp | 624 | DROPPED | POLICY_DENIED | not pod-to-pod |
| `kiwix/kiwix-d9d58c8d4-vtcnx` / `k8s-w-1` | `host/host (10.245.2.92)` / `10.245.2.92` / `k8s-w-1` | 5351 | udp | 620 | DROPPED | POLICY_DENIED | not pod-to-pod |

## Notable observations

Denied or errored captured edges (all remain in the table and are red/dashed in the diagram):
- `lidarr/lidarr-7b45c964b-8xjfq` → `—/world (192.168.1.52)` 41641/udp: 1,212 events, `DROPPED` (POLICY_DENY).
- `sonarr/sonarr-cc778df89-44fjp` → `—/world (192.168.1.52)` 41641/udp: 1,210 events, `DROPPED` (POLICY_DENY).
- `radarr/radarr-55595558c-vqdmf` → `—/world (192.168.1.52)` 41641/udp: 1,210 events, `DROPPED` (POLICY_DENY).
- `seerr/seerr-5bc6f4466d-t5g8x` → `—/world (192.168.1.52)` 41641/udp: 1,110 events, `DROPPED` (POLICY_DENY).
- `seerr/seerr-5bc6f4466d-t5g8x` → `—/world (204.244.250.128)` 9930/udp: 1,110 events, `DROPPED` (POLICY_DENIED).
- `seerr/seerr-5bc6f4466d-t5g8x` → `—/world (204.244.250.128)` 56858/udp: 716 events, `DROPPED` (POLICY_DENIED).
- `romm/romm-5d775db57f-6lsxd` → `host/host (10.245.2.92)` 5351/udp: 640 events, `DROPPED` (POLICY_DENIED).
- `seerr/seerr-5bc6f4466d-t5g8x` → `host/host (10.245.1.169)` 5351/udp: 632 events, `DROPPED` (POLICY_DENIED).
- `maloja/maloja-7b87fc7cf9-vx9m8` → `host/host (10.245.2.92)` 5351/udp: 632 events, `DROPPED` (POLICY_DENIED).
- `speedtest-tracker/speedtest-tracker-5869d7b77-p5vpb` → `host/host (10.245.2.92)` 5351/udp: 632 events, `DROPPED` (POLICY_DENIED).
- `lubelogger/lubelogger-58d8f56f67-lgtjm` → `host/host (10.245.1.169)` 5351/udp: 624 events, `DROPPED` (POLICY_DENIED).
- `changedetection/changedetection-bb8d64ff7-zt2cv` → `host/host (10.245.1.169)` 5351/udp: 624 events, `DROPPED` (POLICY_DENIED).
- `homepage/homepage-84996664c-gpj89` → `host/host (10.245.2.92)` 5351/udp: 624 events, `DROPPED` (POLICY_DENIED).
- `kiwix/kiwix-d9d58c8d4-vtcnx` → `host/host (10.245.2.92)` 5351/udp: 620 events, `DROPPED` (POLICY_DENIED).
- `speedtest-tracker/speedtest-tracker-5869d7b77-p5vpb` → `—/world (192.168.1.52)` 41641/udp: 618 events, `DROPPED` (POLICY_DENY).
- `lubelogger/lubelogger-58d8f56f67-lgtjm` → `—/world (204.244.250.128)` 56858/udp: 614 events, `DROPPED` (POLICY_DENIED).
- `lubelogger/lubelogger-58d8f56f67-lgtjm` → `—/world (192.168.1.52)` 41641/udp: 614 events, `DROPPED` (POLICY_DENY).
- `lubelogger/lubelogger-58d8f56f67-lgtjm` → `—/world (204.244.250.128)` 9930/udp: 614 events, `DROPPED` (POLICY_DENIED).
- `homepage/homepage-84996664c-gpj89` → `—/world (204.244.250.128)` 58910/udp: 606 events, `DROPPED` (POLICY_DENIED).
- `homepage/homepage-84996664c-gpj89` → `—/world (192.168.1.52)` 41641/udp: 606 events, `DROPPED` (POLICY_DENY).
- `homepage/homepage-84996664c-gpj89` → `—/world (204.244.250.128)` 15479/udp: 606 events, `DROPPED` (POLICY_DENIED).
- `maloja/maloja-7b87fc7cf9-vx9m8` → `—/world (204.244.250.128)` 56858/udp: 606 events, `DROPPED` (POLICY_DENIED).
- `maloja/maloja-7b87fc7cf9-vx9m8` → `—/world (192.168.1.52)` 41641/udp: 606 events, `DROPPED` (POLICY_DENY).
- `maloja/maloja-7b87fc7cf9-vx9m8` → `—/world (204.244.250.128)` 9930/udp: 606 events, `DROPPED` (POLICY_DENIED).
- `changedetection/changedetection-bb8d64ff7-zt2cv` → `—/world (192.168.1.52)` 41641/udp: 606 events, `DROPPED` (POLICY_DENY).
- `romm/romm-5d775db57f-6lsxd` → `—/world (192.168.1.52)` 41641/udp: 606 events, `DROPPED` (POLICY_DENY).
- `homepage/homepage-84996664c-gpj89` → `—/world (204.244.250.128)` 9930/udp: 606 events, `DROPPED` (POLICY_DENIED).
- `kiwix/kiwix-d9d58c8d4-vtcnx` → `—/world (204.244.250.128)` 9930/udp: 606 events, `DROPPED` (POLICY_DENIED).
- `kiwix/kiwix-d9d58c8d4-vtcnx` → `—/world (192.168.1.52)` 41641/udp: 606 events, `DROPPED` (POLICY_DENY).
- `prowlarr/prowlarr-75d9d4b55-vk4m7` → `—/world (192.168.1.52)` 41641/udp: 604 events, `DROPPED` (POLICY_DENY).

Workload egress to external or non-pod destinations:
- `lidarr/lidarr-7b45c964b-8xjfq` → `192.168.1.52:41641/udp`: 1,212 events, `DROPPED` (POLICY_DENY).
- `sonarr/sonarr-cc778df89-44fjp` → `192.168.1.52:41641/udp`: 1,210 events, `DROPPED` (POLICY_DENY).
- `radarr/radarr-55595558c-vqdmf` → `192.168.1.52:41641/udp`: 1,210 events, `DROPPED` (POLICY_DENY).
- `seerr/seerr-5bc6f4466d-t5g8x` → `192.168.1.52:41641/udp`: 1,110 events, `DROPPED` (POLICY_DENY).
- `seerr/seerr-5bc6f4466d-t5g8x` → `204.244.250.128:9930/udp`: 1,110 events, `DROPPED` (POLICY_DENIED).
- `seerr/seerr-5bc6f4466d-t5g8x` → `72.11.149.242:443/tcp`: 896 events, `FORWARDED` (—).
- `seerr/seerr-5bc6f4466d-t5g8x` → `204.244.250.128:56858/udp`: 716 events, `DROPPED` (POLICY_DENIED).
- `speedtest-tracker/speedtest-tracker-5869d7b77-p5vpb` → `192.168.1.52:41641/udp`: 618 events, `DROPPED` (POLICY_DENY).
- `lubelogger/lubelogger-58d8f56f67-lgtjm` → `204.244.250.128:56858/udp`: 614 events, `DROPPED` (POLICY_DENIED).
- `lubelogger/lubelogger-58d8f56f67-lgtjm` → `192.168.1.52:41641/udp`: 614 events, `DROPPED` (POLICY_DENY).
- `lubelogger/lubelogger-58d8f56f67-lgtjm` → `204.244.250.128:9930/udp`: 614 events, `DROPPED` (POLICY_DENIED).
- `homepage/homepage-84996664c-gpj89` → `204.244.250.128:58910/udp`: 606 events, `DROPPED` (POLICY_DENIED).
- `homepage/homepage-84996664c-gpj89` → `192.168.1.52:41641/udp`: 606 events, `DROPPED` (POLICY_DENY).
- `homepage/homepage-84996664c-gpj89` → `204.244.250.128:15479/udp`: 606 events, `DROPPED` (POLICY_DENIED).
- `sonarr/sonarr-cc778df89-44fjp` → `192.168.1.152:41641/udp`: 606 events, `FORWARDED` (—).
- `maloja/maloja-7b87fc7cf9-vx9m8` → `204.244.250.128:56858/udp`: 606 events, `DROPPED` (POLICY_DENIED).
- `maloja/maloja-7b87fc7cf9-vx9m8` → `192.168.1.52:41641/udp`: 606 events, `DROPPED` (POLICY_DENY).
- `maloja/maloja-7b87fc7cf9-vx9m8` → `204.244.250.128:9930/udp`: 606 events, `DROPPED` (POLICY_DENIED).
- `changedetection/changedetection-bb8d64ff7-zt2cv` → `192.168.1.52:41641/udp`: 606 events, `DROPPED` (POLICY_DENY).
- `romm/romm-5d775db57f-6lsxd` → `192.168.1.52:41641/udp`: 606 events, `DROPPED` (POLICY_DENY).
- `homepage/homepage-84996664c-gpj89` → `204.244.250.128:9930/udp`: 606 events, `DROPPED` (POLICY_DENIED).
- `radarr/radarr-55595558c-vqdmf` → `192.168.1.152:41641/udp`: 606 events, `FORWARDED` (—).
- `kiwix/kiwix-d9d58c8d4-vtcnx` → `204.244.250.128:9930/udp`: 606 events, `DROPPED` (POLICY_DENIED).
- `kiwix/kiwix-d9d58c8d4-vtcnx` → `192.168.1.52:41641/udp`: 606 events, `DROPPED` (POLICY_DENY).
- `lidarr/lidarr-7b45c964b-8xjfq` → `192.168.1.152:41641/udp`: 604 events, `FORWARDED` (—).
- `prowlarr/prowlarr-75d9d4b55-vk4m7` → `192.168.1.52:41641/udp`: 604 events, `DROPPED` (POLICY_DENY).
- `seerr/seerr-5bc6f4466d-t5g8x` → `204.244.250.128:23104/udp`: 584 events, `DROPPED` (POLICY_DENIED).
- `umami/umami-865c4f696d-gdngv` → `72.11.149.242:51820/udp`: 426 events, `FORWARDED` (—).
- `audiobookshelf/audiobookshelf-7ffbf68d98-h5k6h` → `72.11.149.242:51820/udp`: 424 events, `FORWARDED` (—).
- `kiwix/kiwix-d9d58c8d4-vtcnx` → `204.244.250.128:56858/udp`: 394 events, `DROPPED` (POLICY_DENIED).

## Diagram

- [Graphviz source](TRAFFIC-MAP.dot)
- [Rendered SVG](TRAFFIC-MAP.svg)

## Verdict and placement totals

Verdicts: `DROPPED` 25,460, `FORWARDED` 268,792.

Workload pod-to-pod placement: `same-node` 14,543.

Platform-only events: 76,805; workload-to-platform/host events: 217,447.
