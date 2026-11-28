"""Conservative may-reach edges from GNU ARM/Thumb listings of the linked hook."""

from collections import defaultdict, deque
from dataclasses import dataclass
import re

from .experimental_dip_evidence import CHECKLIST, REQUIRED_PATHS, SYMBOLS


@dataclass(frozen=True)
class Instruction:
    owner: str
    op: str
    args: str
    width: int
    mode: str


@dataclass
class Listing:
    labels: dict
    code: dict


def disassembly(text):
    labels, code = {}, {}
    owner = None
    for line in text.splitlines():
        label = re.fullmatch(r"\s*([0-9a-fA-F]+) <([^>]+)>:", line)
        if label:
            owner = label[2]
            if owner in labels:
                raise ValueError("ambiguous disassembly label")
            labels[owner] = int(label[1], 16)
            continue
        if line.startswith("Disassembly of section"):
            owner = None
        row = re.match(r"^\s*([0-9a-fA-F]+):\s*(.*)$", line)
        if not row or owner is None:
            continue
        pc = int(row[1], 16)
        # 2.20.1 arm-dis.c prints zero-operand nops followed by a tab and ';'.
        body = re.split(r"[;@]", row[2], maxsplit=1)[0].strip()
        raw = re.match(r"^([0-9a-f]{8}|[0-9a-f]{4}(?:\s+[0-9a-f]{4})?)\s+", body)
        width, mode = 0, "unknown"
        if raw:
            width = len("".join(raw[1].split())) // 2
            mode = "arm" if len(raw[1].split()[0]) == 8 else "thumb"
            body = body[raw.end():]
        m = re.fullmatch(r"([a-z.][a-z.0-9]*)\s*(.*)", body)
        op, args = (m[1], " ".join(m[2].split())) if m else ("?", "")
        if pc in code:
            raise ValueError("ambiguous disassembly address")
        code[pc] = Instruction(owner, op, args, width, mode)
    return Listing(labels, code)


COND = r"eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le"
REG = r"(?:r(?:1[0-5]|[0-9])|ip|fp|sl|sb|sp|lr|pc)"
TARGET = re.compile(r"(?:0x)?([0-9a-f]+)(?: <[^<>]+>)?")
REGS = re.compile(r"\{(" + REG + r"(?:,\s*" + REG + r")*)\}")
LITERAL = re.compile(r"(" + REG + r"), \[pc(?:, #(-?(?:0x[0-9a-f]+|\d+)))?\]")
# Straight-line opcodes with supported GNU operand syntax. Any PC write,
# unrecognised opcode, table dispatch or opaque trap stays open for review.
VALUE = rf"(?:{REG}|#-?(?:0x[0-9a-f]+|\d+))"
ALU_ARGS = re.compile(rf"{REG}, {VALUE}(?:, {VALUE})?(?:, (?:lsl|lsr|asr|ror) {VALUE})?")
MEM_ARGS = re.compile(rf"{REG}, \[{REG}(?:, (?:{VALUE}|-{REG})(?:, (?:lsl|lsr|asr) #\d+)?)?\]!?(?:, {VALUE})?")
ALU = re.compile(r"(?:mov|mvn|add|adc|sub|sbc|rsb|and|orr|eor|bic|mul|lsl|lsr|asr|ror|neg|"
                 r"cmp|cmn|tst|teq)(?:s)?(?:" + COND + r")?")
MEM = re.compile(r"(?:ldr|str)(?:b|h|sb|sh)?(?:" + COND + r")?")


def sequential(ins):
    if ins.op == "nop":
        return not ins.args
    if re.match(r"(?:pc|r15),", ins.args) and not ins.op.startswith(("str", "cmp", "tst")):
        return False
    if ALU.fullmatch(ins.op):
        return ALU_ARGS.fullmatch(ins.args)
    if MEM.fullmatch(ins.op):
        return MEM_ARGS.fullmatch(ins.args)
    if ins.op == "swp":
        return (re.fullmatch(rf"{REG}, {REG}, \[{REG}\]", ins.args)
                and not re.search(r"\b(?:pc|r15)\b", ins.args))
    if ins.op in ("push", "pop"):
        return REGS.fullmatch(ins.args) and not re.search(r"\b(?:pc|r15)\b", ins.args)
    if ins.op in ("stmia", "stmdb", "stmfd", "ldmia", "ldmfd"):
        base, _, registers = ins.args.partition(", ")
        return (re.fullmatch(REG + "!?", base) and REGS.fullmatch(registers)
                and not re.search(r"\b(?:pc|r15)\b", ins.args))
    return False


