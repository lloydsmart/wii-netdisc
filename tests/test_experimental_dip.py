"""PC checks for ADR 0005. No cross-toolchain subprocess is used here."""

from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from scripts import experimental_dip_build as build
from scripts import experimental_dip_inspect as inspect
from scripts import experimental_dip_flow as flow
from scripts.experimental_dip_evidence import Journal, collect
from test_stock_dip import footprint_fixture


class SizingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.journal = Journal(self.root / "sizing.jsonl")

    def test_reviewed_sources_and_corrupt_patch(self):
        source = self.root / "fixture"
        shutil.copytree(build.FIXTURE, source)
        build.verify_fixture(source, StringIO(), self.journal)
        with (source / "integration.patch").open("a") as out:
            out.write("\n")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build.verify_fixture(source, StringIO(), self.journal)

    def test_wrong_archive_stops_before_extraction(self):
        archive = self.root / "inputs.tar"
        archive.write_bytes(b"wrong")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build.integrate(self.root, archive, StringIO(), self.journal)
        self.assertEqual([archive], list(self.root.iterdir()))

    def test_patch_failure_prevents_installation(self):
        archive = self.root / "empty.tar"
        with tarfile.open(archive, "w"):
            pass
        tree = self.root / "probe"
        tree.mkdir()
        with (self.root / "patch.log").open("w") as log, \
                patch.object(build.stock, "SOURCE_HASH", build.stock.digest(archive)):
            with self.assertRaises(subprocess.CalledProcessError):
                build.integrate(tree, archive, log, self.journal)
        self.assertFalse((tree / build.stock.DIP.parent).exists())

    def test_control_requires_original_and_canonical_map(self):
        content = b"/actual/tool/lib/gcc\n"
        import hashlib
        expected = hashlib.sha256((inspect.STOCK_TOOLS + "/lib/gcc\n").encode()).hexdigest()
        with patch.object(inspect, "STOCK_MAP", expected):
            args = (inspect.STOCK_ELF, content, "/actual/tool", inspect.STOCK_SPAN)
            inspect.control_identity(*args, self.journal)
            for i, value in ((0, "0"*64), (1, b"unexplained"), (3, {"exe": 6708, "ram": 0})):
                wrong = list(args)
                wrong[i] = value
                with self.assertRaises(inspect.ControlMismatch):
                    inspect.control_identity(*wrong, self.journal)

    def test_bad_control_prevents_probe_extraction(self):
        with patch.object(build.stock, "build"), patch.object(build.stock, "inventory"), \
                patch.object(build, "inspect", side_effect=inspect.ControlMismatch("control")), \
                patch.object(build, "integrate") as integrate:
            with self.assertRaises(inspect.ControlMismatch):
                build.measure_pair(self.root, {"DEVKITARM": "/unused"}, self.journal)
            integrate.assert_not_called()
            self.assertFalse((self.root / "probe").exists())

    def test_missing_elf_and_extended_ram_load(self):
        elf, link_map = footprint_fixture(self.root)
        self.assertEqual(inspect.layout(elf, link_map)[1], {"exe": 36, "ram": 28})
        import struct
        data = bytearray(elf.read_bytes())
        struct.pack_into(">I", data, 52 + 2*32 + 20, 32)
        elf.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "ram LOAD"):
            inspect.layout(elf, link_map)
        with self.assertRaises(FileNotFoundError):
            inspect.layout(self.root / "absent", link_map)

    def rows(self, kind):
        return [row[1:] for line in self.journal.path.read_text().splitlines()
                if (row := json.loads(line))[0] == kind]

    def partial_map(self):
        path = self.root / "attempted.map"
        path.write_text("""table 0x0 0x4000
exe 0x13800000 0x2000
ram 0x13802000 0x40000
Linker script and memory map
.ios_info_table 0x0 0x34
.init 0x13800000 0x10
.text 0x13800010 0x2020
.data 0x13802000 0x20
.rodata 0x13802020 0x20
.bss 0x13802040 0x20
""")
        return path

    exe_count = "arm-eabi-ld: region 'exe' overflowed by 48 bytes"
    text_range = "arm-eabi-ld: dip-plugin.elf.orig section `.text' will not fit in region `exe'"

    def test_all_range_reports_must_agree(self):
        path = self.partial_map()
        rows = inspect.overflow(self.text_range + "\n" + self.exe_count +
                                "\ncollect2: ld returned 1 exit status", path, self.journal)
        self.assertEqual(rows, [("exe", ".text", 0x13800010, 0x13802030, 48),
                                ("exe", "region", 0x13800000, 0x13802030, 48)])
        for case in (self.text_range.replace(".text", ".init"),
                     self.exe_count + "\nld: region 'ram' overflowed by 9 bytes",
                     self.exe_count.replace("48", "49"), self.text_range.replace("exe'", "other'"),
                     self.exe_count + "\nld: section .data overlaps section .text",
                     self.exe_count + "\nthing.s:3: Error: bad instruction"):
            with self.subTest(case=case), self.assertRaises(inspect.OverflowUnresolved):
                inspect.overflow(case, path, self.journal)
        self.assertIn(["exe", ".init", 0x13800000, 0x13800010, 0], self.rows("attempted"))
        self.assertIn(["ram", "region", 0x13802000, 0x13802060, 0], self.rows("attempted"))

    def test_pinned_ld_explicit_end_must_match_named_section(self):
        path = self.partial_map()
        report = "ld: address 0x13802030 of dip-plugin.elf.orig section `.text' is not within region `exe'"
        self.assertEqual(inspect.overflow(report, path, self.journal)[0][-1], 48)
        with self.assertRaises(inspect.OverflowUnresolved):
            inspect.overflow(report.replace("2030", "2034"), path, self.journal)

    def test_explicit_overflow_addresses_survive_contradiction_and_collection(self):
        path = self.partial_map()
        for end in (0x13802034, 0x13802038):
            diagnostic = f"ld: address {end:#x} of dip-plugin.elf.orig section `.text' is not within region `exe'"
            with self.assertRaises(inspect.OverflowUnresolved):
                inspect.overflow(diagnostic, path, self.journal)
        collect(self.root, self.root / "public")
        self.assertEqual(self.rows("overflow-report"), [["exe", ".text", None, 0x13802034],
                                                       ["exe", ".text", None, 0x13802038]])
        self.assertEqual(self.rows("attempted"), [["exe", ".text", 0x13800010, 0x13802030, 48]] * 2)
        self.assertEqual(self.rows("overflow"), [])
        for invalid in (True, -1, 0x100000000, "0x13802034"):
            with self.assertRaises(ValueError):
                self.journal.write("overflow-report", "exe", ".text", None, invalid)

    def test_corroborated_companion_load_overlap(self):
        path = self.partial_map()
        overlap = "ld: section .data loaded at [13802000,1380201f] overlaps section .text loaded at [13800010,1380202f]"
        self.assertTrue(inspect.overflow(overlap + "\n" + self.exe_count, path, self.journal))
        self.assertEqual(self.rows("overlap"), [[".data", 0x13802000, 0x13802020, ".text", 0x13800010, 0x13802030]])
        for case in (overlap, overlap.replace("201f", "2020") + "\n" + self.exe_count):
            with self.assertRaises(inspect.OverflowUnresolved):
                inspect.overflow(case, path, self.journal)

    def test_partial_or_unsupported_layout_cannot_prove_overflow(self):
        path = self.partial_map()
        self.assertEqual(inspect.overflow("netdisc.c:2: error: failed", path, self.journal), [])
        raw = path.read_text()
        for bad in ("", raw.split(".bss")[0], raw.replace(".init", ".data"),
                    raw.replace("exe 0x13800000 0x2000", "exe 0x13800000 0x9000"),
                    raw + ".unassigned 0x13803000 0x4\n"):
            path.write_text(bad)
            with self.assertRaises(inspect.OverflowUnresolved):
                inspect.overflow(self.exe_count, path, self.journal)
        with self.assertRaises(inspect.OverflowUnresolved):
            inspect.overflow(self.exe_count, self.root / "absent", self.journal)

    def test_failure_orchestration_retains_unresolved_and_confirmed_ranges(self):
        for idx, (log, expected) in enumerate((
                (self.exe_count, "region-overflow"),
                (self.text_range.replace(".text", ".init"), "overflow-evidence-unresolved"))):
            work = self.root / str(idx)
            work.mkdir()
            def fail(root, env, out):
                path = root / build.stock.DIP.with_suffix(".map")
                path.parent.mkdir(parents=True)
                shutil.copyfile(self.partial_map(), path)
                print(log, file=out)
                raise subprocess.CalledProcessError(1, "synthetic")
            with patch.object(build.stock, "build"), patch.object(build.stock, "inventory"), \
                    patch.object(build, "inspect", return_value={}), patch.object(build, "integrate"), \
                    patch.object(build.stock, "compile_extraction", side_effect=fail):
                self.assertEqual(build.measure_pair(work, {"DEVKITARM": "/unused"}, self.journal), 1)
            self.assertEqual(self.rows("outcome")[-1], [expected])
        self.assertEqual(len(self.rows("overflow")), 1)
        collect(self.root, self.root / "public")

    def trace(self, listing, required=()):
        return flow.path_evidence(flow.disassembly(listing), self.journal, set(required))

    def test_call_after_return_is_dead(self):
        reached = self.trace("""
100 <DI_EmulateIoctl>:
 100: e12fff1e bx lr
 104: eb00003d bl 200 <cleanup>
200 <cleanup>:
 200: e12fff1e bx lr
""", ["cleanup"])
        self.assertEqual(reached, {0x100})
        self.assertEqual(self.rows("missing"), [["cleanup"]])
        self.assertEqual(self.rows("edge"), [])

    def test_branch_to_interior_does_not_enter_earlier_callee_or_entry(self):
        reached = self.trace("""
100 <DI_EmulateIoctl>:
 100: ea00003f b 204 <nd_hook+0x4>
200 <nd_hook>:
 200: eb00003e bl 300 <cleanup>
 204: e12fff1e bx lr
300 <cleanup>:
 300: e12fff1e bx lr
""", ["nd_hook", "cleanup"])
        self.assertEqual(reached, {0x100, 0x204})
        self.assertEqual(self.rows("missing"), [["cleanup"], ["nd_hook"]])
        self.assertIn(["nd_hook", 0x200, 0, 0, "unresolved"], self.rows("frame"))

    def test_interworking_literal_veneer_resolves_only_instruction_destination(self):
        listing = """
100 <DI_EmulateIoctl>:
 100: e51ff004 ldr pc, [pc, #-4] ; 104 <DI_EmulateIoctl+0x4>
 104: 00000301 .word 0x00000301
300 <nd_hook>:
 300: 4770 bx lr
"""
        self.assertEqual(self.trace(listing, ["nd_hook"]), {0x100, 0x300})
        self.assertEqual(self.rows("edge"), [[0x100, 0x300, "literal"]])
        self.assertEqual(self.rows("missing"), [])
        self.assertEqual(self.trace(listing.replace("0x00000301", "0x00000300")), {0x100})
        self.assertIn([0x100, "ambiguous-mode"], self.rows("unresolved"))

    def test_thumb_to_arm_and_register_literal_veneer(self):
        listing = """
100 <DI_EmulateIoctl>:
 100: 4778 bx pc
 102: 46c0 nop ; (mov r8, r8)
 104: e59fc000 ldr ip, [pc]
 108: e12fff1c bx ip
 10c: 00000301 .word 0x00000301
300 <nd_hook>:
 300: 4770 bx lr
"""
        self.assertEqual(self.trace(listing), {0x100, 0x104, 0x108, 0x300})
        interior = "80 <DI_EmulateIoctl>:\n 80: ea000020 b 108 <veneer+0x8>\n"
        self.assertEqual(self.trace(interior + listing.replace("<DI_EmulateIoctl>", "<veneer>")),
                         {0x80, 0x108})
        self.assertIn([0x108, "indirect"], self.rows("unresolved"))

    def test_conditional_tail_and_returning_call(self):
        listing = """
100 <DI_EmulateIoctl>:
 100: 0a00003e beq 200 <nd_hook>
 104: eb00007d bl 300 <nd_take>
 108: ea0000bc b 400 <cleanup>
200 <nd_hook>:
 200: e12fff1e bx lr
300 <nd_take>:
 300: e1a0f00e mov pc, lr
400 <cleanup>:
 400: e8bd8000 ldmia sp!, {pc}
"""
        self.assertEqual(self.trace(listing), {0x100, 0x104, 0x108, 0x200, 0x300, 0x400})
        self.assertNotIn(0x108, self.trace(listing.replace("e1a0f00e mov pc, lr", "eafffffe b 300 <nd_take>")))
        self.assertEqual(len(set(tuple(x) for x in self.rows("review"))), len(flow.CHECKLIST))

    def test_historical_nops_comments_data_and_unknown_syntax(self):
        listing = """
100 <DI_EmulateIoctl>:
 100: e1a00000  nop            ; (mov r0, r0)
 104: e12fff1e  bx lr
200 <nd_take>:
 200: 46c0      nop            ; (mov r8, r8)
 202: 4770      bx lr
 204: 00000100  .word 0x00000100
"""
        decoded = flow.disassembly(listing)
        for pc in (0x100, 0x200):
            self.assertEqual((decoded.code[pc].op, decoded.code[pc].args), ("nop", ""))
        self.assertEqual(decoded.code[0x204].op, ".word")
        self.assertEqual(self.trace(listing), {0x100, 0x104})
        for bad in ("unknown r0", "nop source-like annotation", "mov pc, r4", "mov r0, ???"):
            self.assertEqual(self.trace(listing.replace("nop            ; (mov r0, r0)", bad)), {0x100})
            self.assertIn([0x100, "unsupported"], self.rows("unresolved"))

    def test_witness_is_a_reachable_call_site_to_the_exact_entry(self):
        listing = """
100 <DI_EmulateIoctl>:
 100: eb00003e bl 200 <DI_HandleIoctl>
 104: e12fff1e bx lr
200 <DI_HandleIoctl>:
 200: e1a00000 nop ; (mov r0, r0)
 204: e12fff1e bx lr
"""
        self.trace(listing.replace("bl 200", "bl 204"))
        self.assertEqual(self.rows("witness"), [])
        self.trace(listing)
        self.assertEqual(self.rows("witness"), [["stock-forward", 0x100, 0x200]])
        self.assertIn(["stock-forward", "manual-required"], self.rows("review"))

    def test_fallthrough_requires_same_instruction_mode(self):
        for next_instruction in ("4770 bx lr", "bx lr"):
            listing = ("100 <DI_EmulateIoctl>:\n 100: e1a00000 nop\n"
                       f"104 <nd_hook>:\n 104: {next_instruction}")
            self.assertEqual(self.trace(listing, ["nd_hook"]), {0x100})
            self.assertIn([0x100, "ambiguous-mode"], self.rows("unresolved"))
            self.assertIn(["nd_hook"], self.rows("missing"))

    def test_return_continuation_uses_callers_mode(self):
        listing = """
100 <DI_EmulateIoctl>:
 100: eb00003e bl 200 <nd_hook>
 104: f000 f8fc bl 300 <DI_HandleIoctl>
200 <nd_hook>:
 200: e12fff1e bx lr
300 <DI_HandleIoctl>:
 300: 4770 bx lr
"""
        self.assertEqual(self.trace(listing), {0x100, 0x200})
        self.assertIn([0x100, "ambiguous-mode"], self.rows("unresolved"))
        self.assertEqual(self.rows("witness"), [])
        interwork = ("100 <DI_EmulateIoctl>:\n 100: fa00003e blx 200 <nd_hook>\n"
                     " 104: e12fff1e bx lr\n200 <nd_hook>:\n 200: 4770 bx lr")
        self.assertEqual(self.trace(interwork), {0x100, 0x104, 0x200})
        self.assertEqual(self.trace(interwork.replace("4770 bx lr", "46f7 mov pc, lr")), {0x100, 0x200})
        self.assertIn([0x200, "ambiguous-mode"], self.rows("unresolved"))

    def test_dynamic_stack_addition_is_unresolved(self):
        for op in ("add sp, sp, r3", "add r13, r2, #4", "add sp, r3", "pop {r4, sp}"):
            self.trace(f"100 <DI_EmulateIoctl>:\n 100: e08dd003 {op}\n 104: e12fff1e bx lr")
            self.assertEqual(self.rows("frame")[-1][-1], "unresolved", op)
        self.trace("100 <DI_EmulateIoctl>:\n 100: e24dd010 sub sp, sp, #16\n"
                   " 104: e28dd010 add sp, sp, #16\n 108: e12fff1e bx lr")
        self.assertEqual(self.rows("frame")[-1][-2:], [16, "entry-only"])

    def test_stack_writeback_and_unsupported_adjustment(self):
        prefix = "100 <DI_EmulateIoctl>:\n"
        self.trace(prefix + " 100: e52de004 str lr, [sp, #-4]!\n 104: e12fff1e bx lr")
        self.assertEqual(self.rows("frame")[-1], ["DI_EmulateIoctl", 256, 4, 0, "entry-only"])
        self.trace(prefix + " 100: e72de004 str lr, [sp, -r4]!\n 104: e12fff1e bx lr")
        self.assertEqual(self.rows("frame")[-1][-1], "unresolved")

    def test_complete_synthetic_probe_keeps_raw_listings_in_scratch(self):
        import struct
        root = self.root / "probe"
        dest = root / build.stock.DIP
        dest.parent.mkdir(parents=True)
        elf, link_map = footprint_fixture(self.root)
        data = bytearray(elf.read_bytes())
        # Extend the synthetic BSS and its PT_LOAD by the same amount.
        struct.pack_into(">I", data, 52 + 2*32 + 20, 0x820)
        struct.pack_into(">I", data, 512 + 7*40 + 20, 0x818)
        dest.with_suffix(".elf.orig").write_bytes(data)
        dest.with_suffix(".map").write_text(link_map.read_text().replace("0x13802008 0x14", "0x13802008 0x818"))
        symbols = ("13800010 00000008 T DI_EmulateIoctl\n13800018 00000004 t private_symbol\n"
                   "13802020 00000800 b nd_completions\n")
        raw = ("13800010 <DI_EmulateIoctl>:\n 13800010: eb000000 bl 13800018 <private_symbol>\n"
               " 13800014: e12fff1e bx lr\n13800018 <private_symbol>:\n 13800018: e12fff1e bx lr\n")
        def listing(argv, *, stdout, stderr, check):
            name = argv[0].name
            self.assertIn(name, {"arm-eabi-nm", "arm-eabi-objdump"})
            stdout.write((symbols if name.endswith("-nm") else raw).encode())
        with patch.object(inspect.subprocess, "run", side_effect=listing):
            result = inspect.inspect(root, self.root, self.journal, {})
        self.assertIn("private_symbol", result)
        self.assertEqual((self.root / "probe-disassembly.txt").read_text(), raw)
        self.assertIn([0x13800010, 0x13800018, "call"], self.rows("edge"))
        self.assertIn(["probe", "nd_completions", "b", 0x13802020, 2048, "unknown"], self.rows("symbol"))
        collect(self.root, self.root / "public")
        published = (self.root / "public/sizing.jsonl").read_text()
        self.assertNotIn("private_symbol", published)
        self.assertNotIn("e12fff1e", published)

    def test_post_link_inspection_failure_preserves_initial_result(self):
        def link(root, env, out):
            path = root / build.stock.DIP.with_suffix(".elf.orig")
            path.parent.mkdir(parents=True)
            path.write_bytes(b"synthetic placeholder")
        with patch.object(build.stock, "build"), patch.object(build.stock, "inventory"), \
                patch.object(build, "integrate"), patch.object(build.stock, "compile_extraction", side_effect=link), \
                patch.object(build, "inspect", side_effect=[{}, ValueError("private disassembly")]):
            self.assertEqual(build.measure_pair(self.root, {"DEVKITARM": "/unused"}, self.journal), 1)
        self.assertIn(["probe", "original-linked"], self.rows("build"))
        self.assertEqual(self.rows("outcome"), [["linked-inspection-unresolved"]])
        collect(self.root, self.root / "public")
        self.assertNotIn("private disassembly", self.journal.path.read_text())

    def test_historical_diagnostics_publish_only_bounded_causes(self):
        log = self.root / "probe.log"
        log.write_text("netdisc_gate.s: Assembler messages:\n"
                       "netdisc_gate.s:10: Error: bad instruction 'unpublishable'\n"
                       "/private/netdisc.c:31:8: error: unknown type name 'unpublishable'\n"
                       "/private/arbitrary.c:7: warning: implicit declaration of 'unpublishable'\n")
        build.build_records("probe", self.root, log, self.journal)
        self.assertEqual(self.rows("diagnostic"), [
            ["assembler", "netdisc_gate.s", 10, "error", "bad-instruction"],
            ["compile", "netdisc.c", 31, "error", "unknown-type"],
            ["compile", "other-input", 7, "warning", "other-compiler"]])
        self.assertEqual(build.build_outcome("netdisc_gate.s:10: Error: bad instruction"), "compile-error")
        collect(self.root, self.root / "public")
        self.assertNotIn("unpublishable", self.journal.path.read_text())

    def test_processor_and_argument_count_causes_are_bounded(self):
        log = self.root / "probe.log"
        log.write_text("netdisc_gate.s:9: Error: selected processor does not support `private_opcode' in Thumb mode\n"
                       "netdisc_gate.s:10: Error: selected processor does not support ARM opcodes\n"
                       "netdisc.c:12: error: too few arguments to function 'private_call'\n"
                       "netdisc.c:13: error: too many arguments to function 'private_call'\n")
        build.build_records("probe", self.root, log, self.journal)
        self.assertEqual([r[-1] for r in self.rows("diagnostic")],
                         ["processor-instruction"] * 2 + ["argument-count"] * 2)
        collect(self.root, self.root / "public")
        self.assertNotIn("private_", (self.root / "public/sizing.jsonl").read_text())

    def test_build_failure_categories(self):
        cases = (("thing.c:10:3: error: unknown type", "compile-error"),
                 ("thing.c:10: error: size of array 'ipc_extent' is negative", "abi-layout-error"),
                 ("ld: undefined reference to foo", "incomplete-link"),
                 ("../../stripios dip-plugin.elf.orig dip-plugin.elf", "conversion-error"))
        for diagnostic, expected in cases:
            self.assertEqual(build.build_outcome(diagnostic), expected)

    def test_distinct_file_local_symbols(self):
        values = inspect.list_symbols("0100 0004 d fd\n0104 0004 d fd\n")
        self.assertEqual([256, 260], [v[1] for v in values.values()])

    def test_public_directory_is_typed_text_only(self):
        self.journal.write("outcome", "build-error")
        (self.root / "probe.elf").write_bytes(b"\x7fELF")
        (self.root / "build.log").write_text("source excerpt\n")
        dest = self.root / "public"
        collect(self.root, dest)
        self.assertEqual(["sizing.jsonl"], [p.name for p in dest.iterdir()])
        self.assertEqual(json.loads((dest / "sizing.jsonl").read_text()), ["outcome", "build-error"])

    def test_invalid_payload_rejected_before_publication(self):
        for i, content in enumerate((b"\x7fELF", b'["source","int main()"]\n', b'["pin","a.c","x"]\n',
                                     b'["command","probe","make","arbitrary source text"]\n')):
            self.journal.path.write_bytes(content)
            dest = self.root / str(i)
            with self.assertRaises(ValueError):
                collect(self.root, dest)
            self.assertFalse(any(dest.iterdir()))

    def test_collector_rejects_unreviewed_id_paths_operands_and_numeric_strings(self):
        for i, row in enumerate((
                ["symbol", "probe", "arbitrary", "T", 1, 1, "unknown"],
                ["artifact", "probe", "/private/arbitrary", 3, "a"*64],
                ["instruction", "nd_hook", 1, "mov", "int private_source()"],
                ["symbol", "probe", "nd_hook", "T", "1", "1", "unknown"],
                ["edge", True, 2, "branch"], ["runner", "image", "someone"],
                ["diagnostic", "assembler", "/abs/a.s", 1, "error", "bad-instruction"],
                ["frame", "unreviewed", 0, 0, 0, "entry-only"])):
            with self.subTest(row=row):
                self.journal.path.write_text('["stage","probe"]\n' + json.dumps(row) + "\n")
                dest = self.root / str(i)
                with self.assertRaises(ValueError):
                    collect(self.root, dest)
                self.assertFalse(any(dest.iterdir()))

    def test_public_selector_rejects_symlinks(self):
        alternate = self.root / "elsewhere"
        alternate.write_text('["outcome","build-error"]\n')
        self.journal.path.symlink_to(alternate)
        with self.assertRaises(ValueError):
            collect(self.root, self.root / "public")


