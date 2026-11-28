"""Typed, text-only publication for the experimental link. Raw logs stay private."""

import json
import os
from pathlib import Path
import re
import sys

from . import stock_dip_build as stock
from .dip_footprint import EXPECTED_REGION, REGIONS, plain_text

PINS = {
    "integration.patch": "3bd1e135d775d7e71d781bbee180369e05d50a11e2b6ba799cd6c28e70e5aa81",
    "netdisc.c": "94d2591c1a069c042f10122cf3588a978df906678bb35db79a5d39e50763d80b",
    "netdisc.h": "97ffc741725856aab42a6a6b8d9019376422c0bb64478b3447eff1afad4e8afc",
    "netdisc_gate.s": "02b7254907f5b3cf42dae580e98d3831c71b20818d6c3f1c22ff5aa7e16e20b4",
    "netdisc_net.c": "51beaa4e702fae35aed06b45db3f0dffa6a7a718b70221d0199a34374d8cee54",
}
PATCHED = {
    "Makefile": "5f38ac636c62a82ea6bf4be68db65cd51635da2d35b1ee67b192b8e2bdca7374",
    "plugin.c": "1538b79f79df30eb43fef4f913c3eb96a183e7ed6a905b200590ba4a0cf9367f",
}

# Public identities come from the reviewed source lists and the matched stock inventory.
REQUIRED_PATHS = set("""
nd_hook admit_arm nd_take nd_exchange operation submit inspect_queue bringup timely
transfer receive_handoff verify_reply cleanup nd_fail nd_pin nd_emit nd_finish DI_HandleIoctl
os_get_thread_id os_open_async os_close_async os_ioctl_async os_ioctlv_async
os_message_queue_create os_message_queue_receive os_message_queue_destroy
os_timer_now os_create_timer os_destroy_timer __os_sync_before_read __os_sync_after_write
""".split())
SYMBOLS = REQUIRED_PATHS | set("""
DI_EmulateIoctl nd_trace nd_completions nd_checks nd_reader nd_commit nd_begin_cleanup
nd_bytes nd bindings queue_words vectors control scratch frame service timers paths
arm_claim read_claim armed verified received active sent nd_finish other
""".split())
CHECKLIST = set("""
stock-forward arm-admission malformed-attempt duplicate-rejection network-selectors
receive-handoff deadline-quarantine eligible-cleanup trace-return
""".split())
DIP = "source/dip-plugin/"
LIB = "source/cios-lib/"
ARTIFACTS = {"stripios", LIB + "cios-lib.a"} | {
    LIB + n + ".o" for n in """direct_syscalls fat_tools ios ipc isfs libc libwbfs/libwbfs
    libwbfs/rijndael libwbfs/wiidisc log mem sdhc_server sdio stealth str_utils swi_mload syscalls
    syscalls_dbg timer tools usbstorage vsprintf""".split()
} | {DIP + n for n in """dip-plugin.elf dip-plugin.elf.orig dip-plugin.map config.o dip.o dip_calls.o
    dma.o fat.o frag.o main.o patches.o plugin.o sdhc.o start.o wbfs.o netdisc.o netdisc_net.o
    netdisc_gate.o""".split()}
INPUTS = PINS | {DIP + n: h for n, h in PATCHED.items()}
DIAG_FILES = set(PINS) | {"plugin.c", "ld", "other-input", "inputs", "prepare", "inspect"}
SECTIONS = set(EXPECTED_REGION)
CAUSES = set("""
bad-instruction bad-operands processor-instruction argument-count unknown-type undeclared-name missing-include syntax-error
layout-assertion undefined-reference duplicate-definition region-range unsupported-overflow
other-compiler other-assembler other-link validation-failed
""".split())


def choices(words):
    return frozenset(words.split())


def pattern(expr):
    return lambda value: isinstance(value, str) and bool(re.fullmatch(expr, value, re.ASCII))


def integer(low, high):
    return lambda value: type(value) is int and low <= value <= high


def matches(rule, value):
    if callable(rule):
        return rule(value)
    return isinstance(value, str) and value in rule


U32 = integer(0, 2**32 - 1)


def optional_u32(value):
    return value is None or U32(value)


