# R0-01 / R0-02: Disc backing stores and IOS networking

Inspected: **2026-11-17**. Status: **source investigation; feasibility unresolved**.

The source identifies a plausible raw-disc backing-store boundary and an IOS-side
socket-client precedent. It does **not** establish that networking remains usable
from d2x's DI context throughout gameplay. In particular, Riivolution patches game
network startup/cleanup, and d2x's reload handling restores storage configuration
after reloading cIOS. Neither precedent proves a persistent network session.

This note addresses [R0-01 and R0-02](feasibility-plan.md), with remaining evidence
gaps below. It neither completes R0 nor selects an architecture.

## Sources and method

Read the local historical conversation for intent and leads, then fetched repository
metadata, commit IDs, trees and individual source files through GitHub's read API.
Temporary inspection copies are ignored under `research/local/`; no upstream code
or archive excerpts are included in this change. No upstream scripts were executed.

These are maintainer/developer repositories, not tutorial mirrors. D2x's README
identifies its cIOSX rev21 ancestry and credits Waninkoko, WiiGator and others.
The original davebaol tree establishes provenance; the detailed trace below uses
the later wiidev tree. USB Loader GX's default branch is `enhanced`, not `master`.
HAI-Riivolution identifies itself as an adaptation for HAI-IOS; GitHub identifies
AerialX/rawksd as its parent. Do not generalise its environment to d2x.

| Source | Immutable revision examined | Role / principal paths |
| --- | --- | --- |
| [Original d2x][original] | `93306ceb7e22c0cfc548493afea0e6873beeba62` | `README.md`, `source/dip-plugin/plugin.c`; ancestry and comparison |
| [wiidev d2x][d2x] | `33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7` | `source/dip-plugin/`, `cios-lib/`, `es-plugin/`, USB/EHCI modules, `data/ciosmaps.xml` |
| [USB Loader GX][gx] | `e25c4f3501ed957b7db73f79c51fdf00715ab2e2` | `source/usbloader/wdvd.c`, `GameBooter.cpp`; PPC client and handoff |
| [devkitPro libogc][ogc] | `ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e` | `libogc/network_wii.c`, `ios.c`; PPC socket IPC and reload |
| [AerialX Riivolution/RawkSD][rawksd] | `4ef79e2e234d7c2f19d030c2d9440852b5c73b7a` | `libios/source/network_wii.c`, `filemodule/source/file_riifs.cpp`, `launcher/source/launcher.cpp` |
| [HAI-Riivolution][hai] | `e67de6991ec24252acadd2c4b0918f21e83c2528` | Same networking files; file-service, DI proxy and launcher context |
| [Nintendont][nin] | `0d0c57cee525149d28c85678d8e2dfc014096d32` | Limited cross-check: `kernel/sock.c` (`SOCKInit`, `SOCKShutdown`) and `kernel/main.c`; a different runtime, not d2x proof |

**Provenance/licence limit:** d2x's root licence is only a short GPLv3 label;
examined DIP files carry GPL-3.0-or-later notices and cios-lib files carry
GPL-2.0-or-later notices. Libogc and the Riivolution network file carry a permissive
three-condition notice. This is a file-level observation, not a completed licence
inventory or compatibility decision. R0-05 must cover the complete dependency set,
including files without clear local notices, before reuse. [DIP notice][plugin],
[cios-lib notice][usbipc], [network notice][hnet], [libogc licence][ogclic].

## R0-01 findings

**R0-01a — Source-verified: ARM hooks, not a resident PPC loader.**
D2x's DIP Makefile targets big-endian ARM926EJ-S/Thumb and links cios-lib.
`main` installs patches through `IOS_InitSystem`;
`Patch_DipModule` selects base-version-specific addresses and
`__Patch_DipModule` redirects original DI init, ioctl and command handlers.
The `DI_HandleIoctl` / `DI_HandleCmd` assembly trampolines resume original
handlers. Thus read callbacks execute in the hooked IOS DI service context;
the plugin's initialisation thread is not a separate network worker.
`DI_EmulateInitDrive` obtains the current thread ID and grants FAT-related
thread rights. Its comment says initialisation occurs on the first open/ioctl/ioctlv;
that timing description remains an upstream claim, not an observed trace.
[Build][dipmake], [initialisation][dipmain], [patches][patches],
[trampolines][calls], [drive init][driveinit].

**R0-01b — Source-verified boundary, with a stock-IOS gap.**
The observable path is:

