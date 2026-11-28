"""ADR 0006 inputs, evidence schema and owner-gated entry point."""

from bisect import bisect_left
from collections import Counter, defaultdict
import os
from pathlib import Path
import re
import subprocess
import sys

from . import experimental_dip_build as paired
from . import experimental_dip_evidence as direct

FIXTURE = direct.stock.ROOT / "research/experimental_adapter"
PINS = {
    "adapter.c": "ef53a899d289e705cb0568afaea04c069205e870f8ff4b38fc3a8e109aeb72a7",
    "adapter.h": "987d343d7aed82914ff666e3ec723540941c920537f6830b7af1a304efabb124",
    "integration.patch": "21b6c2ddc71beb9fc3223afa1966f050be111e5dde8aae2668d0a16f136e8294",
    "mailbox.c": "eb174b828321903f4366f01914d74e4cad8ce0529a8b80410d087b6d41e16960",
    "netdisc_gate.s": "02b7254907f5b3cf42dae580e98d3831c71b20818d6c3f1c22ff5aa7e16e20b4",
    "transaction.c": "76362444a03df39c3b04ee38c76a83753196bb83c18c3d743935479289a694c9",
}
PATCHED = {
    "Makefile": "b51478ad6a3a2b3992f5293356b4341e3b181a93f72c5496a5a7d5fcc1a9c77b",
    "plugin.c": "7e32b68541ae74df35b6b829673d8ff8a2d09c1b50f4b25b10928166368a5876",
}
OBJECTS = ("adapter.o", "mailbox.o", "transaction.o", "netdisc_gate.o")
INPUTS = PINS | {direct.DIP + name: digest for name, digest in PATCHED.items()}
ARTIFACTS = (direct.ARTIFACTS - {direct.DIP + n for n in direct.OBJECTS}
             | {direct.DIP + n for n in OBJECTS})
DIAG_FILES = set(PINS) | (direct.DIAG_FILES - direct.PINS.keys())
STORAGE = {"nd_request": 160, "nd_reply": 192, "nd_completions": 96,
           "queue_words": 32, "nd_path": 32, "nd_trace": 1536, "nd_checks": 192,
           "nd_commit": 32, "nd_reader": 32}
REQUIRED_PATHS = set("""
DI_HandleIoctl nd_hook admit_arm nd_take nd_exchange operation submit inspect_queue
handback_authorised original_acquisition owns_fd nd_sample nd_make_request nd_validate_reply nd_short_decision nd_emit nd_fail
os_get_thread_id os_open_async os_ioctl_async os_close_async os_timer_now os_create_timer
os_stop_timer os_destroy_timer os_message_queue_create os_message_queue_receive
os_message_queue_destroy __os_sync_before_read __os_sync_after_write
""".split())
SYMBOLS = REQUIRED_PATHS | set(STORAGE) | set("""
DI_EmulateIoctl nd nd_provision nd_effects armed arm_claim read_claim validate
provisioned current_registration reserve teardown setup reject nd_verdict clock_result nd_latch_failure acquire_clock confirmed_effects other
""".split())
WITNESSES = {
    "stock-forward": {("DI_EmulateIoctl", "DI_HandleIoctl")},
    "arm-admission": {("nd_hook", "admit_arm"), ("admit_arm", "nd_take")},
    "duplicate-rejection": {("nd_hook", "nd_take")},
    "malformed-attempt": {("nd_hook", "reject")},
    "service-transaction": {("submit", n) for n in ("os_open_async", "os_ioctl_async", "os_close_async")},
    "blocking-receive": {("inspect_queue", "os_message_queue_receive")},
    "deadline-quarantine": {("operation", "nd_sample"), ("nd_sample", "clock_result")},
    "mailbox-handoff": {("operation", "nd_validate_reply"), ("nd_validate_reply", "__os_sync_before_read")},
    "pre-close-decision": {("nd_validate_reply", "nd_emit"), ("nd_short_decision", "nd_emit")},
    "original-acquisition-close": {("operation", "owns_fd"), ("owns_fd", "original_acquisition"),
                                   ("submit", "os_close_async")},
    "final-handback": {("nd_hook", "handback_authorised"), ("nd_hook", "nd_sample"),
                       ("nd_hook", "__os_sync_after_write")},
    "trace-return": {("nd_hook", "nd_emit"), ("nd_emit", "__os_sync_after_write")},
}
CHECKLIST = set(WITNESSES)
# Replace only the experiment-specific closed enumerations. Generic row types,
# ranges, digest checks and the collector's text/path controls remain shared.
SCHEMA = dict(direct.SCHEMA)
for kind, index, choices in (
        ("pin", 0, set(INPUTS)), ("artifact", 1, ARTIFACTS), ("symbol", 1, SYMBOLS),
        ("delta", 0, SYMBOLS), ("frame", 0, SYMBOLS), ("missing", 0, REQUIRED_PATHS),
        ("witness", 0, CHECKLIST), ("review", 0, CHECKLIST), ("diagnostic", 1, DIAG_FILES),
        ("object", 0, set(OBJECTS))):
    SCHEMA[kind] = direct.SCHEMA[kind].copy()
    SCHEMA[kind][index] = choices


