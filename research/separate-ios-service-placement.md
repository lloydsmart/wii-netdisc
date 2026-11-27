# Can a separate IOS service own the TCP diagnostic?

**R0-02, R0-03, R0-05 and R0-06 · 27 November 2026 · original Wii, IOS57 v5918.**

**Investigate a separately linked worker started by d2x MLOAD. Test the DIP
adapter's size first.** MLOAD already declares storage for loadable code and
can start a thread with an explicit entry and stack. A worker with its own
resource-manager queue could serve DIP without blocking MLOAD's dispatch
loop. The decisive qualification is ownership of that storage. MLOAD advertises
its entire loading area to clients and supplies no exclusive reservation for
this worker. A permanent service placement, a distinct PID and network access
all remain unverified. [MLOAD storage][mlstart] · [Loader][elf] · [MLOAD dispatch][ml]

An additional installed module is also credible at the content and startup
level. Extending FAT has an existing DIP client and a worker-thread precedent,
but competes with the filesystem for tightly budgeted RAM. All three need the
same small adapter. The previous *non-network* object and gate already total
1,790 relocatable executable bytes against 1,484 linked bytes of headroom.
This justifies an adapter-only link before investing in a service build.
There is enough evidence for a **proposed ADR 0006 on that experiment**.
Selecting a runtime architecture would require further evidence.
[Measured sizing result][size] · [FAT startup][fat] · [Installer][install]

## Module selection and loading

**Source-verified.** The original-Wii entry in `data/ciosmaps.xml` declares
25 contents including six custom modules. The other 19 entries describe base
contents, including edits to base components. The base map and MLOAD startup
agree on a fixed IRQ entry offset, so moving MLOAD text would affect the base
patch. [Base selection][map] · [MLOAD startup][mlstart]

`maked2x.sh` builds cios-lib and the module targets,
associates each converted ELF with a named module file
and generates separate Wii and vWii maps. USBS is among the build outputs.
The 57/5918 Wii map selects EHCI. Each of the six selected components has an
executable entry, including the three whose ongoing function is to patch
existing handlers. [Base selection][map] · [Build and naming][make]

| Content in the map | Startup and subsequent execution |
| --- | --- |
| MLOAD, 0x1d | Detects base components, initialises patches, heap and timer, registers `/dev/mload`, then serves an eight-word queue. Its loader commands are distinct from IOS loading this module at startup. [Detection][detect] · [Initialisation and loop][ml] |
| FAT, 0x1e | Standalone filesystem service. Starts the LED worker, initialises the FAT heap and timer, registers `fat` and `$` on one 32-word queue, and dispatches file and control requests. [FAT main][fat] · [LED worker][led] |
| EHCI, 0x1f | Controller/storage service. Initialises its own heap, timer and controller. Registers the USB service and SDHC service on the same queue and services a watchdog. Its controller/port ownership matters to a wired LAN adapter. [EHCI main][emain] · [Service loop][eloop] · [Wired lifecycle][life] |
| DIPP, 0x20 | Plugin startup calls `IOS_InitSystem` with `Patch_DipModule` and returns. The base-specific patch connects drive init, ioctl and command handlers to DIP code. Ordinary requests can resume base DI. The thread entering the outer ioctl is the one relevant to the diagnostic. [DIP main][dmain] · [Patch selection][dpatch] · [Dispatch][outer] |
| ES, 0x21 | Plugin startup supplies `Patch_EsModule` for the detected base ES. The hooked ES path handles, among other things, reload redirection and saved configuration. Base ES still participates in title launch. [ES main][esmain] · [ES patches][espatch] · [Reload investigation][life] |
| FFSP, 0x22 | Startup calls `IOP_Init` and supplies both `Patch_FfsModule` and `Patch_IopModule`. It changes existing filesystem dispatch and open-path handling, including title-dependent FAT access. [FFSP main][ffmain] · [Patch selection][ffpatch] · [Open policy][iop] |

**Installer boundary.** In the pinned public installer, `getCiosMaps` parses
the group/base/version records, reads their counts and resolves named modules through
`getCiosModule` (including external module files). `patchmii` adds their
contents. `addModule` sets the new content record's ID, index, size and hash
and increments the title metadata (TMD) count. The unsigned TMD position from
`-1` takes the append path. EHCI alone requests position 2, which moves the
previous occupant to the end. This reorders a record while retaining its
content. Neither the content ID nor that table position identifies the process,
its rights or a launch time. This installer is a comparator for the map format.
The actual stock IOS title loader and its scheduling order are outside the
inspected d2x tree. [Parser and module lookup][install] · [Field type][insttype] ·
[Content loop][addloop] · [TMD update][add]

## Memory and execution contexts

The following are linker **origin + capacity**, in hexadecimal bytes, for
executable and data/BSS regions. Each cited module directory contains
`link.ld` and `start.s`. In these scripts the execution/data virtual origins
match their specified physical load origins. The original DIP ELF independently
confirms both addresses for its two LOADs. The zero-origin table is metadata.
The linker bounds do not allocate physical pages or describe all the other IOS
contents, aliases, cache attributes or accessible domains. [Stock ELF][stock]

| Component | Executable VMA + length | Writable VMA + length | Startup priority / stack bytes |
| --- | --- | --- | --- |
| [MLOAD][mldir] | 0x136d0000 + 0x2000 | 0x136d2000 + 0x9000, plus loading area below | 0x79 / 0x2000, separate 0x900 SWI stack |
| [EHCI][edir] | 0x13780000 + 0x5000 | 0x13785000 + 0x24000 | 0x48 / 0x3000 |
| [FAT][fdir] | 0x137b5000 + 0x5000 | 0x137ba000 + 0x23000 | 0x62 / 0x3000 |
| [DIPP][ddir] | 0x13800000 + 0x2000 | 0x13802000 + 0x40000 | 0x48 / 0x1000 |
| [FFSP][ffdir] | 0x13843000 + 0x3000 | 0x13846000 + 0x3000 | 0x48 / 0x1000 |
| [ES plugin][esdir] | 0x13849000 + 0x2000 | 0x1384b000 + 0x4000 | 0x48 / 0x1000 |