```text
PPC client -> /dev/di ioctl
  -> original IOS DI dispatch (not supplied as source by d2x)
  -> hooked DI_EmulateIoctl / DI_EmulateCmd as appropriate
  -> raw command -> __DI_ReadUnencrypted
       -> Frag_Read -> sector mapping -> USB/SD IPC
       -> WBFS_Read -> USB/SD WBFS IPC
       -> DI_ReadDvd / DI_ReadWod -> original command handler
```

GX's `WDVD_Read` demonstrates the encrypted-read client command; its
`WDVD_UnencryptedRead` demonstrates raw reads. Both pass byte length and
`offset >> 2`. These are **loader functions**, not evidence that commercial games
call `WDVD_Read`. `BootGame` loads the game and transfers control to its entry
point; a launcher-side TCP loop cannot supply later reads without an additional
resident mechanism. [Client][wdvd], [handoff][boot].

In `DI_EmulateCmd`, normal `IOCTL_DI_LOW_READ` goes to `DI_HandleCmd` unless
`MODE_CRYPT` is set; the latter directly calls `__DI_ReadUnencrypted`.
Raw read commands call that common function. The name “unencrypted” describes the
raw read operation; it does not mean every returned image byte is plaintext.
D2x does not include the original DI partition/decryption implementation.
**Hypothesis:** normal encrypted partition reads ultimately obtain raw sectors via
the hooked command path while original IOS performs partition processing.
The exact internal re-entry, decryption/hash ordering and final IPC error translation
need independent verification; they are not proved by these wrappers. [Dispatch][plugin].

**R0-01c — Source-verified: units, alignment and errors differ by layer.**

| Boundary | Observed contract |
| --- | --- |
| `__DI_ReadUnencrypted` | `u32` offset in four-byte words, `u32` byte length; checks starting offset against detected disc type, then adds two configured word offsets |
| `Frag_Read` | Splits leading/trailing partial sectors through a sector buffer allocated with 32-byte alignment; middle reads use sector counts |
| `__Frag_Get` / `__Frag_ReadSect` | Maps logical image sectors to backing-device sectors; holes are zero-filled; SD uses 512-byte sectors, USB size comes from the device |
| USB IPC / `WBFS_Read` | Aligned vectors/control buffers and explicit cache synchronisation; module-to-module `os_ioctlv` already exists |
| Error conventions | Fragment success is 0; mapping/device/no-progress failures include -2/-3/-4. USB helper returns Boolean success; `WBFS_Read` returns IPC failures. GX expects outer DI IPC success 1 and translates it to 0 |

[Fragment functions][frag], [raw dispatcher][plugin], [USB helper][usbipc],
[WBFS IPC][wbfs], [PPC result translation][wdvd].

**Hypothesis/design constraint:** an ISO backend at the raw boundary would use
`byte_offset = uint64(word_offset) * 4`, after accounting for configured offsets.
A 32-bit byte conversion would truncate reads beyond 4 GiB. Validate the entire
range against export size with overflow-safe arithmetic: the existing start-offset
check is insufficient as a network-request validator. Short replies/EOF must not
be mistaken for complete DI reads or sparse holes. Socket errno, backing-store
status and DI request-error state need an explicit translation, still unverified.
Transport buffer alignment/cache ownership also needs its own audit; the sector
bounce buffer alone does not establish safety for every caller buffer.

**R0-01d — Hypothesis: prefer investigating the common raw boundary.**
A sibling backing-store branch in `__DI_ReadUnencrypted` would avoid treating
network export offsets as local USB fragment sectors. Extending the fragment device
switch is another possible seam, but `Frag_Init` currently accepts only USB/SD and
requires their geometry. A separate IOS service has a precedent in `WBFS_Read`'s
IPC, but its permissions, scheduling and buffer ownership remain R0-03 work.
Neither option is selected. [Raw dispatch][plugin], [fragment init][frag], [IPC][wbfs].

Adding a read branch alone is insufficient: emulation-mode checks also govern
reset, seek, cover/error reporting and disc detection. The current emulation mask
contains only WBFS/FRAG. `__DI_CheckDisc` probes a second-layer offset and infers
disc type from success/failure; a network failure there could become a false
single-layer classification. [Modes][modes], [command handling][plugin].

## R0-02 findings

**R0-02a — Source-verified: IOS socket IPC has an ARM-side precedent.**
Libogc's `net_init_chain` opens NCD management, the socket service
`/dev/net/ip/top`, and KD's `/dev/net/kd/request`; it performs link/startup steps
and waits for an IP address. Socket creation/connect use ioctl; send/receive use
ioctlv. This is a PPC library, not a library that can simply be linked into DIP.
[Libogc functions][lnet].

