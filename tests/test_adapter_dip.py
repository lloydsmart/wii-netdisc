"""ADR 0006 PC-only checks. Hardware interfaces are substituted at the host link."""

from pathlib import Path
import selectors
import subprocess
import tempfile
import unittest

from scripts import experimental_adapter as adapter


class NativeAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        work = Path(tmp.name)
        tests = Path(__file__).resolve().parent
        for name in ("string.h", "plugin.h", "mem.h", "syscalls.h"):
            (work / name).write_text('#include "fixture.h"\ns32 os_stop_timer(s32);\n')
        cls.program = work / "adapter"
        subprocess.run(["gcc", "-m32", "-std=gnu99", "-Os", "-ffreestanding", "-fno-builtin",
                        "-fno-pie", "-no-pie", "-nostdlib", "-Wall", "-Werror", "-Wl,-Ttext-segment=0x400000",
                        "-I", work, "-I", tests / "native_dip", "-I", adapter.FIXTURE,
                        *(adapter.FIXTURE / n for n in ("adapter.c", "transaction.c", "mailbox.c")),
                        tests / "native_adapter/fixture.c", "-o", cls.program], check=True)

    def cases(self, names):
        for name in names.split():
            with self.subTest(case=name):
                result = subprocess.run([self.program, name], capture_output=True, text=True, timeout=2)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_admission_and_foreign_page(self):
        self.cases("foreign split changed-replay bad-read bad-extent short-reservation bad-arm bad-output unowned")

    def test_provision_and_caller(self):
        self.cases("variant wrong-opener stale-session stale-build bad-path aliased-mailbox stale-lease changed-registration")

    def test_setup_absolute_timer_and_receives(self):
        self.cases("no-queue no-timer clipped wrap stale-wake early-timer saturated duplicate "
                   "double-timer old-word conflict-first conflict-last receive-error timer-first timer-last half-gap token-collision stale-token-alias")

    def test_retirement_and_disposition(self):
        self.cases("success lost-open ambiguous-open lost-ioctl bad-command no-retirement no-release "
                   "positive-close negative-close late-close stop-failed release-unconfirmed "
                   "negative-open ambiguous-matched-open late-duplicate")

    def test_skipped_and_unissued_operations(self):
        self.cases("preissue close-expired skipped proven-reject capacity withdrawn-control")

    def test_worker_and_dip_verification(self):
        self.cases("late-dip late-outer cleanup-failure clock-after clock-at-latch undefined malformed "
                   "clock-before dip-clock-loss eof absent-raw torn")

    def test_invalid_frame_and_timing_combinations(self):
        self.cases("zero-id zero-sequence unknown-flags valid-absent nonzero-absent false-deadline "
                   "out-of-order late-readiness late-cleanup unflagged-raw modified-request false-absence")

    def test_receipt_observation_and_surviving_deadlines(self):
        self.cases("causal causal-loss delayed-validation timer-causal timer-separated missing-receipt-clock mixed-loss late-loss")

    def test_partial_worker_timelines(self):
        self.cases("connect unproved-deadline phase-after-cleanup missing-failure partial-readiness partial-deadline clipped-deadline unknown-deadline bad-length")

    def test_phase_completion_and_abandonment_bounds(self):
        self.cases("ended-bringup ended-connect ended-unobserved expire-bringup expire-connect "
                   "exchange-at-cutoff exchange-before-cutoff ready-at-cutoff clipped-deadline unknown-deadline")

    def test_validation_failure_precedes_lease_acquisition(self):
        self.cases("reject-delay reject-equality reject-loss reject-work")

    def test_live_handback_and_bound_contracts(self):
        self.cases("handback-time handback-expired handback-lease postfacts-open postfacts-ioctl postfacts-close global-close revoke-ioctl")

    def test_event_samples_and_exact_arm_extent(self):
        self.cases("setup-tick initial-clock zero-tick relocated-arm")

    def test_required_arm_identities(self):
        for index in range(14):
            with self.subTest(index=index):
                result = subprocess.run([self.program, "zero-identity", str(index)], capture_output=True, timeout=2)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_identity_and_wire_rules(self):
        # Each byte in these identity fields is checked. Other field mutations
        # exercise big-endian masks, enum width, interval and consistency rules.
        offsets = [*range(72), 72, 76, 80, 84, 88, 92, 96, 100, 104, 108, 112,
                   116, 120, *range(124, 148), 156, *range(160, 176), 176, 180, 184, 188]
        for offset in offsets:
            with self.subTest(offset=offset):
                result = subprocess.run([self.program, "mutate", str(offset)], capture_output=True, timeout=2)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_pending_caller_observed_from_host(self):
        for case in ("missing-wake", "blocked-close", "handback-reload", "fd-reuse"):
            with self.subTest(case=case), subprocess.Popen(
                [self.program, case], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            ) as child:
                try:
                    with selectors.DefaultSelector() as selector:
                        selector.register(child.stdout, selectors.EVENT_READ)
                        self.assertTrue(selector.select(2))
                        self.assertEqual(child.stdout.readline(), b"waiting\n")
                    self.assertIsNone(child.poll())
                finally:
                    child.kill()
                    child.communicate(timeout=2)


class AdapterSizingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.journal = adapter.journal_at(self.root / "sizing.jsonl")

    def test_approved_dispatch(self):
        import os
        import textwrap
        from unittest.mock import patch
        repo = "lloydsmart/wii-netdisc"
        workflow = ".github/workflows/experimental-adapter.yml"
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        ref = "refs/heads/develop"
        env = dict(GITHUB_EVENT_NAME="workflow_dispatch", GITHUB_RUN_ATTEMPT="1",
                   GITHUB_REPOSITORY_OWNER="lloydsmart", GITHUB_REPOSITORY=repo,
                   GITHUB_ACTOR="lloydsmart", GITHUB_TRIGGERING_ACTOR="lloydsmart", GITHUB_REF=ref,
                   GITHUB_WORKFLOW_REF=f"{repo}/{workflow}@{ref}", GITHUB_SHA=head,
                   GITHUB_WORKFLOW_SHA=head, APPROVED_SHA=head)
        source = (adapter.direct.stock.ROOT / workflow).read_text()
        self.assertNotRegex(source, r"(pull_request|push):")
        gate = textwrap.dedent(source.split("        run: |\n", 1)[1].split("\n\n", 1)[0])
        checkout = source.split("run: test ", 1)[1].splitlines()[0]
        for changed in [None, *env]:
            values = env if changed is None else env | {changed: "wrong"}
            with self.subTest(field=changed):
                rc = subprocess.run(["bash", "-eu", "-c", gate], env=values, capture_output=True).returncode
                self.assertEqual(rc == 0, changed is None)
                if changed:
                    with self.assertRaises(ValueError):
                        adapter.require_dispatch(values, head)
                else:
                    adapter.require_dispatch(values, head)
        for sha in (head, "0"*40):
            rc = subprocess.run(["bash", "-ec", "test " + checkout], env={"APPROVED_SHA": sha}).returncode
            self.assertEqual(rc == 0, sha == head)
        with patch.dict(os.environ, {}, clear=True), patch.object(adapter.paired, "main") as build:
            with self.assertRaises(ValueError):
                adapter.main(["build"])
            build.assert_not_called()

    def test_pin_and_output_isolation(self):
        from io import StringIO
        import shutil
        direct = adapter.direct
        private = self.root / "src"
        shutil.copytree(adapter.FIXTURE, private)
        adapter.paired.verify_fixture(private, StringIO(), self.journal)
        with (private / "adapter.c").open("a") as out:
            print("changed", file=out)
        with self.assertRaises(ValueError):
            adapter.paired.verify_fixture(private, StringIO(), self.journal)
        with self.assertRaises(ValueError):
            direct.collect(self.root, self.root / "wrong-profile")
        self.journal.write("object", "mailbox.o", ".text", 64)
        with self.assertRaises(ValueError):
            self.journal.write("object", "netdisc_net.o", ".text", 48)
        self.journal.path.write_text(self.journal.path.read_text() + '["diagnostic", "private raw map"]\n')
        with self.assertRaises(ValueError):
            direct.collect(self.root, self.root / "public", adapter.SCHEMA, adapter.INPUTS)
        self.assertEqual(list((self.root / "public").iterdir()), [])

    def test_control_and_failed_link(self):
        from unittest.mock import patch
        from scripts import experimental_dip_inspect as inspect
        build = adapter.paired
        with patch.object(build.stock, "build"), patch.object(build.stock, "inventory"), \
                patch.object(build, "inspect", side_effect=inspect.ControlMismatch("unexpected baseline")), \
                patch.object(build, "integrate") as integrate:
            with self.assertRaises(inspect.ControlMismatch):
                build.measure_pair(self.root, {"DEVKITARM": "/unused"}, self.journal)
            integrate.assert_not_called()

    def test_collector_rejects_impossible_extents_and_bare_claims(self):
        import json
        start, limit = adapter.direct.REGIONS["exe"]
        cases = [
            [["literal-site", 0xcafebabe]], [["literal-site", start+2]],
            [["dependency", "probe", "compiler-helper", 0, 0xffffffff]],
            [["dependency", "probe", "compiler-helper", limit-2, 4]],
            [["gap", "probe", "exe", 0, 0xffffffff]],
            [["gap", "probe", "exe", start+4, 8], ["gap", "probe", "exe", start+8, 4]],
            [["gap", "probe", "exe", start+4, 8], ["literal-site", start+8]],
            [["region", "probe", "exe", limit-start+4, 0, 0]],
            [["outcome", "region-overflow"]], [["outcome", "linked-review-required"]],
        ]
        for i, rows in enumerate(cases):
            with self.subTest(rows=rows):
                self.journal.path.write_text("".join(json.dumps(row)+"\n" for row in rows))
                public = self.root / str(i)
                with self.assertRaises(ValueError):
                    adapter.direct.collect(self.root, public, adapter.SCHEMA, adapter.INPUTS)
                self.assertFalse(list(public.iterdir()))
        self.journal.path.write_text('["stage", "approval"]\n["workflow", "provision", "failure"]\n')
        adapter.direct.collect(self.root, self.root / "partial", adapter.SCHEMA, adapter.INPUTS)

    def synthetic_pair(self, name, outcome, check_rows=None):
        """Real extraction, patch, failure handler and collector, with synthetic recipes and control."""
        from contextlib import ExitStack
        import hashlib
        from io import BytesIO
        import json
        import os
        import tarfile
        from unittest.mock import patch
        from scripts import experimental_dip_inspect as inspect
        build = adapter.paired
        work = self.root / name
        work.mkdir()
        archive = work / "inputs.tar"
        stock_objects = "dip.o dip_calls.o dma.o fat.o frag.o main.o patches.o plugin.o sdhc.o start.o wbfs.o"
        experimental = "adapter.o netdisc_gate.o mailbox.o transaction.o"
        makefile = "\n"*40 + "OBJS = config.o \\\n" + stock_objects + "\n"
        plugin = "\n"*680 + "\ts32 ret = 1;\n"
        def digest(content):
            return hashlib.sha256(content).hexdigest()

        original = {"Makefile": makefile, "plugin.c": plugin}
        with tarfile.open(archive, "w") as tar:
            for path, src in original.items():
                entry = tarfile.TarInfo(adapter.direct.DIP+path)
                entry.size = len(src)
                tar.addfile(entry, BytesIO(src.encode()))
        # Use exactly the reviewed zero-context patch against small preimages.
        diff = (adapter.FIXTURE / "integration.patch").read_text()
        lines = [line[1:]+"\n" for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
        postimages = {"Makefile": digest(makefile.replace(stock_objects, lines[0]+stock_objects).encode()),
                      "plugin.c": digest(("\n"*27+lines[1]+"\n"*653+"".join(lines[2:])).encode())}
        j = adapter.journal_at(work / "sizing.jsonl")
        control_elf = b"synthetic original"
        control_map = b"synthetic control map"
        exe, ram = (adapter.direct.REGIONS[k][0] for k in ("exe", "ram"))
        partial_map = ("table 0x0 0x4000\nexe 0x13800000 0x2000\nram 0x13802000 0x40000\n"
                       "Linker script and memory map\n.ios_info_table 0x0 0x34\n.init 0x13800000 0x10\n"
                       ".text 0x13800010 0x2020\n.data 0x13802000 0x20\n.rodata 0x13802020 0x20\n"
                       ".bss 0x13802040 0x20\n")

        def artifacts(root, names):
            for artifact in names:
                path = root / artifact
                path.parent.mkdir(parents=True, exist_ok=True)
                value = control_elf if artifact.endswith(".elf.orig") else control_map if artifact.endswith(".map") else b"fixture"
                path.write_bytes(value)

        def control(root, inputs, env, log):
            artifacts(root, adapter.ARTIFACTS - {adapter.direct.DIP+n for n in adapter.OBJECTS})

        def inspect_layout(root, tools, journal, baseline):
            run = root.name
            journal.write("load", run, 0, 0, 0, 52, 52)
            journal.write("section", run, ".ios_info_table", 0, 52)
            for index, (region, start, used, name, last) in enumerate((
                    ("exe", exe, 6708, ".init", ".text"), ("ram", ram, 246912, ".data", ".bss")), 1):
                journal.write("load", run, index, start, start, used if region == "exe" else 32, used)
                journal.write("section", run, name, start, 32)
                journal.write("section", run, last, start+32, used-32)
                journal.write("region", run, region, used, 0, adapter.direct.REGIONS[region][1]-start-used)
            journal.write("private-digest", run, "symbols", digest(b"symbols"))
            if baseline is None:
                inspect.control_identity(digest(control_elf), control_map, tools, inspect.STOCK_SPAN, journal)
            else:
                journal.write("private-digest", run, "disassembly", digest(b"disassembly"))
                for check in sorted(adapter.CHECKLIST):
                    journal.write("review", check, "manual-required")
                addr = ram+32
                for n, size in adapter.STORAGE.items():
                    journal.write("symbol", run, n, "B", addr, size, "unknown")
                    addr += size
            return {}

        def probe(root, env, log):
            names = set(adapter.ARTIFACTS)
            if name != "linked":
                names -= {adapter.direct.DIP+"dip-plugin"+ext for ext in (".elf", ".elf.orig")}
            if name == "missing-objects":
                names -= {adapter.direct.DIP+n for n in adapter.OBJECTS}
            artifacts(root, names)
            command = ("/unused/bin/arm-eabi-gcc -mcpu=arm926ej-s -mthumb -mthumb-interwork -mbig-endian "
                       "-nostartfiles -nostdlib -Wl,-T,link.ld,-Map,dip-plugin.map -Wl,--gc-sections -Wl,-static "
                       f"config.o {experimental} {stock_objects} ../cios-lib/cios-lib.a -lgcc -o dip-plugin.elf.orig")
            if name == "wrong-argv":
                command = command.replace(" mailbox.o", "")
            if name != "no-invocation":
                print(command, file=log)
            if name == "linked":
                return
            (root / build.stock.DIP.with_suffix(".map")).write_text(partial_map)
            if name == "complete":
                print("arm-eabi-ld: section '.text' will not fit in region 'exe'", file=log)
            if name == "object-failure":
                print("make[1]: *** [Makefile:61: mailbox.o] Error 2", file=log)
            print("arm-eabi-ld: region 'exe' overflowed by", 49 if name == "mismatch" else 48, "bytes", file=log)
            if name == "assembler":
                print("arm-eabi-as: unrecognized option --synthetic-option\nmake: *** [netdisc_gate.o] Error 1", file=log)
            if name == "other-ld":
                print("arm-eabi-ld: final link failed: Nonrepresentable section on output", file=log)
            print("collect2: ld returned 1 exit status\nmake: *** [Makefile:57: dip-plugin.elf] Error 1", file=log)
            raise subprocess.CalledProcessError(2, ["synthetic make"])

        with ExitStack() as stack:
            for obj, field, value in ((build.stock, "SOURCE_HASH", build.stock.digest(archive)),
                                      (adapter, "PATCHED", postimages),
                                      (adapter, "INPUTS", adapter.PINS | {adapter.direct.DIP+k:v for k,v in postimages.items()}),
                                      (inspect, "STOCK_ELF", digest(control_elf)), (inspect, "STOCK_MAP", digest(control_map)),
                                      (build.stock, "build", control), (build.stock, "compile_extraction", probe),
                                      (build, "inspect", inspect_layout)):
                stack.enter_context(patch.object(obj, field, value))
            stack.enter_context(patch.object(build, "partial_objects"))  # cross-tool invocation boundary
            j.write("stage", "approval")
            j.write("revision", "checkout", os.environ.get("GITHUB_SHA", "1"*40))
            for key, value in (("image","ubuntu24"), ("version","20260101.1.1"), ("run",1), ("attempt",1), ("uid",1000)):
                j.write("runner", key, value)
            j.write("stage", "inputs")
            for n, h in adapter.PINS.items():
                j.write("pin", n, h)
            j.write("stage", "prepare")
            j.write("revision", "d2x", build.stock.REV)
            j.write("check", "source-tar", build.stock.SOURCE_HASH)
            j.write("check", "r32", build.stock.R32_HASH)
            for tool, version in (("gcc","4.5.1"), ("ld","2.20.1.20100303"), ("make","4.3"), ("python","3.12")):
                j.write("tool", tool, version)
            self.assertEqual(build.measure_pair(work, {"DEVKITARM": "/unused"}, j), int(name != "linked"))
            j.write("private-digest", "prepare", "environment", digest(b"environment"))
            for step in ("provision", "retrieve", "measure"):
                j.write("workflow", step, "failure" if step == "measure" and name != "linked" else "success")
            rows = [json.loads(line) for line in j.path.read_text().splitlines()]
            self.assertIn(["outcome", outcome], rows)
            adapter.direct.collect(work, work/"public", adapter.SCHEMA, adapter.INPUTS)
            if check_rows:
                check_rows(rows)
            if outcome in ("region-overflow", "linked-review-required"):
                for kind in ("stage", "build", "runner", "tool", "revision", "pin", "check", "artifact",
                             "section", "load", "region", "workflow", "overflow-report" if name != "linked" else "review"):
                    incomplete = [row for row in rows if row[0] != kind]
                    with self.subTest(omitted=kind), self.assertRaises(ValueError):
                        adapter.validate_journal(incomplete)
                if name == "complete":
                    # All fields remain individually well-typed and in range.
                    for kind, position, value in (("overflow-report", 3, 49), ("check", 2, "0"*64),
                                                  ("load", 6, 4), ("attempted", 4, exe+16)):
                        altered = [row.copy() for row in rows]
                        next(row for row in altered if row[0] == kind
                             and (kind != "overflow-report" or row[2] == "region"))[position] = value
                        with self.subTest(contradiction=kind), self.assertRaises(ValueError):
                            adapter.validate_journal(altered)
            else:
                self.assertTrue(any(row[0] == "attempted" for row in rows))
                self.assertFalse(any(row[0] == "overflow" for row in rows))

    def test_complete_link_and_collection(self):
        self.synthetic_pair("complete", "region-overflow")
        self.synthetic_pair("linked", "linked-review-required")

    def test_affirmative_overflow_through_collector(self):
        import json
        from tempfile import TemporaryDirectory

        def collect(rows, valid):
            with TemporaryDirectory(dir=self.root) as tmp:
                work = Path(tmp)
                (work / "sizing.jsonl").write_text("".join(json.dumps(row)+"\n" for row in rows))
                dest = work / "public"
                if valid:
                    adapter.direct.collect(work, dest, adapter.SCHEMA, adapter.INPUTS)
                    self.assertEqual([json.loads(line) for line in (dest/"sizing.jsonl").read_text().splitlines()], rows)
                else:
                    with self.assertRaises(ValueError):
                        adapter.direct.collect(work, dest, adapter.SCHEMA, adapter.INPUTS)
                    self.assertFalse(list(dest.iterdir()))

        marker = ["build", "probe", "complete-link-invoked"]
        def interrupted(rows):
            first = next(i for i, row in enumerate(rows) if row[0] == "overflow")
            outcome = rows.index(["outcome", "region-overflow"])
            self.assertEqual(outcome-first, 2)
            for end in range(first, outcome+1):
                collect(rows[:end], True)
            collect(rows[:outcome]+rows[outcome+1:], True)
            for kind in ("stage", "revision", "runner", "tool", "pin", "check", "artifact", "build",
                         "load", "section", "region", "private-digest", "attempted", "overflow-report", "diagnostic"):
                with self.subTest(omitted=kind):
                    collect([r for r in rows[:outcome] if r[0] != kind], False)
            collect(rows[:first]+[rows[first], rows[first]], False)

        def forged(rows):
            outcome = rows.index(["outcome", "compile-error"])
            diag = next(r for r in rows if r[0] == "diagnostic" and r[1] in ("assembler", "compile"))
            report = next(r for r in rows if r[:3] == ["overflow-report", "exe", "region"])
            attempt = next(r for r in rows if r[:3] == ["attempted", "exe", "region"])
            claim = ["overflow", *attempt[1:]]
            collect([marker, report, attempt, claim, diag, rows[outcome]], False)
            collect([marker, report, attempt, claim], False)
            insert = rows.index(diag)
            injected = rows[:insert]+[marker]+rows[insert:outcome]+[claim]
            collect(injected+rows[outcome:], False)
            collect(injected, False)

        self.synthetic_pair("complete", "region-overflow", interrupted)
        for case in ("assembler", "object-failure"):
            with self.subTest(case=case):
                self.synthetic_pair(case, "compile-error", forged)

    def test_incomplete_or_contradictory_link(self):
        for name in ("missing-objects", "no-invocation", "wrong-argv", "assembler", "mismatch", "other-ld"):
            with self.subTest(name=name):
                self.synthetic_pair(name, "compile-error" if name == "assembler" else "overflow-evidence-unresolved")

    def test_linked_extent_and_public_flow(self):
        from unittest.mock import patch
        import struct
        from scripts import experimental_dip_inspect as inspect
        from test_stock_dip import footprint_fixture
        root = self.root / "probe"
        dest = root / adapter.direct.stock.DIP
        dest.parent.mkdir(parents=True)
        elf, link_map = footprint_fixture(self.root)
        size = sum(adapter.STORAGE.values())
        self.assertEqual(size, 2304)
        data = bytearray(elf.read_bytes())
        struct.pack_into(">I", data, 52 + 2*32 + 20, size + 32)
        struct.pack_into(">I", data, 512 + 7*40 + 20, size + 24)
        dest.with_suffix(".elf.orig").write_bytes(data)
        dest.with_suffix(".map").write_text(link_map.read_text().replace("0x13802008 0x14", f"0x13802008 {size+24:#x}"))
        addr = 0x13802020
        syms = "13800010 00000004 T DI_EmulateIoctl\n"
        for name, count in adapter.STORAGE.items():
            syms += f"{addr:08x} {count:08x} B {name}\n"
            addr += count
        listing = ("13800010 <DI_EmulateIoctl>:\n 13800010: e12fff1e bx lr\n"
                   " 13800014: cafebabe .word 0xcafebabe\n")

        def private(root, toolchain, label, args, elf, journal):
            return syms if label == "symbols" else listing

        with patch.object(inspect, "private_listing", side_effect=private):
            inspect.inspect(root, self.root, self.journal, {})
            syms = syms.replace("00000060 B nd_completions", "0000005f B nd_completions")
            with self.assertRaisesRegex(ValueError, "static allocation"):
                inspect.inspect(root, self.root, adapter.journal_at(self.root / "bad-layout.jsonl"), {})
        adapter.direct.collect(self.root, self.root / "public", adapter.SCHEMA, adapter.INPUTS)
        evidence = (self.root / "public/sizing.jsonl").read_text()
        self.assertIn('"literal-site"', evidence)
        self.assertIn('"gap", "probe", "exe"', evidence)
        self.assertIn('"missing", "nd_validate_reply"', evidence)
        self.assertNotIn("cafebabe", evidence)