The startup records contain the tag 0x0b with `ios_thread_arg = 4` in
**all six**, then entry, priority, stack size and stack pointer. The stack
storage is reserved in the module image. The build links big-endian ARM
ELFs and `stripios` converts the table segment into metadata including a
NOTE and preserves loadable segments with IOS flags. StarStruck's
`LaunchModule` illustrates what a loader can do with these fields. It maps
LOADs with separate physical and virtual addresses, rounds memory size to
pages, reads file data, zeroes the tail, applies access/domain flags and
uses NOTE entries to create threads and assign a process ID. Its
`CreateThread` for an ordinary child inherits the creator's process and
limits priority. Separate module files can therefore describe distinct
threads without establishing distinct security principals. The target PID,
rights and stack available in a hooked base thread remain open. [Startup example][dstart] ·
[Converter][strip] · [Module loader][launch] · [Child creation][threads]

MLOAD has the clearest public **reservation**, with the least clear
**exclusivity**. Its assembly emits 0x80000 bytes for `exe_mem` in
`.exe_mem`, linked at 0x13700000 up to the EHCI origin, exclusive.
Its special strip recipe can reduce that segment's file payload to one byte
while preserving its memory size. `MLOAD_GET_LOAD_BASE` returns the entire
base and length. `Elf_Load` uses the incoming virtual destinations, clears
memory extents and copies file extents. It performs no suballocation,
relocation or lifetime negotiation. Its singleton load metadata feeds
`Elf_Run`, which creates and continues a thread. A returned thread ID alone
does not confirm readiness. The region is declared writable. Instruction
visibility, execution permission, address aliases and isolation from later
loads/writes need separate evidence. As a concrete competing convention,
EHCI's optional `MEM_PRINT` logger names addresses inside this area. Its
source switch is off by default. [MLOAD layout][mllink] · [Backing symbol][mlstart] ·
[Strip recipe][mlmake] · [Converter][strip] · [Load and run][elf] · [Conditional EHCI logger][elog]

FAT illustrates the cost of using an existing host. Of 143,360 writable
linker bytes, its declared 114,688-byte heap and 12,288-byte startup stack
plus the LED worker's 1,024-byte stack leave at most 15,360 bytes before
other stock state. The FATFS sector window alone accounts for another 4,096
bytes. The old network completion pool and full records/checks together would
need 13,568 bytes, before a new worker stack. Reusing all those arrays inside
FAT's static region is already inconsistent with that inventory. Splitting
trace storage would require an owned location and publication budget for each
writer. FAT heap allocations for existing files and queues also compete at
runtime. EHCI and MLOAD each initialise a 16 KiB heap from a static array.
None of these heap declarations measures spare heap. DIP can call base
`DI_Alloc` with unknown capacity. [FAT heap][fat] · [LED stack][led] ·
[FATFS instance][fatfs] · [Sector window][fatwin] · [Sector size][fatcfg] ·
[Probe allocations][probe] · [EHCI heap][emain] · [MLOAD heap][ml] · [DI allocator][dpatch]

## Placement comparison

| Candidate | Incorporation, memory and identity | Stock functionality, scheduling and cost of proof |
| --- | --- | --- |
| Additional installed module | New module target and startup NOTE, named content, revised counts and reviewed TMD order. Fakemote documents adding a seventh content module for this same base. Its own fixed link and startup argument belong to its design. A network service still needs justified physical backing, mapping, identity, stack, static storage and any heap, then registration before the first client open. [Fakemote map example][fake] · [Its linker script][fakelink] · [Its startup][fakestart] | Avoids using a storage dispatch thread and could start again with the selected cIOS. Needs a valid namespace and permissions at both IPC boundaries. It has the highest integration burden because base occupants, page/domain and thread limits, installer compatibility and startup remain open. No source identifies a PID or private region available for this service. |
| Extend an existing service, principally FAT | Replace the custom FAT build in its existing map slot. A separate worker and dedicated registered queue inside that image could leave `fat` and `$` on their existing loop. FAT's LED worker demonstrates thread creation, private stack and explicit start. Existing FAT access policy does not authorise a new name or network opens. [FAT][fat] · [Worker][led] · [Open policy][iop] | Least change to title configuration. Requires paired stock/modified host measurements, capacity for both queues and a worker stack, independent readiness and proof that worker failure leaves FAT operational. A network wait on the sole FAT loop could stall NAND emulation or a dependent filesystem request. EHCI has a stronger potential cycle through wired USB and its storage/watchdog loop. ES/FFSP patch critical launch/filesystem paths. They offer weaker hosts. |
| Separately linked worker under MLOAD | Separate image, explicit load/start by an authorised bootstrap for the current instance, own registered endpoint, RM queue, network queue, trace and stack. The loader calls ordinary thread creation and ignores the NOTE identity field. Inherited process identity is a hypothesis for IOS57. Requires a reviewed exclusive allocation for *all* LOADs, BSS and stack, serialised load/start and release policy. No new TMD content for a dynamically supplied image. [MLOAD dispatch][ml] · [ELF loader][elf] · [GX module selection][gxmodules] | Preferred research candidate. Gives the service a place to run without putting network waits in DI, MLOAD, FAT or EHCI dispatch. Existing GX conditionally loads other modules for particular IOS families/versions. It supplies no general bootstrap for this worker. A pre-title fixture bootstrap needs a readiness receipt and a coexistence argument for every permitted client, including recovery/reload. Reserving part of the published area permanently could break existing loaders. |

