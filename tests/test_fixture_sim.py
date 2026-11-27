"""Synthetic event sequences for ADR 0004. Only this driver sees hidden effects."""

import unittest
from dataclasses import replace

from research.fixture_sim.di import (
    Completion, DI, Mailbox, Ownership, Phase, Retirement, Sample, ServiceReport, Step,
)
from research.fixture_sim.evidence import (
    Accept, Arm, Baseline, CaptureReceipt, Endpoints, Identity, Observer, PeerFrame, PeerSelection, Read, ReplyPath, Return, Review,
)
from research.fixture_sim.gx import GX


RUN = Identity("boot A", 250, "DIP A", "GX A", b"trial001")
READ = Read(RUN.tag, "reserved extent", 3, "unencrypted read", 32, 8)
ENDS = Endpoints("client:41000", "wired peer:8200")
ARM = Arm(RUN, bytes(range(16)), READ, PeerSelection("peer run A", ENDS.listener))
TID = 12


class Driver:
    """Explicit injections and transcript helpers for a single test run."""

    def __init__(self, *, start=0, **options):
        self.di = DI(RUN, **options)
        self.observer = Observer(ARM, modulus=self.di.modulus)
        self.recovery = self.observer.recovery
        self.review = Review(ARM, TID, self.observer)
        self.gx = GX(ARM, self.observer.authorizes)
        self.now = start
        self.bounded = True
        self.sample_times = {}
        self.hidden_resources = {}
        self.hidden_writes = {}
        self.peer_received = bytearray()
        self.peer_frame = self.accepted = None
        self.arm_call = self.read_call = None

    @property
    def clock(self):
        previous = self.di.last_sample
        bound = None
        if previous and self.bounded and 0 <= self.now - self.sample_times[previous] < self.di.modulus // 2:
            bound = previous.anchor
        sample = Sample(self.now % self.di.modulus, bound)
        self.sample_times[sample] = self.now
        return sample

    def arm_call_started(self):
        self.arm_call = self.gx.begin_arm()
        return self.di.accept_arm(ARM, self.gx.path)

    def arm(self):
        receipt = self.arm_call_started()
        self.gx.ipc_completed(self.arm_call, 1)
        self.gx.wrapper_returned(self.arm_call, 0, receipt)

    def dispatch(self):
        self.read_call = self.gx.dispatch(tag_preserved=True, output_preserved=True)
        assert self.read_call is not None

    def claim(self, tid=TID):
        self.arm()
        self.dispatch()
        assert self.di.outer_read(RUN, READ, tid, self.clock, self.gx.path) == "claimed"

    def start(self, action, resource):
        loan = self.di.submit(self.clock)
        assert loan and loan.step == Step(action, resource), (loan, action, resource)
        return loan

    def admit(self):
        self.di.submission_return(0, self.clock)

    def word(self, word, *, synchronize=None):
        assert self.di.storage.mailbox.offer(word)
        return self.di.dequeue(self.clock, synchronize=synchronize)

    def device_write(self, loan, data):
        assert loan.receive and 0 < len(data) <= len(loan.storage.scratch)
        loan.storage.scratch[:len(data)] = data
        self.hidden_writes[loan.receive] = bytes(data)

    def synchronize(self, loan):
        written = self.hidden_writes.get(loan.receive)
        if written and loan.storage.scratch[:len(written)] == written:
            loan.receive.publish(written)

    def complete(self, result, data=b""):
        if data:
            self.device_write(self.di.pending, data)
        self.word(Completion(self.di.storage.reply_pointer, result), synchronize=self.synchronize)

    def operation(self, action, resource, result=0, data=b""):
        loan = self.start(action, resource)
        self.admit()
        if action in ("link", "startup", "ready"):
            loan.storage.service = ServiceReport(loan.step, True)
        self.complete(result, data)
        return loan

    def ready(self):
        self.operation("open", "NCD", 0)
        self.operation("link", "NCD")
        self.operation("close", "NCD")
        self.operation("open", "SO", 0)  # Reuse a confirmed released process fd.
        self.operation("open", "KD", 1)
        self.operation("startup", "KD")
        self.operation("close", "KD")
        self.operation("ready", "SO")

    def connect(self, previous_accepts=0):
        self.operation("acquire socket", "socket", 0)
        self.di.storage.endpoints = ENDS
        self.operation("connect", "socket")
        self.accepted = Accept("peer run A", ENDS, previous_accepts + 1)

    def exchange_start(self, previous_accepts=0):
        self.claim()
        self.ready()
        self.connect(previous_accepts)

    def send(self, size):
        loan = self.start("send", "socket")
        self.admit()
        self.peer_received.extend(loan.send_bytes[:size])
        self.complete(size)

    def peer_reply(self):
        request = bytes(self.peer_received)
        reply = request + self.accepted.connection_id.to_bytes(4, "big")
        self.peer_frame = PeerFrame(self.accepted, request, reply)
        return reply

    def receive(self, data):
        self.operation("receive", "socket", len(data), data)

    def exchange(self):
        self.exchange_start(previous_accepts=0x800000FE)
        self.send(7)
        self.send(17)
        reply = self.peer_reply()
        self.receive(reply[:9])
        self.receive(reply[9:])
        self.di.verify(self.clock)

    def capture(self, *, omit=()):
        for publication in (self.di.trace, self.gx.trace):
            for i, record in enumerate(publication.slots):
                if record.kind not in omit:
                    self.observer.capture(publication.snapshot(i))

    def handback(self, result):
        assert result is not None
        self.gx.ipc_completed(self.read_call, result.raw)
        self.gx.wrapper_returned(self.read_call, 0 if result.raw == 1 else result.raw, result)

    def finish(self, *, quiesced=True, marker=True):
        result = self.di.finish(self.clock, Retirement(self.di.storage.mailbox, quiesced))
        self.handback(result)
        if marker:
            assert self.gx.at_pre_cleanup()
        self.capture()
        self.gx.finish(self.observer.release_receipt())
        self.capture()

    def verified(self):
        return self.review.exchange_verified(self.accepted, self.peer_frame)

    def baseline(self, **controls):
        return self.review.baseline(self.accepted, self.peer_frame, **controls)


class ArmingTests(unittest.TestCase):
    def test_ordinary_and_duplicate_reads(self):
        d = Driver()
        d.arm()
        ordinary = replace(READ, tag=b"ordinary", output="another allocation")
        self.assertEqual(d.di.outer_read(RUN, ordinary, TID, d.clock, ReplyPath()), "ordinary")
        self.assertFalse(d.di.spent)
        self.assertIsNone(d.di.submit(d.clock))
        d.dispatch()
        self.assertEqual(d.di.outer_read(RUN, READ, TID, d.clock, d.gx.path), "claimed")
        self.assertEqual(d.di.outer_read(RUN, READ, TID, d.clock, ReplyPath()).disposition, "duplicate")
        self.assertEqual(d.di.outer_read(RUN, ordinary, TID, d.clock, ReplyPath()), "ordinary")
        self.assertEqual([r.kind for r in d.di.trace.slots], ["entry"])
        self.assertIsNone(d.gx.dispatch(tag_preserved=True, output_preserved=True))
        self.assertIsNone(d.gx.begin_arm())
        self.assertIsNone(d.di.accept_arm(ARM, ReplyPath()))

    def test_malformed_consumes_before_media_or_network(self):
        variants = [replace(READ, **change) for change in (
            {"tag": b"changed!"}, {"output": "wrong extent"}, {"fd": 4},
            {"command": "other read"}, {"length": 64}, {"word_offset": 9},
            {"input_length": 12}, {"output_length": 8},
        )]
        for identity, read in [(RUN, v) for v in variants] + [(replace(RUN, slot=249), READ)]:
            with self.subTest(identity=identity, read=read):
                d = Driver()
                d.arm()
                d.dispatch()
                rejected = d.di.outer_read(identity, read, TID, d.clock, d.gx.path)
                self.assertEqual(rejected.disposition, "rejected before entry")
                self.assertEqual(d.di.outer_read(RUN, READ, TID, d.clock, ReplyPath()).disposition, "duplicate")
                self.assertIsNone(d.di.submit(d.clock))
                self.assertFalse(d.di.trace.slots)
                d.handback(rejected)
                d.capture()
                self.assertEqual(d.baseline(), Baseline.NEVER)

    def test_uncertain_receipt_and_discriminators(self):
        for receipt_fault in ("lost", "wrong build", "wrong tuple", "none"):
            with self.subTest(receipt_fault=receipt_fault):
                d = Driver()
                receipt = d.arm_call_started()
                if receipt_fault == "lost":
                    receipt = None
                if receipt_fault == "wrong build":
                    receipt = replace(receipt, identity=replace(RUN, dip_build="other"))
                if receipt_fault == "wrong tuple":
                    receipt = replace(receipt, read=replace(READ, word_offset=9))
                d.gx.ipc_completed(d.arm_call, 1)
                d.gx.wrapper_returned(d.arm_call, 0, receipt)
                d.capture()
                self.assertEqual(d.baseline(), Baseline.UNKNOWN)
                preserved = receipt_fault != "none"
                self.assertIsNone(d.gx.dispatch(tag_preserved=preserved, output_preserved=preserved))
                self.assertIsNone(d.gx.begin_arm())
                self.assertFalse(d.di.spent)
                d.capture()
                self.assertEqual(d.baseline(), Baseline.NEVER)
        for tag in (False, True):
            d = Driver()
            d.arm()
            self.assertIsNotNone(d.gx.dispatch(tag_preserved=tag, output_preserved=not tag))

    def test_premature_ppc_returns_keep_internal_and_external_loans(self):
        for kind in ("arm", "read"):
            with self.subTest(kind=kind):
                d = Driver()
                receipt = d.arm_call_started()
                call = d.arm_call
                payload = receipt
                if kind == "read":
                    d.gx.ipc_completed(call, 1)
                    d.gx.wrapper_returned(call, 0, receipt)
                    d.dispatch()
                    call = d.read_call
                    d.di.outer_read(RUN, READ, TID, d.clock, d.gx.path)
                    d.start("open", "NCD")  # DI and the PPC IPC request are still inside submission.
                    payload = None
                d.gx.ipc_completed(replace(call, identity=replace(RUN, instance="old")), 1)
                d.gx.wrapper_returned(call, 0, payload)
                self.assertTrue(d.gx.ambiguous)
                d.gx.ipc_completed(call, 1)  # A later ISR cannot repair early release.
                d.gx.wrapper_returned(call, 0, payload)
                self.assertEqual(d.gx.loans, {"internal IPC request", "wait queue", "input", "output"})
                self.assertIsNone(d.gx.dispatch(tag_preserved=True, output_preserved=True))
                self.assertIsNone(d.gx.begin_arm())
                self.assertFalse(d.gx.at_pre_cleanup())
                self.assertTrue(d.gx.reserved)
                self.assertFalse(d.gx.game_launch_allowed)
                d.capture()
                self.assertEqual(d.baseline(), Baseline.UNKNOWN)
                self.assertFalse(d.review.safe_termination)


