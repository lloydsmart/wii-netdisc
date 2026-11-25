"""Measurement regressions using synthetic bytes only."""

from io import StringIO
from pathlib import Path
import os
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import stock_dip_build as build
from scripts.dip_footprint import measure
from scripts.stock_dip_build import REQUIRED, compare, inventory


def footprint_fixture(root, *, exe=0x13800000, ram=0x13802000, ram_filesz=4, extra_load=None,
                      zero_lma_segment=None):
    # Four disjoint file areas: headers, section names, payloads, section table.
    data = bytearray(1024)
    names = b"\0.shstrtab\0.ios_info_table\0.init\0.text\0.linker_tail\0.data\0.bss\0"
    data[192:192 + len(names)] = names
    sections = [
        ("", 0, 0, 0, 0, 0, 0),
        (".shstrtab", 3, 0, 0, 192, len(names), 1),
        (".ios_info_table", 1, 6, 0, 320, 4, 4),
        (".init", 1, 6, exe, 384, 4, 4),
        (".text", 1, 6, exe + 16, 400, 12, 16),
        (".linker_tail", 1, 2, exe + 32, 416, 4, 16),
        (".data", 1, 3, ram, 448, 4, 4),
        (".bss", 8, 3, ram + 8, 452, 20, 8),
    ]
    data[:7] = b"\x7fELF\x01\x02\x01"
    struct.pack_into(">HHIIIIIHHHHHH", data, 16, 2, 40, 1, exe, 52, 512, 0,
                     52, 32, 3 + int(extra_load is not None), 40, len(sections), 1)
    loads = [(320, 0, 4, 4), (384, exe, 36, 36), (448, ram, ram_filesz, 28)]
    if extra_load:
        loads.append(extra_load)
    for i, (off, addr, file_size, memory_size) in enumerate(loads):
        paddr = 0 if i == zero_lma_segment else addr
        struct.pack_into(">8I", data, 52 + 32*i, 1, off, addr, paddr, file_size, memory_size, 7, 4)
    layout = ["table 0x0 0x4000", "exe 0x13800000 0x2000", "ram 0x13802000 0x40000",
              "Linker script and memory map"]
    for i, (name, kind, flags, addr, off, size, align) in enumerate(sections):
        struct.pack_into(">10I", data, 512 + 40*i, names.index(name.encode()), kind,
                         flags, addr, off, size, 0, 0, align, 0)
        if flags:
            layout.append(f"{name}\n                {addr:#010x} {size:#x}")
            if zero_lma_segment is not None:
                _, base, _, extent = loads[zero_lma_segment]
                if base <= addr < base + extent:
                    layout[-1] += f" load address {addr - base:#010x}"
    original, linker_map = root / "sample.elf.orig", root / "sample.map"
    original.write_bytes(data)
    linker_map.write_text("\n".join(layout) + "\n")
    return original, linker_map


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)

    def test_section_span_includes_padding_and_allocated_linker_tail(self):
        original, linker_map = footprint_fixture(self.root)
        log = StringIO()
        measure(original, linker_map, log)
        self.assertIn("table .ios_info_table [0x00000000, 0x00000004)", log.getvalue())
        self.assertIn("0x13800024): 36 bytes", log.getvalue())
        self.assertIn("headroom: 8156 bytes", log.getvalue())
        self.assertIn("span=28 bytes, allocated sections=24, file-backed=4, memory-only=20", log.getvalue())

    def test_map_disagreement(self):
        original, linker_map = footprint_fixture(self.root)
        linker_map.write_text(linker_map.read_text().replace("0x13800020", "0x13800024"))
        with self.assertRaisesRegex(ValueError, ".linker_tail.*disagrees with map"):
            measure(original, linker_map, StringIO())

    def test_bss_requires_memory_segment_coverage(self):
        original, linker_map = footprint_fixture(self.root)
        data = bytearray(original.read_bytes())
        struct.pack_into(">I", data, 52 + 2 * 32 + 20, 4)  # Shorten last PT_LOAD p_memsz.
        original.write_bytes(data)
        with self.assertRaisesRegex(ValueError, ".bss missing matching PT_LOAD"):
            measure(original, linker_map, StringIO())

    def rejected_measurement(self, original, linker_map, reason):
        report = StringIO()
        with self.assertRaisesRegex(ValueError, reason):
            measure(original, linker_map, report)
        self.assertNotIn("headroom:", report.getvalue())
        self.assertNotIn("Executable occupied span", report.getvalue())

    def test_unmatched_map_and_load_in_final_16_bytes(self):
        original, linker_map = footprint_fixture(self.root, extra_load=(464, 0x13801ff0, 16, 16))
        with linker_map.open("a") as out:
            print("unreported 0x13801ff0 0x10", file=out)
        self.rejected_measurement(original, linker_map, "unreported.*no matching ELF section")

    def test_segment_alone_in_headroom(self):
        files = footprint_fixture(self.root, extra_load=(464, 0x13801ff0, 16, 16))
        self.rejected_measurement(*files, "LOAD 3 has no matching allocated section")

    def test_segment_extends_past_final_section(self):
        original, linker_map = footprint_fixture(self.root)
        data = bytearray(original.read_bytes())
        struct.pack_into(">II", data, 52 + 32 + 16, 40, 40)
        original.write_bytes(data)
        self.rejected_measurement(original, linker_map, "unexplained LOAD 1 extent")

    def test_stock_code_in_table(self):
        self.rejected_measurement(*footprint_fixture(self.root, exe=0x1000), ".init belongs in exe")

    def test_stock_data_in_executable_region(self):
        self.rejected_measurement(*footprint_fixture(self.root, ram=0x13801000), ".data belongs in ram")

    def test_zero_stock_physical_addresses(self):
        from scripts.stock_dip_evidence import collect

        work = self.root / "stock-dip"
        evidence = work / "evidence"
        evidence.mkdir(parents=True)
        for run, section, segment in (("a", ".init", 1), ("b", ".data", 2)):
            plugin = work / run / build.DIP.parent
            plugin.mkdir(parents=True)
            original, linker_map = footprint_fixture(plugin, zero_lma_segment=segment)
            original = original.rename(work / run / build.DIP.with_suffix(".elf.orig"))
            # Offer the contradictory map directly to the real publication check.
            linker_map = linker_map.rename(evidence / f"{run}.map")
            with self.subTest(section=section):
                self.rejected_measurement(original, linker_map, f"{section}.*physical load address")
        rejected = collect(self.root)
        self.assertEqual(len(rejected), 2)
        self.assertEqual(list((self.root / "stock-dip-public").iterdir()), [])

    def test_file_bytes_overlapping_bss(self):
        self.rejected_measurement(*footprint_fixture(self.root, ram_filesz=28), "file-backed LOAD bytes")

    def test_second_segment_overlapping_bss(self):
        files = footprint_fixture(self.root, extra_load=(464, 0x13802018, 4, 4))
        self.rejected_measurement(*files, "file-backed LOAD bytes")

    def test_required_bss_has_nobits_type(self):
        original, linker_map = footprint_fixture(self.root)
        data = bytearray(original.read_bytes())
        # A file-backed .bss plus an unrelated, genuinely memory-only RAM
        # section. The sum of all NOBITS sizes used to mask the stock BSS error.
        struct.pack_into(">I", data, 512 + 7 * 40 + 4, 1)
        struct.pack_into(">I", data, 512 + 7 * 40 + 16, 456)
        struct.pack_into(">IIII", data, 512 + 5 * 40 + 4, 8, 2, 0x1380201c, 476)
        struct.pack_into(">I", data, 512 + 5 * 40 + 32, 4)
        struct.pack_into(">II", data, 52 + 32 + 16, 28, 28)
        struct.pack_into(">II", data, 52 + 64 + 16, 28, 32)
        linker_map.write_text(linker_map.read_text().replace("0x13800020 0x4", "0x1380201c 0x4"))
        original.write_bytes(data)
        self.rejected_measurement(original, linker_map, "stock storage type for .bss")

    def test_segment_bridging_executable_and_ram(self):
        original, linker_map = footprint_fixture(self.root)
        data = bytearray(original.read_bytes())
        # One segment includes zero padding between the final code and the
        # next region. Move the section headers out of the padding.
        headers = data[512:832]
        data = data[:420] + bytearray(384 + 8192 + 4 - 420)
        struct.pack_into(">I", data, 32, len(data))
        struct.pack_into(">I", headers, 6 * 40 + 16, 384 + 8192)
        struct.pack_into(">I", headers, 7 * 40 + 16, 384 + 8192 + 4)
        struct.pack_into(">H", data, 44, 2)
        struct.pack_into(">II", data, 52 + 32 + 16, 8192 + 4, 8192 + 28)
        data.extend(headers)
        original.write_bytes(data)
        report = StringIO()
        measure(original, linker_map, report)
        self.assertIn("inter-section padding", report.getvalue())
        self.assertIn("headroom: 8156 bytes", report.getvalue())
        data[421] = 0xff
        original.write_bytes(data)
        self.rejected_measurement(original, linker_map, "unexplained file contents")

    def test_zero_nonallocated_and_unemitted_map_outputs(self):
        original, linker_map = footprint_fixture(self.root, ram_filesz=8)  # Padding before BSS.
        with linker_map.open("a") as out:
            print(".empty 0x13802000 0x0", ".unused", " *(.unused)", sep="\n", file=out)
            size = struct.unpack_from(">I", original.read_bytes(), 512 + 40 + 20)[0]
            print(f".shstrtab 0x0 {size:#x}", file=out)
        report = StringIO()
        measure(original, linker_map, report)
        self.assertIn("headroom: 8156 bytes", report.getvalue())

    def test_exact_executable_end_and_region_overflow(self):
        original, linker_map = footprint_fixture(self.root)
        data = bytearray(original.read_bytes())
        # Move the linker-created section into a separate segment at the boundary.
        struct.pack_into(">H", data, 44, 4)
        struct.pack_into(">8I", data, 52 + 3 * 32, 1, 416, 0x13801ff0, 0x13801ff0, 16, 16, 5, 16)
        struct.pack_into(">III", data, 512 + 5 * 40 + 12, 0x13801ff0, 416, 16)
        original.write_bytes(data)
        linker_map.write_text(linker_map.read_text().replace("0x13800020 0x4", "0x13801ff0 0x10"))
        report = StringIO()
        measure(original, linker_map, report)
        self.assertIn("headroom: 0 bytes", report.getvalue())
        struct.pack_into(">I", data, 512 + 5 * 40 + 20, 17)
        original.write_bytes(data)
        self.rejected_measurement(original, linker_map, "outside region")

    def test_truncated_and_misaligned_sections(self):
        original, linker_map = footprint_fixture(self.root)
        data = bytearray(original.read_bytes())
        struct.pack_into(">I", data, 512 + 4 * 40 + 32, 32)
        original.write_bytes(data)
        self.rejected_measurement(original, linker_map, "misaligned section")
        original.write_bytes(data[:600])
        with self.assertRaises(struct.error):
            measure(original, linker_map, StringIO())

    def test_equal_inventories_missing_the_same_required_object(self):
        for run in ("a", "b"):
            root = self.root / run
            for path in REQUIRED:
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_bytes(b"sample")
            (root / "source/cios-lib/libwbfs").mkdir()
            (root / "source/dip-plugin/input.s").touch()
            with self.assertRaisesRegex(ValueError, "missing required outputs: source/dip-plugin/input.o"):
                inventory(root, self.root)
        with self.assertRaisesRegex(ValueError, "required outputs"):
            compare(self.root, self.root, StringIO(), inventories_complete=False)

    def test_comparison_outcomes(self):
        for run in ("a", "b"):
            (self.root / run).mkdir()
            (self.root / run / "sample.o").write_bytes(b"test")
            (self.root / f"{run}-paths.txt").write_text("sample.o\n")
        compare(self.root, self.root, StringIO(), inventories_complete=True)
        (self.root / "b/sample.o").write_bytes(b"diff")
        with self.assertRaisesRegex(ValueError, "byte differences"):
            compare(self.root, self.root, StringIO(), inventories_complete=True)
        (self.root / "b/sample.o").unlink()
        with self.assertRaisesRegex(OSError, "comparison error"):
            compare(self.root, self.root, StringIO(), inventories_complete=True)
        (self.root / "b-paths.txt").write_text("extra.o\n")
        log = StringIO()
        with self.assertRaisesRegex(ValueError, "unequal inventories"):
            compare(self.root, self.root, log, inventories_complete=True)
        self.assertIn("only in a: sample.o", log.getvalue())
        self.assertIn("only in b: extra.o", log.getvalue())


class PreflightTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()

    def test_path_guards_precede_output_creation(self):
        repo = self.root / "source"
        subprocess.run(["git", "init", "-q", repo], check=True)
        alias = self.root / "alias"
        alias.symlink_to(repo)
        toolchain = self.root / "toolchain"
        toolchain.mkdir()
        archive = self.root / "archive"
        archive.touch()
        for source, work in [
            (repo / ".git", repo / "work"),
            (repo / ".git", self.root / "otherwise-valid"),
            (alias / ".git", self.root / "normalised"),
            (alias, alias / ".git/../work"),
            (repo, build.ROOT / "forbidden-stock-test-output"),
            (repo, toolchain / "work"),
        ]:
            with self.subTest(source=source, work=work), mock.patch.dict(os.environ, {
                "D2X_REPO": str(source), "WORK_DIR": str(work),
                "DEVKITARM": str(toolchain), "R32_ARCHIVE": str(archive),
            }), mock.patch.object(Path, "mkdir", side_effect=AssertionError("output created too early")):
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    build.main()
            self.assertFalse(work.exists())
        build.validate_work_path(self.root / "valid", alias.resolve(), archive, toolchain)

    def test_executability_and_driver_resolution(self):
        helpers = self.root / "libexec/gcc/arm-eabi/4.5.1"
        helpers.mkdir(parents=True)
        (self.root / "bin").mkdir()
        programs = {}
        for name in ("gcc", "cc1", "collect2", "as", "ld", "ar", "nm", "readelf", "size"):
            path = helpers / name if name in ("cc1", "collect2") else self.root / "bin" / ("arm-eabi-" + name)
            path.touch()
            path.chmod(0o755)
            programs[name] = path
        with mock.patch.object(subprocess, "check_output") as resolve:
            for name, path in programs.items():
                with self.subTest(non_executable=name):
                    path.chmod(0o644)
                    with self.assertRaisesRegex(ValueError, "missing verified executable"):
                        build.check_programs(self.root, {}, StringIO())
                    path.chmod(0o755)
            resolve.assert_not_called()
            resolve.return_value = "/bin/true"
            with self.assertRaisesRegex(ValueError, "unexpected compiler helper cc1"):
                build.check_programs(self.root, {}, StringIO())
            resolve.side_effect = lambda args, **kw: str(programs[args[1].split("=")[1]])
            with mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess(
                    [], 0, stdout="all resolved")):
                build.check_programs(self.root, {}, StringIO())

    def test_upload_set_after_inspection_and_comparison_failure(self):
        from scripts.stock_dip_evidence import collect

        work = self.root / "stock-dip"
        evidence = work / "evidence"
        evidence.mkdir(parents=True)
        for run in ("a", "b"):
            root = work / run
            plugin = root / build.DIP.parent
            plugin.mkdir(parents=True)
            original, linker_map = footprint_fixture(plugin)
            original.rename(root / build.DIP.with_suffix(".elf.orig"))
            linker_map = linker_map.rename(root / build.DIP.with_suffix(".map"))
            with mock.patch.object(build, "command"):
                if run == "a":
                    linker_map.write_bytes(b"\x7fELF\0binary")
                    with self.assertRaises(ValueError):
                        build.inspect(root, evidence, {"DEVKITARM": "/unused"})
                    self.assertFalse((evidence / "a.map").exists())
                else:
                    build.inspect(root, evidence, {"DEVKITARM": "/unused"})
            (evidence / f"{run}-paths.txt").write_text(str(build.DIP.with_suffix(".map")) + "\n")
        with self.assertRaisesRegex(ValueError, "byte differences"):
            build.compare(work, evidence, StringIO(), True)
        (evidence / "result.txt").write_text("comparison failed\n")
        (evidence / "a.map").write_text("printable but malformed map")
        (evidence / "a-build.txt").write_bytes(b"\x00binary log")
        (evidence / "a-hashes.txt").symlink_to(evidence / "result.txt")
        (evidence / "bundle.txt").write_text("unexpected source")
        inputs = self.root / "stock-inputs"
        inputs.mkdir()
        (inputs / "measurement.txt").write_bytes(b"\xff")
        rejected = collect(self.root)
        self.assertEqual(len(rejected), 4)
        published = self.root / "stock-dip-public"
        self.assertEqual({p.name for p in published.iterdir()},
                         {"result.txt", "b.map", "a-elf.txt", "b-elf.txt", "a-paths.txt", "b-paths.txt",
                          "a-footprint.txt", "b-footprint.txt"})
        self.assertEqual((published / "b.map").read_bytes(), linker_map.read_bytes())