With stealth mode enabled (the default), MLOAD rejects a new open with
`IPC_ENOENT` when the running-title flag is set. MLOAD can change stealth
mode at runtime. The open handler calls `Stealth_CheckRunningTitle`, whose
query returns `stealth_mode && running_title`. This open-time check establishes
neither revocation nor exclusion of previously opened handles. Exclusive
ownership of the loading area still requires separate evidence. [Default][mldefault] ·
[Mode setting][mlsetting] · [Open handler][mlopen] · [Title check][mlcheck] · [Query result][mlquery]

All candidates pay for the DIP client described below. Any host needs a free
RM name and table slot, thread and queue resources, mapping for the mailbox,
and permission to use NCD, KD and SO from the worker's actual context. An
installed service or FAT extension would need fresh registration on each
actual IOS reload. A dynamic worker also needs its image and bootstrap again.
Same-slot reload invalidates the old handle/instance binding. An unmodified
destination IOS lacks the custom endpoint. Across same-IOS GX cleanup and
game network startup/cleanup, all rely on the same wired stack. The
pre-cleanup diagnostic can establish neither continued access nor coexistence.
The [lifecycle study][life] specifies the later distinguishing observations.

## What an ARM service call establishes

**d2x storage path.** `WBFS_Open` retains the process fd for USB or SD and
selects the disc by ioctlv. `WBFS_Read` cleans aligned controls and vectors,
submits the offset/length and one destination synchronously, and synchronises
the destination after success. For USB, `EHCI_Loop` receives the request,
`__EHCI_Ioctlv` dispatches the WBFS read and flushes the output ranges named by the vectors. The loop
acknowledges the original message. `FAT_Mount` independently demonstrates
open/control/close against FAT. `DI_EmulateInitDrive` marks its executing TID
for FAT access. FFSP's open hook checks that right for FAT paths when a title
runs. Neither the grant nor EHCI's open policy covers a diagnostic service or
the network stack. [DIP storage client][wbfs] · [EHCI dispatch][eloop] ·
[FAT client][fatclient] · [Drive init][outer] · [FFSP policy][iop]

**HAI-Riivolution.** Its launcher embeds file and DIP ELFs. `Haxx_Init`
requests the file module first in its own HAI environment. File startup
declares argument 18, priority 0x48 and an 8 KiB stack. Its `main`
initialises a 160 KiB heap and constructs `Filesystem`. The base
`Module` constructor sets priority, creates an eight-entry queue and
registers the name `file`. `Loop` receives, dispatches and acknowledges the
original message unless the handler suppresses acknowledgement. Idle
timer messages use the queue too. Registration is requested without a
checked success receipt. [Launcher build][haibuild] · [Launcher order][haiinit] ·
[Startup][haistart] · [Main][haimain] · [Name][hainame] · [Dispatch][hailoop]

`DIP::ReadFile` opens or reuses a file fd, seeks and reads. On ARM,
`File_Open` constructs a service-prefixed path and `File_Read` calls
`os_read` then synchronises the destination. The service resolves a path
on open, uses its internal file handle in `Filesystem::HandleRead`,
dispatches to the mounted handler and cleans output before reply. For a RiiFS
mount, `RiiHandler::Mount` calls ARM `net_init`, obtains and connects its
own TCP socket, `Read` exchanges data and `Unmount` closes it. The NCD,
SO and KD opens run in this service code. Its checks and retry policy differ
from the accepted diagnostic. These paths demonstrate a synchronous call chain
with a separately scheduled network owner. They do not establish bounded
return, authenticated DI identity, transferable permissions or a usable
d2x memory placement. HAI's own link declares regions inside the same numeric
range as d2x's MLOAD area. [DI client][haidi] · [ARM file calls][haifile] ·
[Service handlers][haihandlers] · [RiiFS][haiio] · [Network startup][hainet] · [HAI layout][hailink]

**Kernel comparator.** In StarStruck, registration checks path length,
duplicate names, remaining entries and queue ownership by PID. Open matches
a registered prefix, passes process UID/GID and converts an RM-local handle
to a caller-process fd. Subsequent ioctls carry the RM-local handle and
buffer extents. Their public arguments supply no original DI TID or GX
identity. HAI names UID/GID in the open layout where d2x labels a word
`resultfd`. They cannot be used interchangeably as caller authentication.
StarStruck checks buffer access for caller and RM and passes pointers.
Libogc's PPC `IOS_Ioctl` converts the input and output to physical addresses
and flushes both ranges. HAI's ARM file client defines its address conversion
as the identity. The proposed adapter therefore needs independently validated
ARM-visible mailbox extents and cache-line ownership at the new boundary.
A valid GX allocation alone establishes neither. [Registration][rm] ·
[Open and ioctl][fd] · [HAI IPC layout][haiipc] · [d2x IPC layout][ipc] ·
[Libogc PPC handoff][ppcipc] · [HAI ARM file client][haifile]

Synchronous control holds the submitting caller until reply. In StarStruck
even async open can wait inside submission for the RM, allocate an fd and
then lose its notification. Descriptor-table exhaustion can follow RM success.
Other async calls can block sending to a full RM queue. `ResourceReply`
uses the original kernel message and sends the caller's reply-object address
to its callback queue. A full callback queue can lose delivery after the
producer acted. Async close can release the fd-table slot before its result is
observed. Another consumer must never infer ownership from the number alone.
These are concrete counterexamples to inferring boundedness or cancellation
from a syscall name. Which apply on IOS57 is unresolved. [Async calls][async] ·
[Descriptor operations][fd] · [Dispatch and reply][reply] · [Queues][queues]

## One admitted request across two IPC boundaries

