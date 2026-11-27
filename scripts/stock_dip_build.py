"""Prepare, build twice and measure the pinned public DIP sources on Linux."""

import hashlib
import os
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import sys

from .dip_footprint import measure

ROOT = Path(__file__).resolve().parents[1]
REV = "33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7"
TREE = "b8e661b6535beb1d777ac21d25d25623bb5f0668"
EPOCH = "1742677801"
SOURCE_HASH = "b6c8bd6cbe179a7155879fa3eace86af475fe80146b7bab9f2647f6f2303575c"
R32_HASH = "7ca6fafef13876e2e565b4421e2d240c4532c7f0d15f4ffe1e2ed3c485748cd6"
DIP = Path("source/dip-plugin/dip-plugin")
LIB = Path("source/cios-lib/cios-lib.a")
REQUIRED = {Path("stripios"), LIB, *(DIP.with_suffix(s) for s in (".elf.orig", ".elf", ".map"))}
ERRORS = (OSError, ValueError, IndexError, struct.error, subprocess.CalledProcessError)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def command(args, log, **kwargs):
    print("$", shlex.join(map(str, args)), file=log, flush=True)
    subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True, **kwargs)


def verify(path, expected, log):
    actual = digest(path)
    print(f"{actual}  {path} ({path.stat().st_size} bytes)", file=log, flush=True)
    if actual != expected:
        raise ValueError(f"{path}: expected SHA-256 {expected}, got {actual}")


def prepare(work, source, archive, installed, log):
    git = ["git", "--no-replace-objects", "-C", source]
    identity = subprocess.check_output(git + ["show", "-s", "--format=%H %T %ct", REV], text=True)
    print("Commit, tree and committer epoch:", identity.strip(), file=log)
    if identity.split() != [REV, TREE, EPOCH]:
        raise ValueError("upstream identity disagrees with the baseline")
    inputs = work / "inputs.tar"
    command(git + ["archive", "--format=tar", "-o", inputs, REV,
                   "source/cios-lib", "source/dip-plugin", "stripios_src"], log)
    verify(inputs, SOURCE_HASH, log)
    verify(archive, R32_HASH, log)
    # This private reference extraction also provisions the ephemeral runner.
    command(["tar", "-xzf", archive, "-C", work], log)
    reference = work / "devkitARM"
    if installed:
        command(["diff", "-qr", "--no-dereference", reference, installed], log)
    toolchain = installed or reference
    # Give upstream make a clean environment (including no parent Make overrides).
    env = {"PATH": os.environ["PATH"], "LC_ALL": "C", "TZ": "UTC",
           "TMPDIR": str(work), "DEVKITARM": str(toolchain), "SOURCE_DATE_EPOCH": EPOCH}
    if any(c.isspace() for c in str(toolchain)):
        raise ValueError("the upstream Makefiles require a DEVKITARM path without whitespace")
    for tool in ["uname", "git", "g++", "make", "ldd", "readelf", "python3"]:
        command([tool, "-a" if tool == "uname" else "--version"], log, env=env)
    if shutil.which("dpkg-query"):
        command(["dpkg-query", "-W"], log, env=env)
    check_programs(toolchain, env, log)
    return env


