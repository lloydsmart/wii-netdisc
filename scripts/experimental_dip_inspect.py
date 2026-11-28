"""Reconcile a complete original ELF. Report partial linker diagnostics separately."""

from collections import defaultdict
import hashlib
from io import StringIO
import re
import struct
import subprocess

from .dip_footprint import REGIONS, measure, parse_map, plain_text
from .experimental_dip_evidence import SECTIONS
from .experimental_dip_flow import disassembly, path_evidence, public_name
from .stock_dip_build import DIP, digest

STOCK_ELF = "70623d5af228957d031691e32229b47e5bdc0b950e158d795daaba1125b7e63f"
STOCK_MAP = "2edd3b7e30bfef7d4e766222d8c67c681771d4db89101971c83029f9b5c5a1ff"
STOCK_SPAN = {"exe": 6708, "ram": 246912}
STOCK_TOOLS = "/home/runner/work/_temp/stock-dip/devkitARM"


class ControlMismatch(ValueError):
    pass


def control_identity(elf_hash, map_bytes, toolchain, spans, journal):
    # The historical GNU ld map spells out the absolute libgcc archive path.
    canonical = map_bytes.replace((str(toolchain) + "/").encode(), (STOCK_TOOLS + "/").encode())
    map_hash = hashlib.sha256(canonical).hexdigest()
    journal.write("check", "map-normalised", map_hash)
    journal.write("check", "stock-elf", elf_hash)
    if (elf_hash, map_hash, spans) != (STOCK_ELF, STOCK_MAP, STOCK_SPAN):
        raise ControlMismatch("original ELF, path-normalised map or occupied spans differ")


def layout(elf, link_map):
    # Stock section/LOAD reconciliation stays mandatory. Also reject trailing
    # p_memsz/p_filesz and physical extents outside either measured region.
    map_data = measure(elf, link_map, StringIO())
    data = elf.read_bytes()
    phoff, shoff = struct.unpack_from(">II", data, 28)
    phnum, _, shnum, names = struct.unpack_from(">4H", data, 44)
    headers = [struct.unpack_from(">10I", data, shoff + 40*i) for i in range(shnum)]
    strings = headers[names][4]
    sections = []
    for name, kind, flags, addr, _, size, *_ in headers:
        if flags & 2 and size:
            label = data[strings+name:data.index(0, strings+name)].decode("ascii")
            sections.append((label, addr, size, kind))
    loads = []
    for i in range(phnum):
        kind, _, vma, paddr, filesz, memsz, _, _ = struct.unpack_from(">8I", data, phoff+32*i)
        if kind == 1 and memsz:
            loads.append((i, vma, paddr, filesz, memsz))
    spans = {}
    for region, (start, limit) in REGIONS.items():
        entries = [(a+n, k) for _, a, n, k in sections if start <= a < limit]
        end = max(a for a, _ in entries)
        file_end = max((a for a, k in entries if k != 8), default=start)
        extents = [(v, p, f, m) for _, v, p, f, m in loads if start <= v < limit]
        if extents != [(start, start, file_end-start, end-start)]:
            raise ValueError("unreconciled " + region + " LOAD")
        if region != "table":
            spans[region] = end-start
    if len(loads) != len(REGIONS):
        raise ValueError("unexpected LOAD count")
    return map_data, spans, sections, loads


def list_symbols(listing):
    symbols = {}
    instances = defaultdict(int)
    for line in listing.splitlines():
        m = re.fullmatch(r"([\da-fA-F]+)\s+(?:([\da-fA-F]+)\s+)?([tTbBrRdD])\s+(\S+)", line)
        if m:
            addr, size, kind, name = m.groups()
            # nm -n orders identically named file-local objects by address.
            instances[name] += 1
            if instances[name] > 1:
                if not kind.islower():
                    raise ValueError("ambiguous global symbol " + name)
                name = f"{name}@{instances[name]}"
            symbols[name] = (kind, int(addr, 16), int(size or "0", 16))
    if not symbols:
        raise ValueError("empty linked symbol listing")
    return symbols


def fingerprints(elf, symbols):
    """Hash sized, file-backed symbol ranges (nm omits sizes for some assembly labels)."""
    data = elf.read_bytes()
    phoff = struct.unpack_from(">I", data, 28)[0]
    count = struct.unpack_from(">H", data, 44)[0]
    loads = [struct.unpack_from(">8I", data, phoff+32*i) for i in range(count)]
    result = {}
    for name, (kind, addr, size) in symbols.items():
        digest_value = None
        if size and kind.lower() != "b":
            for tag, off, start, _, file_size, *_ in loads:
                if tag == 1 and start <= addr and addr+size <= start+file_size:
                    begin = off+addr-start
                    digest_value = hashlib.sha256(data[begin:begin+size]).hexdigest()
                    break
            if digest_value is None:
                raise ValueError("unmapped file-backed symbol " + name)
        result[name] = (kind, addr, size, digest_value)
    return result


