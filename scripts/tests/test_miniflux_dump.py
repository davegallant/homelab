import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


class MinifluxDumpTest(unittest.TestCase):
    def test_concurrent_hooks_produce_complete_dump(self):
        rendered = subprocess.check_output([
            "helm", "template", "miniflux", str(ROOT / "kubernetes/apps/miniflux/chart"),
            "-n", "miniflux", "-f", str(ROOT / "kubernetes/apps/miniflux/values.production.yaml"),
        ], text=True)
        statefulset = next(doc for doc in yaml.safe_load_all(rendered) if doc and doc.get("kind") == "StatefulSet")
        hook = json.loads(statefulset["spec"]["template"]["metadata"]["annotations"]["pre.hook.backup.velero.io/command"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            fake = path / "pg_dump"
            fake.write_text('#!/bin/sh\nprintf "%s" "$MARKER"\nsleep 0.2\nprintf "%s" "$MARKER"\n')
            fake.chmod(0o755)
            env = {**os.environ, "PATH": f"{path}:{os.environ['PATH']}", "PGDATA": directory, "POSTGRES_USER": "test", "POSTGRES_PASSWORD": "test"}
            processes = [subprocess.Popen(hook, env={**env, "MARKER": marker}, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for marker in ("A", "B")]
            results = [process.communicate(timeout=10) for process in processes]
            self.assertEqual([process.returncode for process in processes], [0, 0], results)
            self.assertIn((path / "dump.sql").read_text(), ("AA", "BB"))
            self.assertEqual(sorted(p.name for p in path.glob("dump.sql.tmp*")), [])


if __name__ == "__main__":
    unittest.main()
