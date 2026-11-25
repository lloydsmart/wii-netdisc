"""Measure the stock ELF32 big-endian ARM link against its GNU ld map."""

import re
import struct
from pathlib import Path

REGIONS = {
    "table": (0, 0x4000),
    "exe": (0x13800000, 0x13802000),
    "ram": (0x13802000, 0x13842000),
}

EXPECTED_REGION = {
    ".ios_info_table": "table", ".init": "exe", ".text": "exe",
    ".data": "ram", ".rodata": "ram", ".bss": "ram",
}

# Explicit AT addresses in the pinned source/dip-plugin/link.ld.
STOCK_LOAD_ADDRESS = {".init": 0x13800000, ".data": 0x13802000}


def plain_text(data):
    value = data.decode("utf-8")
    if any(not (c.isprintable() or c in "\t\r\n") for c in value):
        raise ValueError("disallowed control character in text evidence")
    return value


def parse_map(map_text):
    memory, separator, layout = map_text.partition("Linker script and memory map")
    if not separator:
        raise ValueError("missing linker map layout")
    for region, (start, end) in REGIONS.items():
        row = re.search(rf"^{region}\s+(0x\w+)\s+(0x\w+)", memory, re.MULTILINE)
        if not row or tuple(int(v, 16) for v in row.groups()) != (start, end - start):
            raise ValueError(f"unexpected map bounds for {region}")
    # Output sections start in column zero. GNU ld wraps long output names.
    output_row = re.compile(
        r"(\S+)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)(?:\s+load address (0x[0-9a-fA-F]+))?"
    )
    outputs = {}
    lines = iter(layout.splitlines())
    for line in lines:
        if not line or line[0].isspace():
            continue  # Input sections, symbols and fill inside the output section.
        if line.startswith(("LOAD ", "OUTPUT(", "START GROUP", "END GROUP", "/DISCARD/")):
            continue
        if len(line.split()) == 1:
            continuation = next(lines, "")
            if continuation.lstrip().startswith("*("):
                continue  # GNU ld emits a selector alone for an unused output.
            line += " " + continuation
        match = output_row.fullmatch(line.strip())
        if not match:
            raise ValueError(f"unrecognised linker map output: {line!r}")
        name, addr, size, lma = match.groups()
        key = name, int(addr, 16), int(size, 16)
        if key in outputs:
            raise ValueError(f"duplicate map entry {key}")
        outputs[key] = int(lma or addr, 16)
    if not outputs:
        raise ValueError("empty map layout")
    return outputs