def private_listing(root, toolchain, label, args, elf, journal):
    path = root.parent / (root.name + "-" + label + ".txt")
    with path.open("wb") as out, (root.parent / "inspection.log").open("ab") as err:
        subprocess.run([toolchain / ("bin/arm-eabi-" + args[0]), *args[1:], elf],
                       stdout=out, stderr=err, check=True)
    journal.write("private-digest", root.name, label, digest(path))
    return path.read_text("ascii")


def inspect(root, toolchain, journal, control=None):
    run = root.name
    elf, link_map = [root / DIP.with_suffix(ext) for ext in (".elf.orig", ".map")]
    map_data, spans, sections, loads = layout(elf, link_map)
    for row in loads:
        journal.write("load", run, *row)
    for name, addr, size, _ in sections:
        journal.write("section", run, name if name in SECTIONS else "other", addr, size)
    for name, occupied in spans.items():
        start, end = REGIONS[name]
        journal.write("region", run, name, occupied, occupied-STOCK_SPAN[name], end-start-occupied)
    if control is None:
        control_identity(digest(elf), map_data, toolchain, spans, journal)
    for addr, size in re.findall(rb"^ \*fill\*\s+(0x[\da-f]+)\s+(0x[\da-f]+)", map_data, re.M):
        journal.write("fill", run, int(addr, 16), int(size, 16))
    symbols = list_symbols(private_listing(root, toolchain, "symbols", ["nm", "-nS"], elf, journal))
    symbols = fingerprints(elf, symbols)
    inventory = getattr(journal.policy, "layout_evidence", None)
    if inventory:
        inventory(run, sections, symbols, journal)
    for name, (kind, addr, size, checksum) in symbols.items():
        journal.write("symbol", run, public_name(name, journal.policy.SYMBOLS), kind, addr, size, checksum or "unknown")
    if control is not None:
        for name in sorted(control.keys() | symbols.keys()):
            before, after = control.get(name), symbols.get(name)
            if before != after:
                why = "added" if before is None else "removed" if after is None else "changed"
                journal.write("delta", public_name(name, journal.policy.SYMBOLS), why, before[1] if before else 0,
                              after[1] if after else 0, before[2] if before else 0, after[2] if after else 0)
        asm = private_listing(root, toolchain, "disassembly", ["objdump", "-dz"], elf, journal)
        listing = disassembly(asm)
        path_evidence(listing, journal)
        inventory_literals = getattr(journal.policy, "literal_evidence", None)
        if inventory_literals:
            inventory_literals(listing, journal)
        if any(n not in symbols for n in control if not n.endswith(("_veneer", "_from_thumb", "_from_arm"))):
            raise ValueError("stock symbol disappeared")
        allocations = []
        for name, expected in journal.policy.STORAGE.items():
            kind, addr, size, _ = symbols[name]
            if kind not in "Bb" or size != expected or addr % 32 or not any(
                n == ".bss" and a <= addr and addr+size <= a+s for n, a, s, _ in sections
            ):
                raise ValueError("unreconciled static allocation: " + name)
            allocations.append((addr, addr + size))
        allocations.sort()
        if any(left[1] > right[0] for left, right in zip(allocations, allocations[1:])):
            raise ValueError("overlapping static allocations")
    return symbols


class OverflowUnresolved(ValueError):
    """The failed build has range diagnostics which cannot all be corroborated."""


SECTION_ORDER = {"table": (".ios_info_table",), "exe": (".init", ".text"),
                 "ram": (".data", ".rodata", ".bss")}


def attempted_ranges(path):
    raw = plain_text(path.read_bytes())
    config = raw.partition("Linker script and memory map")[0]
    if any(len(re.findall(rf"^{name}\s+0x", config, re.M)) != 1 for name in REGIONS):
        raise OverflowUnresolved("ambiguous memory configuration")
    outputs = parse_map(raw)
    ranges = {}
    for (name, addr, size), lma in outputs.items():
        if name not in SECTIONS:
            if size == 0 or (addr == 0 and name in {".ARM.attributes", ".comment"}):
                continue
            raise OverflowUnresolved("unclassified output range")
        if name in ranges or lma != addr or addr + size > 0xffffffff or (not size and name != ".rodata"):
            raise OverflowUnresolved("ambiguous output range")
        ranges[name] = (addr, addr + size)
    for region, order in SECTION_ORDER.items():
        origin, limit = REGIONS[region]
        prev = origin
        for name in order:
            lo, hi = ranges[name]
            if lo < prev or (name == order[0] and lo != origin):
                raise OverflowUnresolved("section order or origin")
            prev = hi
        if region == "table" and prev > limit:
            raise OverflowUnresolved("unmeasured table overflow")
    return ranges