SCHEMA["dependency"] = [direct.RUN, {"compiler-helper", "interworking-veneer"}, direct.U32, direct.U32]
SCHEMA["gap"] = [direct.RUN, {"exe", "ram"}, direct.U32, direct.U32]
SCHEMA["literal-site"] = [direct.U32]


def checked_extent(region, address, size, alignment=1, allow_empty=False):
    origin, end = direct.REGIONS[region]
    if not (origin <= address < end and address % alignment == 0
            and (size or allow_empty) and size <= end-address):
        raise ValueError("extent outside linked region")


def validate_journal(rows):
    from .experimental_dip_inspect import STOCK_ELF, STOCK_MAP, STOCK_SPAN
    data = defaultdict(list)
    previous = {}
    for kind, *values in rows:
        data[kind].append(tuple(values))
        if kind == "literal-site":
            checked_extent("exe", values[0], 4, 4)
            if values[0] <= previous.get(kind, 0):
                raise ValueError("duplicate or unordered literal site")
            previous[kind] = values[0]
        elif kind == "dependency":
            run, _, addr, size = values
            checked_extent("exe", addr, size, 2, allow_empty=True)
            if size % 2 or addr < previous.get((kind, run), 0):
                raise ValueError("invalid code dependency")
            previous[kind, run] = addr  # nm may emit multiple labels at one address
        elif kind == "gap":
            run, region, addr, size = values
            checked_extent(region, addr, size)
            if addr < previous.get((kind, run, region), 0):
                raise ValueError("unordered or overlapping gaps")
            previous[kind, run, region] = addr+size
        elif kind == "region":
            run, region, used, delta, trailing = values
            start, end = direct.REGIONS[region]
            if not used or used+trailing != end-start or delta != used-STOCK_SPAN[region]:
                raise ValueError("impossible occupied span")
        elif kind == "section":
            _, name, addr, size = values
            region = direct.EXPECTED_REGION.get(name)
            if not region:
                region = next((r for r, (a, b) in direct.REGIONS.items() if a <= addr < b), None)
            if not region:
                raise ValueError("unmapped section")
            checked_extent(region, addr, size)
        elif kind == "load":
            _, _, addr, physical, file_size, mem_size = values
            region = next((r for r, (a, b) in direct.REGIONS.items() if a == addr), None)
            if not region or addr != physical or file_size > mem_size:
                raise ValueError("invalid linked LOAD")
            checked_extent(region, addr, mem_size)

    # Even a stopped inspection cannot place code or allocated bytes in
    # padding it already reported. Zero-sized nm labels have a location only.
    gaps = defaultdict(list)
    for run, region, start, size in data["gap"]:
        gaps[run, region].append((start, start + size))
    occupied = [(run, addr, size) for run, _, addr, size in data["section"]]
    occupied.extend((run, addr, max(1, size)) for run, _, addr, size in data["dependency"])
    occupied.extend(("probe", addr, 4) for addr, in data["literal-site"])
    for run, addr, size in occupied:
        for region in ("exe", "ram"):
            intervals = gaps[run, region]
            index = bisect_left(intervals, (addr + size,))
            if index and intervals[index - 1][1] > addr:
                raise ValueError("occupied extent intersects a reported gap")

    if len(data["outcome"]) > 1:
        raise ValueError("multiple measurement outcomes")
    verdict = next(iter(data["outcome"]), (None,))[0]
    if data["overflow"] and verdict not in (None, "region-overflow"):
        raise ValueError("affirmative overflow contradicts measurement outcome")
    if not data["overflow"] and verdict not in ("region-overflow", "linked-review-required"):
        return
    interrupted = verdict is None
    linked = verdict == "linked-review-required"
    stages = ["approval", "inputs", "prepare", "control", "inspect", "patch", "probe"]
    if linked:
        stages += ["inspect", "finished"]
    if data["stage"] != [(s,) for s in stages]:
        raise ValueError("missing or contradictory measurement stages")

    # The same digest can legitimately occur before and after extraction.
    # Bind it and the other conclusive facts to the pass that produced them.
    stage = run = None
    initial_pins = []
    claimed = False
    for kind, *values in rows:
        if claimed and kind not in ("overflow", "outcome", "workflow") and not (
                kind == "private-digest" and values[:2] == ["prepare", "environment"]):
            raise ValueError("measurement evidence follows its corroborated overflow")
        if kind == "overflow":
            claimed = True
        if kind == "stage":
            stage = values[0]
            if stage in direct.RUN:
                run = stage
        elif kind == "runner" or (kind == "revision" and values[0] == "checkout"):
            if stage != "approval":
                raise ValueError("runner or checkout outside approval")
        elif kind in ("tool", "revision") and stage != "prepare":
            raise ValueError("build identity outside preparation")
        elif kind == "pin":
            if stage not in ("inputs", "patch") or stage == "inputs" and values[0] not in PINS:
                raise ValueError("pin outside input verification")
            if stage == "inputs":
                initial_pins.append(tuple(values))
        elif kind in ("artifact", "build") and stage != values[0]:
            raise ValueError("artifact or build from a different pass")
        elif kind in ("section", "region", "load", "gap", "symbol", "dependency", "fill"):
            if stage != "inspect" or values[0] != run:
                raise ValueError("layout outside its inspection")
        elif kind in ("literal-site", "delta", "review", "frame", "edge", "unresolved", "missing", "witness"):
            if stage != "inspect" or run != "probe":
                raise ValueError("probe inspection without a linked probe")
        elif kind == "check":
            control_check = values[0] in ("stock-elf", "map-normalised")
            if (control_check and (stage, run) != ("inspect", "control")) or (not control_check and stage != "prepare"):
                raise ValueError("identity outside verification")
        elif kind in ("attempted", "overflow", "overflow-report", "overlap") and stage != "probe":
            raise ValueError("range evidence outside failed probe")
        elif kind == "outcome" and (stage != stages[-1] or (not linked and not claimed)):
            raise ValueError("premature conclusion")
    if Counter(initial_pins) != Counter(PINS.items()):
        raise ValueError("incomplete initial input verification")

    def exact(kind, expected):
        if Counter(data[kind]) != Counter(expected):
            raise ValueError("incomplete or contradictory " + kind)

    workflow = [("provision", "success"), ("retrieve", "success"),
                ("measure", "success" if linked else "failure")]
    if interrupted:
        # The workflow collector writes its footer after the measurement stops.
        if data["workflow"] == [*workflow[:2], ("measure", "cancelled")]:
            workflow[-1] = ("measure", "cancelled")
        workflow = workflow[:len(data["workflow"])]
    exact("workflow", workflow)
    for kind, expected in (("runner", direct.RUNNER), ("revision", ("checkout", "d2x")),
                           ("tool", ("gcc", "ld", "make", "python"))):
        if Counter(row[0] for row in data[kind]) != Counter(list(expected)):
            raise ValueError("missing or contradictory " + kind)
    exact("pin", list(PINS.items()) + list(INPUTS.items()))
    exact("check", [("source-tar", direct.stock.SOURCE_HASH), ("r32", direct.stock.R32_HASH),
                    ("stock-elf", STOCK_ELF), ("map-normalised", STOCK_MAP)])
    builds = [("control", "recipes-completed"), ("control", "original-linked"), ("probe", "complete-link-invoked")]
    if linked:
        builds.extend([("probe", "recipes-completed"), ("probe", "original-linked")])
    exact("build", builds)
    logs = {(run, what) for run, what, _ in data["private-digest"]}
    required = {("control", "build-log"), ("control", "symbols"), ("probe", "build-log")}
    if not interrupted or ("prepare", "environment") in logs:
        required.add(("prepare", "environment"))  # written in the driver's finally block
    if linked:
        required.update({("probe", "symbols"), ("probe", "disassembly")})
    if required != logs or len(logs) != len(data["private-digest"]):
        raise ValueError("missing private evidence identities")
    for run in direct.RUN:
        expected = set(ARTIFACTS)
        if run == "control":
            expected -= {direct.DIP+n for n in OBJECTS}
        elif not linked:
            expected -= {direct.DIP+"dip-plugin"+ext for ext in (".elf", ".elf.orig")}
        artifacts = [(n, size, digest) for r, n, size, digest in data["artifact"] if r == run]
        if Counter(n for n, _, _ in artifacts) != Counter(expected) or any(not size for _, size, _ in artifacts):
            raise ValueError("incomplete artifact inventory")
        if run == "control" and not any(n == direct.DIP+"dip-plugin.elf.orig" and digest == STOCK_ELF
                                        for n, _, digest in artifacts):
            raise ValueError("wrong control ELF artifact")
    errors = [row for row in data["diagnostic"] if row[3] != "warning"]
    if (linked and errors) or any(row[:2] != ("link", "ld") or row[-1] != "region-range" for row in errors):
        raise ValueError("contradictory diagnostic")
    for run in (("control", "probe") if linked else ("control",)):
        validate_linked_layout(run, data)
    if linked:
        if any(data[k] for k in ("overflow", "attempted", "overflow-report", "overlap")):
            raise ValueError("failed-link evidence in linked result")
        exact("review", [(name, "manual-required") for name in CHECKLIST])
        selected = [(name, addr, size) for run, name, kind, addr, size, _ in data["symbol"]
                    if run == "probe" and name in STORAGE and kind in "bB"]
        if Counter((n, size) for n, _, size in selected) != Counter(STORAGE.items()):
            raise ValueError("missing selected storage")
        blocks = sorted((addr, addr+size) for _, addr, size in selected)
        bss = [(a, a+s) for r, n, a, s in data["section"] if r == "probe" and n == ".bss"]
        outside = any(a % 32 or not any(lo <= a and b <= hi for lo, hi in bss) for a, b in blocks)
        if outside or any(b > c for (_, b), (c, _) in zip(blocks, blocks[1:])):
            raise ValueError("invalid selected storage")
    else:
        if not errors or len(errors) != len(data["overflow-report"]) + len(data["overlap"]):
            raise ValueError("contradictory failed link")
        validate_overflow(data, interrupted)


