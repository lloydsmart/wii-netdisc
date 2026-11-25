"""Select permitted text evidence for the hosted stock DIP artifact."""

from io import StringIO
import os
from pathlib import Path
import sys

from .dip_footprint import measure, plain_text
from .stock_dip_build import DIP, ERRORS


def collect(runner_temp):
    inputs = runner_temp / "stock-inputs"
    evidence = runner_temp / "stock-dip/evidence"
    destination = runner_temp / "stock-dip-public"
    destination.mkdir()  # A fresh directory contains only bytes approved below.
    candidates = [inputs / "runner.txt", inputs / "measurement.txt"]
    candidates.extend(evidence / name for name in ("preparation.txt", "result.txt", "comparison.txt"))
    for run in ("a", "b"):
        candidates.append(evidence / f"{run}.map")
        for kind in ("build", "footprint", "elf", "paths", "hashes"):
            candidates.append(evidence / f"{run}-{kind}.txt")

    rejected = []
    for path in candidates:
        try:
            if path.resolve() != path or (path.exists() and not path.is_file()):
                raise ValueError("expected a regular file at the recorded path")
            if not path.exists():
                continue  # Preflight or an earlier operation may have failed.
            if path.suffix == ".map":
                original = evidence.parent / path.stem / DIP.with_suffix(".elf.orig")
                data = measure(original, path, StringIO())
            else:
                data = path.read_bytes()
                plain_text(data)
        except ERRORS as exc:
            rejected.append(f"Excluded {path.name}: {exc}")
            continue
        (destination / path.name).write_bytes(data)
    return rejected


if __name__ == "__main__":
    errors = collect(Path(sys.argv[1]).resolve())
    # Set only after a fresh publication directory has been completely prepared.
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        print("ready=true", file=output)
    for error in errors:
        print(error, file=sys.stderr)
    sys.exit(bool(errors))
