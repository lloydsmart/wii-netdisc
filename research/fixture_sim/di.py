"""One outer-hook claim, persistent loan bundle and serial network submitter."""

from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from .evidence import (
    BRINGUP, CONNECTION, DEFAULT_MODULUS, EXCHANGE, Arm, Echo, Endpoints, Identity, OperationResult,
    Publication, Read, Receipt, Return, ServiceReport, Step,
)


class Phase(Enum):
    BRINGUP = "bring-up"
    CONNECT = "connection"
    EXCHANGE = "exchange"
    CLEANUP = "cleanup"


@dataclass(frozen=True, eq=False)
class Sample:
    """Raw counter in model seconds and evidence of a sub-half-range sampling gap."""

    tick: int
    previous: object | None = None  # Anchor for the independently bounded interval.
    anchor: object = field(default_factory=object, init=False)

    def __post_init__(self):
        if type(self.tick) is not int:
            raise ValueError("raw counter must be an integer")


class Ownership(Enum):
    UNRESOLVED = "unresolved"
    KNOWN = "known"
    RELEASED = "confirmed release"


@dataclass
class Acquisition:
    resource: str
    serial: int
    parent: int | None = None
    number: int | None = None
    ownership: Ownership = Ownership.UNRESOLVED
    close_attempted: bool = False
    close_history: list = field(default_factory=list)


@dataclass
class Storage:
    """The whole queue, timer, reply, paths, vectors, controls and scratch share one lifetime."""

    mailbox: "Mailbox"
    reply_pointer: object = field(default_factory=object)
    scratch: bytearray = field(default_factory=lambda: bytearray(28))
    service: ServiceReport | None = None
    endpoints: Endpoints | None = None
    retired: bool = False


@dataclass(eq=False)
class ReceiveRange:
    """Accept a coherent range only inside the post-completion handoff."""

    visible: bytes | None = None

    _acquiring: bool = False

    def publish(self, data):
        if self._acquiring:
            self.visible = bytes(data)

    def acquire(self, request, synchronize):
        self.visible = None
        if synchronize is not None:
            self._acquiring = True
            try:
                synchronize(request)
            finally:
                self._acquiring = False
        return self.visible


@dataclass
class Request:
    step: Step
    phase: Phase
    acquisition: Acquisition
    storage: Storage
    send_bytes: bytes
    receive: ReceiveRange | None = None
    stage: str = "submitting"


@dataclass(frozen=True)
class Completion:
    pointer: object
    result: int
    command: str = "reply"


@dataclass(frozen=True)
class Retirement:
    """Delivered teardown evidence for this queue and all of its producers."""

    mailbox: "Mailbox"
    producers_quiesced: bool


class Mailbox:
    """Driver-side delivery. A dropped word creates no notification for the reader."""

    def __init__(self, capacity=5):
        self.words = deque(maxlen=capacity)

    def offer(self, word):
        if len(self.words) == self.words.maxlen:
            return False
        self.words.append(word)
        return True