def validate_linked_layout(run, data):
    from .experimental_dip_inspect import STOCK_SPAN
    loads = [row[1:] for row in data["load"] if row[0] == run]
    spans = [row[1:] for row in data["region"] if row[0] == run]
    if len(loads) != 3 or len({row[0] for row in loads}) != 3 or sorted(r[0] for r in spans) != ["exe", "ram"]:
        raise ValueError("missing linked layout")
    sections = [(n, a, s) for r, n, a, s in data["section"] if r == run]
    if not {".ios_info_table", ".init", ".text", ".bss"} <= {n for n, _, _ in sections}:
        raise ValueError("missing required sections")
    for region, (start, end) in direct.REGIONS.items():
        entries = sorted((a, s, n) for n, a, s in sections if start <= a < end)
        segments = [row for row in loads if row[1] == start]
        if len(segments) != 1:
            raise ValueError("missing regional LOAD")
        _, _, _, file_size, memory_size = segments[0]
        file_limit = start + file_size
        previous, file_end, gaps = start, start, []
        for a, size, name in entries:
            if a < previous:
                raise ValueError("overlapping linked sections")
            if a > previous:
                gaps.append((previous, a-previous))
            previous = a+size
            if name in direct.SECTIONS and name != ".bss" and previous > file_limit:
                raise ValueError("file-backed section exceeds LOAD")
            if (name == ".bss" and a < file_limit) or a < file_limit < previous:
                raise ValueError("section crosses file-backed boundary")
            if previous <= file_limit:
                file_end = previous
        used = previous-start
        if not used or file_end != file_limit or used != memory_size:
            raise ValueError("LOAD disagrees with sections")
        if region != "table":
            if not any(r[:2] == (region, used) for r in spans) or run == "control" and used != STOCK_SPAN[region]:
                raise ValueError("unmatched occupied span")
            if gaps != [(a, s) for r, reg, a, s in data["gap"] if (r, reg) == (run, region)]:
                raise ValueError("section gaps disagree")
    code = [(a, a+s) for n, a, s in sections if direct.EXPECTED_REGION.get(n) == "exe"]
    sites = [(a, max(s, 1)) for r, _, a, s in data["dependency"] if r == run]
    if run == "probe":
        sites += [(a, 4) for a, in data["literal-site"]]
    if any(not any(lo <= a and a+s <= hi for lo, hi in code) for a, s in sites):
        raise ValueError("site outside linked code")