def public_name(name, symbols=SYMBOLS):
    canonical = re.sub(r"\.(?:constprop|isra)\.\d+$", "", name)
    return canonical if canonical in symbols else "other"


def frame_evidence(name, entry, instructions, journal, unresolved):
    saved = local = 0
    uncertain = unresolved or not instructions or instructions[0][0] != entry
    past_entry = False
    for _, ins in instructions:
        op, args = ins.op, ins.args
        if op == "push" or (op in ("stmdb", "stmfd") and args.startswith("sp!")):
            registers = REGS.fullmatch(args.removeprefix("sp!, "))
            if registers and not past_entry:
                saved += 4 * len(registers[1].split(","))
            else:
                uncertain = True
        elif op == "str" and re.fullmatch(REG + r", \[sp, #-(?:4|0x4)\]!", args) and not past_entry:
            saved += 4
        elif op in ("add", "adds", "sub", "subs") and re.match(r"(sp|r13),", args):
            amount = re.fullmatch(r"(?:sp|r13), (?:(?:sp|r13), )?#(0x[0-9a-f]+|[0-9]+)", args)
            if not amount:
                uncertain = True
            elif op.startswith("sub") and not past_entry:
                local += int(amount[1], 0)
            elif op.startswith("sub"):
                uncertain = True
        elif re.search(r"\[(sp|r13)[^\]]*\](?:!|,)|^(sp|r13)!", args):
            uncertain = True
        elif re.match(r"(sp|r13),", args) or (op.startswith(("pop", "ldm"))
                                              and re.search(r"\{[^}]*\b(?:sp|r13)\b", args)):
            uncertain = True
        if op.startswith("b") or op == "pop" or not sequential(ins):
            past_entry = True
    journal.write("frame", public_name(name, journal.policy.SYMBOLS), entry, saved, local,
                  "unresolved" if uncertain else "entry-only")


def literal_value(code, pc, ins, match):
    mode = ins.mode
    if mode == "unknown" and match[1] == "pc":
        mode = "arm"  # ARM926 Thumb-1 cannot load PC with this form.
    if mode == "unknown":
        return None
    base = pc + 8 if mode == "arm" else (pc + 4) & ~3
    slot = code.get(base + int(match[2] or "0", 0))
    if slot and slot.op == ".word" and re.fullmatch(r"0x[\da-f]{1,8}", slot.args):
        return int(slot.args, 16)
    return None


WITNESSES = {
    "stock-forward": {("DI_EmulateIoctl", "DI_HandleIoctl")},
    "arm-admission": {("nd_hook", "admit_arm"), ("admit_arm", "nd_take")},
    "malformed-attempt": {("nd_hook", "nd_fail"), ("nd_hook", "nd_finish")},
    "duplicate-rejection": {("nd_hook", "nd_take")},
    "network-selectors": {("operation", "submit"), ("submit", "os_ioctlv_async")},
    "receive-handoff": {("operation", "receive_handoff"), ("receive_handoff", "__os_sync_before_read")},
    "deadline-quarantine": {("timely", "nd_fail"), ("operation", "nd_pin")},
    "eligible-cleanup": {("nd_exchange", "cleanup"), ("cleanup", "operation")},
    "trace-return": {("nd_finish", "nd_emit"), ("nd_hook", "nd_finish")},
}


