"""Check policy reconciliation and the monitor pod's actual Mullvad exit."""

import json
import os
import ssl
import urllib.request
from pathlib import Path


def get_json(url, *, token=None, context=None):
    headers = {"Authorization": "Bearer " + token} if token else {}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, context=context, timeout=15) as response:
        return json.load(response)


failures = []
token = Path("/var/run/secrets/kubernetes.io/serviceaccount/token").read_text()
context = ssl.create_default_context(
    cafile="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
)
api = "https://192.168.1.210:6443"
checks = {
    "policy": "/apis/cilium.io/v2/ciliumegressgatewaypolicies/qbittorrent",
    "argo": "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/qbittorrent-egress",
}
for name, path in checks.items():
    try:
        result = get_json(api + path, token=token, context=context)
        if name == "policy":
            metadata = result["metadata"]
            if metadata.get("deletionTimestamp"):
                failures.append("policy is Terminating")
            if metadata.get("annotations", {}).get("protected") != "do-not-delete":
                failures.append("protected annotation missing")
            if "homelab.davegallant.ca/protect-egress" not in metadata.get("finalizers", []):
                failures.append("policy finalizer missing")
        else:
            status = result.get("status", {})
            if status.get("sync", {}).get("status") != "Synced":
                failures.append("policy Application is not Synced")
            if status.get("health", {}).get("status") != "Healthy":
                failures.append("policy Application is not Healthy")
    except Exception as error:
        failures.append(name + " check failed: " + type(error).__name__)

try:
    result = get_json("https://am.i.mullvad.net/json")
    if result.get("mullvad_exit_ip") is not True:
        failures.append("public echo is not a Mullvad exit")
except Exception as error:
    failures.append("public echo failed: " + type(error).__name__)

if failures:
    payload = json.dumps({
        "title": "qBittorrent egress guard",
        "message": "; ".join(failures),
        "priority": 8,
    }).encode()
    try:
        request = urllib.request.Request(
            os.environ["GOTIFY_URL"].rstrip("/") + "/message",
            data=payload,
            headers={"X-Gotify-Key": os.environ["GOTIFY_TOKEN"],
                     "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            print(json.dumps({"failures": failures, "notification_status": response.status}))
    except Exception as error:
        print(json.dumps({"failures": failures, "notification_error": type(error).__name__}))
    raise SystemExit(1)

print(json.dumps({"policy": "protected", "argo": "Synced/Healthy", "mullvad_exit": True}))
