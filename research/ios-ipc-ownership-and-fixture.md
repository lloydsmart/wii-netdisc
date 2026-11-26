# Who owns a timed-out DIP request, and what can GX still observe?

**R0-02 / R0-03 · 25 November 2026 · Recommendation 2 (hypothesis).**
Keep direct DIP as the candidate caller. Defer a modified link. A single
persistent slot can protect the bytes of a late receive. It cannot make the DI
thread return from an open that blocks *inside submission*. There is a plausible
second PPC reader and a way to stage the challenge separately from the read. Two choices still change the program that would be measured:
where the fixture can recognise its read before backing-media access, and
whether a stalled call may end only through independent recovery. Both the arm
and the read also depend on a PPC IPC path that preserves its internal request
until the matching completion.

The target is one synthetic read on an original Wii, with IOS57 v5918 and d2x
`33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7`, before GX calls its cleanup
helper. The proposed experiment ends there. [Baseline and verdicts](ios57-baseline-plan.md) ·
[Prior fit study](direct-dip-tcp-probe-fit.md) · [Network lifecycle](r0-02-r0-03-ios57-v5918-network-lifecycle.md)

**Evidence.** Inspected public source as text against the pinned Git trees on
25 November 2026, from Wii NetDisc `bb8746f74eb29d5248600a76284df2f6a14f49f3`.
Links identify the functions and revisions. **Source-verified** refers to the
named client or reimplementation. **Historical** identifies published WiiBrew
reverse-engineering observations. **Hypothesis** identifies a proposed fixture
contract. **Unresolved** identifies an evidence gap on 57/5918. The only
**experimentally verified** quantities used here are the previous PC stock
measurements. No new ARM link, IOS execution or hardware observation took place.
[Stock measurements](d2x-build-baseline.md)

## IPC-01 · What an ARM caller can infer from a return

**Source-verified.** Both ARM assembly files emit a numbered trap and return
to the caller. Neither marshals callbacks. HAI supplies the most explicit
client declarations. d2x calls the final open/close arguments pointers and
uses variadic tails for ioctl/ioctlv. The following is the common 32-bit ARM
calling convention suggested by the traps, clients and StarStruck wrappers.
The queue argument is an integer ID and the last argument is writable caller
reply storage. The four entries are open (0x23), close (0x24), ioctl (0x28)
and ioctlv (0x29). The first four argument words go in r0–r3, the remainder
on the ARM call stack, and the return value in r0. A pointed-to path,
vector or payload must outlive submission. PPC libogc implements a separate
callback and user-data interface. [d2x declarations][ddecl] · [Trap entries][dtrap] ·
[HAI declarations][hdecl] · [HAI traps][htrap] · [Stack argument count][kargs] ·
[Async wrappers][kasync] · [PPC IPC][ppcio]

| ARM operation | Arguments in order | Evidence to take from the two returns |
| --- | --- | --- |
| Open | Path, mode, queue, reply | Save the trap return. On successful delivery read the RM handle from the signed reply result. Handle zero is valid. Open has a special failure path below. |
| Close | RM handle, queue, reply | A successful submit admits the close. Record its later result against the original acquisition. |
| Ioctl | RM handle, request, input pointer, input bytes, I/O pointer, I/O bytes, queue, reply | Keep raw submission and operation results. Some operations also return service data, e.g. the signed KD startup word. |
| Ioctlv | RM handle, request, input vector count, I/O vector count, vector pointer, queue, reply | Counts are numbers of pointer/byte-length pairs. A receive returns a byte count in the result and data in the destinations. |

**Source-verified, StarStruck open.** For a matching resource manager (RM),
`OpenFD_Inner` prepares a per-thread open message and calls
`SendMessageCheckReceive`. The send and the wait for the RM reply can block
inside submission. The caller ignores the helper's return status and reads
`message->Request.Result` directly. After a helper error that field alone
cannot establish a fresh RM reply. On a genuine RM success the resource can
already exist. The kernel searches the process table starting at slot zero,
stores the RM's internal ID and returns the slot number. If the table is full,
it returns `IPC_EMAX` without installing a process descriptor or showing a
compensating RM close.

Only a nonnegative inner return causes `OpenFDAsync` to write the reply
command and process descriptor into caller storage and try sending its address
to the completion queue. A full queue can leave an installed descriptor
without a delivered completion. Either table exhaustion or delivery failure
can therefore leave an acquisition to account for. Infer an empty acquisition
ledger only from a known pre-admission rejection. Otherwise record the raw
status and quarantine unknown ownership. [Open and descriptor allocation][kfd] ·
[Async open publication][kasync] · [Resource-manager send and wait][kipc]

For the other calls the resource queue send itself uses the blocking mode.
Even a perfectly empty private completion queue cannot bound that send.
WiiBrew independently describes synchronous work in ARM async open.
This is a counterexample to a deadline proof, with no inference about the
exact failure codes or frequency on 57/5918. [Open wrapper][kasync] ·
[Open and close internals][kfd] · [Send and reply][kipc] · [Queue send][kqueue] ·
[Historical syscall record][brewcall]

**Source-verified, reply identity.** HAI's packed public request is 32 bytes
on this ABI, with command at byte 0, result at 4, fd at 8 and arguments at 12.
d2x USB compares a dequeued *word* to the address of one of two static
`areply` objects and reads its second word as signed. It handles these before
the ordinary RM dispatch/ack path. HAI's DNS path compares the pointer to an
aligned static full message. StarStruck keeps a separate internal wrapper,
writes the reply command and signed result into the caller's object and sends
its address. Only those two words convey completion here. Use a whole aligned
32-byte object, and keep the operation identity in private state. HAI also
acks its DNS callback, whereas StarStruck's resource reply accepts its internal
request object, and USB consumes a client completion directly. A second ack
of caller storage has no established release semantics. Retain the raw result
bits for interpretation as an error, a handle, a byte count or an IPv4 value,
according to the operation. [HAI layout][hlayout] ·
[d2x layouts][dlayout] · [USB tokens][usbtoken] · [USB submission][usbsubmit] ·
[USB dispatch][usbdispatch] · [DNS wait][hdns] · [Kernel reply][kipc]