**Proposed diagnostic contract.** GX still calls DI synchronously. DIP is the
client of one service transaction. The service is the client of up to 64
network submissions. Each boundary has its own owners, completion addresses,
clock evidence and release conditions. Use the existing synthetic TCP peer.
No target device name, ioctl number, PID or load address is assigned here.
[Accepted admission and evidence rules][adr5] · [Synthetic wire contract][wire]

1. **Before arming.** Establish fresh IOS, DIP, service and GX build/instance
   identities, the exclusive allocations in each participant's address domain,
   and independent observation. The worker creates its own RM queue, registers
   a fixture endpoint and publishes checked readiness. A thread-create return,
   a delay or a successful open against an unverified name is insufficient.
   The fixture must bind the permitted open/session and mailbox to the intended
   DI context, exclude competing openers and overlapping registered prefixes,
   and check the service build independently. A tag, fd, self-reported TID or
   matching path can correlate evidence but cannot authenticate an opener.
   If target credentials or exclusive mapped access cannot support that
   binding, caller attribution and permission remain unresolved.
2. **Arm and classify locally.** Retain the outer `DI_EmulateIoctl` gate,
   trusted arm/read reservations, complete bound tuple and live exclusive
   output. GX dispatches only after checking the arm receipt, safe PPC
   handback and preservation of at least one allocation identity. DIP keeps
   the replay rule and atomic one-use claim. The existing arm selector is a
   PC fixture choice whose collision with opaque base DI remains unresolved.
   After arm, with neither reserved identity, resume the stock switch with
   its original arguments and status, without touching foreign input or opening
   a service. A recognisable malformed read spends the claim and rejects
   before media or IPC. Reject recognisable duplicates, including after
   failure. On a valid claim record hook, actual DI TID/fd, build, tag and
   sequence **before** the first service trap. Never hold the admission gate
   while waiting. [Reviewed gate and handback][gate] · [Integration point][hook]
3. **Open once and submit once.** From that hook context issue a private
   async open, accept fd zero on a uniquely matched successful reply, retain
   the fd for this instance/claim only. Issue one fixed-size async ioctl, then at
   most one eligible close on the same acquisition. No retry or reopening.
   This gives DIP a separate budget of **three** submissions, one outstanding
   at a time, with distinct full-line completions and capacity reserved for
   close and terminal evidence. DIP owns its queue, path, request, response
   and timers. Publish intent before each trap, distinguish not-issued,
   submission return and completion. Check the clock immediately before issue
   and at consumption. A lost open reply can leave both a service-side session
   and an unknown DIP-side fd.
4. **Copy across the boundary.** Use fixed, pointer-free, versioned big-endian
   messages in whole-line, disjoint, persistent IPC buffers. Request fields
   bind operation/length, instance and builds, claim serial, DI TID/fd,
   read tuple, local/peer IPv4 and port, eight-byte tag, 16-byte challenge
   and deadline epoch. The service first checks the open session, operation,
   exact extents, alignment, non-overlap and one-use state against its independent
   provision. It synchronises validated input lines, copies a private snapshot
   and checks its reserved fields and entire bound tuple before dispatch.
   It records its own executing TID and independently established process
   context alongside the asserted DI identity. Reject an unexpected
   request without contacting the network. The reply binds the same run and
   serial, service instance/build, exact verified length and bytes, phase
   times, first failure, terminal sequence and cleanup/quarantine disposition.
   A failure reply can explicitly mark the byte evidence absent. It cannot
   fabricate a successful exchange. No pointer to a PPC buffer, DI stack or
   transport descriptor crosses the interface.
5. **Execute and reply.** On its own stack the worker opens NCD/SO/KD, owns
   every network fd and the SO socket from acquisition, and services its
   private completion queue. Retain wired link, KD service result, SO
   readiness, one connect, partial sends/receives and eligible closes. Latch
   the verified 28 bytes and peer-assigned nonzero big-endian ID before
   cleanup. Keep the original inbound RM message live until one final reply
   after cleanup or terminal quarantine. The service publishes and cleans its
   bounded response, drops its access to the caller buffers, then acknowledges
   that original message once. Even after an inner timeout it can report
   failure only if every possible late network producer points exclusively
   to service-owned storage. A blocked service may never reach the ack.
6. **Consume and return.** At each boundary the producer cleans initialised
   input, vectors and payload before handoff. Relinquish output lines free
   of dirty private bytes. The sole consumer validates address domain, bounds,
   alignment and non-aliasing before cache operations. On a unique matching
   completion, establish producer retirement, synchronise completion and output
   before reading, and copy only validated bytes. DIP matches the expected
   completion address and reply command, raw result, session/serial, build,
   tag, length, full echo and nonzero ID against its private snapshot. Only
   a completed operation with a defined output can supply reply bytes. Check
   for stale, duplicate or conflicting words and final time before accepting.
   DIP alone writes the live PPC output, cleans it, records status/terminal
   sequence, freezes its trace and returns via the original DI caller. Service
   ack, callback delivery, DIP terminal intent and actual PPC handback are
   four distinct events. [Cache and reply ownership][ownership] ·
   [Previous receive and publication contract][probe]

**Deadlines and evidence refinement.** Keep 30 seconds for bring-up, five for
one connect, one absolute five-second exchange through verification, and one
five-second cleanup window from verification or abandonment. Preserve equality
as late, bounded wrap checks and the independent observer's 35-second
checkpoint and 55-second hard cutoff from before arm. For sizing, propose a
separate absolute outer budget of 50 seconds from before service open through
eligible close, clipped to the remaining observer lease. Queue wait,
registration delay after readiness, handoff and cleanup consume time. Neither
side can renew a budget when copying or retrying. Attribute times to their
actual clock and writer. Correlating ticks across contexts requires a checked
common epoch, rate, visibility and maximum gap. [Deadline contract][adr5]