class ApprovalTests(unittest.TestCase):
    workflow = (build.stock.ROOT / ".github/workflows/experimental-dip.yml").read_text()
    gate = textwrap.dedent(workflow.split("        run: |\n", 1)[1].split("\n\n", 1)[0])
    sha = "a"*40

    def approved(self):
        return dict(GITHUB_EVENT_NAME="workflow_dispatch", GITHUB_REPOSITORY="lloydsmart/wii-netdisc",
                    GITHUB_REPOSITORY_OWNER="lloydsmart", GITHUB_ACTOR="lloydsmart",
                    GITHUB_TRIGGERING_ACTOR="lloydsmart", GITHUB_RUN_ATTEMPT="1",
                    GITHUB_REF="refs/heads/develop", APPROVED_SHA=self.sha, GITHUB_SHA=self.sha,
                    GITHUB_WORKFLOW_SHA=self.sha, GITHUB_WORKFLOW_REF=(
                        "lloydsmart/wii-netdisc/.github/workflows/experimental-dip.yml@refs/heads/develop"))

    def test_actual_first_step_rejects_each_mismatch(self):
        env = self.approved()
        def run(values):
            return subprocess.run(["bash", "-eu", "-c", self.gate], env=values,
                                  capture_output=True).returncode
        self.assertEqual(run(env), 0)
        for key in env:
            with self.subTest(field=key):
                self.assertNotEqual(run(env | {key: "wrong"}), 0)
        self.assertNotIn("pull_request:", self.workflow)
        self.assertNotIn("push:", self.workflow)

    def test_actual_checkout_gate_checks_head(self):
        command = self.workflow.split("run: test ", 1)[1].splitlines()[0]
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=build.stock.ROOT, text=True).strip()
        for sha, expected in ((head, 0), ("0"*40, 1)):
            rc = subprocess.run(["bash", "-ec", "test " + command], cwd=build.stock.ROOT,
                                env={"APPROVED_SHA": sha}).returncode
            self.assertEqual(rc, expected)