**Source-verified, queue and authority.** The create call takes caller backing
storage and capacity in message words. d2x USB allocates 128 bytes for 32
entries. StarStruck assigns an ID to a finite circular queue bound to the
creating PID. Normal sends append, receives remove the head, and jam can put
a word at the front. Blocking send/receive may sleep on full/empty.
Nonblocking delivery can fail. Resource reply releases internal async
accounting before trying to enqueue the notification. Timer delivery ignores
the return from its nonblocking send. Destruction wakes waiters and makes the
queue slot available again. Destruction supplies no evidence about external
producers still holding its identity or address. WiiBrew's kernel notes also
distinguish queue owner, capacity, count and backing pointer from the thread
accounting in a request wrapper. [Historical kernel structures][brewkernel] · [USB queue][usbdispatch] ·
[Queue implementation][kqueue] · [Reply delivery][kipc] · [Timer expiry][ktimer]

StarStruck looks up ordinary RM handles by PID, accounts for pending messages
by submitting thread and passes process credentials at open. Close clears an
ordinary descriptor slot after its resource-queue send, before a later async
result. The number can be reassigned. The SO socket number is a separate
service result used *inside* ioctls on the SO handle. The pinned clients do
not establish its kernel/process/thread ownership or last-close behaviour in
target SO. The d2x hook grants its executing thread a FAT-specific right.
Neither that grant nor a PID shared with another thread establishes network
or cleanup authority. [Descriptor lookup and close][kfd] · [Socket close][hsockclose] ·
[DI thread rights][dright]

**Hypothesis, minimum loan to IOS.** Retain open paths, aligned control/KD/NCD
lines, vector array, every pointed-to input/output, reply and queue backing
in dedicated storage. Clean producer-written inputs and vectors before
submission. Relinquish whole output and reply cache lines with no dirty
private bytes, keep them untouched while pending, then invalidate/synchronise
before reading the matching completion and its outputs. Copy exactly a
validated positive count from aligned scratch into the permanent frame.
StarStruck checks caller/RM buffer permissions on its ioctl paths. d2x WBFS
cleans controls and invalidates its destination after the operation. HAI's
receive path uses after-write sync on received data and can round a bounce
copy up. It cannot settle target cache direction or grant SO access to DIP
BSS. HAI's timed DNS path destroys a stack-backed queue and may free its input
on expiry. It shows no drain or request cancellation. Thread stop/cancel,
timer stop, queue destroy and socket close provide no public contract for
cancelling an arbitrary outstanding IPC. [Vector checks][kvec] ·
[WBFS_Read][dwbfs] · [HAI receive][hrecv] · [Timed DNS][hdns] · [Kernel syscall table][ktable]

## IPC-02 · Clocks and the four different end times

**Source-verified / historical.** Timer creation takes initial and repeat
intervals in microseconds, queue ID and message word. Zero repeat requests
one expiry. Creation returns a timer ID or an error. Stop, restart and destroy
operate on that ID. StarStruck converts the interval to ticks, unlinks a
one-shot on expiry and separately delivers the word. Stop/destroy changes
timer state without removing any word already in the destination queue.
For reading time, d2x declares a signed result and a timer-ID argument. HAI
declares unsigned `os_time_now()` and supplies no argument in its declaration
list. Its C spelling alone does not check the argument count. At the same
trap StarStruck dispatches to `u32 GetTimerValue(void)`, which reads the
hardware counter. This favours a no-argument raw tick sample. An elapsed
microsecond count cannot be inferred from the timer creation ABI. [Declarations][ddecl] ·
[HAI clock][hdecl] · [Dispatch][ktable] · [Timer implementation][ktimer] ·
[Historical syscall table][brewcall]

WiiBrew describes a writable 32-bit counter at core clock / 128. At nominal
243 MHz this gives about 1.898 million ticks/s and a wrap every 37.7 minutes.
Treat monotonicity as conditional on one uninterrupted IOS epoch and stable
clock configuration. Compare unsigned elapsed ticks modulo 2³² with
a converted budget, with all allowed observation gaps below half the counter
range. At equality fail the deadline. Never infer a timely result after an
unbounded stall, multiple possible wraps or an instance change. Target rate,
reset behaviour and accuracy require comparison to an independent clock.
[Historical Starlet timer description][brewtime] · [Tick conversion][ktimer]

| Interval | Start and end under the candidate policy |
| --- | --- |
| Bring-up, baseline | 30 s from before the first NCD open through SO readiness. All NCD, KD and SO startup calls, closes and retries needed for readiness share it. |
| Connection, owner decision | Candidate 5 s total from readiness through socket creation and one connect. A pending connect stays with that socket. There is no reconnect. |
| Exchange, baseline | One absolute 5 s from before the first send through receipt and verification of the full reply. Partial I/O, retryable results and waking late consume the same budget. |
| Cleanup, owner decision | Candidate 5 s total for eligible closes. Start once on abandonment or verified exchange. A known outstanding operation bars any conflicting close. Cleanup expiry starts no new cleanup window. |

**Hypothesis.** The phase deadline determines timeliness. Safe DI return also
requires that no future writer can touch DI stack, caller buffers or the
shared publication after return, and that GX honours a terminal stop. Final
release needs known dispositions for all resources or evidence that the IOS
instance and its I/O agents have ended. These times can all differ. A fourth
time belongs to the independent observer: start its watchdog *before* arming
or dispatch, with a pre-agreed latest time to initiate controlled recovery,
including slack for scheduling, capture and dispatch. Use per-phase watchdog
checkpoints plus a hard outer limit that progress cannot extend. The two
candidate 5 s allowances and watchdog slack need owner decisions. Neither a
timer message nor the sum of the phase budgets establishes a worst-case DI
return or resource-release time. [Baseline deadlines](ios57-baseline-plan.md)

## IPC-03 · One persistent slot and its transitions

**Hypothesis A.** The hooked DI thread is the sole network submitter and
queue consumer. One fixture owns the slot for one IOS instance, even after
DI returns. The slot includes the immutable request, all network storage
listed above, private queue and timer bookkeeping, phase, attempt serial and
resource ledger. The ledger has separate entries for NCD, KD, SO and the
socket on that SO acquisition. Record acquisition and close-attempt serials,
including valid number zero. Set a close entry to *in flight* before the
trap. No other component acts on a recorded number. GX owns only local fixture
allocations and the launch decision. The peer owns its accepted connection
and log. No network operation borrows GX memory.