class OwnershipTests(unittest.TestCase):
    def test_hidden_open_outcomes_are_observationally_equivalent(self):
        for status, outcomes in (
            (0, ("no acquisition yet", "installed fd")),
            (-1, ("no acquisition", "RM only, fd table full", "installed fd")),
        ):
            histories = []
            for hidden in outcomes:
                d = Driver(queue_capacity=1)
                d.claim()
                loan = d.start("open", "NCD")
                self.assertTrue(loan.storage.mailbox.offer(Phase.BRINGUP))
                if not hidden.startswith("no acquisition"):
                    d.hidden_resources["RM object"] = 91
                if hidden == "installed fd":
                    d.hidden_resources["process fd"] = 3
                    reply = Completion(loan.storage.reply_pointer, d.hidden_resources["process fd"])
                    self.assertFalse(loan.storage.mailbox.offer(reply))
                d.di.submission_return(status, d.clock)
                d.now = 30
                d.di.dequeue(d.clock)
                d.capture()
                self.assertEqual(loan.acquisition.ownership, Ownership.UNRESOLVED)
                self.assertIsNone(loan.acquisition.number)
                self.assertIsNone(d.di.submit(d.clock))
                self.assertFalse(d.di.storage.retired)
                histories.append((d.di.phase, d.di.first_failure, tuple(d.di.trace.slots),
                                  d.baseline(), d.review.safe_termination))
            for other in histories[1:]:
                self.assertEqual(histories[0], other)

    def test_known_pre_admission_rejection_preserves_prior_handles(self):
        d = Driver()
        d.claim()
        d.operation("open", "NCD", 0)
        d.operation("link", "NCD")
        d.operation("close", "NCD")
        d.operation("open", "SO", 0)
        self.assertIsNone(d.di.submit(d.clock, ingress=Mailbox(capacity=0)))
        self.assertEqual([a.resource for a in d.di.ledger], ["NCD", "SO"])
        d.operation("close", "SO")
        d.finish()
        self.assertTrue(d.review.safe_termination)
        self.assertEqual(d.baseline(listener=True, wired=True), Baseline.FAILURE)

    def test_blocked_submission_independent_watchdog_and_return(self):
        d = Driver()
        d.claim()
        pending = d.start("open", "NCD")
        d.now = 31
        self.assertFalse(d.word(Phase.BRINGUP))
        self.assertFalse(d.word(Completion(d.di.storage.reply_pointer, 0)))
        self.assertEqual(pending.stage, "submitting")
        d.capture()
        d.observer.advance(55)
        self.assertTrue(d.observer.watchdog_due)
        d.recovery.initiate()
        self.assertIsNone(d.di.first_failure)
        self.assertIs(d.di.pending, pending)
        self.assertFalse(d.di.dequeue(d.clock))
        self.assertIsNone(d.di.finish(d.clock, Retirement(d.di.storage.mailbox, True)))
        self.assertFalse(d.review.safe_termination)
        self.assertEqual(d.baseline(listener=True, wired=True), Baseline.UNKNOWN)
        d.admit()
        self.assertEqual(d.di.first_failure, (Phase.BRINGUP, "deadline"))
        self.assertTrue(d.di.dequeue(d.clock))  # old timer
        self.assertTrue(d.di.dequeue(d.clock))  # open handle 0
        self.assertEqual(d.di.ledger[0].ownership, Ownership.KNOWN)
        self.assertEqual(d.di.ledger[0].number, 0)
        d.operation("close", "NCD")
        d.finish()
        self.assertTrue(d.review.safe_termination)

    def test_quarantined_receive_writes_and_never_completing_loan(self):
        d = Driver()
        d.exchange_start()
        d.send(24)
        reply = d.peer_reply()
        loan = d.start("receive", "socket")
        d.admit()
        d.now = 5
        d.word(Phase.EXCHANGE)
        before = d.di.first_failure
        d.device_write(loan, reply)  # Device wrote after timeout, without delivering a word.
        self.assertFalse(d.di.received)
        self.assertIs(d.di.pending, loan)
        self.assertIsNone(d.di.submit(d.clock))
        self.assertIsNone(d.di.finish(d.clock, Retirement(d.di.storage.mailbox, True)))
        self.assertEqual([a.resource for a in d.di.ledger if a.ownership == Ownership.KNOWN],
                         ["SO", "socket"])
        d.recovery.initiate()
        self.assertFalse(loan.storage.retired)
        self.assertFalse(d.review.safe_termination)
        d.synchronize(loan)
        d.complete(28)
        self.assertEqual(d.di.late[-1], (Step("receive", "socket"), 28, reply))
        self.assertFalse(d.di.received)
        self.assertIsNone(d.di.verified)
        d.operation("close", "socket", -2)
        self.assertEqual(d.di.first_failure, before)
        self.assertIsNone(d.di.submit(d.clock))

    def test_ambiguous_close_number_reuse(self):
        for outcome in ("error completion", "ambiguous submission", "lost completion"):
            with self.subTest(outcome=outcome):
                d = Driver()
                d.exchange()
                loan = d.start("close", "socket")
                d.di.submission_return(-1 if outcome == "ambiguous submission" else 0, d.clock)
                d.hidden_resources[loan.acquisition.number] = "later unrelated acquisition"
                if outcome == "error completion":
                    d.complete(-1)
                else:
                    d.now = 5
                    d.word(Phase.CLEANUP)
                self.assertEqual(loan.acquisition.ownership, Ownership.UNRESOLVED)
                self.assertIsNone(d.di.submit(d.clock))
                self.assertEqual(loan.acquisition.close_history.count("submitting"), 1)
                self.assertEqual(loan.acquisition.parent, d.di.ledger[1].serial)
                self.assertEqual(d.di.ledger[1].ownership, Ownership.KNOWN)
                d.capture()
                self.assertTrue(d.verified())
                self.assertFalse(d.review.safe_termination)

    def test_late_receive_error_leaves_remaining_cleanup_budget(self):
        d = Driver()
        d.exchange_start()
        d.send(24)
        d.start("receive", "socket")
        d.admit()
        d.now = 5
        d.word(Phase.EXCHANGE)
        d.now = 6
        d.complete(-4)
        self.assertEqual(d.di.late, [(Step("receive", "socket"), -4, b"")])
        d.operation("close", "socket")
        d.operation("close", "SO")
        d.finish()
        self.assertEqual(d.di.first_failure, (Phase.EXCHANGE, "deadline"))
        self.assertFalse(d.di.cleanup_failures)
        self.assertTrue(d.review.safe_termination)
        self.assertEqual(d.baseline(listener=True, wired=True), Baseline.FAILURE)

    def test_late_close_releases_only_original_acquisition(self):
        for result in (0, -1):
            with self.subTest(result=result):
                d = Driver()
                d.exchange()
                loan = d.start("close", "socket")
                d.admit()
                d.now = 5
                d.word(Phase.CLEANUP)
                d.hidden_resources[0] = "new socket"
                d.complete(result)
                self.assertEqual(loan.acquisition.ownership,
                                 Ownership.RELEASED if result == 0 else Ownership.UNRESOLVED)
                self.assertEqual(d.di.ledger[1].ownership, Ownership.KNOWN)
                self.assertEqual(d.di.first_failure, (Phase.CLEANUP, "deadline"))
                self.assertIsNone(d.di.submit(d.clock))
                d.finish()
                self.assertTrue(d.verified())
                self.assertEqual(d.baseline(), Baseline.PASS)
                self.assertFalse(d.review.safe_termination)
                self.assertTrue(d.gx.reserved)