The service is now the **network caller**. Its timely full verification and
matching peer transcript establish a service exchange. DIP must independently
check the returned bytes and identity. Record its verification time against
the original exchange deadline as well as the outer deadline. With a single
final reply, service cleanup can delay DIP verification past the exchange
deadline. Preserve the earlier service result but withhold an end-to-end
timely pass in that case. This measures the worker's network authority.
A cleanup or outer-close failure stays visible in its own ledger. A baseline
pass also needs timely readiness, both safe PPC handbacks and
independent observation of the **actual synchronous DI return before the
actual GX pre-cleanup marker**. Correlate both writers' committed sequences
with peer accept/endpoints and GX evidence. Missing attribution, clock or
return ordering yields an indeterminate claim. Positively skipped dispatch,
local/service rejection and outer IPC failure each have their own evidence.
Attribute a network failure only with confirmed service entry, the specific
error, missed deadline or bad peer reply, and independently healthy listener
and wired controls. Score safe termination separately.
[Verdict definitions][adr4] · [Original observer contract][ownership]

**Late work and scheduling.** A timeout or malformed reply latches the first
failure. With uncertain submission, conflicting words, lost delivery or
ambiguous close, pin the affected mailbox, RM message if still held, queue,
paths, callbacks, fd/session and dependent resources. Never guess a handle,
reuse the lines, rearm, or fall back to media for a claimed read. A late
uniquely attributable result may refine ownership only. Preserve distinct
outer and inner dispositions, including “outer reply retired, inner receive
still owns scratch” and “worker finished, DIP never received its reply”.
DIP may hand back a diagnostic failure if it can sever every live PPC pointer
and freeze publication while retaining its own outstanding loans. Otherwise
the caller stays pending. GX cannot advance on an ambiguous handback. A
watchdog bounds the decision to abandon. Recovery requires independent
confirmation that the old instance **and relevant I/O** ended. [Recovery and handback][ownership]

The wait chain is GX → DI → worker → network RM → wired stack. Put neither
DI locks nor the FAT, EHCI or MLOAD dispatch queue on the reverse path. The
worker must not call back into the held DI request, wait for GX launch, or
require its own occupied RM queue to deliver a network completion. Give each
queue one consumer from creation. Use a bounded scan with a genuine blocking
wake/timer or independently justified scheduling progress. Repeated yields by
a higher-priority ready thread can starve a lower-priority worker. A stalled
trap, full queue, dropped timer or a priority inversion can still prevent
return. Preserve independent pre-trap records from *both* contexts and
observer evidence outside this chain. [Queue waits][queues] ·
[Scheduler][threads] · [Reply delivery][reply]

## DIP cost and existing code reuse

**Experimentally verified on PC.** The matched stock executable occupies 6,708
of 8,192 bytes. Static RAM has 15,232 trailing bytes. The full direct hook
attempted 12,128 executable bytes, 5,420 above stock and 3,936 over capacity.
There was no final modified ELF or measured modified RAM span. Only that
complete implementation has a no-fit result. [Measurement and inputs][size]

| Where the work belongs | Reuse and incremental cost |
| --- | --- |
| DIP only | Keep reservation validation, snapshot, receipt, one-use classification, rejection, actual hook/TID publication, stock continuation and final PPC handoff from `admit_arm`, `nd_hook` and `nd_take`. Moving classification to the service would put ordinary traffic through IPC and could expose foreign cache lines. Moving the only entry/return writer would lose evidence precisely when an outer trap stalls. [Gate][gate] · [One-use primitive][once] |
| DIP IPC client | New open/ioctl/close state, original-acquisition tracking, deadline, queue scan, reply/session checks, copies and terminal quarantine. The stock ELF retains the 440-byte assembly syscall block, including async traps, queues, timers, thread ID and cache sync. It retains memcpy/memset, but discarded memcmp. Reusing bodies still costs callers, literals, interworking, alignment and any newly retained library code. [Stock retention and symbol sizes][fit] |
| Service | Move `bringup`, `prepare`, `transfer`, `receive_handoff`, `verify_reply`, acquisition ledger and eligible cleanup substantially as written. Keep 64 unique 32-byte network completions, one active loan, close reserves, bounded queue scans, absolute deadlines, exact fragment copies and terminal quarantine. Replace the global arm, hook-TID attribution, lease and publication dependencies with a validated request and service-owned state. Never delegate a DI-owned socket after timeout. [Network implementation][net] |
| Each writer and external observer | Move the operation-by-operation trace, exact wire ranges and network ledgers to the worker. Keep a smaller independent DIP journal for arm/rejection, both IPC handoffs, first failure and return. Each writer needs its own immutable records, capacity reserve and commit line, payload-before-commit ordering, reader-owned lease and sequence. Bind traces by instance, tag and claim. A blocked DIP caller leaves its own last committed record. Formatting, capture and peer comparison remain external. [Record layout and publication][probe] |

**Incremental executable assessment (hypothesis).** `netdisc.o` contributed
1,774 bytes of relocatable executable sections, `netdisc_net.o` 3,268 and
`netdisc_gate.o` 16. Removing only the network object leaves a **1,790-byte
pre-link comparator**, already 306 bytes above the stock margin before adding
the outer IPC client. No object has an independently attributed linked delta.
In particular the 362-byte difference between whole-link growth and the
5,058-byte relocatable sum cannot be booked as savings. [Object evidence][size]

