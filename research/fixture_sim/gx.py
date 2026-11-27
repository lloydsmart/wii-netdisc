"""GX owns the local PPC calls, reserved output and actual helper marker."""

from .evidence import Arm, Call, CaptureReceipt, FinalReply, Publication, Receipt, ReplyPath, Return


class GX:
    def __init__(self, arm: Arm, authorize_release):
        self._authorize_release = authorize_release
        self.arm = arm
        self.trace = Publication("GX", arm.identity)
        self.current: Call | None = None
        self.path: ReplyPath | None = None
        self.completion: FinalReply | None = None
        self.arm_started = False
        self.armed = False
        self.dispatched = False
        self.stopped = False
        self.ambiguous = False
        self.result: FinalReply | None = None
        self.marker = False
        self.reserved = True
        self.loans = frozenset()

    def _call(self, kind):
        self.current = Call(self.arm.identity, kind)
        self.path = ReplyPath()
        self.completion = None
        self.loans = frozenset(("internal IPC request", "wait queue", "input", "output"))
        event = "arm call" if kind == "arm" else "dispatch"
        self.trace.emit(event, (self.current, self.arm.read))
        return self.current

    def begin_arm(self):
        if self.arm_started or self.stopped:
            return None
        self.arm_started = True
        return self._call("arm")

    def ipc_completed(self, call, raw):
        """Final reply handling, with the interrupt's request address and raw result."""
        if self.current is None or call is not self.current or self.ambiguous:
            return
        if self.path.returned is None:
            self.ambiguous = self.stopped = True
            return
        payload, sequence = self.path.returned
        expected = 1 if isinstance(payload, Receipt) else payload.raw
        if raw != expected:
            self.ambiguous = self.stopped = True
            return
        if self.completion is None:
            self.completion = FinalReply(call, raw, payload, sequence)
            self.trace.emit(call.kind + " final", self.completion)

    def wrapper_returned(self, call, status, payload):
        if self.current is None or call is not self.current or self.ambiguous:
            return
        self.trace.emit(call.kind + " wrapper", (call, status, payload))
        final = self.completion
        if final is None:
            self.ambiguous = self.stopped = True
            return
        self.current = None
        self.loans = frozenset()
        matched = (payload == final.payload and status == (0 if final.raw == 1 else final.raw))
        if call.kind == "arm":
            self.armed = matched and payload == Receipt(self.arm.identity, self.arm.read)
            self.trace.emit("arm handback", self.armed)
        elif (matched and isinstance(payload, Return) and payload.identity == self.arm.identity
              and payload.intended == self.arm.read
              and ((payload.disposition == "completed" and final.di_sequence is not None)
                   or (payload.disposition == "rejected before entry" and payload.raw == -1
                       and final.di_sequence is None))):
            self.result = final
            kind = "read handback" if payload.disposition == "completed" else payload.disposition
            self.trace.emit(kind, final)
        else:
            self.stopped = True

    def dispatch(self, *, tag_preserved, output_preserved):
        if self.stopped or self.dispatched or self.current is not None:
            return None
        if not self.armed or not (tag_preserved or output_preserved):
            self.trace.emit("skipped")
            self.stopped = True
            return None
        self.dispatched = True
        return self._call("read")

    def at_pre_cleanup(self):
        if self.stopped or self.marker or not self.result:
            return False
        self.marker = True
        self.trace.emit("pre-cleanup", self.result)
        return True

    def finish(self, receipt):
        if (self.marker and not self.stopped and isinstance(receipt, CaptureReceipt)
                and self._authorize_release(receipt)
                and receipt == CaptureReceipt(self.trace.slots[-1], self.result.payload)):
            self.reserved = False
            self.stopped = True
            self.trace.emit("released", receipt)

    @property
    def game_launch_allowed(self):
        return False