def check_programs(toolchain, env, log):
    helpers = toolchain / "libexec/gcc/arm-eabi/4.5.1"
    programs = {}
    for name in ("cc1", "collect2", "gcc", "as", "ar", "ld", "readelf", "nm", "size"):
        exe = helpers / name if name in ("cc1", "collect2") else toolchain / "bin" / ("arm-eabi-" + name)
        if not exe.resolve().is_relative_to(toolchain) or not exe.is_file() or not os.access(exe, os.X_OK):
            raise ValueError(f"missing verified executable: {exe}")
        programs[name] = exe
    for name in ("cc1", "collect2", "as", "ld"):
        resolved = subprocess.check_output([programs["gcc"], f"-print-prog-name={name}"],
                                           text=True, env=env).strip()
        print(f"gcc resolves {name} to {resolved}", file=log, flush=True)
        actual = Path(resolved)
        if not actual.is_absolute():
            raise ValueError(f"compiler did not resolve {name} to an absolute path: {resolved}")
        expected = [programs[name]]
        if name in ("as", "ld"):
            expected.append(toolchain / "arm-eabi/bin" / name)
        if (not actual.resolve().is_relative_to(toolchain) or not actual.is_file()
                or not os.access(actual, os.X_OK) or not any(
                    p.is_file() and actual.samefile(p) for p in expected)):
            raise ValueError(f"unexpected compiler helper {name}: {actual}")
        programs[f"driver-{name}"] = actual
    for exe in dict.fromkeys(programs.values()):
        result = subprocess.run(["ldd", exe], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, env=env)
        print(f"ldd {exe}\n{result.stdout}", file=log, flush=True)
        result.check_returncode()
        if "not found" in result.stdout:
            raise ValueError(f"unresolved host dependency for {exe}")
    for name in ("gcc", "as", "ar", "ld", "readelf", "nm", "size"):
        command([programs[name], "--version"], log, env=env)


def build(root, inputs, env, log):
    options = {"env": env, "cwd": root}
    command(["tar", "-xf", inputs], log, **options)
    compile_extraction(root, env, log)


def compile_extraction(root, env, log):
    options = {"env": env, "cwd": root}
    command(["g++", "stripios_src/main.cpp", "-o", "stripios"], log, **options)
    command(["make", "--trace", "-C", "source/cios-lib"], log, **options)
    command(["make", "--trace", "-C", "source/dip-plugin", "STRIP=../../stripios"], log, **options)


def inventory(root, evidence):
    paths = sorted((p.relative_to(root) for p in root.rglob("*")
                    if p.is_file() and (p == root / "stripios" or
                                        p.name.endswith((".o", ".a", ".map", ".elf", ".elf.orig")))),
                   key=str)
    (evidence / f"{root.name}-paths.txt").write_text("".join(f"{p}\n" for p in paths))
    with (evidence / f"{root.name}-hashes.txt").open("w") as log:
        for path in paths:
            full = root / path
            print(digest(full), full.stat().st_size, path, file=log)
    required = REQUIRED.copy()
    for directory in (LIB.parent, LIB.parent / "libwbfs", DIP.parent):
        for src in (root / directory).iterdir():
            if src.suffix in (".c", ".s"):
                required.add(src.relative_to(root).with_suffix(".o"))
    missing = required.difference(paths)
    if missing:
        raise ValueError("missing required outputs: " + ", ".join(map(str, sorted(missing))))


def inspect(root, evidence, env):
    original = root / DIP.with_suffix(".elf.orig")
    linker_map = root / DIP.with_suffix(".map")
    errors = []
    with (evidence / f"{root.name}-footprint.txt").open("w") as report:
        try:
            validated_map = measure(original, linker_map, report)
            (evidence / f"{root.name}.map").write_bytes(validated_map)
        except ERRORS as exc:
            print(f"Footprint validation failed: {exc}", file=report)
            errors.append(str(exc))
    # Keep independent listings for diagnosis even when the map check fails.
    try:
        prefix = Path(env["DEVKITARM"]) / "bin/arm-eabi-"
        with (evidence / f"{root.name}-elf.txt").open("w") as log:
            command([str(prefix) + "readelf", "-h", "-SW", "-lW", "-A", original], log, env=env)
            command([str(prefix) + "nm", "-nS", original], log, env=env)
            command([str(prefix) + "size", "-A", "-x", original], log, env=env)
        with (evidence / f"{root.name}-elf.txt").open("a") as log:
            command([str(prefix) + "readelf", "-h", "-lW", root / DIP.with_suffix(".elf")], log, env=env)
    except ERRORS as exc:
        errors.append(str(exc))
    if errors:
        raise ValueError(" / ".join(errors))


