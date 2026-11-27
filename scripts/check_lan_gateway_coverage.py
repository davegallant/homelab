#!/usr/bin/env python3
"""Keep every Pangolin/Newt app on the LAN gateway, or excluded with a reason.

Offline (run by `just lint`): every directory under kubernetes/apps/ or
ansible/playbooks/ that deploys a Newt image must appear exactly once in the
lan-gateway values as an `apps` entry or an `excluded` entry with a reason;
every entry must have a Newt workload behind it (the LAN must never see more
than Pangolin publishes); and every app namespace must be a destination of the
homelab-lan-gateway AppProject; and `lanDnsClients` must equal `lanCidr` minus
the Talos node addresses, so cluster DNS keeps the public answer.

`--pangolin` additionally reads live Pangolin resources over `ssh vps` and
fails on any hostname the values file does not cover.
"""

from pathlib import Path
import argparse
import ipaddress
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
VALUES = Path("kubernetes/apps/lan-gateway/chart/values.yaml")
PROJECT = Path("kubernetes/apps/argocd/project-lan-gateway.yaml")
CLUSTER_VARS = Path("kubernetes/cluster/vars.yaml")
SCAN_DIRS = (Path("kubernetes/apps"), Path("ansible/playbooks"))
SCAN_SUFFIXES = {".yaml", ".yml", ".j2"}
NEWT_IMAGE = "fosrl/newt"
DOMAIN = "davegallant.ca"
PANGOLIN_QUERY = "select fullDomain from resources where enabled = 1 order by fullDomain;"


def find_newt_apps(root: Path) -> dict[str, list[str]]:
    """Map app directory name -> files that reference the Newt image."""
    found: dict[str, list[str]] = {}
    for base in SCAN_DIRS:
        base_dir = root / base
        if not base_dir.is_dir():
            continue
        for path in sorted(base_dir.rglob("*")):
            if path.suffix not in SCAN_SUFFIXES or not path.is_file():
                continue
            rel = path.relative_to(base_dir)
            if rel.parts[0] == "lan-gateway":
                continue
            if NEWT_IMAGE in path.read_text(errors="ignore"):
                found.setdefault(rel.parts[0], []).append(str(path.relative_to(root)))
    return found


def expected_dns_clients(lan_cidr: str, node_addresses: list[str]) -> list[str]:
    networks = [ipaddress.ip_network(lan_cidr)]
    for address in node_addresses:
        excluded = ipaddress.ip_network(f"{address}/32")
        networks = [
            part
            for network in networks
            for part in (network.address_exclude(excluded) if excluded.subnet_of(network) else [network])
        ]
    return [str(n) for n in sorted(networks)]


def hostname(entry: dict) -> str:
    return entry.get("hostname") or f"{entry['name']}.{DOMAIN}"


def check(root: Path) -> list[str]:
    errors: list[str] = []
    values = yaml.safe_load((root / VALUES).read_text()) or {}
    apps = values.get("apps") or []
    excluded = values.get("excluded") or []
    newt = find_newt_apps(root)

    seen: dict[str, str] = {}
    for kind, entries in (("apps", apps), ("excluded", excluded)):
        for entry in entries:
            name = entry.get("name")
            if not name:
                errors.append(f"{VALUES}: {kind} entry without a name")
                continue
            if name in seen:
                errors.append(f"{VALUES}: {name} is listed in both {seen[name]} and {kind}")
            seen[name] = kind
            if kind == "excluded" and not str(entry.get("reason") or "").strip():
                errors.append(f"{VALUES}: excluded {name} needs a reason")
            if name not in newt:
                errors.append(
                    f"{VALUES}: {kind} entry {name} has no Newt workload; only apps "
                    "already public through Pangolin belong on the LAN gateway"
                )

    for name, files in sorted(newt.items()):
        if name not in seen:
            errors.append(
                f"{name} runs Newt ({', '.join(files)}) but is not in {VALUES}; "
                "add it to apps (and the AppProject) or to excluded with a reason"
            )

    project = yaml.safe_load((root / PROJECT).read_text()) or {}
    destinations = {d.get("namespace") for d in project.get("spec", {}).get("destinations", [])}
    for entry in apps:
        namespace = entry.get("namespace") or entry.get("name")
        if namespace not in destinations:
            errors.append(f"{PROJECT}: add destination namespace {namespace} for {entry.get('name')}")

    cluster_vars = root / CLUSTER_VARS
    if cluster_vars.is_file():
        nodes = (yaml.safe_load(cluster_vars.read_text()) or {}).get("talos_nodes") or []
        expected = expected_dns_clients(values.get("lanCidr", ""), [n["address"] for n in nodes])
        actual = [str(ipaddress.ip_network(c)) for c in values.get("lanDnsClients") or []]
        if sorted(actual) != expected:
            errors.append(
                f"{VALUES}: lanDnsClients must be lanCidr minus the Talos node addresses: "
                + ", ".join(expected)
            )
    else:
        errors.append(f"{CLUSTER_VARS} not found")
    return errors


def check_pangolin(root: Path, domains: list[str]) -> list[str]:
    values = yaml.safe_load((root / VALUES).read_text()) or {}
    covered = {hostname(e) for e in values.get("apps") or []}
    covered |= {hostname(e) for e in values.get("excluded") or []}
    return [
        f"Pangolin publishes {d} but {VALUES} neither routes nor excludes it"
        for d in domains
        if d and d not in covered
    ]


def pangolin_domains() -> list[str]:
    result = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=10", "vps",
         f"sqlite3 -readonly ~/config/db/db.sqlite '{PANGOLIN_QUERY}'"],
        check=True, capture_output=True, text=True,
    )
    return [line.strip() for line in result.stdout.splitlines()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pangolin", action="store_true", help="also compare with live Pangolin over ssh vps")
    args = parser.parse_args()

    errors = check(ROOT)
    if args.pangolin:
        errors += check_pangolin(ROOT, pangolin_domains())
    if errors:
        for error in errors:
            print(f"LAN gateway coverage: {error}", file=sys.stderr)
        raise SystemExit(1)
    values = yaml.safe_load((ROOT / VALUES).read_text())
    print(
        f"LAN gateway covers {len(values.get('apps') or [])} Newt apps; "
        f"{len(values.get('excluded') or [])} excluded with reasons"
        + ("; live Pangolin matches" if args.pangolin else "")
    )


if __name__ == "__main__":
    main()