def validate_overflow(data, interrupted):
    from .experimental_dip_inspect import SECTION_ORDER
    ranges = {}
    for region, name, lo, hi, excess in data["attempted"]:
        key = region, name
        if ranges.setdefault(key, (lo, hi, excess)) != (lo, hi, excess):
            raise ValueError("conflicting attempted extents")
    overflowing = set()
    for region in ("exe", "ram"):
        start, limit = direct.REGIONS[region]
        previous = start
        for name in SECTION_ORDER[region]:
            extent = ranges.get((region, name))
            if (not extent or extent[0] < previous or (extent[0] == extent[1] and name != ".rodata")
                    or (name == SECTION_ORDER[region][0] and extent[0] != start)):
                raise ValueError("incomplete attempted map")
            previous = extent[1]
        if previous > limit:
            overflowing.add(region)
        total = ranges.get((region, "region"))
        if total and total != (start, previous, max(0, previous-limit)):
            raise ValueError("region count disagrees with sections")
    confirmed = []
    for region, name, count, reported_end in data["overflow-report"]:
        extent = ranges.get((region, name))
        if not extent or not extent[2] or count not in (None, extent[2]) or reported_end not in (None, extent[1]):
            raise ValueError("uncorroborated range diagnostic")
        confirmed.append((region, name, *extent))
    if not confirmed or {r[0] for r in confirmed} != overflowing:
        raise ValueError("unreported or unsupported regional overflow")
    # The producer corroborates all reports before writing its first affirmative
    # row. Interruption can leave a prefix of that final sequence.
    if interrupted:
        confirmed = confirmed[:len(data["overflow"])]
    if data["overflow"] != confirmed:
        raise ValueError("unsupported overflow conclusion")
    for left, lo, hi, right, a, b in data["overlap"]:
        if (left == right or max(lo, a) >= min(hi, b)
                or any(ranges.get((direct.EXPECTED_REGION[n], n), ())[:2] != (x, y)
                       for n, x, y in ((left, lo, hi), (right, a, b)))):
            raise ValueError("unsupported overlap")