Riivolution's `libios/source/network_wii.c` instead uses ARM `os_open`,
`os_ioctl` and `os_ioctlv`, with aligned allocations/cache operations.
`net_init` calls `NCDGetLinkStatus`, opens IP/top, calls
`NWC24iStartupSocket`, starts sockets and obtains an IP address.
`RiiHandler::Mount` creates/connects TCP; `Read` obtains file data through
`ReceiveCommand` / `netrecv`. The inspected AerialX and HAI copies of the network
and RiiFS files match. HAI's `Filesystem::HandleRead` dispatches to the handler
inside an IOS message loop; this is more relevant than a PPC-only demonstration.
[ARM networking][hnet], [RiiFS][riifs], [file service][fileservice],
[message loop][loop].

The precedent is not a ready-made bounded transport: `Mount` retries `-EAGAIN`
without an overall deadline and returns its socket to blocking mode. `netrecv`
loops over reads of at most 8 KiB. `net_recvfrom` allocates a temporary buffer for
unaligned or low-memory destinations and rounds its copy length to four bytes;
that buffer contract needs review before adapting it to DI output. [RiiFS][riifs],
[ARM receive wrapper][hnet].

**Uncertainty:** this verifies client code, not the closed-source IOS socket stack,
NCD/KD services or Ethernet driver on a chosen base. HAI's file-module startup
declares process ID 18 and its own stack/priority; d2x read hooks run in a different
context. D2x already has storage IPC and FAT thread-right handling, but that does not
prove DI may open/use all network services with suitable buffer permissions.
No hardware result, privilege audit or d2x network implementation was obtained.
[HAI startup][haistart], [DI init][driveinit], [d2x syscalls][syscalls].

**R0-02b — Source-verified: gameplay networking has lifecycle interference.**
Both AerialX and HAI `ApplyBinaryPatches` search game sections for socket-startup
and NWC24 cleanup patterns when `ToMount` is nonempty, then modify the instructions.
The accompanying comment attributes this to startup failures/socket shutdown.
The patch writes are source-verified; their effectiveness and coverage are not.
HAI's `RVL_Unmount` also issues KD cleanup when no mounts remain.
[Original launcher][alaunch], [HAI launcher][hlaunch], [unmount][unmount].

**Hypothesis:** game or launcher cleanup can interfere with a runtime-owned
connection. Independent descriptors do not establish independent network-stack
lifetime. Riivolution is consequently not proof of transparent full-ISO streaming
with arbitrary, unpatched game networking. Determine ownership and startup/cleanup
effects before adopting its patterns; do not inherit its game patches as a decision.

**R0-02c — Source-verified: “reload block” does not promise socket survival.**
In d2x ES's `ES_EmulateIoctlv` launch case, fake-IOS-launch handling can save DI/FFS and
ES configuration and invoke `__ES_CustomLaunch` for the configured cIOS.
DIP's `DI_Config_Save/Load` serialises storage configuration/fragment data;
`__DI_InitDriveEmulation` reopens WBFS or reinitialises fragments. The saved
`dipConfigState` contains mode, device and fragment size, not a network session.
[ES launch][eslaunch], [persistence][config], [restore][plugin], [state][modes].

**Hypothesis/design constraint:** treat a real IOS reload as session loss requiring
reinitialisation and renegotiation, with export identity rechecked and cached data
invalidated. A selected cIOS may also differ from the frontend's IOS
(`GameBooter::BootGame`), so connection setup before that switch is insufficient.
Reset, return-to-menu, startup failures and game-requested network shutdown need
distinct handling. [Loader lifecycle][boot], [libogc reload][iosreload].

**R0-02d — Source-verified constraints; availability still uncertain.**
D2x has materially different USB configurations: `ciosmaps.xml` selects EHCI for
bases such as 56/57, but USBS for base 58; `USB_Init` in `usb2.c` opens
`/dev/usb/ven`. EHCI's `ehci_release_ports` writes ownership bits for ports
1/2 and disconnected/USB1.1 ports; its comment warns that OHCI drivers cannot be
activated later by discovering devices for them. This is a lifecycle/port-allocation
lead, not evidence that a particular Ethernet adapter works. Base, port, adapter
and attachment timing remain unverified. [Module map][map], [USB client][usb2],
[EHCI initialisation][ehciinit], [port handoff][ports].

DIP's linker script reserves 8 KiB for executable sections and 256 KiB for data,
rodata and BSS. Those are layout limits, **not measured free space or a cache
budget**. Synchronous network calls from the read callback would delay DI
completion; a separate worker would still need bounded waits, cancellation and
safe late-reply ownership. No scheduling/deadlock or concurrent game-network
analysis has established that either design is safe. [Linker layout][layout],
[synchronous IPC][wbfs], [socket calls][hnet].