def path_evidence(listing, journal, required=None):
    if required is None:
        required = journal.policy.REQUIRED_PATHS
    witnesses = getattr(journal.policy, "WITNESSES", WITNESSES)
    code, labels = listing.code, listing.labels
    entry = labels.get("DI_EmulateIoctl")
    # A call's continuation becomes reachable only after a return from its
    # exact destination. Tail branches retain the current return context.
    todo = deque()
    seen, pcs, edges, faults = set(), set(), set(), set()
    returns = defaultdict(set)
    callers = defaultdict(set)
    if entry is None:
        faults.add((0, "missing-entry"))
    else:
        todo.append((entry, entry, None))

    def transfer(pc, dest, kind, context, mode=None):
        target = code.get(dest)
        if not target or target.op.startswith("."):
            faults.add((pc, "missing-target"))
        elif mode not in ("arm", "thumb") or target.mode != mode:
            faults.add((pc, "ambiguous-mode"))
        else:
            edges.add((pc, dest, kind))
            todo.append((context, dest, None))
            return True
        return False

    def resume(return_pc, continuation):
        caller_mode = code[continuation[1]].mode
        ret = code[return_pc]
        # BX LR explicitly interworks. For other return forms only credit
        # same-mode continuations within this limited traversal.
        if ret.op.startswith("bx") or ret.mode == caller_mode:
            todo.append(continuation)
        else:
            faults.add((return_pc, "ambiguous-mode"))

    while todo:
        state = todo.popleft()
        if state in seen:
            continue
        seen.add(state)
        context, pc, constant = state
        ins = code.get(pc)
        if ins is None or ins.op.startswith("."):
            faults.add((pc, "data" if ins else "gap"))
            continue
        pcs.add(pc)
        op, args = ins.op, ins.args
        following = pc + ins.width if ins.width else None

        def valid_continuation():
            if following is None or following not in code:
                faults.add((pc, "gap"))
            elif code[following].op.startswith("."):
                faults.add((pc, "data"))
            elif ins.mode == "unknown" or code[following].mode != ins.mode:
                faults.add((pc, "ambiguous-mode"))
            else:
                return True
            return False

        def advance(value=None):
            if valid_continuation():
                todo.append((context, following, value))

        # Explicit condition codes on returns have a separate fallthrough.
        ret = re.fullmatch(r"(bx|mov|pop|ldmia|ldmfd)(" + COND + r")?", op)
        if ret and ((ret[1] == "bx" and args == "lr") or (ret[1] == "mov" and args == "pc, lr") or
                    (ret[1] in ("pop", "ldmia", "ldmfd") and
                     (ret[1] == "pop" or args.startswith("sp!, ")) and
                     REGS.fullmatch(args.removeprefix("sp!, ")) and re.search(r"\bpc\b", args))):
            if pc not in returns[context]:
                returns[context].add(pc)
                for continuation in callers[context]:
                    resume(pc, continuation)
            if ret[2]:
                advance()
            continue
        branch = re.fullmatch(r"(blx|bl|b)(" + COND + r")?", op)
        if branch:
            dest = TARGET.fullmatch(args)
            if dest:
                address = int(dest[1], 16)
                mode = None if ins.mode == "unknown" else ins.mode
                if mode and branch[1] == "blx":
                    mode = "thumb" if mode == "arm" else "arm"
                if branch[1] == "b":
                    transfer(pc, address, "conditional" if branch[2] else "branch", context, mode)
                elif transfer(pc, address, "call", address, mode):
                    if valid_continuation():
                        cont = (context, following, None)
                        callers[address].add(cont)
                        for return_pc in returns[address]:
                            resume(return_pc, cont)
            else:
                faults.add((pc, "indirect"))
            if branch[2]:
                advance()
            continue
        if op == "bx":
            if args == "pc" and ins.mode == "thumb" and (pc + 4) % 4 == 0:
                transfer(pc, pc + 4, "interwork", context, "arm")
            elif constant and constant[0] == args:
                address = constant[1]
                transfer(pc, address & ~1, "interwork", context, "thumb" if address & 1 else "arm")
            else:
                faults.add((pc, "indirect"))
            continue
        literal = LITERAL.fullmatch(args) if op == "ldr" else None
        if literal:
            address = literal_value(code, pc, ins, literal)
            if literal[1] == "pc":
                if address is None:
                    faults.add((pc, "indirect"))
                else:
                    transfer(pc, address & ~1, "literal", context, "thumb" if address & 1 else "arm")
            else:
                advance((literal[1], address) if address is not None else None)
        elif sequential(ins):
            advance()
        else:
            faults.add((pc, "unsupported"))
    # These are individual branch-site witnesses. None proves the predicate,
    # operation selector, ordering or eventual return on its own.
    for pc, dest, kind in sorted(edges):
        journal.write("edge", pc, dest, kind)
        target = code[dest].owner
        if dest == labels[target]:
            pair = public_name(code[pc].owner, journal.policy.SYMBOLS), public_name(target, journal.policy.SYMBOLS)
            for item, pairs in witnesses.items():
                if pair in pairs:
                    journal.write("witness", item, pc, dest)
    for fault in sorted(faults):
        journal.write("unresolved", *fault)
    by_owner = defaultdict(list)
    for pc in sorted(pcs):
        by_owner[code[pc].owner].append((pc, code[pc]))
    uncertain_frames = {code[pc].owner for pc, _ in faults if pc in code}
    for name, instructions in by_owner.items():
        frame_evidence(name, labels[name], instructions, journal, name in uncertain_frames)
    reached = {public_name(n, journal.policy.SYMBOLS) for n, addr in labels.items() if addr in pcs}
    for name in sorted(required - reached):
        journal.write("missing", name)
    for item in sorted(journal.policy.CHECKLIST):
        journal.write("review", item, "manual-required")
    return pcs