| Transition | Actor and ownership of the affected resources | Evidence required to progress |
| --- | --- | --- |
| Unarmed → armed | GX stages fresh bytes. DI validates and copies the arm record to permanent storage. No network handle, operation or timer exists. GX keeps the fixture allocation reserved. | GX may dispatch only after safe IPC handback of the arm call (IPC-06), matching receipt, epoch, build and intended request identity. A second arm is refused. |
| Armed → claimed | DI alone matches the synthetic request, consumes the arm once and publishes actual caller entry before setup or submission. | An exclusive claim and visible entry. An unmatched ordinary read leaves the arm untouched. |
| Armed → spent (malformed) | DI recognises a fixture discriminator but validation fails. Consume the attempt and reject before media or network access. | A subsequent valid-looking duplicate stays rejected. |
| Claimed → ready | DI creates one private queue for the fixture. On each phase entry it arms that phase's single one-shot timer. | Successful setup and a valid phase clock. |
| Ready/completed → submitting | For each sequential operation DI records the operation/owner, freezes all loaned lines and publishes intent *before* crossing into IOS. Prior handles stay in the ledger. | Queue/timer success, no live loan and time remaining. Submission can stall here. |
| Submitting → pending or error | IOS may already use the slot. DI records the trap status only if control returns. On documented pre-admission rejection no result is expected. Unknown side effects go to quarantine. | Zero admission still needs the matching reply. Never wait for a callback known to have been rejected or retry an ambiguous failure. |
| Pending → completed | IOS produces the result. DI dequeues the exact object, synchronises it and samples the clock. On a timely result it records any new handle/socket, bytes, service result or release. | Valid command, expected pointer, sole pending operation, coherent data and in-budget validation. Only now may DI prepare the lines for another operation. |
| Submitting/pending → expired → quarantined | DI latches expiry only after identifying the active phase and observing valid elapsed time at or beyond its budget. If stuck, the external observer records the missed checkpoint separately. Keep every possible loan, queue, timer and handle pinned. Prohibit more network work, rearm and game launch. | Clock evidence distinguishes DI's own deadline from a watchdog observation. Neither ends the loan. |
| Quarantined → late completion | Only DI, if it regains control before recovery, may consume the existing reply. Record the late result and any newly acquired resource. No second exchange and no reuse for ordinary work. | Matching completion releases that operation's loan. Late success never erases expiry. |
| Completed/late → cleanup pending | DI alone may issue one allowed close at a time, after all dependencies on the resource have completed and within the remaining cleanup window. Socket close uses the live SO handle first. Also account for NCD/KD on partial setup. | Per-resource acquisition, close attempt, submission and eventual result. Uncertain ownership ends active cleanup. |
| Cleanup → terminal or recovery required | After known release, quiesce the timer, deal with queued events, freeze final trace and return the raw DI result. The slot stays spent. Otherwise pin it and inhibit launch until independent recovery. | GX needs a matching synchronous return with safe IPC handback (IPC-06). Account for each release individually or establish the end of the old IOS instance and relevant I/O or DMA. A late reply alone proves neither for other resources. |

**Queue invariant.** Use a private queue with one reply object address and a
distinct immutable expiry token per *phase*. One one-shot per phase for at
most four phases, each entered once. One outstanding completion plus all four
possible undrained expiry words needs five word slots (20 bytes before
alignment). Two slots suffice only with proof that all older producers and
their queued words have retired. Do not register this queue as an RM or send
other events to it. Stop/destroy the outgoing timer and check its result.
Identify the token's phase first. A timer word only wakes DI. For either event
order, sample the active phase's absolute elapsed time using the bounded-gap
rule in IPC-02. Latch deadline failure once when elapsed time reaches or
exceeds the budget, including at equality. Discard recognised stale timer
words. An early current-phase token leaves the operation pending and its
original deadline in force. If that one-shot has fired early, the independent
watchdog still covers a missing subsequent wake. An unrelated word cannot
prove expiry. An unknown producer violates the queue invariant and requires
quarantine. An unbounded sampling gap leaves timeliness unknown even if the
wrapped counter looks in budget. Check again after submission and verification.
Partial progress never restarts the exchange clock.

A reused reply pointer carries no transaction serial of its own. Reuse within
this one run depends on exactly one delivered reply for the previous accepted
submission and exclusive dequeue. An old duplicate delivered while the same
address is pending again would be indistinguishable, even with a private serial.
If one-reply semantics cannot be justified, that reuse design fails review.
Never recycle it across an uncertain submit,
full queue, unexpected pointer, duplicate reply, lost delivery or ambiguous
timer retirement. Preserve the slot, its queue ID and backing even if a
nonblocking drain reports empty. A queue observed empty now can still have a
future producer. Use a sticky first failure, a separate immutable verified
exchange and an append-only cleanup disposition for each acquisition.

### Cases that determine the outcome

| Event | Action and disposition under A |
| --- | --- |
| Open returns an immediate error | Record raw status. Only a known pre-admission rejection leaves this entry empty. Otherwise an RM resource or process descriptor may exist without a usable handle. Quarantine it without guessing a number. |
| Open succeeds before expiry | Record the matched nonnegative reply as a new acquisition. A negative operation result is a failed open. Preserve any previously acquired handles for cleanup. |
| Open expires, returns late or never returns | While the trap or reply is pending, keep path, reply, queue and ledger alive. A late valid handle becomes owned by this acquisition and eligible for exactly one bounded close if safe. If it never arrives, retain unknown ownership until recovery. A timely enqueue first observed past the deadline is late for this test. |
| Receive completes before expiry | Invalidate its destination. Check result against remaining length. Copy only positive in-range bytes. EOF before 28 bytes, a terminal error or over-count fails. A partial count progresses within the same exchange. Latch verification only after full validation before expiry. |
| Valid phase clock reaches the deadline with a receive pending or on completion | Latch the deadline once, independently of which word was dequeued first. While pending, nobody reads, clears, frees or reuses the destination. Later writes land only in static quarantined scratch. After a matching late completion DI can record the coherent late count/bytes separately. They cannot complete the exchange in time. |
| Receive never completes | Keep socket, SO handle, vectors, reply, queue and destination pinned. Do not close underneath the receive or return a buffer still used by IOS. Independent recovery owns the stop decision. |
| Close completes normally | Consume the matching completion once and retire only that acquisition. Successful socket close and successful SO handle close are separate observations. |
| Close errors, stalls or expires | Keep the first failure and any verified exchange. A close error can leave final disposition unknown. A timeout leaves the close outstanding. Never close the numeric handle again or assume it is still allocated. |
| Close completes late or cleanup itself fails | Record a matched late success as released for its original ledger entry, keeping the cleanup deadline failure. Late error, missing completion, failed timer teardown or unproved disposition ends cleanup in quarantine. No further use of SO beneath an unresolved socket operation. |
| Both events arrive, queue exhausts, or evidence is lost | Classify by absolute time even when completion is dequeued first. If the timer word arrives first, identify its phase and check elapsed time. Retain the loan pending a matching reply. An early or stale wake leaves the active deadline unchanged. Delivery failure, stale/foreign completion or indefinite waiting invokes the observer. Never infer cancellation or release from silence. |

