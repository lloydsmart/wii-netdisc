"""Immutable evidence exchanged across the one-shot fixture boundaries."""

from dataclasses import dataclass, fields
from enum import Enum
from types import MappingProxyType


DEFAULT_MODULUS = 256


class Evidence:
    """A closed set of immutable values can cross the publication boundary."""

    __slots__ = ()

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            frozen = immutable(value)
            if frozen is not value:
                object.__setattr__(self, field.name, frozen)


def immutable(value):
    if value is None or type(value) in (int, str, bytes, bool) or type(value) in EVIDENCE_TYPES:
        return value
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    if type(value) is tuple:
        return tuple(immutable(item) for item in value)
    raise TypeError("unsupported value in fixture evidence")


@dataclass(frozen=True, slots=True)
class Identity(Evidence):
    instance: str
    slot: int
    dip_build: str
    gx_build: str
    tag: bytes

    def __post_init__(self):
        Evidence.__post_init__(self)
        if type(self.tag) is not bytes or len(self.tag) != 8:
            raise ValueError("the run tag occupies eight bytes")


@dataclass(frozen=True, slots=True)
class Read(Evidence):
    tag: bytes
    output: str  # Exclusive allocation identity in the outer hook's namespace
    fd: int
    command: str
    length: int
    word_offset: int
    input_length: int = 32
    output_length: int = 32


@dataclass(frozen=True, slots=True)
class PeerSelection(Evidence):
    peer_run: str
    listener: str


@dataclass(frozen=True, slots=True)
class Arm(Evidence):
    identity: Identity
    challenge: bytes
    read: Read
    peer: PeerSelection

    def __post_init__(self):
        Evidence.__post_init__(self)
        if (type(self.challenge) is not bytes or len(self.challenge) != 16
                or not isinstance(self.identity, Identity) or not isinstance(self.read, Read)
                or self.identity.tag != self.read.tag):
            raise ValueError("arm requires one matching tag and a 16-byte challenge")
        if (not isinstance(self.peer, PeerSelection) or type(self.peer.peer_run) is not str
                or not self.peer.peer_run or type(self.peer.listener) is not str or not self.peer.listener):
            raise ValueError("select a listener and peer run before arming")
        if (self.read.command != "unencrypted read" or self.read.input_length != 32
                or type(self.read.fd) is not int or not 0 <= self.read.fd < 2**31
                or type(self.read.word_offset) is not int or not 0 <= self.read.word_offset < 2**32
                or type(self.read.length) is not int or not 0 < self.read.length < 2**32
                or type(self.read.output_length) is not int or self.read.output_length != self.read.length
                or type(self.read.output) is not str or not self.read.output):
            raise ValueError("invalid intended read")

    @property
    def request(self):
        return self.identity.tag + self.challenge


@dataclass(frozen=True, slots=True)
class Receipt(Evidence):
    identity: Identity
    read: Read


@dataclass(frozen=True, slots=True)
class Return(Evidence):
    identity: Identity
    disposition: str  # completed, rejected before entry, or duplicate
    raw: int
    intended: Read


@dataclass(frozen=True, slots=True)
class Endpoints(Evidence):
    client: str
    listener: str


@dataclass(frozen=True, slots=True)
class Echo(Evidence):
    endpoints: Endpoints
    reply: bytes
    connection_id: int
    elapsed: int


@dataclass(frozen=True, slots=True)
class Accept(Evidence):
    peer_run: str
    endpoints: Endpoints
    connection_id: int


@dataclass(frozen=True, slots=True)
class PeerFrame(Evidence):
    connection: Accept
    received: bytes
    sent: bytes


@dataclass(frozen=True, slots=True)
class Record(Evidence):
    identity: Identity
    writer: str
    sequence: int
    kind: str
    value: object
    tick: int | None = None  # Raw DI sample at phase boundaries and verdicts.


@dataclass(frozen=True, slots=True)
class Frame(Evidence):
    """Visible payload between two independently sampled commit words."""

    record: Record
    first_commit: int | None
    last_commit: int | None
    complete: bool = True


