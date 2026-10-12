#!/usr/bin/env python3
"""Check the deployed Headscale policy and its managed node tags."""

import json
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "ansible/playbooks/pangolin/main.yml"
POLICY = ROOT / "ansible/playbooks/pangolin/policy.headscale.hujson"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "pangolin"]


def headscale(*args: str, input_text: str | None = None) -> str:
    command = SSH + ["docker", "exec"]
    if input_text is not None:
        command.append("-i")
    command += ["headscale", "headscale", *args]
    result = subprocess.run(
        command,
        input=input_text,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{' '.join(args)} failed: {detail}")
    return result.stdout


def main() -> int:
    try:
        playbook = yaml.safe_load(PLAYBOOK.read_text())[0]
        expected_tags = playbook["vars"]["headscale_node_tags"]
        policy = POLICY.read_text()

        headscale("policy", "check", "--file", "/dev/stdin", input_text=policy)
        active_policy = headscale("policy", "get")
        if active_policy.rstrip() != policy.rstrip():
            raise RuntimeError("deployed policy differs from the repository policy")

        nodes = json.loads(headscale("nodes", "list", "-o", "json"))
        nodes_by_name = {node["name"]: node for node in nodes}
        if len(nodes_by_name) != len(nodes):
            raise RuntimeError("Headscale returned duplicate node names")

        errors = []
        for name, tag in expected_tags.items():
            node = nodes_by_name.get(name)
            if node is None:
                errors.append(f"{name}: missing from Headscale")
            elif node.get("tags", []) != [tag]:
                errors.append(
                    f"{name}: expected [{tag}], got {node.get('tags', [])}"
                )

        managed_tags = set(expected_tags.values())
        for name, node in nodes_by_name.items():
            if name not in expected_tags and managed_tags.intersection(
                node.get("tags", [])
            ):
                errors.append(f"{name}: has an unmanaged policy tag")

        if errors:
            raise RuntimeError("node tag mismatch:\n  " + "\n  ".join(errors))

        print(
            f"Headscale policy is valid and matches the repository; "
            f"{len(expected_tags)} managed node tags match."
        )
        return 0
    except (OSError, KeyError, IndexError, TypeError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