## IPC-04 · Who could finish a late operation?

**A — terminal quarantine (preferred hypothesis).** DI can opportunistically
take an already delivered late reply. If DI has returned, no one dequeues:
even a late successful open belongs to the quarantined instance until its end
and cessation of relevant I/O have been independently confirmed.
GX may accept a diagnostic failure return only after safe PPC IPC handback
(IPC-06) and evidence that DI froze publication and severed every GX pointer. It must stop before releasing fixture storage
or starting a game on any uncertain disposition. If DI cannot do that, leave
the synchronous call pending. The watchdog must be able to preserve evidence
and initiate recovery without waiting for DI, an IOS close or the PPC launch
thread. This bounds the decision to abandon the run. It does not bound
software cleanup.

**Unresolved recovery boundary.** An independently established end of the old
IOS instance *and* cessation of its device/DMA activity would end the loans.
A new PPC process, a reset-button observation, the same slot/version string
or an empty queue supplies no such proof. Libogc's IOS reload shuts down
subsystems, uses ES IPC to launch the replacement and reinitialises IPC.
A wait loop with a counter later in that path cannot bound the earlier ES
calls. A complete cold stop and separately identified clean boot is a candidate
physical boundary. Its safety, controller reset, boot route, backup and
recovery time on this console are unverified. No second run in this instance.
Before any hardware task the owner must approve and verify an independent
recovery route and a way to retain the last observation outside the console.
[Reload entry][reload] · [ES launch and IPC restart][launch] · [Recovery gate](ios57-baseline-plan.md)

**B — independent completion drainer (hypothesis).** The strongest case is a
thread created by the actual DI caller, in the same process, with a persistent
private stack, suitable permitted priority and explicit start. StarStruck
creates a stopped child with the creator's PID and limits its priority. HAI's C header
declares `os_get_process_id` for syscall 4. Its assembly
exports `os_get_parent_thread_id`, the name also used by d2x. StarStruck
dispatches syscall 4 to `GetProcessID`. These names establish neither the
target identity semantics nor a worker's cleanup authority. d2x calls the thread-create flag autostart, HAI and
StarStruck make it detached. Record the actual DI and worker TIDs and establish
their PID and rights independently. A DIP startup thread could be a different
identity. [Thread declarations][ddecl] · [HAI thread declarations][hdecl] ·
[HAI assembly][htrap] · [Kernel dispatch][ktable] · [CreateThread and StartThread][kthread]

Give the drainer exclusive queue consumption **from the start**, with a
separate bounded notification to DI. DI still submits the network operations
for caller attribution. Publish the operation identity and resource ledger
*before* the trap. The worker must reconcile a reply that races ahead of the
submit return. A single, acknowledged handoff gives it exclusive cleanup
authority only when DI can issue no conflicting action. If the submitter never
confirms handoff, the worker can retain the result and keep the resources
pinned. Starting a second consumer at timeout would race DI for the same word.
The PID checks make same-process queue and FD access plausible. They do not
establish target SO socket authority, inherited d2x thread rights, scheduling
while a trap stalls, or safe thread exit and stack retirement. Worker closes
can themselves stall. A drainer cannot make a stuck DI submit return. Its
extra synchronisation, wakeup channel, stack and recovery path buy little
for one terminal attempt. [Queue PID checks][kqueue] · [Thread accounting and FD table][kfd] ·
[DI rights][dright]

**Separate service.** HAI's registered service loop, startup identity/stack
and DI-to-file-service client are concrete precedents. A service can own the
network descriptors, buffers and late completions from birth. That removes
cross-thread transfer of a DI-owned socket. It adds DIP-to-service submission,
a persistent request and bounded handback, a service identity/region, startup,
permissions at both boundaries and another trace to correlate. A service
blocked in open can also miss its own timeout. Even on success it measures
the service's network authority. It cannot answer the direct caller question.
Reconsider it if complete direct logic exceeds the stock region or the direct
identity fails an authorised access test. [HAI dispatch][hloop] ·
[Service startup][hstart] · [DI client and d2x base inventory](ios57-baseline-plan.md)

## IPC-05 · Arming exactly one read

**Source-verified boundary.** GX zeroes eight 32-bit aligned words. The
unencrypted read uses the command in word 0, byte length in word 1 and
word offset in word 2. All 32 bytes reach the libogc ioctl input handoff.
Libogc translates the two top-level addresses and flushes both ranges.
The d2x outer hook takes an ioctl descriptor with input and I/O pointers
and lengths plus a separate fd argument. Unhandled commands continue into
base DI. The inner command hook takes input, output and size. Its unencrypted
case uses the first three words. The 57/5918 patch table and return trampolines
identify the boundary, but omit the intervening base implementation. GX and
d2x use word 3 for *set frag list*, a different command with storage side
effects. That evidence cannot establish unchanged forwarding of words 3–7
for an unencrypted read. Even perfect forwarding leaves 20 bytes for a
24-byte tag/challenge pair. [GX read][gxread] · [PPC ioctl][ppcio] ·
[Hook arguments][dhooktype] · [57/5918 hooks][dpatch] · [Continuations][dcont] ·
[Read case][dread] · [GX frag request][gxfrag] · [DIP frag handling][dfrag]