The break-even estimate is **1,790 − bytes removed from the old local
paths + new client bytes + link effects ≤ 1,484**. For scale, the measured
stock `WBFS_Read` body is 100 bytes and `__usbstorage_Read_Write` is 156.
Allow two WBFS-sized bodies for marshalling and reply/handback, and one to
three storage-helper-sized bodies for the common submission, wait, deadline
and failure path. That gives roughly **360–670 new executable bytes** before
net changes to the writer and linker costs. On those assumptions the
unchanged local objects plus new work would be about **2,150–2,460 bytes**.
Fitting would require removing roughly **660–980 bytes** from the old local
paths at neutral link overhead. These estimates use stock function sizes as
analogies. Actual text could fall outside this range. Moving large trace
*arrays* mostly saves RAM.
Even the local writer, arm checks and terminal evidence still need reachable
code. There is no measured basis to claim those text savings. [Stock function sizes][fit]

**RAM and stack (hypothesis).** DIP could use three distinct 32-byte
completion lines (96 bytes), an eight-word queue (32), a dedicated path line
(32), and, illustratively, one 128-byte request and one 128-byte response
(256). That is **416 bytes** before the arm state, bindings, timer, trace,
lease, padding and handoff. A sample 32-record DIP journal using the current
record/check format adds 1,152 bytes plus two 32-byte publication/lease
lines. Verify its worst-case capacity, including failure and close, before
adopting that count. Such a layout makes static RAM less pressing than text.
The worker separately pays for code, stack, queues, network pool, transfer
buffers and trace. The old 320-record trace and checks alone use 11,520
bytes. Keep scratch/mailboxes static for this one shot and explicitly
account for any heap used during registration or by RMs. The DI startup
stack and a worker stack cannot pay for frames on the hooked caller.
[Static declarations][probe] · [DIP baseline][stock]

**Reusable tests.** Keep the existing native tests for untouched foreign
pages, split-line malformed inputs, one-use admission, last pre-issue
deadline, abandonment epoch, acquisition and cleanup. Keep the synthetic
TCP peer's fragmented exchanges and the deterministic fixture's observer
and PPC handback cases. They cover distinct interfaces. For a future adapter,
exercise a wrong opener/build or stale instance, fd-number reuse after reload,
a full submission queue, a lost ack after service success, a duplicate or
malformed response, a stalled worker while DI times out, a late service
write confined to its reserved mailbox, a clean
outer reply with inner work still live, and a prompt worker reply followed by
a blocked DI close. Drive both queue delivery orders and a never-scheduled
worker. Assert stock forwarding, absence of borrowed PPC pointers, one-use
state, independent verdicts and untouched storage on late completion. A host
fixture can test the chosen transitions. It cannot establish IOS scheduling
or cache semantics. [Native cases][native] · [Fixture results][sim]

## Proposed ADR 0006 and next experiment

**Propose one PC-only matched stock/adapter sizing experiment for owner
review.** All placements can fail at the same DI hook. An adapter link can
answer that question without inventing a service address, implementing the
server, or reserving scarce target memory. A service-only link cannot answer
it. A combined link adds a second variable, while a general IPC simulation
cannot determine executable size. Use only the few injected outcomes needed
to keep the real adapter paths testable. The TCP diagnostic remains the
specified eventual service workload.

1. Review and freeze the outer contract above, including the two timing
   observations, a complete field/size layout, trace capacity, failure
   outcomes and synthetic registration/caller-binding assumptions. ADR 0006
   must require DIP to commit its own reply-verification evidence before
   issuing the outer close, so the observer can see the result if close stalls. Preserve
   the old direct probe and measurements. If caller identity, lifetime or
   actual-return evidence cannot be represented without weakening a required
   predicate, stop before authorising a link.
2. After independent review, merge and separate owner approval of the exact
   implementation commit, use the established ephemeral PC sizing procedure
   with fresh extractions, matched r32 inputs, flags and unchanged DIP linker
   regions. One stock DIP and one complete adapter only. The service response
   is a variable fixture input. The ARM client must include real open/control/
   close submission, wait, cache, validation, failure and publication paths.
   A constant reply or a host mock replacing a required client trap
   invalidates the measurement. [Prior execution boundaries][adr5]
3. Require stock ELF identity and reproduced 6,708-byte executable and
   246,912-byte RAM spans. Reconcile original ELFs, maps and LOAD
   VMA/LMA, file/memory ends, BSS and alignment. The modified executable
   must end at or below 0x13802000 and static RAM at or below 0x13842000.
   Report deltas, retained stock routes, new functions/helpers, veneers,
   every mailbox/queue/trace and visible stack frames. Verify the complete
   path from ordinary forwarding and malformed claim through successful,
   blocked and quarantined outcomes. Preserve validated text evidence,
   input hashes, tool versions and corroborated partial maps on overflow.
4. Stop on a mismatched control, overflow, missing path, unexplained extent,
   unresolved material dependency or any need to change flags, regions or
   ordinary DI behaviour. An evidenced no-fit closes this adapter design.
   After a static pass, investigate whether the worker image, stack and
   writable state can occupy an exclusively owned part of MLOAD's advertised
   area while preserving existing clients and startup. That would need
   an accounting of loaders and aliases, a serialised
   bootstrap/readiness contract, provenance review and a separately approved
   service sizing task. If exclusivity cannot be justified, revisit the
   installed-module option. Do not infer an address from a gap.

**R0-05 boundary.** The project's probe is original GPL-3.0-only code.
DIP plugin bodies examined have GPL-3.0-or-later notices, the startup
assembly, MLOAD loader and FAT main carry GPL-2.0-or-later notices, and
FatFs has its own notice. HAI's network file has a three-condition notice.
StarStruck files cited carry GPLv2 notices. Use comparisons as interface
evidence. Review individual assembly, headers, libraries, installer/tool
sources and any linked runtime before code reuse or artifact redistribution.
The r32 toolchain and stock input hashes establish the control's identity.
Redistributing any new binary requires its own review. Keep outputs to
reviewed text evidence. No firmware, packaging, installation, upstream
changes, workflow dispatch or hardware execution form part of this research.
[Project source][gate] · [DIP notices][dmain] · [MLOAD notices][elf] ·
[FatFs notice][fatnotice] · [HAI notice][hainet] · [StarStruck notice][async]