@dataclass(frozen=True, eq=False, slots=True)
class Call(Evidence):
    """The actual pinned PPC request address used by the final reply handler."""

    identity: Identity
    kind: str


@dataclass(frozen=True, slots=True)
class FinalReply(Evidence):
    call: Call
    raw: int
    payload: Receipt | Return
    di_sequence: int | None


class ReplyPath:
    """One synchronous IPC's return channel. DI deposits its result only on exit."""

    def __init__(self):
        self.returned = None

    def deliver(self, payload, di_sequence=None):
        if self.returned is not None:
            raise ValueError("IPC already returned")
        self.returned = (payload, di_sequence)
        return payload


@dataclass(frozen=True, slots=True)
class CaptureReceipt(Evidence):
    marker: Record
    terminal: Return


@dataclass(frozen=True, slots=True)
class Step(Evidence):
    action: str
    resource: str


def admitted_step(record):
    if record and record.kind == "submission":
        match record.value:
            case (Step() as step, status) if type(status) is int and status == 0:
                return step
    return None


@dataclass(frozen=True, slots=True)
class ServiceReport(Evidence):
    """Coherent service output, interpreted under the fixture's readiness assumption."""

    step: Step
    successful: bool


@dataclass(frozen=True, slots=True)
class OperationResult(Evidence):
    """DI's interpretation of one delivered word and its final coherent range."""

    step: Step
    result: int
    tick: int
    late: bool
    phase: str
    elapsed: int | None
    data: bytes | None


EVIDENCE_TYPES = (Identity, Read, Arm, Receipt, Return, Endpoints, Echo, Accept, PeerFrame,
                  Record, Frame, Call, FinalReply, PeerSelection, CaptureReceipt, Step, ServiceReport, OperationResult)


# Successful service checks abstract just the evidence of readiness. No IOS opcodes.
BRINGUP = (Step("open", "NCD"), Step("link", "NCD"), Step("close", "NCD"),
           Step("open", "SO"), Step("open", "KD"), Step("startup", "KD"),
           Step("close", "KD"), Step("ready", "SO"))
CONNECTION = (Step("acquire socket", "socket"), Step("connect", "socket"))
EXCHANGE = (Step("send", "socket"), Step("receive", "socket"))


class Publication:
    """Append-only logical slots. Visibility of each snapshot is driver-controlled."""

    def __init__(self, writer, identity):
        self.writer = writer
        self.identity = identity
        self.slots: list[Record] = []
        self.uncommitted = set()
        self.interrupt_next = False

    def emit(self, kind, value=None, *, tick=None):
        sequence = len(self.slots) + 1
        record = Record(self.identity, self.writer, sequence, kind, value, tick)
        self.slots.append(record)
        if self.interrupt_next:
            self.uncommitted.add(sequence)
            self.interrupt_next = False
        return record

    def snapshot(self, index, *, committed=True, complete=True, interrupted=False):
        record = self.slots[index]
        commit = record.sequence if committed and record.sequence not in self.uncommitted else None
        return Frame(record, commit, None if interrupted else commit, complete)


class Baseline(Enum):
    PASS = "pass"
    FAILURE = "attributable failure"
    NEVER = "probe never ran"
    UNKNOWN = "indeterminate"