def layout_evidence(run, sections, symbols, journal):
    for region in ("exe", "ram"):
        origin, limit = direct.REGIONS[region]
        previous = origin
        for address, size in sorted((a, s) for _, a, s, _ in sections if origin <= a < limit):
            if address > previous:
                journal.write("gap", run, region, previous, address - previous)
            previous = address + size
    for name, (kind, addr, size, _) in symbols.items():
        if kind not in "tT":
            continue
        if name.endswith(("_veneer", "_from_arm", "_from_thumb")):
            journal.write("dependency", run, "interworking-veneer", addr, size)
        elif name.startswith(("__aeabi_", "__gnu_")) or re.fullmatch(
            r"__(?:u?div|u?mod|mul|ashl|ashr|lshr)(?:si|di)3", name
        ):
            journal.write("dependency", run, "compiler-helper", addr, size)


def literal_evidence(listing, journal):
    origin, limit = direct.REGIONS["exe"]
    for addr, row in sorted(listing.code.items()):
        if origin <= addr < limit and row.op == ".word":
            journal.write("literal-site", addr)


def journal_at(path):
    return direct.Journal(path, sys.modules[__name__])


def require_dispatch(env, head):
    owner = "lloydsmart"
    repo = owner + "/wii-netdisc"
    ref = "refs/heads/develop"
    approved = env.get("APPROVED_SHA", "")
    expected = dict(GITHUB_EVENT_NAME="workflow_dispatch", GITHUB_REPOSITORY=repo,
                    GITHUB_REPOSITORY_OWNER=owner, GITHUB_ACTOR=owner, GITHUB_TRIGGERING_ACTOR=owner,
                    GITHUB_REF=ref, GITHUB_RUN_ATTEMPT="1", GITHUB_SHA=approved, GITHUB_WORKFLOW_SHA=approved,
                    GITHUB_WORKFLOW_REF=f"{repo}/.github/workflows/experimental-adapter.yml@{ref}")
    if not re.fullmatch(r"[0-9a-f]{40}", approved) or approved != head or any(
        env.get(k) != v for k, v in expected.items()
    ):
        raise ValueError("adapter sizing requires the exact approved first owner dispatch")


def main(args):
    if args == ["build"]:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=direct.stock.ROOT, text=True).strip()
        require_dispatch(os.environ, head)
        return paired.main(sys.modules[__name__])
    if len(args) == 2 and args[0] == "collect":
        temp = Path(args[1]).resolve()
        direct.collect(temp / "dip-sizing-evidence", temp / "dip-sizing-public", SCHEMA, INPUTS)
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            print("ready=true", file=out)
        return 0
    raise ValueError("expected build or collect RUNNER_TEMP")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