**Proposed arm contract.** Use a separately staged, fixture-only local control
request on the already open DI instance. This is a proposed interface. Its
admission on the base, build identification and collision-free dispatch need
review. Neither a production opcode nor an address is assigned here.

1. Prepare a fresh 8-byte tag and fresh 16-byte challenge for *this attempt*.
   A PC can generate a single-use random pair for a local SD fixture before
   the run. GX consumes it once and logs it with boot epoch, slot, probe/GX
   build IDs and planned read. Keep a used-tag ledger off-console, including
   aborted runs. Independent wired controls may contact the peer. GX never
   needs a socket.
2. Before arming, start capture and the watchdog. Reserve a dedicated aligned
   output allocation for this one read. Use an ordinary typed IPC input for
   the arm record: format/version, full pair, expected read command, byte
   length and word offset, and instance binding. Use the reserved allocation
   as the arm call's I/O buffer. DI compares lengths with the expected format,
   validates alignment and range, copies the input to its single static slot
   and returns a receipt echoing tag, observed identity and build. Store the
   observed I/O address as an **identity value** for the next call. No IOS
   writer retains access to that allocation between calls. GX requires the
   expected receipt, raw status and safe handback of the arm IPC (IPC-06)
   before submitting the read. Lost receipt means stop,
   even if DI might have armed. Never retry arming.
3. In a fixture GX wrapper keep the normal synchronous unencrypted command,
   length, word offset and output allocation. Put only the fresh tag in two
   of the spare words, leaving the remaining three reserved. Isolate this
   request from concurrent users of GX's static input array. The proposed
   gate is the **outer** DI hook, where the typed ioctl envelope supplies the
   input length. Require fixture build/epoch, armed state, same IOS-side fd
   and exclusive output identity/length, exact command/length/offset, and the
   entire run tag. Compare fd values only within their own namespace. Use the
   validated live I/O argument for writing. Never follow an address from a
   spare word. Record the executing TID. The arm handler and network entry
   are distinct events.
4. Before dispatch require evidence that at least one fixture discriminator
   (the reserved output identity or fresh tag) reaches the outer gate intact.
   Losing both makes the synthetic read indistinguishable from ordinary traffic.
   Until preservation can be established, GX must withhold dispatch. At the
   gate, an unrelated ordinary read follows normal handling and leaves the arm
   available. For a recognisable fixture read, validate the full tuple and
   consume the armed state in one serialized decision. A valid match enters
   once. A malformed attempt (including wrong length, missing tag on the
   reserved output, or changed destination with the correct tag) spends the
   arm and returns a diagnostic rejection before media access. Keep the
   allocation exclusive and the spent binding until termination. Reject every
   recognisable duplicate, even one that subsequently passes all field checks.

**Owner decision.** Intercepting the validated synthetic read directly in
`DI_EmulateIoctl` avoids sending it through opaque base code. This changes the
entry site from the fit study's `DI_EmulateCmd`. It requires explicit agreement
on caller equivalence and evidence of the actual TID before a result is called
direct-DIP. If the inner site is essential, the outer hook could bind a
single dynamic dispatch to that TID, with the inner hook checking the scoped
claim, command, length, offset and dedicated destination. It would require
evidence that this exact call nests on that thread, preserves the necessary
arguments and can fail closed before *any* backing read. Public d2x resumes
base code at that point. Do not fall back to “next read wins” if the entry or
identity check is lost. [Outer dispatch][douter] · [Command handling][dread] · [Fit study](direct-dip-tcp-probe-fit.md)

## IPC-06 · Seeing the caller while GX is asleep

**Source-verified PPC path.** Place the synchronous request immediately before
`BootGame` enters `AppCleanUp`. That cleanup stops GUI/video work and later
calls `DeinitNetwork`. The marker belongs immediately before its
`net_wc24cleanup` call. In pinned libogc, `IOS_Ioctl` calls
`__ipc_syncrequest`, which disables interrupts around queueing and attempts to sleep on
the request queue. With a valid queue, `LWP_ThreadSleep` blocks the current thread and the
scheduler switches to a runnable thread. The IPC reply interrupt invalidates
the buffers and signals the wait queue. This supports independent PPC
execution during a pending DI request, conditional on the actual linked
libogc, scheduler, interrupts and priority. There is no maximum scheduling
latency in this trace. [Boot order][gxboot] · [AppCleanUp][gxclean] ·
[Helper marker][gxnet] · [Sync wait][ppcwait] · [Interrupt reply][ppcreply] ·
[LWP queue][psleep] · [Scheduler switch][psched]

**Source-verified premature return.** `IOS_Ioctl` allocates an internal IPC
heap request, records the translated input and I/O buffers, and flushes them.
`__ipc_syncrequest` ignores the result of `LWP_InitQueue`. Slot exhaustion
sets the wait queue to the null sentinel. The separate IPC submission queue
can still accept the request pointer, and the sender can pass its physical
address to IOS. Sleep on the null queue returns an error immediately.
Libogc ignores that result too, reads `req->result` without a demonstrated
reply, calls `LWP_CloseQueue` (a no-op for the sentinel), and returns to
`IOS_Ioctl`, which frees the request. The submission queue or IOS can still
reference it. Later, the reply interrupt uses the returned request address
to inspect the object, invalidate the ioctl buffers and signal the synchronous
waiter. Keeping only the GX buffers pinned cannot protect a freed or reused
internal request. [IPC heap allocation/free][preq] · [Queue and send][psend] ·
[Sync wait][ppcwait] · [Wait-queue failure][psleep] · [Ioctl release][ppcio] ·
[Interrupt reply][ppcreply]

**Fixture handback requirement (unresolved).** For both the arm ioctl and
the synthetic read, accept handback only with a functioning wait for that
request's reply or an independently correlated actual PPC IPC completion.
In either design, retain the internal request, any allocated wait-queue
identity, and all input/output buffers through final reply handling. A DI
progress record, arm receipt or wrapper return alone cannot establish this.
The linked libogc path needs verification and possibly instrumentation or a
corrected submission/wait path that rejects wait setup failure before enqueue
and prevents early release after admission. Correlation must precede release.
Observing a premature return later cannot repair an internal lifetime violation.
On ambiguity, preserve remaining loans and stop. GX must not issue the read
after an ambiguous arm, advance to the pre-helper marker, rearm, or launch a game.