class Observer:
    """Independent capture from visible frames and an observer-local clock."""

    def __init__(self, plan: Arm, *, modulus=DEFAULT_MODULUS, cutoff=55, progress_limit=35):
        self.plan = plan
        self.modulus = modulus
        self.recovery = Recovery(plan.identity.instance)
        self._issued_receipt = None
        self.identity = plan.identity
        self._streams = {"DI": {}, "GX": {}}
        self.records = MappingProxyType({writer: MappingProxyType(stream)
                                         for writer, stream in self._streams.items()})
        self.conflicts = set()
        self.clock = 0
        self.last_progress = 0
        self.cutoff = cutoff
        self.progress_limit = progress_limit
        self.reader_frozen = False
        self.display_frozen = False
        self.watchdog_due = False

    def capture(self, frame):
        r = frame.record
        if (self.reader_frozen or self.display_frozen
                or r.identity != self.identity or r.writer not in self.records
                or frame.complete is not True or type(r.sequence) is not int or r.sequence < 1
                or (frame.first_commit, frame.last_commit) != (r.sequence, r.sequence)):
            return False
        stream = self._streams[r.writer]
        if r.sequence in stream:
            if r != stream[r.sequence]:
                self.conflicts.add((r.writer, r.sequence))
            return False
        if r.sequence > max(stream, default=0):
            self.last_progress = self.clock
        stream[r.sequence] = r
        return True

    def advance(self, now):
        if now < self.clock:
            raise ValueError("observer clock moved backwards")
        self.clock = now
        overdue = now >= self.cutoff or now - self.last_progress >= self.progress_limit
        if overdue and not self.termination_confirmed:
            self.watchdog_due = True

    def record(self, writer, kind):
        matches = [r for r in self.records[writer].values() if r.kind == kind]
        return matches[0] if len(matches) == 1 else None

    def through(self, record):
        return record is not None and all(i in self.records[record.writer]
                                          for i in range(1, record.sequence + 1))

    def ends_at(self, record):
        return self.through(record) and max(self.records[record.writer]) == record.sequence

    def di_between(self, start, end):
        stream = self.records["DI"]
        return (stream[i] for i in sorted(stream) if start.sequence < i < end.sequence)

    def saw(self, writer, *kinds):
        return any(r.kind in kinds for r in self.records[writer].values())

    def phase_start(self, name):
        matches = [r for r in self.records["DI"].values()
                   if r.kind == "phase" and type(r.value) is tuple and len(r.value) == 2
                   and r.value[0] == name and type(r.value[1]) is int and r.value[1] > 0]
        return matches[0] if len(matches) == 1 else None

    def clock_agrees(self, start, tick, elapsed):
        return (type(start.tick) is int and 0 <= start.tick < self.modulus
                and type(elapsed) is int and type(tick) is int
                and tick == (start.tick + elapsed) % self.modulus)

    def timely_result(self, op, start, phase, earliest, latest):
        return (isinstance(op, OperationResult) and op.phase == phase and op.late is False
                and type(op.result) is int and type(op.elapsed) is int and earliest <= op.elapsed <= latest
                and self.clock_agrees(start, op.tick, op.elapsed))

    def operations(self, start, end, phase, latest):
        """Corroborate successful admissions, timed results and required service outputs."""
        if not start or not end or start.sequence >= end.sequence:
            return None
        if ("DI", start.sequence) in self.conflicts or ("DI", end.sequence) in self.conflicts:
            return None
        outcomes = []
        intended = pending = service_due = None
        elapsed = 0
        for r in self.di_between(start, end):
            if ("DI", r.sequence) in self.conflicts:
                return None
            if service_due is not None:
                if (r.kind != "service" or not isinstance(r.value, ServiceReport)
                        or r.value.step != service_due or r.value.successful is not True):
                    return None
                service_due = None
            elif r.kind == "intent":
                match r.value:
                    case (Step() as step, int(), int(at)) if elapsed <= at <= latest:
                        if intended or pending:
                            return None
                        intended, elapsed = step, at
                    case _:
                        return None
            elif r.kind == "submission":
                step = admitted_step(r)
                if step is None or pending is not None or intended not in (None, step):
                    return None
                pending, intended = step, None
            elif r.kind == "completion":
                op = r.value
                if (not self.timely_result(op, start, phase, elapsed, latest)
                        or op.step != pending or pending is None or op.result < 0):
                    return None
                if pending.action == "close" and op.result != 0:
                    return None
                if pending.action in ("link", "startup", "ready"):
                    service_due = pending
                outcomes.append(op)
                pending, elapsed = None, op.elapsed
            else:
                return None
        # Connection enters exchange at its last completion. Other endpoints
        # (ready, verified, invalid reply) carry their own observed elapsed time.
        end_elapsed = elapsed if end.kind == "phase" else latest
        if intended or pending or service_due or not self.clock_agrees(start, end.tick, end_elapsed):
            return None
        return outcomes

    def handled(self, kind):
        """Join dispatch, final interrupt handling and wrapper for one actual PPC request."""
        start = self.record("GX", "arm call" if kind == "arm" else "dispatch")
        final = self.record("GX", kind + " final")
        wrapper = self.record("GX", kind + " wrapper")
        if not (start and final and wrapper and start.sequence < final.sequence < wrapper.sequence):
            return None
        f = final.value
        if not (isinstance(f, FinalReply) and isinstance(f.call, Call)
                and f.call.kind == kind and f.call.identity == self.identity
                and type(start.value) is tuple and len(start.value) == 2
                and start.value[0] is f.call and isinstance(start.value[1], Read)):
            return None
        intended = start.value[1]
        if kind == "arm":
            valid = f.raw == 1 and f.di_sequence is None and f.payload == Receipt(self.identity, intended)
        else:
            valid = (isinstance(f.payload, Return) and f.payload.identity == self.identity
                     and f.payload.intended == intended and f.payload.raw == f.raw)
        status = 0 if f.raw == 1 else f.raw
        if valid and wrapper.value == (f.call, status, f.payload):
            return f
        return None

    def read_chain(self):
        arm = self.handled("arm")
        read = self.handled("read")
        handback = self.record("GX", "arm handback")
        dispatch = self.record("GX", "dispatch")
        if (not self.saw("GX", "skipped") and arm and read and handback and handback.value is True
                and arm.payload.read == read.payload.intended
                and self.record("GX", "arm wrapper").sequence < handback.sequence < dispatch.sequence):
            return read
        return None

    def terminal_chain(self):
        final = self.read_chain()
        terminal = self.record("DI", "return")
        handback = self.record("GX", "read handback")
        marker = self.record("GX", "pre-cleanup")
        failure = self.record("DI", "first failure")
        if (not self.saw("GX", "rejected before entry") and final and terminal
                and handback and self.through(marker)
                and final.payload.intended == self.plan.read and final.payload.disposition == "completed"
                and final.raw == (-1 if failure else 1)
                and final.di_sequence == terminal.sequence and final.payload == terminal.value
                and self.record("GX", "read wrapper").sequence < handback.sequence < marker.sequence
                and final == handback.value == marker.value):
            return terminal
        return None

    def _eligible_receipt(self):
        terminal = self.terminal_chain()
        cleanup = self.record("DI", "cleanup")
        retired = self.record("DI", "queue retired")
        if (self.conflicts or not self.ends_at(terminal) or not cleanup or not retired
                or retired.value is not True or cleanup.value is not True
                or not retired.sequence < cleanup.sequence < terminal.sequence):
            return None
        records = (self.records["DI"][i] for i in range(1, terminal.sequence))
        if ownership_consistent(records, require_retirement=True):
            return CaptureReceipt(self.record("GX", "pre-cleanup"), terminal.value)
        return None

    def release_receipt(self):
        eligible = self._eligible_receipt()
        if eligible is None:
            return None
        if self._issued_receipt is None:
            self._issued_receipt = eligible
        if self._issued_receipt == eligible:
            return self._issued_receipt
        return None

    def authorizes(self, receipt):
        return (receipt is not None and receipt is self._issued_receipt
                and receipt == self._eligible_receipt())

    @property
    def termination_confirmed(self):
        if self.recovery.end_confirmed:
            return True
        release = self.record("GX", "released")
        return bool(self.through(release) and self.authorizes(release.value)
                    and release.value.marker.sequence + 1 == release.sequence)