DELTA = integer(-2**32 + 1, 2**32 - 1)
RUN = choices("control probe")
SHA = pattern(r"[0-9a-f]{64}")
VERSION = pattern(r"[0-9]{1,4}(?:\.[0-9]{1,8}){1,4}")
ALLOWED = ("sizing.jsonl",)
SCHEMA = {
    "stage": [choices("approval inputs prepare control patch probe inspect finished")],
    "outcome": [choices("control-mismatch invalid-evidence patch-error input-error build-error "
                        "region-overflow overflow-evidence-unresolved linked-review-required "
                        "linked-inspection-unresolved compile-error incomplete-link conversion-error abi-layout-error")],
    "build": [RUN, choices("recipes-completed original-linked complete-link-invoked")],
    "pin": [set(INPUTS), SHA],
    "revision": [choices("checkout d2x"), pattern(r"[0-9a-f]{40}")],
    "tool": [choices("gcc ld make python"), VERSION],
    "artifact": [RUN, ARTIFACTS, U32, SHA],
    "private-digest": [choices("control probe prepare"), choices("build-log symbols disassembly environment inspection"), SHA],
    "check": [choices("map-normalised stock-elf source-tar r32"), SHA],
    "load": [RUN, integer(0, 65535), U32, U32, U32, U32],
    "section": [RUN, SECTIONS | {"other"}, U32, U32],
    "region": [RUN, choices("exe ram"), U32, DELTA, U32],
    "symbol": [RUN, SYMBOLS, set("tTbBrRdD"), U32, U32, lambda v: v == "unknown" or SHA(v)],
    "delta": [SYMBOLS, choices("added changed removed"), U32, U32, U32, U32],
    "frame": [SYMBOLS, U32, U32, U32, choices("unresolved entry-only")],
    "edge": [U32, U32, choices("call branch conditional literal interwork")],
    "unresolved": [U32, choices("indirect unsupported missing-target gap data ambiguous-mode missing-entry")],
    "missing": [REQUIRED_PATHS],
    "witness": [CHECKLIST, U32, U32],
    "review": [CHECKLIST, {"manual-required"}],
    "fill": [RUN, U32, U32],
    "overflow": [choices("exe ram"), SECTIONS | {"region"}, U32, U32, integer(1, 2**32-1)],
    "overlap": [SECTIONS, U32, U32, SECTIONS, U32, U32],
    "attempted": [choices("exe ram"), SECTIONS | {"region"}, U32, U32, U32],
    "overflow-report": [choices("exe ram other"), SECTIONS | {"region", "other"}, optional_u32, optional_u32],
    "diagnostic": [choices("compile assembler link validation"), DIAG_FILES, U32,
                   choices("warning error fatal-error"), CAUSES],
    "workflow": [choices("provision retrieve measure"), choices("success failure skipped cancelled")],
    "object": [choices("netdisc.o netdisc_net.o netdisc_gate.o"),
               choices(".init .text .data .rodata .bss .ARM.attributes .comment other"), U32],
}
RUNNER = {"image": {"ubuntu24"}, "version": pattern(r"20[0-9]{6}\.[0-9]{1,4}\.[0-9]{1,4}"),
          "run": integer(1, 2**63-1), "attempt": integer(1, 1), "uid": integer(1, 2**32-2)}


FIXTURE = stock.ROOT / "research/experimental_dip"
OBJECTS = ("netdisc.o", "netdisc_net.o", "netdisc_gate.o")
STORAGE = {"nd_completions": 2048}


def validate(row, schema=SCHEMA, inputs=INPUTS):
    if type(row) is not list or not row or type(row[0]) is not str:
        raise ValueError("malformed evidence row")
    kind = row[0]
    if kind == "runner":
        if len(row) == 3 and isinstance(row[1], str) and row[1] in RUNNER and matches(RUNNER[row[1]], row[2]):
            return
        raise ValueError("invalid runner identity")
    fields = schema.get(kind)
    if fields is None or len(row) != len(fields) + 1 or not all(
        matches(rule, value) for rule, value in zip(fields, row[1:])
    ):
        raise ValueError("invalid evidence fields")
    if kind == "pin" and inputs[row[1]] != row[2]:
        raise ValueError("unexpected input identity")
    if kind == "overflow-report":
        _, _, section, amount, reported_end = row
        if (section == "region") != (amount is not None) or (amount is not None and reported_end is not None):
            raise ValueError("invalid linker range report")
    if kind == "tool" and row[1] in ("gcc", "ld"):
        if row[2] != {"gcc": "4.5.1", "ld": "2.20.1.20100303"}[row[1]]:
            raise ValueError("unexpected r32 tool identity")
    if kind in ("overflow", "attempted"):
        _, region, section, lo, hi, excess = row
        origin, limit = REGIONS[region]
        if (section != "region" and EXPECTED_REGION[section] != region or
                lo < origin or hi < lo or excess != max(0, hi - limit) or
                section == "region" and lo != origin):
            raise ValueError("invalid range evidence")
    if kind == "revision":
        expected = stock.REV if row[1] == "d2x" else os.environ.get("GITHUB_SHA", row[2])
        if expected != row[2]:
            raise ValueError("unexpected revision")
    if kind == "check" and row[1] in ("source-tar", "r32"):
        if row[2] != {"source-tar": stock.SOURCE_HASH, "r32": stock.R32_HASH}[row[1]]:
            raise ValueError("unexpected archive identity")


class Journal:
    def __init__(self, path, policy=None):
        self.path = path
        self.policy = policy or sys.modules[__name__]

    def write(self, kind, *fields):
        row = [kind, *(str(v) if isinstance(v, Path) else v for v in fields)]
        validate(row, self.policy.SCHEMA, self.policy.INPUTS)
        with self.path.open("a", encoding="ascii") as stream:
            print(json.dumps(row, ensure_ascii=True), file=stream)


def collect(work, destination, schema=SCHEMA, inputs=INPUTS):
    destination.mkdir()
    for name in ALLOWED:
        src = work / name
        if src.resolve() != src or not src.is_file() or src.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("absent or invalid sizing journal")
        lines = plain_text(src.read_bytes()).splitlines()
        if not lines:
            raise ValueError("empty sizing journal")
        rows = [json.loads(line) for line in lines]
        for row in rows:
            validate(row, schema, inputs)
        if "literal-site" in schema:
            from .experimental_adapter import validate_journal
            validate_journal(rows)
        # Reserialise only parsed data after validating the entire artifact.
        (destination / name).write_text("".join(json.dumps(row) + "\n" for row in rows))


if __name__ == "__main__":
    temp = Path(sys.argv[1]).resolve()
    collect(temp / "dip-sizing-evidence", temp / "dip-sizing-public")
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        print("ready=true", file=output)