## Claim ledger

| ID and level | Claim | Decision consequence or missing observation |
| --- | --- | --- |
| SP-01 · Source-verified, R0-03 | The six selected ELFs combine three live services with three plugin startup/patch paths. The installer can incorporate additional content. [Map][map] · [Installer][add] | Content order and metadata do not supply a new PID or an occupied-page inventory. |
| SP-02 · Source-verified, R0-03 | MLOAD declares a 512 KiB loading area and creates a worker from supplied image metadata. FAT already creates a second thread. [Loader][elf] · [Allocation][mlstart] · [FAT worker][led] | MLOAD has no per-client reservation in this path. FAT's existing storage competes with the trace and worker. |
| SP-03 · Source-verified, R0-02 | d2x issues ARM storage IPC. HAI's registered file service can perform socket work on behalf of its DI client. [Storage path][wbfs] · [RiiFS owner][haiio] | Shows a communication mechanism. Permission for each actual IOS57 caller remains open. |
| SP-04 · Source-verified comparator, R0-02/06 | StarStruck distinguishes process fd, RM handle, thread accounting and callback storage. Open/queue delivery can block or lose the observation. [Descriptor path][fd] · [Reply][reply] | Preserve two independent loan/ownership ledgers and watchdog evidence. |
| SP-05 · Experimentally verified on PC, R0-03 | Matched 6,708/8,192 executable bytes, 15,232 static bytes free. The direct probe overflowed by 3,936 bytes. [Experiment][size] | Only a modified adapter link can settle incremental fit. No service or target result. |
| SP-06 · Hypothesis, R0-03/06 | A one-shot copied request to a separately scheduled MLOAD worker could preserve stock DI routing and service-side TCP attribution. | Test adapter fit first. Require independent service admission, DI handback and GX ordering. |
| SP-07 · Unresolved target assumptions, R0-02/03 | Exclusive mapped physical backing, safe bootstrap/reload, actual PIDs/TIDs, free RM/queue slots, caller credentials, NCD/KD/SO authority and ETH readiness remain unknown. | A PC link cannot establish any of these. Loss after GX or game cleanup requires a separate lifecycle observation. |
| SP-08 · Unresolved target assumptions, R0-06 | Scheduler progress, bounded clock gaps, callback identity/retirement, cross-domain cache visibility, stack margins and independent end of I/O lack target evidence. | Withhold the affected verdict on missing evidence. The hardware recovery gate remains closed. |
| SP-09 · Source-verified notices / open review, R0-05 | The candidate hosts and comparators have different per-file notices and build inputs. [Earlier provenance review][provenance] | No redistribution decision or new toolchain authority follows. |

R0 remains open. Standard read-only NBD and raw ISO first remain the product
direction. GX and other frontends select and launch, the Wii runtime handles
disc semantics, the server publishes exports, and RetroMount performs
independent format transformation. [Feasibility plan](feasibility-plan.md)

## Primary sources and scope of inspection

Inspected public source text on 27 November 2026 against the following
immutable revisions. Each link identifies the inspected revision. PC
measurements come from the previously reviewed runs. The source inspection
used neither proprietary IOS contents nor console data.

| Source | Revision and role |
| --- | --- |
| [wiidev/d2x-cios][droot] | `33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7` · original-Wii map, module/link/load and storage sources |
| [larsenv/d2x-cios-installer][install] | `67b77efdfa1d859ad968b09281642361181ad569` · public installer source for XML and TMD semantics |
| [xerpi/fakemote][fake] | `ad985238dc0716c1f28826eef9b9366689914011` · independent extra-module example for 57/5918 |
| [ymweiss/HAI-Riivolution][haiinit] | `e67de6991ec24252acadd2c4b0918f21e83c2528` · separate file RM and ARM network client |
| [DacoTaco/StarStruck][launch] | `ec0508f1db187f97764e6c1ac4b0076c09ec77f4` · public kernel reimplementation, used as a comparator |
| [wiidev/usbloadergx][gxmodules] | `e25c4f3501ed957b7db73f79c51fdf00715ab2e2` · frontend module-selection conditions |
| [lloydsmart/wii-netdisc][size] | `797e719cf587e6e779728ff48b34ba2468627385` · reviewed measurements, original probe and fixture contracts |