def measure(original: Path, linker_map: Path, report):
    data = original.read_bytes()
    if data[:7] != b"\x7fELF\x01\x02\x01":
        raise ValueError("expected ELF32 big-endian input")
    (etype, machine, _, _, phoff, shoff, _, _, phsize, phnum, shsize,
     shnum, names_index) = struct.unpack_from(">HHIIIIIHHHHHH", data, 16)
    if (etype, machine, phsize, shsize) != (2, 40, 32, 40):
        raise ValueError("expected ARM executable with ELF32 program and section headers")

    # ELF32 program headers: type, file offset, VMA, physical address,
    # file size, memory size, flags and alignment.
    loads = []
    for i in range(phnum):
        kind, off, vma, paddr, filesz, memsz, _, _ = struct.unpack_from(
            ">8I", data, phoff + i * phsize
        )
        if kind == 1:  # PT_LOAD
            if filesz > memsz or (filesz and off + filesz > len(data)):
                raise ValueError(f"invalid LOAD {i} extent")
            loads.append((i, off, vma, paddr, filesz, memsz))
            print(f"LOAD {i} offset={off:#x} vma={vma:#010x} paddr={paddr:#010x} "
                  f"filesz={filesz} memsz={memsz}", file=report)

    sections = [struct.unpack_from(">10I", data, shoff + i * shsize) for i in range(shnum)]
    strings_offset, strings_size = sections[names_index][4:6]
    if strings_offset + strings_size > len(data):
        raise ValueError("truncated ELF section name table")
    names = data[strings_offset:strings_offset + strings_size]
    map_bytes = linker_map.read_bytes()
    map_sections = parse_map(plain_text(map_bytes))
    matched = set()
    anchors = {i: [] for i, *_ in loads}
    allocated = []
    high = {key: start for key, (start, _) in REGIONS.items()}
    ram_bytes = bss_bytes = 0
    seen = set()
    for name_off, kind, flags, addr, off, size, _, _, align, _ in sections:
        name = names[name_off:names.index(0, name_off)].decode("ascii")
        key = name, addr, size
        if not flags & 2:  # Non-allocated output sections can have a VMA of zero.
            if size and name in EXPECTED_REGION:
                raise ValueError(f"stock section {name} is not allocated")
            matched.add(key)
            continue
        if not size:
            continue
        end = addr + size
        region = next((key for key, (a, b) in REGIONS.items() if a <= addr < b and end <= b), None)
        if region is None or (name, addr, size) not in map_sections:
            raise ValueError(f"{name} {addr:#x}+{size:#x} outside region or disagrees with map")
        matched.add(key)
        if name in EXPECTED_REGION and region != EXPECTED_REGION[name]:
            raise ValueError(f"{name} belongs in {EXPECTED_REGION[name]}, found in {region}")
        if any(addr < stop and start < end for start, stop in allocated):
            raise ValueError(f"overlapping allocated section {name}")
        allocated.append((addr, end))
        if align and (align & (align - 1) or addr % align):
            raise ValueError(f"misaligned section {name}")
        nobits = kind == 8  # SHT_NOBITS consumes memory only
        load_addr = map_sections[name, addr, size]
        if name in EXPECTED_REGION and nobits != (name == ".bss"):
            raise ValueError(f"unexpected stock storage type for {name}")
        if nobits and any(filesz and (addr < vma + filesz and vma < end or
                                      load_addr < paddr + filesz and paddr < load_addr + size)
                          for _, _, vma, paddr, filesz, _ in loads):
            raise ValueError(f"file-backed LOAD bytes overlap memory-only {name}")
        covering = []
        for i, offset, vma, paddr, filesz, memsz in loads:
            if not (vma <= addr and end <= vma + memsz):
                continue
            displacement = addr - vma
            if not nobits and (end > vma + filesz or off - offset != displacement):
                continue
            section_lma = paddr + displacement
            if name in STOCK_LOAD_ADDRESS and section_lma != STOCK_LOAD_ADDRESS[name]:
                raise ValueError(f"{name} physical load address {section_lma:#010x} in LOAD {i}; "
                                 f"stock linker script requires {STOCK_LOAD_ADDRESS[name]:#010x}")
            if section_lma == load_addr:
                covering.append(i)
        if not covering:
            raise ValueError(f"{name} missing matching PT_LOAD extent")
        for i in covering:
            anchors[i].append((addr, end))
        print(f"{region} {name} [{addr:#010x}, {end:#010x}) size={size} align={align} "
              f"{'NOBITS' if nobits else 'file-backed'} LOAD={covering}", file=report)
        high[region] = max(high[region], end)
        seen.add(name)
        if region == "ram":
            ram_bytes += size
            if nobits:
                bss_bytes += size

    required = {".ios_info_table", ".init", ".text", ".bss"}
    if required - seen or not bss_bytes:
        raise ValueError(f"incomplete stock layout: missing {sorted(required - seen)} or memory-only BSS")
    exe_start, exe_end = REGIONS["exe"]
    for name, addr, size in sorted(map_sections.keys() - matched):
        if size:
            raise ValueError(f"map output {name} {addr:#x}+{size:#x} has no matching ELF section")

    # Interior gaps between mapped sections include alignment and region padding.
    # A segment reaching into trailing headroom needs section evidence on both
    # sides of that gap. Segment alignment alone cannot explain a trailing extent.
    for i, off, vma, paddr, filesz, memsz in loads:
        if not memsz:
            continue
        if not anchors[i]:
            raise ValueError(f"LOAD {i} has no matching allocated section")
        for base in {vma, paddr}:
            start, end = max(base, high["exe"]), min(base + memsz, exe_end)
            if start < end:
                first = min(a for a, _ in anchors[i]) + base - vma
                last = max(b for _, b in anchors[i]) + base - vma
                if start < first or end > last:
                    raise ValueError(f"unexplained LOAD {i} extent [{start:#x}, {end:#x}) in linker headroom")
                if any(a + base - vma < end and start < b + base - vma for a, b in anchors[i]):
                    raise ValueError(f"LOAD {i} places section content in linker headroom")
                file_end = min(end, base + filesz)
                if start < file_end and any(data[off + start - base:off + file_end - base]):
                    raise ValueError(f"unexplained file contents in LOAD {i} linker headroom")
                print(f"LOAD {i} spans inter-section padding [{start:#x}, {end:#x})", file=report)
    print(f"Executable occupied span [{exe_start:#010x}, {high['exe']:#010x}): "
          f"{high['exe'] - exe_start} bytes", file=report)
    print(f"Contiguous trailing executable headroom: {exe_end - high['exe']} bytes", file=report)
    print(f"Static RAM: span={high['ram'] - REGIONS['ram'][0]} bytes, "
          f"allocated sections={ram_bytes}, file-backed={ram_bytes - bss_bytes}, "
          f"memory-only={bss_bytes}", file=report)
    return map_bytes