class DI:
    def __init__(self, identity: Identity, *, modulus=DEFAULT_MODULUS, connection=5, cleanup=5,
                 exclusive_one_reply=True, queue_capacity=5, operation_records=64):
        self.budgets = {Phase.BRINGUP: 30, Phase.CONNECT: connection,
                        Phase.EXCHANGE: 5, Phase.CLEANUP: cleanup}
        if modulus % 2 or not all(0 < n < modulus // 2 for n in self.budgets.values()):
            raise ValueError("each budget must fit below half the counter range")
        self.modulus = modulus
        self.exclusive_one_reply = exclusive_one_reply
        self.operation_records = operation_records
        self.identity = identity
        self.trace = Publication("DI", identity)
        self.arm: Arm | None = None
        self.spent = False
        self.phase: Phase | None = None
        self.elapsed = 0
        self.last_sample = None
        self.armed_timers = set()
        self.return_path = None
        self.plan = deque()
        self.storage = Storage(Mailbox(queue_capacity))
        self.pending: Request | None = None
        self.ledger: list[Acquisition] = []
        self.submissions = 0
        self.first_failure = None
        self.cleanup_failures = []
        self.cleanup_stopped = False
        self.sent = 0
        self.endpoints = None
        self.received = bytearray()
        self.verified: Echo | None = None
        self.returned: Return | None = None
        self.late = []
        self.queue_untrusted = False

    def accept_arm(self, arm, path):
        if self.arm or arm.identity != self.identity:
            return None
        self.arm = arm
        return path.deliver(Receipt(self.identity, arm.read))

    def outer_read(self, identity, read: Read, tid, clock, path):
        if not self.arm or (read.tag != self.identity.tag and read.output != self.arm.read.output):
            return "ordinary"
        if self.spent:
            return path.deliver(Return(self.identity, "duplicate", -1, self.arm.read))
        self.spent = True
        if identity != self.identity or read != self.arm.read:
            return path.deliver(Return(self.identity, "rejected before entry", -1, self.arm.read))
        self.return_path = path
        self.trace.emit("entry", tid, tick=clock.tick)
        self._phase(Phase.BRINGUP, BRINGUP)
        self._time(clock)
        return "claimed"

    def _armed_timer(self, word):
        return isinstance(word, Phase) and word in self.armed_timers

    def _matching_reply(self, word):
        return (isinstance(word, Completion) and word.pointer is self.storage.reply_pointer
                and word.command == "reply")

    def _queue_consistent(self):
        """Inspect the bounded queue under its current producer bindings."""
        reply_possible = self.pending is not None and self.pending.stage in ("pending", "submitting")
        for word in self.storage.mailbox.words:
            if self._armed_timer(word):
                continue
            if reply_possible and self._matching_reply(word):
                reply_possible = False
            else:
                return False
        return True

    def _unexpected_word(self):
        self.queue_untrusted = True
        if self.pending and self.pending.stage in ("pending", "submitting"):
            self.pending.stage = "quarantined"
        self._abandon("unexpected queue word")
        self.cleanup_stopped = True

    def _phase(self, phase, plan=()):
        # Inspection and changing the binding are one deterministic event.
        if not self.queue_untrusted and not self._queue_consistent():
            if self.phase is None:
                self.phase = phase  # The initial claim supplies the failure's phase.
            self._unexpected_word()
            return
        self.phase = phase
        self.elapsed = 0
        self.plan = deque(plan)
        if phase != Phase.BRINGUP:
            self.trace.emit("phase", (phase.value, self.budgets[phase]),
                            tick=self.last_sample.tick if self.last_sample else None)
        if not self.queue_untrusted:
            self.armed_timers.add(phase)

    def _abandon(self, reason, *, network=False):
        issue = (self.phase, reason)
        evidence = (self.phase.value, reason, self.elapsed, self.budgets[self.phase])
        if self.first_failure is None:
            self.first_failure = issue
            self.trace.emit("first failure", evidence, tick=self.last_sample.tick if self.last_sample else None)
        if self.phase == Phase.CLEANUP:
            if reason not in self.cleanup_failures:
                self.cleanup_failures.append(reason)
                self.trace.emit("cleanup failure", reason)
            self.cleanup_stopped = True
        else:
            if network:
                self.trace.emit("network failure", evidence)
            self._phase(Phase.CLEANUP)

    def _time(self, clock, *, check_deadline=True):
        previous = self.last_sample
        valid = type(clock.tick) is int and 0 <= clock.tick < self.modulus
        delta = 0
        if valid and previous is not None:
            delta = (clock.tick - previous.tick) % self.modulus
            valid = clock.previous is previous.anchor and delta < self.modulus // 2
        if not valid:
            self._abandon("unbounded clock")
            self.cleanup_stopped = True
            return False
        self.last_sample = clock
        self.elapsed += delta
        if check_deadline and self.elapsed >= self.budgets[self.phase]:
            self._abandon("deadline", network=True)
            return False
        return True

    def _next_step(self):
        if self.phase != Phase.CLEANUP:
            return self.plan[0] if self.plan else None
        if self.cleanup_stopped or any(a.ownership == Ownership.UNRESOLVED for a in self.ledger):
            return None
        owned = next((a for a in reversed(self.ledger) if a.ownership == Ownership.KNOWN), None)
        if owned and not owned.close_attempted:
            return Step("close", owned.resource)
        return None

    def submit(self, clock, *, ingress=None):
        if ingress is not None and (type(ingress) is not Mailbox or ingress is self.storage.mailbox):
            raise ValueError("admission evidence requires the separate bounded ingress")
        if self.phase is None or self.pending or self.returned or not self._time(clock):
            return None
        if self.queue_untrusted:
            return None
        if not self._queue_consistent():
            self._unexpected_word()
            return None
        step = self._next_step()
        if not step:
            return None
        if self.submissions >= self.operation_records:
            self._abandon("operation trace full")
            self.cleanup_stopped = True
            return None
        if self.submissions and not self.exclusive_one_reply:
            self._abandon("reply pointer unsafe to reuse")
            self.cleanup_stopped = True
            return None
        if step.action in ("open", "acquire socket"):
            parent = self._owned("SO").serial if step.resource == "socket" else None
            acquisition = Acquisition(step.resource, len(self.ledger) + 1, parent)
            self.ledger.append(acquisition)
        else:
            acquisition = self._owned(step.resource)
        if step.action == "close":
            acquisition.close_attempted = True
            acquisition.close_history.append("submitting")
            acquisition.ownership = Ownership.UNRESOLVED
        data = self.arm.request[self.sent:] if step.action == "send" else b""
        self.storage.service = None
        self.pending = Request(step, self.phase, acquisition, self.storage, data)
        if step.action == "receive":
            self.pending.receive = ReceiveRange()
        self.submissions += 1
        self.trace.emit("intent", (step, acquisition.serial, self.elapsed))
        # Optional PC adapter: a full bounded ingress rejects before forwarding.
        # This synchronous outcome is distinct from an unclassified trap return.
        if ingress is not None and not ingress.offer(self.pending):
            self.trace.emit("ingress full", (step, acquisition.serial))
            if step.action in ("open", "acquire socket"):
                self.ledger.remove(acquisition)
            elif step.action == "close":
                acquisition.ownership = Ownership.KNOWN
                acquisition.close_history.append("not forwarded")
            self.pending = None
            self._abandon("submission rejected", network=True)
        return self.pending

    def _owned(self, resource):
        return next(a for a in self.ledger
                    if a.resource == resource and a.ownership == Ownership.KNOWN)

    def submission_return(self, status, clock):
        r = self.pending
        if not r or r.stage != "submitting":
            return
        self.trace.emit("submission", (r.step, status))
        self._time(clock)
        if self.queue_untrusted:
            return
        if status == 0:
            r.stage = "pending"
            return
        r.stage = "uncertain"
        if r.step.action == "close":
            r.acquisition.close_history.append(("submission", status))
        if r.phase == self.phase:
            self._abandon("admission uncertain")

    def dequeue(self, clock, *, synchronize=None):
        mailbox = self.storage.mailbox
        if (not mailbox.words or self.phase is None or self.returned or self.queue_untrusted
                or (self.pending and self.pending.stage != "pending")):
            return False
        if not self._queue_consistent():
            self._unexpected_word()
            return False
        word = mailbox.words.popleft()
        if self._armed_timer(word):
            self._time(clock, check_deadline=word == self.phase)
        else:
            self._complete(word.result, clock, synchronize)
        return True

    def _complete(self, result, clock, synchronize):
        r = self.pending
        step, acq = r.step, r.acquisition
        r.stage = "reply delivered"
        timely = self._time(clock)
        late = not timely or r.phase != self.phase
        data = b""
        if step.action == "send" and 0 < result <= len(r.send_bytes):
            data = r.send_bytes[:result]
        if r.receive and 0 < result <= 28 - len(self.received):
            data = r.receive.acquire(r, synchronize)
            if data is not None and len(data) != result:
                data = None
        self.trace.emit("completion", OperationResult(step, result, clock.tick, late, r.phase.value,
                                                     None if late else self.elapsed, data))
        if data is None:
            r.stage = "quarantined"
            self._abandon("receive visibility unresolved")
            return
        self.pending = None
        if step.action in ("open", "acquire socket"):
            if result >= 0:
                acq.number = result
                conflicts = [other for other in self.ledger if other is not acq
                             and other.ownership != Ownership.RELEASED and other.number == result
                             and (other.resource == "socket") == (acq.resource == "socket")]
                if conflicts:
                    for other in conflicts:
                        other.ownership = Ownership.UNRESOLVED
                    self._abandon("conflicting live handle")
                    self.cleanup_stopped = True
                    return
                acq.ownership = Ownership.KNOWN
            else:
                acq.ownership = Ownership.RELEASED
        if step.action == "close":
            acq.close_history.append(("completion", result))
            if result == 0:
                acq.ownership = Ownership.RELEASED
        if late:
            self.late.append((step, result, data))
        if result < 0 or (step.action == "close" and result != 0):
            if r.phase == self.phase:
                self._abandon("operation error", network=True)
            return
        if late or self.phase == Phase.CLEANUP:
            return
        if step.action in ("link", "startup", "ready"):
            service = self.storage.service
            if service is None or service.step != step:
                self._abandon("missing service evidence")
                return
            self.trace.emit("service", service)
            if not service.successful:
                self._abandon("service error", network=True)
                return
        if step.action == "connect":
            self.endpoints = self.storage.endpoints
            if self.endpoints is None:
                self._abandon("missing connection endpoints")
                return
        if step.action == "send":
            if not 0 < result <= len(r.send_bytes):
                self._abandon("invalid send count", network=True)
                return
            self.sent += result
            if self.sent < len(self.arm.request):
                return
        if step.action == "receive":
            if not 0 < result <= 28 - len(self.received):
                self._abandon("invalid receive count", network=True)
                return
            self.received.extend(data)
            if len(self.received) < 28:
                return
        self.plan.popleft()
        if self.plan:
            return
        if self.phase == Phase.BRINGUP:
            self.trace.emit("ready", self.elapsed, tick=clock.tick)
            self._phase(Phase.CONNECT, CONNECTION)
        elif self.phase == Phase.CONNECT:
            self._phase(Phase.EXCHANGE, EXCHANGE)

    def verify(self, clock):
        if self.phase != Phase.EXCHANGE or len(self.received) != 28:
            return
        reply = bytes(self.received)
        connection_id = int.from_bytes(reply[24:], "big")
        valid = reply[:24] == self.arm.request and connection_id != 0
        if not self._time(clock):
            return
        if not valid:
            self.trace.emit("invalid reply", reply, tick=clock.tick)
            self._abandon("bad reply", network=True)
            return
        self.verified = Echo(self.endpoints, reply, connection_id, self.elapsed)
        self.trace.emit("verified", self.verified, tick=clock.tick)
        self._phase(Phase.CLEANUP)

    def finish(self, clock, retirement):
        """Freeze publication and sever GX's output loan before synchronous return."""
        if self.phase != Phase.CLEANUP or self.pending or self.returned:
            return None
        self._time(clock)
        if self._next_step() is not None:
            return None
        mailbox = self.storage.mailbox
        quiesced = retirement == Retirement(mailbox, True)
        if quiesced:
            # The event already sampled time. Only known timer words may remain.
            for _ in range(len(mailbox.words)):
                if self.queue_untrusted:
                    break
                if not self._armed_timer(mailbox.words.popleft()):
                    self._unexpected_word()
        else:
            self._abandon("queue retirement uncertain")
        clean = (quiesced and not self.queue_untrusted
                 and all(a.ownership == Ownership.RELEASED for a in self.ledger))
        self.trace.emit("queue retired", quiesced and not self.queue_untrusted)
        self.storage.retired = clean
        self.trace.emit("cleanup", clean)
        self.returned = Return(self.identity, "completed", 1 if self.first_failure is None else -1,
                               self.arm.read)
        terminal = self.trace.emit("return", self.returned)
        return self.return_path.deliver(self.returned, terminal.sequence)