[droot]: https://github.com/wiidev/d2x-cios/tree/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7
[map]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/data/ciosmaps.xml#L250-L302
[make]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/maked2x.sh#L20-L83
[mldir]: https://github.com/wiidev/d2x-cios/tree/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module
[edir]: https://github.com/wiidev/d2x-cios/tree/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/ehci-module
[fdir]: https://github.com/wiidev/d2x-cios/tree/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/fat-module
[ddir]: https://github.com/wiidev/d2x-cios/tree/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin
[ffdir]: https://github.com/wiidev/d2x-cios/tree/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/ffs-plugin
[esdir]: https://github.com/wiidev/d2x-cios/tree/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/es-plugin
[mlstart]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/start.s#L23-L140
[mllink]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/link.ld
[mlmake]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/Makefile#L12-L53
[mldefault]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/main.c#L50
[mlsetting]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/main.c#L180-L188
[mlopen]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/main.c#L313-L328
[mlcheck]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/stealth.c#L31-L43
[mlquery]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/swi.c#L153-L161
[ml]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/main.c
[elf]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/elf.c
[detect]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/detect.c
[fat]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/fat-module/main.c#L354-L567
[led]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/fat-module/led.c#L29-L105
[fatfs]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/fat-module/fat_wrapper.c#L38-L49
[fatwin]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/fat-module/ff.h#L76-L112
[fatcfg]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/fat-module/ffconf.h#L126-L138
[fatnotice]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/fat-module/ff.c#L1-L21
[emain]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/ehci-module/main.c
[eloop]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/ehci-module/loop.c
[elog]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/ehci-module/tinyehci/usbstorage.c#L98-L109
[dmain]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/main.c
[dpatch]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/patches.c#L25-L147
[dstart]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/start.s
[outer]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.c#L675-L790
[esmain]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/es-plugin/main.c
[espatch]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/es-plugin/patches.c#L47-L113
[ffmain]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/ffs-plugin/main.c
[ffpatch]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/ffs-plugin/patches.c
[iop]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/ffs-plugin/iop.c#L44-L149
[strip]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/stripios_src/main.cpp#L163-L300
[wbfs]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/wbfs.c#L30-L98
[fatclient]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/fat.c#L59-L99
[ipc]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/ipc.h#L47-L106
[install]: https://github.com/larsenv/d2x-cios-installer/blob/67b77efdfa1d859ad968b09281642361181ad569/sources/libios.c#L46-L321
[insttype]: https://github.com/larsenv/d2x-cios-installer/blob/67b77efdfa1d859ad968b09281642361181ad569/sources/libios.h
[addloop]: https://github.com/larsenv/d2x-cios-installer/blob/67b77efdfa1d859ad968b09281642361181ad569/sources/patchmii.c#L246-L275
[add]: https://github.com/larsenv/d2x-cios-installer/blob/67b77efdfa1d859ad968b09281642361181ad569/sources/libios.c#L358-L381
[fake]: https://github.com/xerpi/fakemote/blob/ad985238dc0716c1f28826eef9b9366689914011/README.md#L21-L54
[fakelink]: https://github.com/xerpi/fakemote/blob/ad985238dc0716c1f28826eef9b9366689914011/link.ld
[fakestart]: https://github.com/xerpi/fakemote/blob/ad985238dc0716c1f28826eef9b9366689914011/source/start.s
[haibuild]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/launcher/common.mk
[haiinit]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/launcher/source/haxx.cpp#L168-L199
[haistart]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/source/crt0.s
[haimain]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/source/main.cpp
[hainame]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/include/files.h#L12-L13
[hailoop]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/proxiios.cpp#L5-L75
[haidi]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/dipmodule/source/dip.cpp#L551-L603
[haifile]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/libfile/files.c
[haihandlers]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/source/module.cpp
[haiio]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/source/file_riifs.cpp#L20-L272
[hainet]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c
[hailink]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/scripts/link.ld#L7-L29
[haiipc]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/include/ipc.h#L49-L103
[launch]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/scheduler/threads.c#L598-L762
[threads]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/scheduler/threads.c
[rm]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/messaging/resourceManager.c
[fd]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/filedesc/calls_inner.c
[async]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/filedesc/calls_async.c
[reply]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/messaging/ipc.c#L395-L446
[queues]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/messaging/messageQueue.c
[gxmodules]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/system/IosLoader.cpp#L553-L593
[ppcipc]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/ipc.c#L1051-L1077
[size]: https://github.com/lloydsmart/wii-netdisc/blob/797e719cf587e6e779728ff48b34ba2468627385/research/experimental-dip-sizing-results.md
[stock]: https://github.com/lloydsmart/wii-netdisc/blob/797e719cf587e6e779728ff48b34ba2468627385/research/d2x-build-baseline.md
[fit]: https://github.com/lloydsmart/wii-netdisc/blob/797e719cf587e6e779728ff48b34ba2468627385/research/direct-dip-tcp-probe-fit.md
[life]: https://github.com/lloydsmart/wii-netdisc/blob/797e719cf587e6e779728ff48b34ba2468627385/research/r0-02-r0-03-ios57-v5918-network-lifecycle.md
[probe]: https://github.com/lloydsmart/wii-netdisc/blob/797e719cf587e6e779728ff48b34ba2468627385/research/experimental_dip/README.md
[adr5]: https://github.com/lloydsmart/wii-netdisc/blob/797e719cf587e6e779728ff48b34ba2468627385/docs/decisions/0005-experimental-dip-sizing-link.md
[adr4]: https://github.com/lloydsmart/wii-netdisc/blob/797e719cf587e6e779728ff48b34ba2468627385/docs/decisions/0004-pc-only-fixture-simulation.md
[ownership]: https://github.com/lloydsmart/wii-netdisc/blob/797e719cf587e6e779728ff48b34ba2468627385/research/ios-ipc-ownership-and-fixture.md
[wire]: https://github.com/lloydsmart/wii-netdisc/blob/797e719cf587e6e779728ff48b34ba2468627385/research/tcp_peer/README.md
[gate]: https://github.com/lloydsmart/wii-netdisc/blob/797e719cf587e6e779728ff48b34ba2468627385/research/experimental_dip/netdisc.c
[once]: https://github.com/lloydsmart/wii-netdisc/blob/797e719cf587e6e779728ff48b34ba2468627385/research/experimental_dip/netdisc_gate.s
[hook]: https://github.com/lloydsmart/wii-netdisc/blob/797e719cf587e6e779728ff48b34ba2468627385/research/experimental_dip/integration.patch
[net]: https://github.com/lloydsmart/wii-netdisc/blob/797e719cf587e6e779728ff48b34ba2468627385/research/experimental_dip/netdisc_net.c
[native]: https://github.com/lloydsmart/wii-netdisc/blob/797e719cf587e6e779728ff48b34ba2468627385/tests/test_native_dip.py
[sim]: https://github.com/lloydsmart/wii-netdisc/blob/797e719cf587e6e779728ff48b34ba2468627385/research/fixture_sim/README.md
[provenance]: https://github.com/lloydsmart/wii-netdisc/blob/797e719cf587e6e779728ff48b34ba2468627385/research/r0-01-r0-02-source-investigation.md