def ownership_consistent(records, *, require_retirement):
    """Replay a DI prefix ending between operations, or the whole retired ledger."""
    live = {}
    acquired = set()
    attempted_closes = set()
    pending = None
    admitted = False
    retired = False
    for r in records:
        if r.kind == "cleanup failure" and r.value in ("operation error", "admission uncertain",
                                                      "queue retirement uncertain", "unexpected queue word"):
            return False
        if r.kind == "queue retired":
            if pending or live or retired:
                return False
            retired = True
        if r.kind not in ("intent", "ingress full", "submission", "completion"):
            continue
        if retired or (r.kind != "completion" and type(r.value) is not tuple):
            return False
        if r.kind == "intent":
            if pending or len(r.value) != 3:
                return False
            step, serial, _ = r.value
            if not isinstance(step, Step) or type(serial) is not int:
                return False
            if step.action in ("open", "acquire socket"):
                if serial in acquired or (step.resource == "socket" and
                                          not any(name == "SO" for name, _ in live.values())):
                    return False
                acquired.add(serial)
            elif serial not in live or live[serial][0] != step.resource:
                return False
            if step.action == "close":
                if serial in attempted_closes or (step.resource == "SO" and
                                                  any(name == "socket" for name, _ in live.values())):
                    return False
                attempted_closes.add(serial)
            pending = step, serial
            admitted = False
            continue
        if pending is None:
            return False
        step, serial = pending
        if r.kind == "ingress full":
            if admitted or r.value != pending:
                return False
            pending = None
        elif r.kind == "submission":
            if admitted or admitted_step(r) != step:
                return False
            admitted = True
        else:
            outcome = r.value
            if (not admitted or not isinstance(outcome, OperationResult)
                    or outcome.step != step or type(outcome.result) is not int or outcome.data is None):
                return False
            result = outcome.result
            if step.action in ("open", "acquire socket") and result >= 0:
                if any(number == result and (name == "socket") == (step.resource == "socket")
                       for name, number in live.values()):
                    return False
                live[serial] = step.resource, result
            if step.action == "close" and result == 0:
                del live[serial]
            pending = None
    return pending is None and (retired if require_retirement else not retired)


