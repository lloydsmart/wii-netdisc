"""Run the real probe C in a fresh native Linux x86 process for each scenario."""

from pathlib import Path
import subprocess
import tempfile
import unittest


class NativeProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        work = Path(directory.name)
        tests = Path(__file__).resolve().parent
        for name in ("string.h", "plugin.h", "mem.h", "syscalls.h"):
            (work / name).write_text('#include "fixture.h"\n')
        cls.program = work / "native-dip"
        subprocess.run(["gcc", "-m32", "-std=gnu99", "-ffreestanding", "-fno-builtin", "-fno-pie",
                        "-no-pie", "-nostdlib", "-Wall", "-Werror", "-Wl,-Ttext-segment=0x400000",
                        "-I", work, "-I", tests / "native_dip", "-I", tests.parent / "research/experimental_dip",
                        tests / "native_dip/fixture.c", "-o", cls.program], check=True)

    def scenarios(self, *cases):
        for mode, description in cases:
            with self.subTest(description):
                result = subprocess.run([self.program, mode], capture_output=True, text=True, timeout=2)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_admission(self):
        self.scenarios(("A", "arm-shaped malformed read spends claim"), ("I", "invalid output extent"),
                       ("P", "inaccessible arm input"), ("G", "owned input alone identifies malformed read"),
                       ("S", "invalid synchronized arm cannot bind tag"), ("D", "exact replay preserves read"),
                       ("a", "changed arm replay spends the read"))

    def test_recognition_cache_ownership(self):
        self.scenarios(("X", "split tag synchronized within the owned read allocation"),
                       ("O", "unrelated ordinary input preserves preceding dirty byte"),
                       ("Q", "bound output cannot authorise invalidating foreign input"),
                       ("f", "matching foreign tag forwards to stock and preserves the arm"),
                       ("q", "byte-identical foreign read with bound output rejects without a load"))

    def test_reservation_provision(self):
        self.scenarios(("0", "absent provision"), ("1", "unaligned arm base"), ("2", "unaligned read end"),
                       ("3", "short arm reservation"), ("4", "reversed bounds"), ("5", "end outside MEM1"),
                       ("6", "overlapping input reservations"), ("7", "output aliases read reservation"),
                       ("8", "arm bytes in read allocation"), ("9", "foreign arm bytes"))

    def test_reserved_read_extent(self):
        self.scenarios(("e", "starts inside but extends past end"), ("l", "unrepresentable input span"),
                       ("r", "read using the arm allocation"), ("b", "last owned line is valid"))

    def test_owned_read_uses_fresh_tag(self):
        self.scenarios(("c", "matching stale tag cannot admit the read"),
                       ("h", "matching fresh tag admits the intended read"))

    def test_final_issue_deadline(self):
        self.scenarios(("u", "close intent published one tick before expiry"),
                       ("U", "close intent reaches equality before issue"),
                       ("t", "clock advances during the final lease synchronization"),
                       ("K", "eligible cleanup issues a previously unissued close once"),
                       ("N", "opening intent expires without acquiring a loan"))

    def test_abandonment_epoch(self):
        self.scenarios(("B", "one tick left"), ("E", "at expiry"), ("L", "one tick late"),
                       ("J", "first close uses last tick"), ("Z", "verification starts cleanup before publication"), ("W", "six-second submission and twelve-second completion"))

    def test_acquisition_and_cleanup(self):
        self.scenarios(("F", "matched socket error"), ("T", "ambiguous socket submission"),
                       ("C", "duplicate socket completion"), ("Y", "lost socket completion"),
                       ("M", "negative RM acquisition"), ("V", "verified exchange survives ambiguous close"),
                       ("H", "28 coherent one-byte receives, zero in both descriptor namespaces"))