def compare(work, evidence, log, inventories_complete):
    paths = [(evidence / f"{run}-paths.txt").read_text().splitlines() for run in ("a", "b")]
    if not all(paths) or paths[0] != paths[1]:
        for label, own, other in (("a", paths[0], paths[1]), ("b", paths[1], paths[0])):
            for path in sorted(set(own) - set(other)):
                print(f"only in {label}: {path}", file=log)
        raise ValueError("empty or unequal inventories")
    if not inventories_complete:
        raise ValueError("required outputs or their hashes are missing; see inventory diagnostics")
    different = False
    for path in paths[0]:
        result = subprocess.run(["cmp", "-s", work / "a" / path, work / "b" / path])
        if result.returncode not in (0, 1):
            raise OSError(f"comparison error ({result.returncode}): {path}")
        print("differs" if result.returncode else "identical", path, file=log)
        different |= result.returncode == 1
    if different:
        raise ValueError("artifact byte differences")


def validate_work_path(work, source, archive, installed):
    protected = [archive]
    if installed:
        protected.append(installed)
    for repo in (ROOT, source):
        paths = subprocess.check_output(
            ["git", "-C", repo, "rev-parse", "--show-toplevel", "--absolute-git-dir",
             "--path-format=absolute", "--git-common-dir"], text=True,
        ).splitlines()
        top, git_dir, common_dir = (Path(p).resolve() for p in paths)
        if repo != top:
            raise ValueError(f"expected Git checkout root {top}, got {repo}")
        protected.extend((top, git_dir, common_dir))
    if any(work.is_relative_to(p) or p.is_relative_to(work) for p in protected):
        raise ValueError("WORK_DIR overlaps a protected input or repository")


def main():
    if os.geteuid() == 0:
        raise ValueError("run the measurement as an unprivileged user")
    work, source, archive = (Path(os.environ[key]).resolve()
                             for key in ("WORK_DIR", "D2X_REPO", "R32_ARCHIVE"))
    installed = Path(os.environ["DEVKITARM"]).resolve() if os.environ.get("DEVKITARM") else None
    validate_work_path(work, source, archive, installed)
    os.umask(0o022)
    work.mkdir()  # Refuse stale results and concurrent reuse.
    evidence = work / "evidence"
    evidence.mkdir()
    print("Measurement evidence:", evidence, flush=True)
    with (evidence / "preparation.txt").open("w") as log:
        try:
            env = prepare(work, source, archive, installed, log)
        except ERRORS as exc:
            print(f"Preparation failed: {exc}", file=log)
            raise

    failures = []
    inventories_complete = True
    for run in ("a", "b"):
        root = work / run
        root.mkdir()
        with (evidence / f"{run}-build.txt").open("w") as log:
            try:
                build(root, work / "inputs.tar", env, log)
            except ERRORS as exc:
                failures.append(f"{run} build: {exc}")
            else:
                print(f"{run} build succeeded", file=log)
        # Each diagnostic is independent, even after link or conversion failure.
        try:
            inventory(root, evidence)
        except ERRORS as exc:
            inventories_complete = False
            failures.append(f"{run} inventory: {exc}")
        try:
            inspect(root, evidence, env)
        except ERRORS as exc:
            failures.append(f"{run} ELF inspection: {exc}")
    with (evidence / "comparison.txt").open("w") as log:
        try:
            compare(work, evidence, log, inventories_complete)
        except ERRORS as exc:
            print(f"Comparison failed: {exc}", file=log)
            failures.append(f"comparison: {exc}")
        else:
            print("Complete inventories are byte-identical.", file=log)
    summary = "\n".join(failures) if failures else "Both stock builds, measurements and byte comparisons passed."
    (evidence / "result.txt").write_text(summary + "\n")
    print(summary, flush=True)
    return int(bool(failures))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, *ERRORS) as error:
        sys.exit(f"stock DIP preparation failed: {error}")
