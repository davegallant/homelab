#!/usr/bin/env python3
"""Bootstrap for the GasWatch CronWorkflow: install deps, then run gaswatch.py.

The DHI Python image ships no shell, so the old `sh -ec` venv/pip flow
cannot run. This script does the same two steps in Python instead.
"""

import runpy
import subprocess
import sys

DEPS_DIR = "/tmp/deps"


def main() -> int:
    print("gaswatch: installing dependencies...", flush=True)
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--target",
            DEPS_DIR,
            "-r",
            "requirements.txt",
        ]
    )
    sys.path.insert(0, DEPS_DIR)
    runpy.run_path("gaswatch.py", run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