class DeadlineTests(unittest.TestCase):
    def test_open_completion_and_expiry_delivery_permutations(self):
        for now in (29, 30, 31):
            for timer_first in (False, True):
                with self.subTest(now=now, timer_first=timer_first):
                    d = Driver()
                    d.claim()
                    loan = d.start("open", "NCD")
                    d.admit()
                    completion = Completion(loan.storage.reply_pointer, 0)
                    words = [Phase.BRINGUP, completion] if timer_first else [completion, Phase.BRINGUP]
                    for word in words:
                        self.assertTrue(loan.storage.mailbox.offer(word))
                    d.now = now  # Even a reply queued earlier waits for DI observation.
                    d.di.dequeue(d.clock)
                    d.di.dequeue(d.clock)
                    self.assertEqual(loan.acquisition.ownership, Ownership.KNOWN)
                    self.assertEqual(loan.acquisition.number, 0)
                    if now == 29:
                        self.assertIsNone(d.di.first_failure)
                        self.assertEqual(d.di.phase, Phase.BRINGUP)
                    else:
                        self.assertEqual(d.di.first_failure, (Phase.BRINGUP, "deadline"))
                        self.assertEqual(len(d.di.late), 1)
                        d.operation("close", "NCD")
                        self.assertIsNone(d.di.submit(d.clock))

    def test_early_stale_duplicate_wakeups(self):
        d = Driver()
        d.exchange_start()
        loan = d.start("send", "socket")
        d.admit()
        d.now = 3
        for token in (Phase.BRINGUP, Phase.CONNECT, Phase.EXCHANGE, Phase.EXCHANGE):
            d.word(token)
        self.assertIs(d.di.pending, loan)
        self.assertEqual(d.di.phase, Phase.EXCHANGE)
        self.assertIsNone(d.di.first_failure)
        d.now = 5
        d.word(Phase.CONNECT)
        self.assertIsNone(d.di.first_failure)
        d.word(Phase.EXCHANGE)
        d.word(Phase.EXCHANGE)
        self.assertEqual(d.di.first_failure, (Phase.EXCHANGE, "deadline"))
        self.assertIs(d.di.pending, loan)
        self.assertEqual(len([r for r in d.di.trace.slots if r.kind == "first failure"]), 1)

    def test_partial_io_and_verification_share_absolute_deadline(self):
        for boundary in ("send", "receive", "verify"):
            with self.subTest(boundary=boundary):
                d = Driver()
                d.exchange_start()
                d.now = 2
                d.send(7)
                d.now = 4
                loan = d.start("send", "socket")
                d.admit()
                d.peer_received.extend(loan.send_bytes)
                if boundary == "send":
                    d.now = 5
                d.complete(17)
                if boundary != "send":
                    reply = d.peer_reply()
                    d.receive(reply[:27])
                    d.start("receive", "socket")
                    d.admit()
                    if boundary == "receive":
                        d.now = 5
                    d.complete(1, reply[27:])
                d.now = 5
                d.di.verify(d.clock)
                self.assertEqual(d.di.first_failure, (Phase.EXCHANGE, "deadline"))
                self.assertIsNone(d.di.verified)
                self.assertEqual(d.di.phase, Phase.CLEANUP)

    def test_counter_wrap_and_unbounded_gap(self):
        for gap, bounded in ((4, True), (260, False), (128, True)):
            with self.subTest(gap=gap):
                d = Driver(start=254)
                d.exchange_start()
                d.send(24)
                reply = d.peer_reply()
                d.start("receive", "socket")
                d.admit()
                d.now += gap
                d.bounded = bounded
                d.complete(28, reply)
                d.di.verify(d.clock)
                if gap == 4:
                    self.assertEqual(d.di.verified.elapsed, 4)
                else:
                    self.assertEqual(d.di.first_failure, (Phase.EXCHANGE, "unbounded clock"))
                    self.assertIsNone(d.di.verified)
                    self.assertIsNone(d.di.submit(d.clock))
                    d.capture()
                    self.assertEqual(d.baseline(listener=True, wired=True), Baseline.UNKNOWN)

    def test_provisional_connect_and_cleanup_bounds(self):
        d = Driver(connection=2, cleanup=3)
        d.claim()
        d.ready()
        d.operation("acquire socket", "socket", 8)
        d.start("connect", "socket")
        d.admit()
        d.now = 2
        d.word(Phase.CONNECT)
        self.assertEqual(d.di.first_failure, (Phase.CONNECT, "deadline"))
        self.assertIsNone(d.di.submit(d.clock))
        d.complete(0)
        d.now = 4
        d.operation("close", "socket")
        d.now = 5
        self.assertIsNone(d.di.submit(d.clock))
        self.assertEqual(d.di.cleanup_failures, ["deadline"])
        self.assertEqual(d.di.ledger[1].ownership, Ownership.KNOWN)
        self.assertEqual(sum(r.kind == "intent" and r.value[0].action == "connect"
                             for r in d.di.trace.slots), 1)

    def test_queue_exhaustion_does_not_notify_di(self):
        d = Driver(queue_capacity=1)
        d.claim()
        loan = d.start("open", "NCD")
        d.admit()
        self.assertTrue(loan.storage.mailbox.offer(Phase.BRINGUP))
        d.hidden_resources[0] = "allocated before delivery"
        self.assertFalse(loan.storage.mailbox.offer(Completion(loan.storage.reply_pointer, 0)))
        d.di.dequeue(d.clock)  # An early wake, then an empty queue with a missing reply.
        d.now = 31
        self.assertFalse(d.di.dequeue(d.clock))
        self.assertIsNone(d.di.first_failure)
        self.assertIs(d.di.pending, loan)
        self.assertIsNone(loan.acquisition.number)
        d.observer.advance(55)
        self.assertTrue(d.observer.watchdog_due)
        self.assertFalse(d.review.safe_termination)

    def test_reply_identity_and_pointer_reuse_assumption(self):
        for bad in ("pointer", "command", "duplicate"):
            with self.subTest(bad=bad):
                d = Driver()
                d.claim()
                loan = d.start("open", "NCD")
                d.admit()
                if bad == "duplicate":
                    d.complete(0)
                pointer = object() if bad == "pointer" else loan.storage.reply_pointer
                d.word(Completion(pointer, 0, "other" if bad == "command" else "reply"))
                self.assertEqual(d.di.first_failure, (Phase.BRINGUP, "unexpected queue word"))
                self.assertIsNone(d.di.submit(d.clock))
                self.assertFalse(loan.storage.retired)

        d = Driver(exclusive_one_reply=False)
        d.claim()
        d.operation("open", "NCD", 0)
        self.assertIsNone(d.di.submit(d.clock))
        self.assertEqual(d.di.first_failure, (Phase.BRINGUP, "reply pointer unsafe to reuse"))
        # Under a false exactly-once assumption an old reply during reuse is indistinguishable.
        observations = []
        for stale in (True, False):
            d = Driver()
            d.claim()
            previous = d.operation("open", "NCD", 0)
            current = d.start("link", "NCD")
            d.admit()
            current.storage.service = ServiceReport(current.step, True)
            source = previous if stale else current
            d.word(Completion(source.storage.reply_pointer, 0))
            observations.append((d.di.pending, tuple(d.di.trace.slots), d.di.first_failure))
            self.assertIsNone(d.di.first_failure)
        self.assertEqual(*observations)

    def test_trace_space_and_timer_retirement(self):
        d = Driver(operation_records=1)
        d.claim()
        d.operation("open", "NCD", 0)
        self.assertIsNone(d.di.submit(d.clock))
        self.assertEqual(d.di.first_failure, (Phase.BRINGUP, "operation trace full"))
        self.assertEqual(d.di.ledger[0].ownership, Ownership.KNOWN)
        d = Driver()
        d.exchange()
        d.operation("close", "socket")
        d.operation("close", "SO")
        d.finish(quiesced=False)
        self.assertEqual(d.di.cleanup_failures, ["queue retirement uncertain"])
        self.assertFalse(d.di.storage.retired)
        self.assertFalse(d.review.safe_termination)
        self.assertEqual(d.baseline(), Baseline.PASS)

    def test_final_queue_drain_checks_remaining_words_and_retirement_identity(self):
        for tail in ("stale timer", "foreign reply", "foreign retirement"):
            with self.subTest(tail=tail):
                d = Driver()
                d.exchange()
                d.operation("close", "socket")
                d.operation("close", "SO")
                queue = d.di.storage.mailbox
                word = Completion(object(), 0) if tail == "foreign reply" else Phase.CONNECT
                self.assertTrue(queue.offer(word))
                retirement_queue = Driver().di.storage.mailbox if tail == "foreign retirement" else queue
                d.handback(d.di.finish(d.clock, Retirement(retirement_queue, True)))
                self.assertEqual(d.di.storage.retired, tail == "stale timer")
                self.assertEqual(bool(queue.words), tail == "foreign retirement")


