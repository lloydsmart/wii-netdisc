"""One matched stock control and one complete, independently authorised sizing link."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from . import stock_dip_build as stock
from .experimental_dip_evidence import ARTIFACTS, DIAG_FILES, PATCHED, PINS, SECTIONS, Journal
from .experimental_dip_inspect import ControlMismatch, OverflowUnresolved, inspect, overflow

FIXTURE = stock.ROOT / "research/experimental_dip"


def verify_fixture(source, log, journal):
    for name, expected in PINS.items():
        stock.verify(source / name, expected, log)
        journal.write("pin", name, expected)


def integrate(root, inputs, log, journal):
    # Both extraction and mutation are confined to this fresh scratch tree.
    stock.verify(inputs, stock.SOURCE_HASH, log)
    stock.command(["tar", "-xf", inputs], log, cwd=root)
    verify_fixture(FIXTURE, log, journal)
    patch = root / "integration.patch"
    shutil.copyfile(FIXTURE / patch.name, patch)
    stock.verify(patch, PINS[patch.name], log)
    cmd = ["git", "apply", "--no-index", "--unidiff-zero", "--whitespace=error"]
    stock.command(cmd + ["--check", patch], log, cwd=root)
    stock.command(cmd + [patch], log, cwd=root)
    for name, expected in PATCHED.items():
        path = stock.DIP.parent / name
        stock.verify(root / path, expected, log)
        journal.write("pin", path, expected)
    for name, expected in PINS.items():
        if name != patch.name:
            dest = root / stock.DIP.parent / name
            if dest.exists():
                raise ValueError("experimental source collision")
            shutil.copyfile(FIXTURE / name, dest)
            stock.verify(dest, expected, log)


# Severity and cause are derived from the private message. No message text,
# source identifiers from it, or caller-supplied paths cross the collector.
SOURCE_DIAG = re.compile(r"^(.+?\.[A-Za-z]+):(\d+):(?:\d+:)?\s*(fatal error|error|warning):\s*(.*)", re.I)
CAUSE_PATTERNS = (
    ("layout-assertion", r"(?:ipc_extent|pool_extent|pool_alignment|vector_extent|queue_extent|"
                         r"arm_extent|record_stride|commit_extent).*negative"),
    ("unknown-type", r"unknown type|type name"),
    ("undeclared-name", r"undeclared|was not declared"),
    ("missing-include", r"No such file or directory"),
    ("processor-instruction", r"(?:selected )?processor (?:does not|doesn't) support|"
                              r"instruction (?:is )?not supported (?:on|by|in)"),
    ("argument-count", r"too (?:few|many) arguments (?:to|for) (?:function|method)|"
                       r"(?:incorrect|wrong) number of arguments"),
    ("bad-instruction", r"bad instruction|unknown (?:instruction|opcode)|invalid instruction"),
    ("bad-operands", r"operand|immediate value|register expected"),
    ("syntax-error", r"expected|syntax error"),
    ("undefined-reference", r"undefined reference"),
    ("duplicate-definition", r"multiple definition"),
)


def diagnostics(log):
    for line in log.splitlines():
        source = SOURCE_DIAG.match(line)
        if source:
            path, number, severity, message = source.groups()
            label = Path(path).name
            label = label if label in DIAG_FILES else "other-input"
            stage = "assembler" if path.lower().endswith(".s") else "compile"
            fallback = "other-assembler" if stage == "assembler" else "other-compiler"
        elif re.search(r"undefined reference|multiple definition|^\S*\bld: ", line):
            stage, label, number, severity, message = "link", "ld", 0, "error", line
            fallback = "region-range" if re.search(r"overflowed by|will not fit", line) else "other-link"
        else:
            continue
        cause = next((key for key, pat in CAUSE_PATTERNS if re.search(pat, message, re.I)), fallback)
        yield stage, label, int(number), severity.lower().replace(" ", "-"), cause


def build_records(run, root, logfile, journal):
    journal.write("private-digest", run, "build-log", stock.digest(logfile))
    for name in sorted(ARTIFACTS):
        path = root / name
        if path.is_file():
            journal.write("artifact", run, name, path.stat().st_size, stock.digest(path))
    for row in diagnostics(logfile.read_text(errors="replace")):
        journal.write("diagnostic", *row)


def build_outcome(log):
    failures = [row for row in diagnostics(log) if row[3] != "warning"]
    if any(row[-1] == "layout-assertion" for row in failures):
        return "abi-layout-error"
    if any(row[0] in ("compile", "assembler") for row in failures):
        return "compile-error"
    if "undefined reference" in log or re.search(r"(?m)^\S*ld: |collect2: ld returned", log):
        return "incomplete-link"
    if re.search(r"(?m)^(?:\.\./)+stripios dip-plugin\.elf\.orig dip-plugin\.elf$", log):
        return "conversion-error"
    return "build-error"


def partial_objects(root, toolchain, journal):
    # Relocatable sizes help explain overflow; they are never linked spans.
    for name in ("netdisc.o", "netdisc_net.o", "netdisc_gate.o"):
        obj = root / stock.DIP.parent / name
        if not obj.is_file():
            continue
        with (root.parent / "inspection.log").open("ab") as err:
            report = subprocess.check_output([toolchain / "bin/arm-eabi-size", "-A", obj], stderr=err, text=True)
        for section, size in re.findall(r"^([.\w]+)\s+(\d+)\s+\d+\s*$", report, re.M):
            family = next((n for n in SECTIONS | {".comment", ".ARM.attributes"}
                           if section == n or section.startswith(n + ".")), "other")
            journal.write("object", obj.name, family, int(size))


def record_inspection_error(work, run, error, journal):
    path = work / "inspection.log"
    with path.open("a") as out:
        print(error, file=out)
    journal.write("private-digest", run, "inspection", stock.digest(path))
    journal.write("diagnostic", "validation", "inspect", 0, "error", "validation-failed")


def measure_pair(work, env, journal):
    control = None
    for run in ("control", "probe"):
        root = work / run
        root.mkdir()
        log = work / (run + ".log")
        toolchain = Path(env["DEVKITARM"])
        with log.open("w") as out:
            if run == "probe":
                journal.write("stage", "patch")
                try:
                    integrate(root, work / "inputs.tar", out, journal)
                except stock.ERRORS as exc:
                    print(exc, file=out, flush=True)
                    build_records(run, root, log, journal)
                    journal.write("diagnostic", "validation", "integration.patch", 0, "error", "validation-failed")
                    journal.write("outcome", "patch-error")
                    return 1
            journal.write("stage", run)
            try:
                if run == "control":
                    stock.build(root, work / "inputs.tar", env, out)
                else:
                    stock.compile_extraction(root, env, out)
            except subprocess.CalledProcessError:
                out.flush()
                build_records(run, root, log, journal)
                build_log = log.read_text(errors="replace")
                outcome = build_outcome(build_log)
                if run == "probe":
                    try:
                        evidence = overflow(build_log, root / stock.DIP.with_suffix(".map"), journal)
                    except OverflowUnresolved:
                        outcome = "overflow-evidence-unresolved"
                    else:
                        for row in evidence:
                            journal.write("overflow", *row)
                        if evidence:
                            outcome = "region-overflow"
                    try:
                        partial_objects(root, toolchain, journal)
                    except stock.ERRORS as exc:
                        record_inspection_error(work, run, exc, journal)
                journal.write("outcome", outcome)
                return 1
        # An incomplete inventory, converted ELF alone or unreconciled map
        # cannot produce a valid modified measurement.
        journal.write("build", run, "recipes-completed")
        if (root / stock.DIP.with_suffix(".elf.orig")).is_file():
            journal.write("build", run, "original-linked")
        try:
            build_records(run, root, log, journal)
            stock.inventory(root, work)
            journal.write("stage", "inspect")
            control = inspect(root, toolchain, journal, control)
        except (KeyError, *stock.ERRORS) as exc:
            if run == "control":
                raise
            record_inspection_error(work, run, exc, journal)
            journal.write("outcome", "linked-inspection-unresolved")
            return 1
    journal.write("stage", "finished")
    journal.write("outcome", "linked-review-required")
    return 0


def main():
    if os.geteuid() == 0:
        raise ValueError("run unprivileged")
    work, source, archive = (Path(os.environ[n]).resolve() for n in ("WORK_DIR", "D2X_REPO", "R32_ARCHIVE"))
    installed = Path(os.environ["DEVKITARM"]).resolve() if os.environ.get("DEVKITARM") else None
    stock.validate_work_path(work, source, archive, installed)
    os.umask(0o022)
    work.mkdir()
    # Hosted approval/provisioning evidence is created before prepare().
    external = os.environ.get("SIZING_JOURNAL_DIR")
    journal = Journal((Path(external) if external else work) / "sizing.jsonl")
    stage = "inputs"
    try:
        with (work / "preparation.log").open("w") as log:
            journal.write("stage", stage)
            verify_fixture(FIXTURE, log, journal)
            stage = "prepare"
            journal.write("stage", stage)
            env = stock.prepare(work, source, archive, installed, log)
            journal.write("revision", "d2x", stock.REV)
            journal.write("check", "source-tar", stock.SOURCE_HASH)
            journal.write("check", "r32", stock.R32_HASH)
        versions = (work / "preparation.log").read_text()
        for tool, prefix in (("gcc", "arm-eabi-gcc (devkitARM release 32)"),
                             ("ld", "GNU ld (GNU Binutils)"), ("make", "GNU Make"),
                             ("python", "Python")):
            found = re.search("^" + re.escape(prefix) + r" ([0-9.]+)$", versions, re.M)
            if not found:
                raise ValueError("missing resolved version for " + tool)
            journal.write("tool", tool, found[1])
        stage = "inspect"
        return measure_pair(work, env, journal)
    except ControlMismatch as exc:
        record_inspection_error(work, "control", exc, journal)
        journal.write("outcome", "control-mismatch")
        return 1
    except (KeyError, *stock.ERRORS) as exc:
        with (work / "preparation.log").open("a") as out:
            print(exc, file=out)
        journal.write("diagnostic", "validation", stage, 0, "error", "validation-failed")
        journal.write("outcome", "input-error" if stage in ("inputs", "prepare") else "invalid-evidence")
        return 1
    finally:
        journal.write("private-digest", "prepare", "environment", stock.digest(work / "preparation.log"))


if __name__ == "__main__":
    sys.exit(main())