def overflow(log, link_map, journal):
    """Check every range report before emitting any corroborated no-fit rows."""
    reports, overlaps = [], []
    unsupported = False
    for line in log.splitlines():
        if not re.search(r"\bregion\b|\boverflow(?:ed)?\b|will not fit|overlaps section", line, re.I):
            continue
        if not (re.match(r"^\S*\bld:", line) or
                re.match(r"^\s*(?:region |(?:address 0x[0-9a-f]+ of )?\S+ section )", line)):
            continue
        section = re.fullmatch(r"\S*\bld: (?:\S+ )?section [`']([^']+)' will not fit in region [`']([^']+)'\s*", line)
        count = re.fullmatch(r"\S*\bld: region [`']([^']+)' overflowed by (\d+) bytes?\s*", line)
        address = re.fullmatch(r"\S*\bld: address (0x[0-9a-f]+) of \S+ section [`']([^']+)'"
                               r" is not within region [`']([^']+)'\s*", line)
        overlap = re.fullmatch(r"\S*\bld: section (\S+) loaded at \[((?:0x)?[0-9a-f]+),((?:0x)?[0-9a-f]+)\]"
                               r" overlaps section (\S+) loaded at \[((?:0x)?[0-9a-f]+),((?:0x)?[0-9a-f]+)\]", line)
        if overlap:
            left, lo, hi, right, start, end = overlap.groups()
            # ld prints inclusive load addresses. Map extents are half-open.
            overlaps.append((left, int(lo, 16), int(hi, 16)+1, right, int(start, 16), int(end, 16)+1))
            continue
        attempted_end = None
        if address:
            value, name, region = address.groups()
            attempted_end = int(value, 16)
            if attempted_end > 0xffffffff:
                unsupported = True
                continue
            amount = None
        elif section:
            name, region = section.groups()
            amount = None
        elif count:
            region, value = count.groups()
            if len(value) > 10 or int(value) > 0xffffffff:
                unsupported = True
                continue
            name, amount = "region", int(value)
        else:
            unsupported = True
            continue
        reports.append((region, name, amount, attempted_end))
        section_id = "region" if amount is not None else name if name in SECTIONS else "other"
        journal.write("overflow-report", region if region in ("exe", "ram") else "other",
                      section_id, amount, attempted_end)
    if unsupported:
        journal.write("diagnostic", "link", "ld", 0, "error", "unsupported-overflow")
    if not reports and not overlaps and not unsupported:
        return []
    # A companion error can independently invalidate the partial layout. Allow
    # the usual collect2/make failure summaries, but no unexplained ld errors.
    errors = "\n".join(line for line in log.splitlines()
                       if not re.fullmatch(r"collect2: (?:error: )?ld returned \d+ exit status", line))
    other_error = re.search(r"undefined reference|multiple definition|file format not recognized|"
                            r"relocation truncated|cannot find |internal compiler error|(?:fatal )?error:", errors, re.I)
    unknown_ld = any(re.match(r"^\S*\bld: ", line) and "will not fit in region" not in line
                     and " is not within region " not in line and " overflowed by " not in line
                     and " overlaps section " not in line for line in log.splitlines())
    inconsistent = bool(unsupported or other_error or unknown_ld)
    try:
        ranges = attempted_ranges(link_map)
    except (OSError, ValueError, KeyError) as exc:
        raise OverflowUnresolved("unresolved attempted ranges") from exc
    # An overlap may accompany a real region overflow. It cannot establish
    # a region verdict by itself, and every printed endpoint must agree.
    for left, lo, hi, right, start, end in overlaps:
        if (left == right or ranges.get(left) != (lo, hi) or ranges.get(right) != (start, end)
                or max(lo, start) >= min(hi, end)):
            inconsistent = True
        else:
            journal.write("overlap", left, lo, hi, right, start, end)
    evidence = []
    for region, name, reported, attempted_end in reports:
        if region not in ("exe", "ram"):
            inconsistent = True
            continue
        origin, limit = REGIONS[region]
        if reported is not None:
            occupied = (ranges[n] for n in SECTION_ORDER[region])
            lo, hi = origin, max(end for start, end in occupied if end > start)
        elif name in SECTION_ORDER[region]:
            lo, hi = ranges[name]
        else:
            inconsistent = True
            continue
        excess = max(0, hi-limit)
        row = region, name, lo, hi, excess
        journal.write("attempted", *row)
        if (not excess or hi <= lo or (name == "region" and reported != excess)
                or (attempted_end is not None and attempted_end != hi)):
            inconsistent = True
        evidence.append(row)
    overflowing = {region for region in ("exe", "ram")
                   if any(ranges[n][1] > REGIONS[region][1] for n in SECTION_ORDER[region])}
    if {row[0] for row in evidence} != overflowing:
        inconsistent = True
    if "literal-site" in journal.policy.SCHEMA:
        # Retain the map extents behind regional counts and companion overlaps.
        for region in ("exe", "ram"):
            _, limit = REGIONS[region]
            for name in SECTION_ORDER[region]:
                lo, hi = ranges[name]
                row = region, name, lo, hi, max(0, hi-limit)
                if row not in evidence:
                    journal.write("attempted", *row)
    if inconsistent or not evidence:
        raise OverflowUnresolved("contradictory or unsupported diagnostics")
    return evidence