class ObservationTests(unittest.TestCase):
    def test_complete_reference_run(self):
        d = Driver(start=250)
        d.claim()
        d.now += 27
        d.ready()
        d.now += 3
        d.connect(previous_accepts=0xA00000EE)
        d.now += 2
        d.send(1)
        d.send(23)
        reply = d.peer_reply()
        d.receive(reply[:13])
        d.now += 2
        d.receive(reply[13:])
        d.di.verify(d.clock)
        self.assertEqual(d.di.verified.connection_id, 0xA00000EF)
        self.assertEqual(d.di.verified.elapsed, 4)
        self.assertEqual(d.di.verified.reply, ARM.request + bytes.fromhex("a00000ef"))
        d.capture()
        self.assertTrue(d.verified())
        self.assertEqual(d.baseline(), Baseline.UNKNOWN)
        d.operation("close", "socket")
        d.operation("close", "SO")
        d.finish()
        self.assertTrue(all(a.ownership == Ownership.RELEASED for a in d.di.ledger))
        self.assertEqual(len({a.serial for a in d.di.ledger}), 4)
        self.assertEqual([a.number for a in d.di.ledger], [0, 0, 1, 0])
        self.assertTrue(d.di.storage.retired)
        self.assertFalse(d.gx.reserved)
        self.assertFalse(d.gx.loans)
        self.assertTrue(d.verified())
        self.assertEqual(d.baseline(), Baseline.PASS)
        self.assertTrue(d.review.safe_termination)
        self.assertFalse(d.gx.game_launch_allowed)
        self.assertIsNone(d.di.submit(d.clock))
        self.assertIsNone(d.di.accept_arm(ARM, ReplyPath()))
        self.assertFalse(d.di.dequeue(d.clock))

    def test_reply_checks_and_independent_controls(self):
        for fault in ("tag", "challenge", "zero id", "EOF", "over-count", "send error"):
            with self.subTest(fault=fault):
                d = Driver()
                d.exchange_start()
                if fault == "send error":
                    d.operation("send", "socket", -4)
                else:
                    d.send(24)
                    reply = bytearray(d.peer_reply())
                    if fault == "tag":
                        reply[7] ^= 1
                    if fault == "challenge":
                        reply[23] ^= 1
                    if fault == "zero id":
                        reply[24:] = bytes(4)
                    count = {"EOF": 0, "over-count": 29}.get(fault, 28)
                    d.operation("receive", "socket", count, reply)
                    d.di.verify(d.clock)
                d.operation("close", "socket")
                d.operation("close", "SO")
                d.finish()
                self.assertFalse(d.verified())
                self.assertEqual(d.baseline(listener=True, wired=True), Baseline.FAILURE)
                for listener, wired in ((None, None), (False, True), (True, False)):
                    self.assertEqual(d.baseline(listener=listener, wired=wired), Baseline.UNKNOWN)
                self.assertTrue(d.review.safe_termination)

    def test_successful_ipc_requires_coherent_readiness_evidence(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                d = Driver()
                d.claim()
                d.operation("open", "NCD", 0)
                loan = d.start("link", "NCD")
                d.admit()
                if not missing:
                    loan.storage.service = ServiceReport(loan.step, False)
                d.complete(0)
                d.operation("close", "NCD")
                d.finish()
                self.assertEqual(d.baseline(listener=True, wired=True),
                                 Baseline.UNKNOWN if missing else Baseline.FAILURE)
                self.assertTrue(d.review.safe_termination)

    def test_peer_evidence_must_join_the_accept_endpoints_id_and_bytes(self):
        d = Driver()
        d.exchange()
        d.capture()
        frame = d.peer_frame
        for change in ({"connection": replace(d.accepted, peer_run="old")},
                       {"connection": replace(d.accepted, connection_id=1)},
                       {"connection": replace(d.accepted, endpoints=Endpoints("other", "peer"))},
                       {"received": bytes(24)}, {"sent": frame.sent[:-1]}):
            with self.subTest(change=change):
                self.assertFalse(d.review.exchange_verified(d.accepted, replace(frame, **change)))
        for change in ({"endpoints": Endpoints("different client", "another peer")},
                       {"connection_id": 1}):
            wrong = replace(d.accepted, **change)
            self.assertFalse(d.review.exchange_verified(wrong, replace(frame, connection=wrong)))
        self.assertFalse(d.review.exchange_verified(None, None))

    def test_publication_capture_and_frozen_watchdog(self):
        for freeze in ("reader_frozen", "display_frozen"):
            d = Driver()
            d.claim()
            d.start("open", "NCD")  # No submission return required for independent capture.
            trace = d.di.trace
            entry = trace.snapshot(0)
            self.assertFalse(d.observer.capture(trace.snapshot(0, committed=False)))
            self.assertFalse(d.observer.capture(trace.snapshot(0, interrupted=True)))
            self.assertFalse(d.observer.capture(trace.snapshot(0, complete=False)))
            for field in ("instance", "gx_build", "dip_build", "tag"):
                stale = replace(RUN, **{field: b"old tag!" if field == "tag" else "old"})
                self.assertFalse(d.observer.capture(replace(entry, record=replace(entry.record, identity=stale))))
            self.assertFalse(d.observer.records["DI"])
            self.assertTrue(d.observer.capture(entry))
            d.observer.advance(30)
            self.assertTrue(d.observer.capture(trace.snapshot(1)))
            self.assertFalse(d.observer.capture(trace.snapshot(1)))  # A stale display gives no heartbeat.
            setattr(d.observer, freeze, True)
            d.admit()
            d.complete(0)
            d.capture()
            self.assertEqual([r.kind for r in d.observer.records["DI"].values()], ["entry", "intent"])
            d.observer.advance(55)  # Progress at 30 cannot postpone the absolute cutoff.
            self.assertTrue(d.observer.watchdog_due)
            self.assertFalse(d.recovery.requested)
            d.recovery.initiate()
            self.assertTrue(d.recovery.requested)
            self.assertEqual(d.baseline(listener=True, wired=True), Baseline.UNKNOWN)
            self.assertFalse(d.review.safe_termination)
            for instance, ios, io in (("another", True, True), (RUN.instance, False, True),
                                      (RUN.instance, True, False)):
                d.recovery.confirm_end(instance, ios_ended=ios, io_ended=io)
                self.assertFalse(d.review.safe_termination)
            d.recovery.confirm_end(RUN.instance, ios_ended=True, io_ended=True)
            self.assertTrue(d.review.safe_termination)
            self.assertEqual(d.di.ledger[0].ownership, Ownership.KNOWN)  # Last live DI observation.

    def test_interrupted_writer_leaves_a_permanent_gap(self):
        d = Driver()
        d.exchange_start()
        d.di.trace.interrupt_next = True
        d.send(24)
        d.receive(d.peer_reply())
        d.di.verify(d.clock)
        d.operation("close", "socket")
        d.operation("close", "SO")
        d.finish()
        self.assertEqual(len(d.di.trace.uncommitted), 1)
        sequence, = d.di.trace.uncommitted
        self.assertNotIn(sequence, d.observer.records["DI"])
        self.assertTrue(d.verified())
        self.assertEqual(d.baseline(), Baseline.UNKNOWN)

    def test_backfilled_record_cannot_postpone_a_progress_cutoff(self):
        d = Driver()
        d.claim()
        d.start("open", "NCD")
        d.observer.capture(d.di.trace.snapshot(1))
        d.observer.advance(34)
        self.assertFalse(d.observer.watchdog_due)
        self.assertTrue(d.observer.capture(d.di.trace.snapshot(0)))
        d.observer.advance(35)
        self.assertTrue(d.observer.watchdog_due)

    def test_marker_and_caller_evidence_gaps(self):
        for omit in ("absent marker", "pre-cleanup", "entry", "ready", "return",
                     "read handback", "arm handback", "intent", "wrong caller"):
            with self.subTest(omit=omit):
                d = Driver()
                d.claim(tid=99 if omit == "wrong caller" else TID)
                d.ready()
                d.connect()
                d.send(24)
                d.receive(d.peer_reply())
                d.di.verify(d.clock)
                d.operation("close", "socket")
                d.operation("close", "SO")
                d.handback(d.di.finish(d.clock, Retirement(d.di.storage.mailbox, True)))
                if omit != "absent marker":
                    d.gx.at_pre_cleanup()
                d.capture(omit=(omit,))
                self.assertTrue(d.verified())
                self.assertEqual(d.baseline(), Baseline.UNKNOWN)

    def test_failure_order_evidence_survives_loss_of_separate_return_record(self):
        d = Driver()
        d.claim()
        self.assertIsNone(d.di.submit(d.clock, ingress=Mailbox(capacity=0)))
        d.handback(d.di.finish(d.clock, Retirement(d.di.storage.mailbox, True)))
        d.gx.at_pre_cleanup()
        d.capture(omit=("return", "read handback", "pre-cleanup"))
        self.assertEqual(d.baseline(listener=True, wired=True), Baseline.UNKNOWN)
        d.observer.capture(d.gx.trace.snapshot(-1))
        self.assertEqual(d.baseline(listener=True, wired=True), Baseline.FAILURE)

    def test_published_marker_alone_cannot_release_the_gx_reservation(self):
        d = Driver()
        d.exchange()
        d.operation("close", "socket")
        d.operation("close", "SO")
        d.handback(d.di.finish(d.clock, Retirement(d.di.storage.mailbox, True)))
        d.gx.at_pre_cleanup()
        d.capture(omit=("pre-cleanup",))
        d.gx.finish(d.observer.release_receipt())
        d.gx.finish(d.gx.trace.slots[-1])
        self.assertTrue(d.gx.reserved)
        self.assertFalse(d.review.safe_termination)
        d.capture()
        d.gx.finish(d.observer.release_receipt())
        d.capture()
        self.assertTrue(d.review.safe_termination)

    def test_conflicting_commit_sequence_cannot_support_a_verdict(self):
        d = Driver()
        d.exchange()
        d.operation("close", "socket")
        d.operation("close", "SO")
        d.finish()
        slot = next(i for i, r in enumerate(d.di.trace.slots) if r.kind == "verified")
        frame = d.di.trace.snapshot(slot)
        damaged = replace(frame.record, value=replace(frame.record.value, connection_id=4))
        self.assertFalse(d.observer.capture(replace(frame, record=damaged)))
        self.assertFalse(d.verified())
        self.assertEqual(d.baseline(), Baseline.UNKNOWN)

    def test_cleanup_stall_preserves_verified_exchange_without_handback(self):
        d = Driver()
        d.exchange()
        d.start("close", "socket")
        d.now = 50
        d.capture()
        self.assertTrue(d.verified())
        self.assertFalse(d.gx.at_pre_cleanup())
        self.assertEqual(d.baseline(listener=True, wired=True), Baseline.UNKNOWN)
        self.assertFalse(d.review.safe_termination)

    def test_mismatched_ppc_result_cannot_establish_handback(self):
        d = Driver()
        d.claim()
        d.gx.ipc_completed(d.read_call, 0)
        d.gx.wrapper_returned(d.read_call, 0, Return(RUN, "completed", 1, READ))
        self.assertFalse(d.gx.at_pre_cleanup())
        self.assertTrue(d.gx.reserved)
        d.capture()
        self.assertEqual(d.baseline(), Baseline.UNKNOWN)


class RemediationTests(unittest.TestCase):
    def test_same_labelled_request_and_early_marker_never_match_later_di_return(self):
        for kind in ("arm", "read"):
            for correct_address in (False, True):
                with self.subTest(kind=kind, correct_address=correct_address):
                    d = Driver()
                    if kind == "arm":
                        call = d.gx.begin_arm()
                        purported = None
                    else:
                        d.exchange()
                        d.start("close", "socket")  # Still executing inside submission.
                        call = d.read_call
                        purported = Return(RUN, "completed", 1, READ)
                    other = replace(call)
                    self.assertIsNot(other, call)
                    d.gx.ipc_completed(call if correct_address else other, 1)
                    d.gx.wrapper_returned(call, 0, purported)
                    self.assertTrue(d.gx.loans)
                    self.assertFalse(d.gx.at_pre_cleanup())
                    if kind == "arm":
                        genuine = d.di.accept_arm(ARM, d.gx.path)
                    else:
                        d.admit()
                        d.complete(0)
                        d.operation("close", "SO")
                        genuine = d.di.finish(d.clock, Retirement(d.di.storage.mailbox, True))
                        self.assertEqual(genuine, purported)
                    d.gx.ipc_completed(call, 1)
                    d.gx.wrapper_returned(call, 0, genuine)
                    self.assertFalse(d.gx.at_pre_cleanup())
                    self.assertTrue(d.gx.reserved)
                    self.assertTrue(d.gx.loans)
                    d.capture()
                    self.assertEqual(d.baseline(), Baseline.UNKNOWN)
                    self.assertFalse(d.review.safe_termination)

    def test_foreign_final_callback_cannot_finish_returned_arm(self):
        d = Driver()
        receipt = d.arm_call_started()
        d.gx.ipc_completed(replace(d.arm_call), 1)
        d.gx.wrapper_returned(d.arm_call, 0, receipt)
        self.assertTrue(d.gx.ambiguous)
        self.assertTrue(d.gx.loans)
        self.assertIsNone(d.gx.dispatch(tag_preserved=True, output_preserved=True))

    def test_arm_publication_and_peer_inputs_own_immutable_bytes(self):
        tag = bytearray(RUN.tag)
        challenge = bytearray(ARM.challenge)
        identity = replace(RUN, tag=tag)
        arm = Arm(identity, memoryview(challenge), replace(READ, tag=tag), ARM.peer)
        di = DI(identity)
        di.accept_arm(arm, ReplyPath())
        trace = di.trace
        trace.emit("staged", (arm, (challenge,)))
        observer = Observer(ARM)
        self.assertTrue(observer.capture(trace.snapshot(0)))
        wire = bytearray(ARM.request)
        accepted = Accept("peer run A", ENDS, 1)
        frame = PeerFrame(accepted, wire, wire)
        tag[0] ^= 1
        challenge[0] ^= 1
        wire[0] ^= 1
        self.assertEqual(di.arm.request, ARM.request)
        captured = observer.record("DI", "staged")
        self.assertEqual(captured.identity, RUN)
        self.assertEqual(captured.value, (ARM, (ARM.challenge,)))
        self.assertEqual((frame.received, frame.sent), (ARM.request, ARM.request))
        with self.assertRaises(TypeError):
            observer.records["DI"][captured.sequence] = replace(captured, kind="changed")
        with self.assertRaises(TypeError):
            trace.emit("invalid", (("nested", []),))
        stale_tag = bytearray(b"previous")
        stale = replace(captured, identity=replace(RUN, tag=stale_tag))
        stale_tag[:] = RUN.tag
        self.assertFalse(observer.capture(replace(trace.snapshot(0), record=stale)))

    def test_stale_scratch_and_replayed_send_count_need_visible_current_range(self):
        outcomes = []
        for source in ("receive result", "stale send count"):
            for visibility in ("no write", "hidden write", "prior loan", "short range"):
                with self.subTest(source=source, visibility=visibility):
                    d = Driver()
                    d.exchange_start(int.from_bytes(RUN.tag[:4], "big") - 1)
                    send = d.start("send", "socket")
                    d.admit()
                    d.peer_received.extend(send.send_bytes[:4])
                    d.complete(4)
                    d.send(20)
                    reply = d.peer_reply()
                    old = d.operation("receive", "socket", 24, reply[:24])
                    current = d.start("receive", "socket")
                    d.admit()
                    self.assertEqual(current.storage.scratch[:4], reply[24:])
                    synchronize = None
                    if visibility == "hidden write":
                        d.device_write(current, reply[24:])
                    elif visibility == "prior loan":
                        synchronize = lambda _: d.synchronize(old)
                    elif visibility == "short range":
                        d.device_write(current, reply[24:26])
                        synchronize = d.synchronize
                    origin = current if source == "receive result" else send
                    d.word(Completion(origin.storage.reply_pointer, 4), synchronize=synchronize)
                    d.di.verify(d.clock)
                    d.capture()
                    self.assertEqual(d.di.received, ARM.request)
                    self.assertFalse(d.verified())
                    self.assertEqual(d.di.first_failure, (Phase.EXCHANGE, "receive visibility unresolved"))
                    self.assertIs(d.di.pending, current)
                    self.assertIsNone(d.di.submit(d.clock))
                    self.assertFalse(d.review.safe_termination)
                    outcomes.append(tuple(d.di.trace.slots))
        self.assertTrue(all(history == outcomes[0] for history in outcomes))

    def test_indistinguishable_stale_close_can_falsely_release_a_live_fd(self):
        histories = []
        for stale in (False, True):
            d = Driver()
            d.exchange()
            prior = d.operation("close", "socket")
            close_so = d.start("close", "SO")
            d.admit()
            d.hidden_resources["SO fd"] = close_so.acquisition.number
            if not stale:
                del d.hidden_resources["SO fd"]  # Only a real SO close releases it.
            origin = prior if stale else close_so
            d.word(Completion(origin.storage.reply_pointer, 0))
            d.finish()
            self.assertEqual("SO fd" in d.hidden_resources, stale)
            self.assertTrue(d.review.safe_termination)
            histories.append(tuple(d.di.trace.slots))
        self.assertEqual(*histories)

    def test_first_captured_exchange_and_ready_evidence_checked_against_contract(self):
        for fault in ("short", "zero id", "wrong decoded id", "5s", "30s"):
            with self.subTest(fault=fault):
                d = Driver()
                d.exchange()
                d.operation("close", "socket")
                d.operation("close", "SO")
                d.handback(d.di.finish(d.clock, Retirement(d.di.storage.mailbox, True)))
                d.gx.at_pre_cleanup()
                kind = "ready" if fault == "30s" else "verified"
                d.capture(omit=(kind,))
                i = next(i for i, r in enumerate(d.di.trace.slots) if r.kind == kind)
                snapshot = d.di.trace.snapshot(i)
                echo = d.di.verified
                if fault == "short":
                    value = replace(echo, reply=ARM.request)
                elif fault == "zero id":
                    value = replace(echo, reply=ARM.request + bytes(4))
                elif fault == "wrong decoded id":
                    value = replace(echo, connection_id=3)
                    d.accepted = replace(d.accepted, connection_id=3)
                elif fault == "5s":
                    value = replace(echo, elapsed=5)
                else:
                    value = 30
                if kind == "verified":
                    d.peer_frame = replace(d.peer_frame, sent=value.reply, connection=d.accepted)
                self.assertTrue(d.observer.capture(replace(snapshot, record=replace(snapshot.record, value=value))))
                self.assertFalse(d.observer.conflicts)
                self.assertEqual(d.verified(), fault == "30s")
                self.assertEqual(d.baseline(), Baseline.UNKNOWN)

    def test_first_cleanup_claim_must_reconcile_close_and_loan_history(self):
        for corrupted in ("cleanup", "close completion", "ingress receipt", "missing submission"):
            with self.subTest(corrupted=corrupted):
                d = Driver()
                d.exchange()
                if corrupted == "cleanup":
                    d.operation("close", "socket", -1)
                else:
                    d.operation("close", "socket")
                    d.operation("close", "SO")
                d.handback(d.di.finish(d.clock, Retirement(d.di.storage.mailbox, True)))
                d.gx.at_pre_cleanup()
                for i, r in enumerate(d.di.trace.slots):
                    frame = d.di.trace.snapshot(i)
                    if corrupted == "cleanup" and r.kind == "cleanup":
                        r = replace(r, value=True)
                    if r.kind == "completion" and r.value.step == Step("close", "socket"):
                        if corrupted == "close completion":
                            r = replace(r, value=replace(r.value, result=-1))
                        if corrupted == "ingress receipt":
                            r = replace(r, kind="ingress full", value=(r.value.step, 4))
                    if (corrupted == "missing submission" and r.kind == "submission"
                            and r.value[0] == Step("close", "socket")):
                        continue
                    self.assertTrue(d.observer.capture(replace(frame, record=r)))
                for i in range(len(d.gx.trace.slots)):
                    d.observer.capture(d.gx.trace.snapshot(i))
                self.assertTrue(d.verified())
                self.assertIsNone(d.observer.release_receipt())
                d.gx.finish(d.observer.release_receipt())
                self.assertTrue(d.gx.reserved)
                self.assertFalse(d.review.safe_termination)

    def test_clock_attestation_covers_consumed_sample_and_stale_wake_intervals(self):
        d = Driver()
        d.exchange_start()
        d.send(24)
        d.start("receive", "socket")
        d.admit()
        for now in (90, 180):
            d.now = now
            d.word(Phase.CONNECT)
            self.assertEqual(d.di.elapsed, now)
        d.now = 258
        d.complete(28, d.peer_reply())
        d.di.verify(d.clock)
        self.assertEqual(d.di.first_failure, (Phase.EXCHANGE, "deadline"))
        self.assertIsNone(d.di.verified)
        for bad in (-1, 256):
            d = Driver()
            d.arm()
            d.dispatch()
            d.di.outer_read(RUN, READ, TID, Sample(bad), d.gx.path)
            self.assertIsNone(d.di.submit(d.clock))
            self.assertEqual(d.di.first_failure, (Phase.BRINGUP, "unbounded clock"))
        d = Driver()
        d.exchange_start()
        skipped = d.clock  # A genuine sampler anchor, never accepted by DI.
        self.assertIsNone(d.di.submit(Sample(2, skipped.anchor)))
        self.assertEqual(d.di.first_failure, (Phase.EXCHANGE, "unbounded clock"))

    def test_plan_binds_listener_and_peer_run_before_accept(self):
        for wrong in ("listener", "peer run"):
            with self.subTest(wrong=wrong):
                d = Driver()
                d.claim()
                d.ready()
                d.operation("acquire socket", "socket", 0)
                ends = replace(ENDS, listener="unplanned:90") if wrong == "listener" else ENDS
                d.di.storage.endpoints = ends
                d.operation("connect", "socket")
                run = "unselected" if wrong == "peer run" else "peer run A"
                d.accepted = Accept(run, ends, 7)
                d.send(24)
                d.receive(d.peer_reply())
                d.di.verify(d.clock)
                d.operation("close", "socket")
                d.operation("close", "SO")
                d.finish()
                self.assertIsNotNone(d.di.verified)
                retargeted = replace(ARM, peer=PeerSelection(run, ends.listener))
                with self.assertRaises(ValueError):
                    replace(d.review, arm=retargeted)
                self.assertFalse(d.verified())
                self.assertEqual(d.baseline(), Baseline.UNKNOWN)

    def test_ingress_rejection_and_ambiguous_trap_have_distinct_evidence(self):
        full = Mailbox(1)
        full.offer("prior occupant")
        d = Driver()
        d.claim()
        self.assertIsNone(d.di.submit(d.clock, ingress=full))
        self.assertEqual(list(full.words), ["prior occupant"])
        self.assertFalse(d.di.ledger)
        d.finish()
        self.assertTrue(d.review.safe_termination)

        d = Driver()
        d.claim()
        loan = d.start("open", "NCD")
        d.hidden_resources["fd"] = 7
        d.di.submission_return(-1, d.clock)
        self.assertFalse(d.word(Completion(loan.storage.reply_pointer, 7)))
        self.assertEqual(loan.stage, "uncertain")
        self.assertEqual(loan.acquisition.ownership, Ownership.UNRESOLVED)
        self.assertIs(d.di.pending, loan)
        self.assertIsNone(d.di.submit(d.clock))
        self.assertFalse(d.review.safe_termination)

    def test_conflicting_process_descriptor_quarantines_both_acquisitions(self):
        d = Driver()
        d.claim()
        d.operation("open", "NCD", 0)
        d.operation("link", "NCD")
        d.operation("close", "NCD")
        so = d.operation("open", "SO", 7)
        kd = d.operation("open", "KD", 7)
        self.assertNotEqual(so.acquisition.serial, kd.acquisition.serial)
        for acq in (so.acquisition, kd.acquisition):
            self.assertEqual(acq.ownership, Ownership.UNRESOLVED)
            self.assertFalse(acq.close_attempted)
        self.assertIsNone(d.di.submit(d.clock))
        d.finish()
        self.assertFalse(d.review.safe_termination)
        self.assertEqual(d.baseline(listener=True, wired=True), Baseline.UNKNOWN)

    def test_timer_requires_previously_armed_producer(self):
        d = Driver()
        d.claim()
        d.word(Phase.CLEANUP)
        self.assertEqual(d.di.first_failure, (Phase.BRINGUP, "unexpected queue word"))
        self.assertTrue(d.di.queue_untrusted)
        self.assertIsNone(d.di.submit(d.clock))
        d.finish()
        self.assertFalse(d.review.safe_termination)
        self.assertEqual(d.baseline(), Baseline.UNKNOWN)

    def test_rejection_requires_negative_gate_result_and_real_read_handback(self):
        d = Driver()
        d.arm()
        d.dispatch()
        d.handback(Return(RUN, "rejected before entry", 1, READ))
        d.capture()
        self.assertTrue(d.gx.loans)
        self.assertEqual(d.baseline(), Baseline.UNKNOWN)
        # Even a first capture that consistently changes each read-side raw/status
        # cannot turn the successful result into the gate's negative rejection.
        d = Driver()
        d.arm()
        d.dispatch()
        rejected = d.di.outer_read(RUN, replace(READ, fd=4), TID, d.clock, d.gx.path)
        d.handback(rejected)
        false_payload = replace(rejected, raw=1)
        success = replace(d.gx.result, raw=1, payload=false_payload)
        for i, r in enumerate(d.gx.trace.slots):
            if r.kind in ("read final", "rejected before entry"):
                r = replace(r, value=success)
            if r.kind == "read wrapper":
                r = replace(r, value=(d.read_call, 0, false_payload))
            d.observer.capture(replace(d.gx.trace.snapshot(i), record=r))
        self.assertFalse(d.observer.conflicts)
        self.assertEqual(d.baseline(), Baseline.UNKNOWN)

    def test_arm_rejects_unrepresentable_intended_tuple(self):
        for change in ({"fd": -1}, {"fd": 2**31}, {"length": 2**32, "output_length": 2**32},
                       {"length": 0, "output_length": 0}, {"word_offset": 2**32},
                       {"word_offset": -1}, {"command": "other"}, {"input_length": 31}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(ARM, read=replace(READ, **change))

    def test_three_reference_verdicts_with_launch_inhibited(self):
        cases = (("clean", Baseline.PASS, True), ("close failed", Baseline.PASS, False),
                 ("close blocked", Baseline.UNKNOWN, False))
        for case, baseline, safe in cases:
            with self.subTest(case=case):
                d = Driver()
                d.exchange()
                if case == "close blocked":
                    d.start("close", "socket")
                    d.capture()
                else:
                    d.operation("close", "socket", -1 if case == "close failed" else 0)
                    if case == "clean":
                        d.operation("close", "SO")
                    d.finish()
                self.assertTrue(d.verified())
                self.assertEqual(d.baseline(), baseline)
                self.assertEqual(d.review.safe_termination, safe)
                self.assertFalse(d.gx.game_launch_allowed)

    def test_returned_read_requires_its_own_final_callback_and_terminal_sequence(self):
        for fault in ("foreign address", "wrong terminal sequence"):
            with self.subTest(fault=fault):
                d = Driver()
                d.exchange()
                d.operation("close", "socket")
                d.operation("close", "SO")
                result = d.di.finish(d.clock, Retirement(d.di.storage.mailbox, True))
                if fault == "foreign address":
                    d.gx.ipc_completed(replace(d.read_call), result.raw)
                    d.gx.wrapper_returned(d.read_call, 0, result)
                    self.assertTrue(d.gx.loans)
                    self.assertFalse(d.gx.at_pre_cleanup())
                    d.capture()
                else:
                    d.handback(result)
                    d.gx.at_pre_cleanup()
                    wrong = replace(d.gx.result, di_sequence=d.gx.result.di_sequence + 1)
                    kinds = ("read final", "read handback", "pre-cleanup")
                    d.capture(omit=kinds)
                    for i, r in enumerate(d.gx.trace.slots):
                        if r.kind in kinds:
                            d.observer.capture(replace(d.gx.trace.snapshot(i), record=replace(r, value=wrong)))
                self.assertIsNone(d.observer.release_receipt())
                self.assertEqual(d.baseline(), Baseline.UNKNOWN)
                self.assertTrue(d.verified())


class SecondReviewTests(unittest.TestCase):
    def test_watchdog_requires_validated_actual_release(self):
        clean = Driver()
        clean.exchange()
        clean.operation("close", "socket")
        clean.operation("close", "SO")
        clean.finish()
        borrowed = clean.gx.trace.slots[-1]
        for damage in ("borrowed", "renamed dispatch"):
            with self.subTest(damage=damage):
                d = Driver()
                if damage == "borrowed":
                    d.exchange()
                    d.operation("close", "socket", -1)
                    d.finish()
                    d.gx.trace.emit("released", borrowed.value)
                    d.capture()
                else:
                    d.claim()
                    d.start("open", "NCD")
                    d.capture(omit=("dispatch",))
                    frame = d.gx.trace.snapshot(-1)
                    d.observer.capture(replace(frame, record=replace(frame.record, kind="released")))
                self.assertFalse(d.review.safe_termination)
                d.recovery.initiate()
                d.observer.advance(d.observer.cutoff)
                self.assertTrue(d.observer.watchdog_due)

    def test_gx_cannot_issue_its_own_capture_receipt(self):
        d = Driver()
        d.exchange()
        d.operation("close", "socket")
        d.operation("close", "SO")
        terminal = d.di.finish(d.clock, Retirement(d.di.storage.mailbox, True))
        d.handback(terminal)
        d.gx.at_pre_cleanup()
        homemade = CaptureReceipt(d.gx.trace.slots[-1], terminal)
        d.gx.finish(homemade)
        self.assertTrue(d.gx.reserved)
        d.capture()
        authorized = d.observer.release_receipt()
        d.gx.finish(replace(authorized))
        self.assertTrue(d.gx.reserved)
        self.assertFalse(d.review.safe_termination)
        d.gx.finish(authorized)
        self.assertFalse(d.review.safe_termination)
        d.capture()
        self.assertTrue(d.review.safe_termination)
        d.observer.advance(d.observer.cutoff)
        self.assertFalse(d.observer.watchdog_due)

    def test_replaying_consumed_sample_cannot_verify_at_second_twelve(self):
        d = Driver()
        d.exchange_start()
        d.send(24)
        loan = d.start("receive", "socket")
        d.admit()
        old = d.di.last_sample
        d.device_write(loan, d.peer_reply())
        d.synchronize(loan)
        d.now = 12
        d.di.storage.mailbox.offer(Completion(d.di.storage.reply_pointer, 28))
        d.di.dequeue(old, synchronize=d.synchronize)
        d.di.verify(old)
        self.assertIsNone(d.di.verified)
        self.assertEqual(d.di.first_failure, (Phase.EXCHANGE, "unbounded clock"))

    def test_snapshot_before_final_write_cannot_verify_old_id(self):
        d = Driver()
        d.exchange_start()
        d.send(24)
        reply = d.peer_reply()
        d.receive(reply[:24])
        loan = d.start("receive", "socket")
        d.admit()
        d.device_write(loan, reply[24:])
        d.synchronize(loan)
        d.device_write(loan, bytes(4))
        d.complete(4)
        self.assertEqual(d.di.received, ARM.request + bytes(4))
        d.di.verify(d.clock)
        self.assertEqual(d.di.first_failure, (Phase.EXCHANGE, "bad reply"))
        self.assertIsNone(d.di.verified)

    def test_already_queued_duplicate_close_cannot_release_so(self):
        d = Driver()
        d.exchange()
        d.start("close", "socket")
        d.admit()
        queue = d.di.storage.mailbox
        reply = Completion(d.di.storage.reply_pointer, 0)
        queue.offer(reply)
        d.di.dequeue(d.clock)
        queue.offer(reply)  # First visible after dequeue but before the next binding.
        self.assertIsNone(d.di.submit(d.clock))
        self.assertTrue(d.di.queue_untrusted)
        self.assertEqual(d.di.ledger[1].ownership, Ownership.KNOWN)
        self.assertFalse(d.di.ledger[1].close_attempted)
        d.finish()
        self.assertFalse(d.review.safe_termination)

    def test_timer_waiting_before_its_phase_cannot_become_legitimate(self):
        d = Driver()
        d.exchange_start()
        d.send(24)
        d.receive(d.peer_reply())
        d.di.storage.mailbox.offer(Phase.CLEANUP)
        d.di.verify(d.clock)
        self.assertTrue(d.di.queue_untrusted)
        self.assertNotIn(Phase.CLEANUP, d.di.armed_timers)
        self.assertIsNone(d.di.submit(d.clock))

    def test_damaged_transfer_service_and_skip_transcripts(self):
        for damage in ("20 bytes", "late receive", "after verification", "missing receive",
                       "missing send admission", "failed link", "skipped"):
            with self.subTest(damage=damage):
                d = Driver()
                d.exchange()
                d.operation("close", "socket")
                d.operation("close", "SO")
                d.handback(d.di.finish(d.clock, Retirement(d.di.storage.mailbox, True)))
                d.gx.at_pre_cleanup()
                if damage == "skipped":
                    d.gx.trace.emit("skipped")
                for pub in (d.di.trace, d.gx.trace):
                    for i, r in enumerate(pub.slots):
                        if r.kind == "completion" and r.value.step == Step("receive", "socket"):
                            count = r.value.result
                            if damage == "20 bytes" and count == 19:
                                r = replace(r, value=replace(r.value, result=11, data=r.value.data[:11]))
                            if damage == "late receive":
                                r = replace(r, value=replace(r.value, late=True))
                            if damage == "after verification":
                                r = replace(r, value=replace(r.value, elapsed=1))
                            if damage == "missing receive" and count == 9:
                                continue
                        if (damage == "missing send admission" and r.kind == "submission"
                                and r.value[0] == Step("send", "socket")):
                            continue
                        if damage == "failed link" and r.kind == "service" and r.value.step.action == "link":
                            r = replace(r, value=replace(r.value, successful=False))
                        d.observer.capture(replace(pub.snapshot(i), record=r))
                self.assertEqual(d.verified(), damage in ("failed link", "skipped"))
                self.assertEqual(d.baseline(listener=True, wired=True), Baseline.UNKNOWN)

    def test_relabelled_cleanup_error_is_not_a_network_failure(self):
        d = Driver()
        d.exchange()
        d.operation("close", "socket", -1)
        d.handback(d.di.finish(d.clock, Retirement(d.di.storage.mailbox, True)))
        d.gx.at_pre_cleanup()
        for pub in (d.di.trace, d.gx.trace):
            for i, r in enumerate(pub.slots):
                if r.kind == "cleanup failure":
                    r = replace(r, kind="network failure", value=d.di.trace.slots[i - 1].value)
                d.observer.capture(replace(pub.snapshot(i), record=r))
        self.assertTrue(d.verified())
        self.assertEqual(d.review.baseline(None, None, listener=True, wired=True), Baseline.UNKNOWN)

    def test_verification_needs_a_fresh_sample_even_after_a_timely_receive(self):
        for replay in (False, True):
            with self.subTest(replay=replay):
                d = Driver()
                d.exchange_start()
                d.send(24)
                d.receive(d.peer_reply())
                previous = d.di.last_sample
                if replay:
                    d.now = 12
                    d.di.verify(previous)
                    self.assertEqual(d.di.first_failure, (Phase.EXCHANGE, "unbounded clock"))
                    self.assertIsNone(d.di.verified)
                else:
                    fresh = d.clock
                    self.assertEqual(previous.tick, fresh.tick)
                    self.assertIs(fresh.previous, previous.anchor)
                    self.assertIsNot(fresh, previous)
                    d.di.verify(fresh)
                    d.capture()
                    self.assertTrue(d.verified())
                    self.assertEqual(d.di.verified.elapsed, 0)

    def test_visibility_handoff_occurs_after_reply_while_di_still_owns_slot(self):
        for case in ("missing", "final", "late"):
            with self.subTest(case=case):
                d = Driver()
                d.exchange_start()
                d.send(24)
                reply = d.peer_reply()
                d.receive(reply[:24])
                loan = d.start("receive", "socket")
                d.admit()
                d.device_write(loan, bytes(4))
                d.synchronize(loan)
                self.assertIsNone(loan.receive.visible)
                d.device_write(loan, reply[24:])

                def final_handoff(request):
                    self.assertIs(request, loan)
                    self.assertEqual(request.stage, "reply delivered")
                    self.assertIs(d.di.pending, request)
                    self.assertEqual(bytes(d.di.received), ARM.request)
                    d.synchronize(request)

                if case == "late":
                    d.now = 5
                sync = None if case == "missing" else final_handoff
                d.word(Completion(loan.storage.reply_pointer, 4), synchronize=sync)
                d.di.verify(d.clock)
                d.capture()
                if case == "missing":
                    self.assertIs(d.di.pending, loan)
                    self.assertEqual(loan.stage, "quarantined")
                if case == "late":
                    self.assertEqual(d.di.late, [(loan.step, 4, reply[24:])])
                    self.assertEqual(bytes(d.di.received), ARM.request)
                    self.assertEqual(d.di.first_failure, (Phase.EXCHANGE, "deadline"))
                self.assertEqual(d.verified(), case == "final")

    def test_prior_timer_words_survive_reuse_and_phase_inspection(self):
        d = Driver()
        d.exchange_start()
        d.send(24)
        queue = d.di.storage.mailbox
        queue.offer(Phase.EXCHANGE)
        loan = d.start("receive", "socket")
        d.admit()
        self.assertTrue(d.di.dequeue(d.clock))
        self.assertIs(d.di.pending, loan)
        d.complete(28, d.peer_reply())
        queue.offer(Phase.EXCHANGE)
        d.di.verify(d.clock)
        self.assertTrue(d.di.dequeue(d.clock))
        self.assertFalse(d.di.queue_untrusted)
        self.assertIsNone(d.di.first_failure)
        d.capture()
        self.assertTrue(d.verified())

    def test_execution_evidence_precludes_never_ran_even_without_entry_capture(self):
        executed = Driver()
        executed.exchange()
        for kind in ("skip", "rejection"):
            with self.subTest(kind=kind):
                d = Driver()
                d.arm()
                if kind == "skip":
                    d.gx.dispatch(tag_preserved=False, output_preserved=False)
                else:
                    d.dispatch()
                    rejected = d.di.outer_read(RUN, replace(READ, fd=4), TID, d.clock, d.gx.path)
                    d.handback(rejected)
                d.capture()
                self.assertEqual(d.baseline(), Baseline.NEVER)
                # First independently captured DI evidence is a tagged network
                # intent, even though its entry frame was never captured.
                d.observer.capture(executed.di.trace.snapshot(1))
                self.assertEqual(d.baseline(), Baseline.UNKNOWN)

    def test_genuine_network_failure_survives_later_cleanup_failure(self):
        d = Driver()
        d.exchange_start()
        d.operation("send", "socket", -7)
        d.operation("close", "socket", -1)
        d.finish()
        self.assertEqual(d.di.first_failure, (Phase.EXCHANGE, "operation error"))
        self.assertEqual(d.baseline(listener=True, wired=True), Baseline.FAILURE)
        self.assertFalse(d.verified())
        self.assertFalse(d.review.safe_termination)

        damaged = Observer(ARM)
        for pub in (d.di.trace, d.gx.trace):
            for i, r in enumerate(pub.slots):
                if r.kind == "submission" and r.value == (Step("send", "socket"), 0):
                    r = replace(r, value=(Step("receive", "socket"), 0))
                damaged.capture(replace(pub.snapshot(i), record=r))
        self.assertEqual(Review(ARM, TID, damaged).baseline(listener=True, wired=True), Baseline.UNKNOWN)

    def test_confirmed_external_end_disarms_cutoff_while_submission_is_blocked(self):
        d = Driver()
        d.claim()
        loan = d.start("open", "NCD")
        d.recovery.initiate()
        d.recovery.confirm_end(RUN.instance, ios_ended=True, io_ended=True)
        d.observer.advance(d.observer.cutoff)
        self.assertTrue(d.review.safe_termination)
        self.assertIs(d.di.pending, loan)
        self.assertFalse(d.observer.watchdog_due)


class ThirdReviewTests(unittest.TestCase):
    def test_two_available_replies_cannot_decide_receive_or_close(self):
        for action, results in (("receive", (4, -1)), ("close", (0, -1)), ("close", (0, 0))):
            for pair in {results, results[::-1]}:
                with self.subTest(action=action, pair=pair):
                    d = Driver()
                    if action == "receive":
                        d.exchange_start()
                        d.send(4)
                        d.send(20)
                        reply = d.peer_reply()
                        d.receive(reply[:24])
                    else:
                        d.exchange()
                    loan = d.start(action, "socket")
                    d.admit()
                    if action == "receive":
                        d.device_write(loan, reply[24:])
                    for result in pair:
                        self.assertTrue(loan.storage.mailbox.offer(Completion(loan.storage.reply_pointer, result)))
                    d.di.dequeue(d.clock, synchronize=d.synchronize)
                    d.di.verify(d.clock)
                    d.di.dequeue(d.clock)
                    if d.di.pending is None:
                        d.finish()
                    else:
                        d.capture()
                    self.assertEqual((d.verified(), d.baseline(listener=True, wired=True), d.review.safe_termination),
                                     (action == "close", Baseline.UNKNOWN, False))
                    self.assertTrue(d.di.queue_untrusted)
                    self.assertIs(d.di.pending, loan)
                    self.assertEqual(loan.stage, "quarantined")
                    if action == "close":
                        self.assertEqual(loan.acquisition.ownership, Ownership.UNRESOLVED)
                    self.assertEqual(len(loan.storage.mailbox.words), 2)
                    self.assertIsNone(d.di.submit(d.clock))

    def test_di_publication_after_terminal_invalidates_cleanup_authority(self):
        for when in ("before issuance", "after issuance", "after release"):
            with self.subTest(when=when):
                d = Driver()
                d.exchange()
                d.operation("close", "socket")
                d.operation("close", "SO")
                d.handback(d.di.finish(d.clock, Retirement(d.di.storage.mailbox, True)))
                d.gx.at_pre_cleanup()
                d.capture()
                receipt = None
                if when != "before issuance":
                    receipt = d.observer.release_receipt()
                    self.assertIsNotNone(receipt)
                if when == "after release":
                    d.gx.finish(receipt)
                    d.capture()
                    self.assertTrue(d.review.safe_termination)
                terminal = d.observer.record("DI", "return")
                extra = d.di.trace.emit("intent", (Step("send", "socket"), 4, 0))
                self.assertEqual(extra.sequence, terminal.sequence + 1)
                d.observer.capture(d.di.trace.snapshot(-1))
                self.assertIsNone(d.observer.release_receipt())
                d.gx.finish(receipt)
                self.assertEqual(d.gx.reserved, when != "after release")
                self.assertFalse(d.review.safe_termination)
                self.assertTrue(d.verified())
                d.observer.advance(d.observer.cutoff)
                self.assertTrue(d.observer.watchdog_due)
                d.recovery.confirm_end(RUN.instance, ios_ended=True, io_ended=True)
                self.assertTrue(d.review.safe_termination)

    def test_captured_phase_clocks_and_bringup_ownership(self):
        for fault in ("receive tick", "verification elapsed", "KD descriptor", "none"):
            with self.subTest(fault=fault):
                d = Driver()
                d.exchange()
                d.operation("close", "socket")
                d.operation("close", "SO")
                d.handback(d.di.finish(d.clock, Retirement(d.di.storage.mailbox, True)))
                d.gx.at_pre_cleanup()
                for pub in (d.gx.trace, d.di.trace):
                    for index in reversed(range(len(pub.slots))):
                        frame = pub.snapshot(index)
                        r = frame.record
                        if (fault == "receive tick" and r.kind == "completion"
                                and r.value.step.action == "receive" and r.value.result == 19):
                            r = replace(r, value=replace(r.value, tick=12))
                        if fault == "verification elapsed" and r.kind == "verified":
                            r = replace(r, value=replace(r.value, elapsed=1))
                        if (fault == "KD descriptor" and r.kind == "completion"
                                and r.value.step == Step("open", "KD")):
                            r = replace(r, value=replace(r.value, result=0))
                        self.assertTrue(d.observer.capture(replace(frame, record=r)))
                self.assertEqual(d.verified(), fault in ("none", "KD descriptor"))
                self.assertEqual(d.baseline(), Baseline.PASS if fault == "none" else Baseline.UNKNOWN)
                if fault == "KD descriptor":
                    self.assertIsNone(d.observer.release_receipt())

    def test_genuine_fragment_clock_wrap_in_reverse_capture_order(self):
        d = Driver(start=63, modulus=64)
        d.exchange_start()
        d.send(7)
        d.now += 1
        d.send(17)
        reply = d.peer_reply()
        d.receive(reply[:24])
        d.now += 1
        d.receive(reply[24:])
        d.now += 1
        d.di.verify(d.clock)
        for i in reversed(range(len(d.di.trace.slots))):
            d.observer.capture(d.di.trace.snapshot(i))
        self.assertTrue(d.verified())

    def test_clock_contradiction_withholds_attribution_for_failed_send(self):
        d = Driver()
        d.exchange_start()
        d.send(4)
        d.operation("send", "socket", -1)
        d.operation("close", "socket")
        d.operation("close", "SO")
        d.finish()
        self.assertEqual(d.baseline(listener=True, wired=True), Baseline.FAILURE)
        observer = Observer(ARM)
        for pub in (d.di.trace, d.gx.trace):
            for i, r in enumerate(pub.slots):
                frame = pub.snapshot(i)
                if r.kind == "completion" and r.value.step.action == "send" and r.value.result == 4:
                    frame = replace(frame, record=replace(r, value=replace(r.value, tick=2)))
                observer.capture(frame)
        review = Review(ARM, TID, observer)
        self.assertEqual(review.baseline(listener=True, wired=True), Baseline.UNKNOWN)

    def test_skip_record_requires_empty_payload(self):
        for genuine in (True, False):
            with self.subTest(genuine=genuine):
                d = Driver()
                d.arm()
                d.gx.dispatch(tag_preserved=not genuine, output_preserved=False)
                for i, r in enumerate(d.gx.trace.slots):
                    frame = d.gx.trace.snapshot(i)
                    if r.kind == "dispatch":
                        frame = replace(frame, record=replace(r, kind="skipped"))
                    d.observer.capture(frame)
                self.assertEqual(d.baseline(), Baseline.NEVER if genuine else Baseline.UNKNOWN)