**Hypothesis, memory reservation and lifetime.** Use an owned, line-rounded
GX MEM2 allocation for the fixture I/O buffer, with distinct lines for the
compact IOS publication. GX initialises its MEM2 allocator from Arena2,
reserves the range, caps its upper end and uses aligned allocation headers.
Check allocation success, base, end without arithmetic wrap, alignment, length
and exclusion of allocator metadata, loader/reload areas and all other users.
MEM1 from GX's explicit MEM1 aligned allocator is another candidate for DI IPC.
Libogc also offers allocation from its bounded IPC buffer heap. None proves
the actual hook sees the same storage rather than a bounce buffer. Wii libogc
describes MEM1 and MEM2 physical bases and cached/uncached PPC aliases.
Translate with the IPC convention, compare the *same physical extent* on each
side, and retain one PPC alias for shared reads. An ordinary GX pointer, the end
of DIP BSS or an apparent gap in Arena2 confers no reservation. MLOAD registers
a MEM2 protection change during initialisation. This supplies neither a
fixture allocation in DIP RAM nor evidence of PPC access to a particular
symbol in the running build. [MLOAD initialisation][minit] · [GX startup][gxmain] ·
[GX allocators][gxalloc] · [Arena reservation][gxarena] · [Allocator alignment][gxblock] ·
[PPC memory map][pmap] · [IPC heap][pheap] · [Top-level translation][ppcio]

Only the synchronous synthetic read lends this I/O area to the IOS writer.
Before entry, GX owns and flushes whole lines, then becomes read-only for the
loan. The ARM network operations use separate DIP static storage. Freeze and
complete all ARM trace writes, relinquish the shared lines and clear the live
pointer *before* returning from DI. A late completion can never write directly
to the trace or return buffer. GX holds the allocation through terminal
capture. If DI stalls it stays allocated, with no arena reset or game handoff.
Effective cross-CPU access, stable mapping between arm/read, and visibility
*before reply interrupt* remain target questions. A normal return-buffer
read after `IOS_Ioctl` cannot witness a call that never returns.

**Hypothesis, publication contract.** Use one IOS writer, one PPC reader and
fixed single-publication slots keyed by run tag, epoch and increasing sequence.
Keep the commit word on its own aligned 32-byte line. Reserve slots for caller
entry, operation intent, phase results, first failure, verified full reply,
cleanup and terminal status. Include raw submit/completion results, handles,
service words, byte counts and elapsed time. Totals can summarise partial
progress alongside the required records. Never overwrite committed evidence.
Reserve slots for failure, exchange and final disposition independently of
progress capacity. If the next required event cannot be recorded, end the
attempt before another submission and latch trace exhaustion. Losing a required
event prevents a baseline pass.

- Start with invalid commit words. IOS invalidates before first use of
  PPC-prepared lines. For each record, write its payload, clean all touched
  lines to shared memory, order and complete the writes, then store the
  matching aligned commit sequence and clean/drain that line. Include the
  actual TID, tag, operation and elapsed ticks in the evidence chain. Keep
  PPC reader indices, heartbeat and local log on disjoint PPC-only lines.
- PPC invalidates the commit line and orders its load. On the expected
  sequence it invalidates and orders the payload loads, copies to PPC-private
  memory, then invalidates/rechecks commit and validates epoch, tag, lengths
  and sequence. Accept only a complete matching copy. Skip uncommitted slots.
  Detect gaps, stale epochs, conflicting sequences and exhaustion. A writer
  stopped mid-publication leaves earlier committed slots intact. No busy wait
  for an incomplete slot can hold the watchdog.
- Libogc flush includes a PPC synchronising barrier. Its invalidate alias
  performs cache-block invalidations. The reader needs an explicit ordering
  contract around its loads as well. StarStruck's ARM flush includes write
  drain and AHB maintenance, and its invalidate path checks access. Treat the
  target cache syscalls, compiler ordering, atomic aligned publication and
  bus visibility as things to verify. A C volatile field or an uncached PPC
  alias alone cannot make dirty ARM lines visible. [PPC cache API][pcache] ·
  [PPC line operations][plines] · [ARM cache implementation][kcache] · [WBFS precedent][dwbfs]

**Recommended evidence sink.** Start a dedicated PPC observer with its own
stack and private capture space before arming. Use a fixture-owned MEM1 video
framebuffer, with exclusive scanout/display ownership agreed before dispatch.
Have the observer render stable, legible records, including tag, stage, counts,
exact reply and cleanup fields, without invoking GX's rendering pipeline or
acquiring a launch-thread lock. Capture video continuously on a separate
local recorder through the stop. Record dispatch, raw DI return, GX-normalised
status and helper marker in separate PPC-owned evidence. Stop normal game
launch at the diagnostic boundary. GX normally flips two framebuffers, and
its StopGX blanks the display before the network marker. The fixture must
retain its own scanout through that blanking step or restore it before the
marker. Latch the marker at the helper call site and hold the final record
for external capture. Libogc's VI framebuffer and flush paths
program display state without DI or networking. Stock GUI ownership is a
conflict to resolve. [GX framebuffers and flip][gxvideo] · [VI update][pvideo] ·
[PPC thread creation][pthread] · [Cleanup order][gxclean]

A PPC snapshot remains readable while its thread, cache and memory are live.
RAM and the current screen have no post-recovery durability contract. Require
a readable off-console frame for each required record (or a later cumulative
display of it), plus an independently timed loss-of-progress record. If the
reader, display or whole PPC stalls, only previously captured evidence
survives. An external watchdog/observer must still be able to initiate the
owner-approved recovery. SD file I/O, another synchronous IOS request and the
network under test cannot be the sole stalled-IOS evidence sink.