@dataclass
class Recovery:
    """External decision and independent termination evidence for the named instance."""

    instance: str
    requested: bool = False
    end_confirmed: bool = False

    def initiate(self):
        self.requested = True

    def confirm_end(self, instance, *, ios_ended, io_ended):
        if instance == self.instance and ios_ended and io_ended:
            self.end_confirmed = True


@dataclass(frozen=True, slots=True)
class Review:
    """Score captured evidence against the run plan and independent controls."""

    arm: Arm
    intended_tid: int
    capture: Observer

    def __post_init__(self):
        if self.capture.plan != self.arm:
            raise ValueError("evidence belongs to another run")

    def transfer_history(self, end, elapsed):
        start = self.capture.phase_start("exchange")
        if not start or start.value != ("exchange", 5) or not 0 <= elapsed < 5:
            return None
        outcomes = self.capture.operations(start, end, "exchange", elapsed)
        if outcomes is None:
            return None
        sent, received = bytearray(), bytearray()
        for op in outcomes:
            if type(op.data) is not bytes or op.result <= 0 or op.result != len(op.data):
                return None
            if op.step == EXCHANGE[0] and not received and len(sent) + op.result <= 24:
                sent.extend(op.data)
            elif op.step == EXCHANGE[1] and len(sent) == 24 and len(received) + op.result <= 28:
                received.extend(op.data)
            else:
                return None
        if bytes(sent) == self.arm.request and len(received) == 28:
            return bytes(received)
        return None

    def ready_to_exchange(self, entry, ready):
        connection = self.capture.phase_start("connection")
        exchange = self.capture.phase_start("exchange")
        if (not ready or type(ready.value) is not int or not 0 <= ready.value < 30
                or not connection or connection.sequence != ready.sequence + 1
                or connection.tick != ready.tick or not exchange):
            return False
        setup = self.capture.operations(entry, ready, "bring-up", ready.value)
        connect = self.capture.operations(connection, exchange, "connection", connection.value[1] - 1)
        return (setup is not None and tuple(op.step for op in setup) == BRINGUP
                and setup[-1].elapsed == ready.value
                and connect is not None and tuple(op.step for op in connect) == CONNECTION
                and ownership_consistent(self.capture.di_between(entry, exchange), require_retirement=False))

    def exchange_verified(self, accepted, peer_frame):
        verified = self.capture.record("DI", "verified")
        if not verified or not accepted or not peer_frame:
            return False
        failure = self.capture.record("DI", "first failure")
        if (failure and failure.sequence < verified.sequence
                or (verified.writer, verified.sequence) in self.capture.conflicts):
            return False
        echo = verified.value
        if not (isinstance(echo, Echo) and isinstance(accepted, Accept)
                and isinstance(peer_frame, PeerFrame)
                and isinstance(echo.endpoints, Endpoints) and type(echo.reply) is bytes
                and type(echo.connection_id) is int and type(accepted.connection_id) is int
                and len(echo.reply) == 28 and type(echo.elapsed) is int and 0 <= echo.elapsed < 5):
            return False
        wire_id = int.from_bytes(echo.reply[24:], "big")
        return (accepted.peer_run == self.arm.peer.peer_run
                and echo.endpoints.listener == self.arm.peer.listener
                and peer_frame.connection == accepted and accepted.endpoints == echo.endpoints
                and wire_id != 0 and wire_id == echo.connection_id == accepted.connection_id
                and echo.reply[:24] == self.arm.request and peer_frame.received == self.arm.request
                and peer_frame.sent == echo.reply
                and self.transfer_history(verified, echo.elapsed) == echo.reply)

    def demonstrated_failure(self, failure):
        first = self.capture.record("DI", "first failure")
        if (not self.capture.through(failure) or not first or first.value != failure.value
                or first.sequence + 1 != failure.sequence or first.sequence <= 1):
            return False
        stream = self.capture.records["DI"]
        entry = self.capture.record("DI", "entry")
        if not entry or entry.sequence >= first.sequence:
            return False
        # Establish the phase independently of the failure label. Cleanup can
        # close the same resources as bring-up after abandoning a partial setup.
        phase, budget, start = "bring-up", 30, entry
        for seq in range(entry.sequence + 1, first.sequence):
            r = stream[seq]
            if r.kind == "phase":
                start = r
                match (phase, r.value):
                    case ("bring-up", ("connection", int(limit))) if limit > 0:
                        phase, budget = "connection", limit
                    case ("connection", ("exchange", 5)):
                        phase, budget = "exchange", 5
                    case _:
                        return False
        match failure.value:
            case (reported, str(reason), int(elapsed), limit) if reported == phase and limit == budget:
                pass
            case _:
                return False
        if not self.capture.clock_agrees(start, first.tick, elapsed):
            return False
        previous_elapsed = 0
        for r in self.capture.di_between(start, first):
            if r.kind == "completion":
                if not self.capture.timely_result(r.value, start, phase, previous_elapsed, min(elapsed, budget - 1)):
                    return False
                previous_elapsed = r.value.elapsed
        if reason == "deadline":
            return elapsed >= budget
        if not 0 <= elapsed < budget:
            return False
        cause = stream[first.sequence - 1]
        steps = {"bring-up": BRINGUP, "connection": CONNECTION, "exchange": EXCHANGE}[phase]
        if reason == "bad reply":
            reply = cause.value
            return (phase == "exchange" and cause.kind == "invalid reply" and type(reply) is bytes
                    and self.transfer_history(cause, elapsed) == reply
                    and (reply[:24] != self.arm.request or reply[24:] == bytes(4)))
        if reason == "submission rejected":
            intent = stream.get(cause.sequence - 1)
            return (cause.kind == "ingress full" and intent and intent.kind == "intent"
                    and type(intent.value) is tuple and len(intent.value) == 3
                    and intent.value[0] in steps and intent.value[:2] == cause.value)
        completed = stream.get(cause.sequence - 1) if reason == "service error" else cause
        if not completed or completed.kind != "completion" or not isinstance(completed.value, OperationResult):
            return False
        op = completed.value
        intent = stream.get(completed.sequence - 2)
        if (op.step not in steps or op.step != admitted_step(stream.get(completed.sequence - 1))
                or not intent or intent.kind != "intent" or type(intent.value) is not tuple
                or len(intent.value) != 3 or intent.value[0] != op.step or type(intent.value[2]) is not int
                or not 0 <= intent.value[2] <= op.elapsed):
            return False
        if reason == "service error":
            report = cause.value
            return (cause.kind == "service" and isinstance(report, ServiceReport)
                    and report.successful is False and report.step == op.step
                    and op.step.action in ("link", "startup", "ready") and op.result >= 0)
        if reason == "operation error":
            return op.result < 0 or (op.step.action == "close" and op.result != 0)
        if phase == "exchange" and reason == "invalid " + op.step.action + " count":
            remaining = 24 if op.step.action == "send" else 28
            for seq in range(entry.sequence + 1, cause.sequence):
                prior = stream[seq]
                if prior.kind == "completion":
                    if not isinstance(prior.value, OperationResult):
                        return False
                    if prior.value.step == op.step:
                        remaining -= prior.value.result
            return not 0 < op.result <= remaining
        return False

    def baseline(self, accepted=None, peer_frame=None, *, listener=None, wired=None):
        entry = self.capture.record("DI", "entry")
        skipped = self.capture.record("GX", "skipped")
        if self.capture.conflicts:
            return Baseline.UNKNOWN
        # This fixture publishes DI records only inside a claimed network read.
        executed = bool(self.capture.records["DI"])
        if self.capture.saw("GX", "skipped"):
            read_activity = self.capture.saw("GX", "dispatch", "read final", "read wrapper",
                                             "read handback", "pre-cleanup", "released", "rejected before entry")
            if (self.capture.ends_at(skipped) and skipped.value is None and skipped.tick is None
                    and not executed and not read_activity):
                return Baseline.NEVER
            return Baseline.UNKNOWN
        if executed and self.capture.saw("GX", "rejected before entry"):
            return Baseline.UNKNOWN
        final = self.capture.read_chain()
        if not final or final.payload.intended != self.arm.read:
            return Baseline.UNKNOWN
        rejected = self.capture.record("GX", "rejected before entry")
        wrapper = self.capture.record("GX", "read wrapper")
        if (not executed and self.capture.through(rejected) and wrapper.sequence < rejected.sequence
                and rejected.value == final and final.di_sequence is None and final.raw == -1
                and final.payload.disposition == "rejected before entry"):
            return Baseline.NEVER

        marker = self.capture.record("GX", "pre-cleanup")
        if not (entry and entry.value == self.intended_tid and marker and marker.value == final
                and wrapper.sequence < marker.sequence and final.payload.disposition == "completed"
                and type(final.di_sequence) is int and entry.sequence < final.di_sequence):
            return Baseline.UNKNOWN
        if listener is False or wired is False:
            return Baseline.UNKNOWN
        terminal = self.capture.terminal_chain()
        ready = self.capture.record("DI", "ready")
        verified = self.capture.record("DI", "verified")
        if (self.capture.through(terminal) and self.ready_to_exchange(entry, ready)
                and verified and entry.sequence < ready.sequence < verified.sequence < terminal.sequence
                and self.exchange_verified(accepted, peer_frame)):
            return Baseline.PASS
        failure = self.capture.record("DI", "network failure")
        if (self.demonstrated_failure(failure) and entry.sequence < failure.sequence < final.di_sequence
                and final.raw == -1 and listener and wired):
            return Baseline.FAILURE
        return Baseline.UNKNOWN

    @property
    def safe_termination(self):
        return self.capture.termination_confirmed