## Consequences and next investigation

**Historical:** the archive favours d2x/NBD, wired Ethernet, reusable frontends and
ISO-first scope. Its claims of feasibility, small implementation size and easy
frontend integration remain unverified. RetroMount remains a format converter;
export publication and selection remain separate responsibilities.

**Recommended next investigation:** close the R0-02 lifecycle/privilege gaps and
compare the two integration contexts in R0-03 before designing NBD integration.
Choose one explicit Wii base/revision for analysis; trace socket service ownership,
NCD/KD startup/cleanup, DI-thread access, USB Ethernet dependency/port handoff and
the missing encrypted-read re-entry. Account for actual section occupancy,
thread stacks, shared buffers, completion queues and reload state. Keep a separate
R0-05 provenance/toolchain review. R0-04 protocol negotiation/interoperability,
throughput and game compatibility have not been investigated here.

**Smallest useful coding experiment, for a separately authorised task:** a
host-only synthetic backing-store adapter test. Model word-to-byte conversion and
complete-read/error behaviour with deterministic generated bytes and a fake backend;
exercise offsets beyond 4 GiB, export-end crossings, partial-sector boundaries,
short reads, EOF and injected failures. Require exact bytes on success, bounded
failure and no overflow/out-of-bounds access. This can validate an independently
written boundary contract without copying upstream code, disc images or Wii tools.
It cannot answer the IOS feasibility question.

After the source gaps and an explicit toolchain/hardware plan are reviewed, the
smallest decisive IOS experiment would be a bounded synthetic TCP exchange from
the intended DI/service identity across launcher handoff and simulated game
startup/cleanup, then reload/reconnect. It should measure permissions, completion
and session loss before attempting NBD or booting an image. This is a proposal,
not authorisation to implement or access a console.

No finding is **experimentally verified**. The historical JSON remains ignored,
unpublished and unchanged; its SHA-256 before and after inspection is
`d69af646f95e29ab727f32820a48009ab6fd20ef6375b8cf9b8759f69f37dab8`.
No ADR was accepted or runtime implemented.

[original]: https://github.com/davebaol/d2x-cios/tree/93306ceb7e22c0cfc548493afea0e6873beeba62
[d2x]: https://github.com/wiidev/d2x-cios/tree/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7
[gx]: https://github.com/wiidev/usbloadergx/tree/e25c4f3501ed957b7db73f79c51fdf00715ab2e2
[ogc]: https://github.com/devkitPro/libogc/tree/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e
[rawksd]: https://github.com/AerialX/rawksd/tree/4ef79e2e234d7c2f19d030c2d9440852b5c73b7a
[hai]: https://github.com/ymweiss/HAI-Riivolution/tree/e67de6991ec24252acadd2c4b0918f21e83c2528
[nin]: https://github.com/FIX94/Nintendont/blob/0d0c57cee525149d28c85678d8e2dfc014096d32/kernel/sock.c#L209
[plugin]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.c#L42
[dipmake]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/Makefile
[dipmain]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/main.c#L29
[patches]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/patches.c#L51
[calls]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/dip_calls.s#L40
[driveinit]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.c#L775
[frag]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/frag.c#L81
[usbipc]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/usbstorage.c#L62
[wbfs]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/wbfs.c#L71
[modes]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.h#L39
[config]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/config.c#L68
[eslaunch]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/es-plugin/plugin.c#L427
[syscalls]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/syscalls.h
[map]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/data/ciosmaps.xml#L250
[usb2]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/usb-module/usb2.c#L236
[ehciinit]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/ehci-module/tinyehci.c#L79
[ports]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/ehci-module/tinyehci/ehci.c#L1025
[layout]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/link.ld
[wdvd]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/usbloader/wdvd.c#L258
[boot]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/usbloader/GameBooter.cpp#L571
[lnet]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/network_wii.c#L273
[iosreload]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/ios.c#L361
[ogclic]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/LICENSE
[hnet]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c
[riifs]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/source/file_riifs.cpp#L20
[fileservice]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/source/module.cpp#L372
[loop]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/proxiios.cpp#L19
[haistart]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/source/crt0.s#L7
[alaunch]: https://github.com/AerialX/rawksd/blob/4ef79e2e234d7c2f19d030c2d9440852b5c73b7a/launcher/source/launcher.cpp#L437
[hlaunch]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/launcher/source/launcher.cpp#L437
[unmount]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/launcher/source/riivolution.cpp#L622