**Existing diagnostics.** Stock DIP compiles out its formatted print calls.
MLOAD defaults to debug off, and its RAM-log case returns zero with the
buffer compiled out. Its service loop checks stealth/title access on open.
GX's `mload_init` uses a heap and retries synchronous opens. Its
`mload_get_log` sends a different command from d2x's get-log-buffer case and
expects a subsequent read. Even a matched, enabled implementation would use
further IOS IPC and needs a reader scheduled independently of the DI waiter.
MLOAD's Gecko path polls hardware, and GX's ordinary USB Gecko send uses an
unlimited retry setting and EXI locking. An external serial receiver could
preserve bytes, but enabling a logger or attaching a sink does not bound its
calls. The stock paths supply no equivalent independent progress record.
[DIP macro][ddebug] · [MLOAD dispatch][mdebug] · [Build setting][mconfig] ·
[MLOAD access][mopen] · [GX client][mclient] · [GX log command][mlog] ·
[Command definitions][mlogid] · [ARM Gecko][mgecko] · [PPC Gecko][pgecko]

## IPC-07 · Evidence and the link decision

**Hypothesis, verdict rules.** The direct caller sends exactly the 8 tag
bytes followed by the 16 challenge bytes on one connection. It assembles
all 28 reply bytes, checks the entire 24-byte echo and decodes the trailing
nonzero unsigned big-endian 32-bit connection ID. Only the peer assigns that
ID, on accept. Join the IOS record to that peer run's accept, both endpoints,
exact received/sent bytes and ID. No clock synchronisation with the peer is
needed. The existing peer is loopback-only. Independent wired controls and
a wired fixture retaining the same framing and logging are still required.
[Protocol and peer evidence](tcp_peer/README.md) · [Baseline verdicts](ios57-baseline-plan.md)

| Observation | Verdict |
| --- | --- |
| Actual caller verifies the full reply before its exchange deadline and the peer records agree | **Exchange verified.** Latch the bytes, ID and time before the first cleanup operation. |
| Above, with instance/build/tag attribution, bring-up in budget, safe handback for both PPC calls, and the matching synchronous DI return before the externally captured GX pre-helper marker | **Baseline pass.** Record raw IPC and wrapper status, since GX maps both raw 1 and raw 0 to zero. Report any cleanup failure separately. |
| Independently recorded intended entry before cleanup, a demonstrated network error, exchange deadline miss or bad reply, and verified listener/wired controls | **Attributable baseline failure.** Record the precise stage and evidence. An overdue watchdog with only pre-submit intent cannot identify an SO failure. |
| GX positively records skipped dispatch or a matching rejection before network-probe entry | **Probe never ran.** An arm receipt is insufficient evidence of network caller entry. |
| Missing entry without positive rejection, lost required record, failed controls, wrong instance, or uncertain DI return/marker ordering | **Indeterminate** for the unsupported claim. A verified exchange survives missing return evidence. |
| Cleanup fails, hangs or requires independent recovery | **Operationally unsuccessful fixture** if safe termination fails. Report this alongside the exchange and baseline verdicts. A hang or reset alone establishes no attributable networking failure. |

**Material cost added to FIT-07.** The stock limits are 1,484 trailing
executable bytes and 15,232 trailing static RAM bytes. The earlier
1,050–1,825 B estimate plus 30 B for comparison is a starting estimate for
logic with some of these contracts left open. There is no new byte estimate
for a complete executable. [Previous estimate and retained symbols](direct-dip-tcp-probe-fit.md)

| Charged where | Dependencies exposed by the ownership study |
| --- | --- |
| DIP executable | Arm admission/receipt, full-tuple matching, spent gate and rejection before media access. Pre-submit intent, wrap-safe absolute comparison, timer-generation validation, failed-admission ambiguity and exactly-once close accounting. Trace commit/barriers, first failure, exchange latch and final freeze. Charge two hook sites if retaining inner dispatch. Existing trap bodies do not pay for this control flow. |
| DIP static RAM | One aligned full reply line, static paths, controls, vectors, scratch and assembled frames from the previous budget. Add acquisition/close state, expected fixture identity, four distinct phase tokens, queue capacity proof and durable terminal flags. The five queue words fit in one 32-byte line. Include all alignment and padding in the map. |
| GX/shared RAM | Publication slots belong to the reserved I/O allocation, separate from DIP's private network storage. For example, 16 slots with a commit line and one payload line each already use 1,024 B. Multi-line records, especially the reply with identity/timestamps, need more. Count required fields and slot exhaustion before accepting a layout. Charge the observer copy, thread stack, scanout and off-console capture separately. |
| Stack and services | A needs no new ARM worker stack by design. The existing 4,096 B DIP startup stack gives no DI caller-stack margin. B adds a permanent ARM stack, queue/notification and synchronisation. A service adds a separate memory region, stack and request/reply storage. Static allocation says nothing about IOS service heap or actual stack high-water marks. |

**Next experimentally meaningful step.** Seek separate authorisation for a
minimal PC-only simulation with one arm, one outstanding request slot, one
acquisition ledger, one independent observer and an external recovery decision.
Model the hook choice, quarantine policy and watchdog bounds as explicit
assumptions or parameters. Hardware design decisions can follow this exercise.

Keep injected ground truth in the test driver. DI sees submit returns and
delivered replies, GX sees receipts, wrapper returns and any independently
correlated IPC completion, and the observer sees only committed records it
actually captures and its own clock. For example, inject successful RM
acquisition with a lost notification. The oracle knows what exists, while
DI must leave the acquisition unresolved. Model recovery initiation and
confirmed end of IOS and its relevant I/O as separate events.

Inject a blocked submit, descriptor exhaustion after RM success, lost delivery,
late open/receive/close, ambiguous close with number reuse, either queue order,
early and stale timer words, equality, bounded wrap and an unbounded clock gap.
Exercise ordinary, malformed and valid reads, including a valid duplicate after
malformed rejection. Interrupt trace publication and inject premature PPC return
at both arm and read, including an outstanding internal request. Check that
the fixture stops on ambiguous handback, records the first failure, and never
claims twice, closes twice or releases a possible loan. Score exchange
verification, baseline verdict and safe termination separately. Require actual
handback, synchronous return and external marker capture for a baseline pass.
Passing would establish consistency of project-owned transitions under the
modelled events only. Target IOS behaviour and libogc lifetime safety still
need independent evidence.

| Still unresolved | What would answer it, and where to stop |
| --- | --- |
| ABI and provenance | **Source:** check the selected GX link inputs against the pinned libogc, audit per-file terms, and inventory fixture-control command collisions in public paths. StarStruck kernel files carry GPLv2 notices, d2x has mixed per-file notices, and HAI/libogc include third-party client code. These are references for behaviour. Reuse needs a specific provenance decision. Private 57/5918 RM and dispatch internals end the source trail. [Source inventory](r0-01-r0-02-source-investigation.md) · [Reimplementation notice][kasync] |
| Which caller and which bytes | **PC:** exercise the chosen gate with altered spare words, wrong lengths, changed destination, stale arm and a lost receipt. **Hardware only:** demonstrate exact hook/TID, input lengths and bytes actually received, mapping of the dedicated output and absence of backing I/O. A PC mock can model both pass-through and copying. It cannot choose between them. |
| Deadlines, ownership and publication | **PC:** test the wrap boundary, stale tokens, delivery loss, blocked submit, torn/stale records, overflow and terminal handback with adversarial event ordering. **Hardware only:** measure tick rate, permission/authority of the actual caller, cache visibility while DI is held, observer heartbeat on the wired-disconnected fixture, timer/scheduler latency and survival of capture through recovery. A successful sample provides measured conditions, never a universal bound. |
| Size | **PC link, later:** after the policy and simulation decision, compare a matched stock control with a complete reachable probe, original ELF/map, LOAD extents, veneers and stack frames under the stock flags/regions. Include arm/rejection, all NCD/KD/SO and short-I/O paths, deadline, quarantine, publication and cleanup. Stop on overflow, stripped evidence paths, an unowned loan or an altered region. Actual DI stack margin and service allocations remain target measurements. |
| Recovery and handoff | **Owner/hardware gate:** identify a recovery route independent of stalled IOS, verify rollback for this console and prove the fixture inhibits game launch and captures evidence before termination. A drainer or service trades ownership boundaries without supplying that proof. |

R0 remains open. ADR 0003 covers only stock compilation. A modified DIP link
would need an explicit owner decision under ADR 0001, a reviewed update to the
stock-only scope in AGENTS.md and the feasibility plan, provenance review of
the proposed diff and separate runner approval. GX instrumentation, service
packaging and console execution have separate scopes. The hardware recovery
gate remains closed. [ADR 0001](../docs/decisions/0001-research-first.md) ·
[ADR 0003](../docs/decisions/0003-stock-dip-build-strategy.md) ·
[Agent instructions](../AGENTS.md) · [R0 plan](feasibility-plan.md)

[ddecl]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/syscalls.h#L32-L86
[kargs]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/interrupt/syscall.cpp#L32-L62
[brewkernel]: https://wiibrew.org/w/index.php?title=IOS/Kernel&oldid=118245
[dtrap]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/syscalls.s#L29-L86
[hdecl]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/include/syscalls.h#L40-L86
[htrap]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/asyscalls.s#L5-L54
[kasync]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/filedesc/calls_async.c#L1-L73
[preq]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/ipc.c#L193-L201
[psend]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/ipc.c#L277-L325
[ppcio]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/ipc.c#L1051-L1103
[kfd]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/filedesc/calls_inner.c#L33-L207
[kipc]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/messaging/ipc.c#L395-L446
[kqueue]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/messaging/messageQueue.c#L27-L295
[hlayout]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/include/ipc.h#L33-L103
[dlayout]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/ipc.h#L47-L104
[usbtoken]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/usb-module/module.h#L27-L36
[usbsubmit]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/usb-module/usb2.c#L195-L235
[usbdispatch]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/usb-module/main.c#L162-L249
[hdns]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L452-L480
[ktimer]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/scheduler/timer.c#L37-L377
[hsockclose]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L978-L993
[dright]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.c#L775-L790
[kvec]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/filedesc/calls_inner.c#L327-L439
[dwbfs]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/wbfs.c#L69-L98
[hrecv]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L901-L971
[ktable]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/interrupt/syscall.cpp#L65-L130
[reload]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/ios.c#L361-L404
[launch]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/ios.c#L247-L333
[kthread]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/scheduler/threads.c#L197-L311
[hloop]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/proxiios.cpp#L12-L63
[hstart]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/source/crt0.s#L7-L39
[gxread]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/usbloader/wdvd.c#L258-L277
[dhooktype]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.h#L103-L116
[dpatch]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/patches.c#L51-L145
[dcont]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/dip_calls.s#L40-L61
[dread]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.c#L221-L323
[gxfrag]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/usbloader/wdvd.c#L402-L425
[dfrag]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.c#L525-L557
[douter]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.c#L675-L763
[gxboot]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/usbloader/GameBooter.cpp#L554-L579
[gxclean]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/sys.cpp#L86-L131
[gxnet]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/network/networkops.cpp#L79-L87
[ppcwait]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/ipc.c#L701-L719
[ppcreply]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/ipc.c#L330-L389
[psleep]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/lwpcompat/lwpc_queue.c#L7-L42
[psched]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/tuxedo/thread.c#L245-L258
[gxmain]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/main.cpp#L34-L46
[gxalloc]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/memory/mem2.cpp#L35-L79
[gxarena]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/memory/mem2alloc.cpp#L17-L117
[gxblock]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/memory/mem2alloc.hpp#L27-L36
[pmap]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/gc/tuxedo/mm.h#L5-L38
[pheap]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/ipc.c#L721-L803
[pcache]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/gc/ogc/cache.h#L109-L138
[plines]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/tuxedo/cache.c#L8-L30
[kcache]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/memory/memory.c#L123-L178
[gxvideo]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/video.cpp#L116-L208
[pvideo]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/video.c#L2738-L2784
[pthread]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/lwpcompat/lwpc_thread.c#L15-L51
[ddebug]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/dip_calls.h#L26-L34
[mdebug]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/main.c#L40-L179
[mconfig]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/debug.h#L29-L40
[mopen]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/main.c#L304-L344
[minit]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/main.c#L202-L262
[mclient]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/mload/mload.c#L27-L60
[mlog]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/mload/mload.c#L402-L415
[mlogid]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/mload/mload.h#L40-L57
[mgecko]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/gecko.c#L32-L154
[pgecko]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/usbgecko.c#L12-L203
[brewcall]: https://wiibrew.org/w/index.php?title=IOS/Syscalls&oldid=121675
[brewtime]: https://wiibrew.org/w/index.php?title=Hardware/Starlet_Timer&oldid=46308
