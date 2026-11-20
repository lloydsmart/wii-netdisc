# R0-02 / R0-03 — Wired TCP across game handoff on IOS57 v5918

**Finding, 20 November 2026.** On an original Wii with stock IOS57 v5918 as the
base for d2x `33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7`, wired TCP after
handoff to an unpatched game is **unresolved for both candidate owners**. USB
Loader GX calls the cleanup helper before the optional IOS reload. In the
inspected libogc source, the helper sends KD ioctl 7 only if opening KD succeeds
and leaves the result unchecked. A game can later request startup and cleanup
on the same IOS services. The sources identify those
callers but leave open which other sockets IOS57 affects and who may restart it.
A real IOS reload also replaces the runtime that owned the connection.

This follows the [PR #5 disc-read investigation](r0-01-r0-02-source-investigation.md).
The question is whether the IOS owner can exchange new bytes with a wired peer
after each event. The pinned d2x tree implements neither proposed TCP owner.
**Source-verified** below describes code at the linked revisions. **Hypothesis**
marks deductions about the target. No finding is experimentally verified.

## R0-02 — From the USB port to the socket

**Source-verified.** The original-Wii 57/5918 entry in `data/ciosmaps.xml` names
MLOAD, FAT, EHCI, DIPP, ES and FFSP. Other contents are identified by number.
The custom EHCI module's `main` calls `EHCI_Init` before its service loop.
`ehci_release_ports` hands controller indices 1 and 2, disconnected ports and
ports classified as USB 1.1 to the companion controller. A connected device on a
retained port can therefore take a different path. The code describes port
ownership at initialisation. It supplies no observation of LAN adapter binding,
port numbering on the case, or a working Ethernet link. [Base map][map] ·
[EHCI main][emain] · [EHCI_Init][ehci] · [ehci_release_ports][ports]

**Historical reverse-engineering evidence.** WiiBrew identifies OHCI0, the USB
core and ETH in the IOS57 family. It records that the SO socket service opens
`/dev/net/usbeth/top` for Ethernet and that ETH exposes link-up, link-down and
packet operations. The candidate wired path for *both* owners is SO → ETH →
IOS USB/controller owning the port → USB LAN adapter → Ethernet. Neither socket
client below opens the adapter directly. Which USB interface ETH opens on this
revision, when it binds, and whether KD cleanup brings ETH down are unverified.
The stock-family inventory and the d2x map alone cannot answer those questions.
[IOS57 inventory][ios57] · [IOS module observations][iosmodules] · [ETH interface][usbeth]

**Source-verified client sequence.** In libogc's PPC `net_init_chain`, the client
queries link status on NCD (`/dev/net/ncd/manage`), closes that handle, opens SO
(`/dev/net/ip/top`), and requests socket startup on KD (`/dev/net/kd/request`).
It checks the KD reply buffer after IPC success, retries an in-progress result,
and accepts a result its source describes as already started. It closes KD,
requests SO startup and waits for a host IP. The SO handle carries socket,
connect, send and receive requests. The socket number returned by SO is distinct
from the IOS handle used to submit them. Each is distinct from the wired link.
[Initialisation and KD reply][ppcinit] · [Socket operations][ppcsock]

**Who stops what.** A client can close one socket with `net_close`, close its SO
handle with `net_deinit`, or request KD cleanup with `net_wc24cleanup`. The last
helper tries to open `/dev/net/kd/request`. If the open succeeds, it issues
ioctl 7 without a socket argument and closes the KD handle. It checks neither
the ioctl return value nor the KD reply buffer. IOS hosts the resource
managers. The launcher, game and candidate runtime can request changes to their
state. Neither owner starts an ETH, NCD, KD or SO process in the paths examined.
The stock modules' registration order, rules for last close, and authority to
stop or restart the wired interface are missing from the 57/5918 source trace.
[Socket close][close] · [SO close and KD cleanup][cleanup]

## R0-03 — Which caller would own the connection?

| Owner | Source-verified caller evidence | Conclusion for 57/5918 |
| --- | --- | --- |
| DIP disc-read handler | `Patch_DipModule` selects a DI hook for this base. `DI_EmulateInitDrive` grants the executing thread FAT access. `WBFS_Open` and `WBFS_Read` issue storage IPC from DIP. [DI hook][dip] · [Thread rights][rights] · [Storage IPC][wbfs] | **Unknown.** The corresponding network evidence would be NCD/KD/SO opens and accepted requests, followed by TCP data, from the hooked DI thread. No such call path appears here. DIP would own startup, socket and close. A synchronous network wait would hold up the disc read. Its linker limits give no measurement of space available for that work. [DIP layout][layout] |
| Separate IOS service called by DIP | HAI-Riivolution's `DIP::ReadFile` calls the file layer. Its file module registers a queue, dispatches `Filesystem::HandleRead`, and can run `RiiHandler::Read`. `Mount` initiates TCP and `Unmount` closes its socket. The file module declares its own startup identity (18) and stack. [DI client][riidip] · [Dispatch loop][loop] · [File read][fsread] · [RiiFS owner][riifs] · [Startup record][identity] | **Unknown, with an ARM service precedent.** On d2x, DIP would need permission to call the new service, and that service would need permission to use NCD/KD/SO with its own buffers. The base map has no such service to start. Separate scheduling and storage for the socket still leave DIP waiting for a bounded reply and both callers reliant on one wired stack. |

In the ARM comparison, `net_init` returns immediately when it already holds an
IP/top handle. Otherwise it queries NCD, opens SO, requests KD and SO startup,
then polls the host IP. Its KD wrapper returns the ioctl status without checking
the KD output the way libogc does. **Hypothesis.** A cached handle or a
successful startup wrapper can therefore mask a dead data path. Moving that
wrapper into a separate process would supply neither evidence of permission nor
evidence of recovery. [ARM net_init and NWC24iStartupSocket][arminit]

## Four events in an unpatched game session

**Source-verified handoff.** On its Wii disc path, `GameBooter::BootGame` calls
`AppCleanUp` **before** comparing the chosen slot with the running IOS.
`AppCleanUp` calls `DeinitNetwork`, which calls both `net_wc24cleanup` and
`net_deinit`. Even when the reload branch is skipped, GX shuts down devices and
`Disc_JumpToEntrypoint` calls `__IOS_ShutdownSubsystems`. The pinned libogc
implementation of the latter closes STM and ES. A trace of the earlier helper
call alone leaves both ioctl submission and cleanup success unverified.
[Boot path][boot] · [AppCleanUp][app] · [DeinitNetwork][deinit] ·
[Cleanup helper][cleanup] · [Jump][jump] · [Subsystem close][subclose]

**Source-verified game-side example.** In the Mario Kart Wii decompilation,
`SOStartupEx` checks NCD link status, opens IP/top, calls `NWC24iStartupSocket`
and waits for DHCP. A failed DHCP wait can itself invoke `SOCleanup`. From the
active state, `SOCleanup` calls `NWC24iCleanupSocket` and closes the game's SO
handle on success. The game's state variables belong to its PPC client. They
reveal neither the IOS socket table nor how every game uses it. [Game startup][gameup] ·
[Game cleanup][gamedown]

| Event | Can the existing IOS-owned socket still exchange data? | Can the runtime make a fresh TCP connection? |
| --- | --- | --- |
| GX handoff, same IOS | **Unknown for both.** Probe the same connection before GX calls the helper and after handoff. Record separately whether KD confirmed cleanup between probes. | **Unknown for both.** The owner must be able to use SO after GX teardown and, if necessary, start networking with no PPC launcher left. |
| Game starts networking | **Unknown for both.** Another startup could coexist, fail, or disturb the live exchange. The game's startup result alone cannot distinguish them. | **Unknown for both.** Can the owner create and use a second socket while the game has an active network client? A successful game connection proves only the game's access. |
| Game shuts networking down | **Unknown for both.** KD cleanup precedes the game's SO close in the example. Its effect on an independent DI or service socket is unobserved. | **Unknown for both.** A fresh socket might work immediately, might need NCD/KD/SO reinitialisation, or the owner might be unable to restore access. |
| Actual IOS reload | **Treat as lost for both (inference).** The old owner and SO instance are replaced. The d2x restore path carries storage state and has no socket restoration. | **Conditional and unverified.** The destination IOS must contain the owner. DIP must initialise again, or the service must start and register and DIP must reopen it. Either then needs wired startup and a new TCP exchange. Reload into stock IOS alone leaves neither custom owner available. |

**Reload evidence.** `IOS_ReloadIOS` explicitly launches a new IOS. In the d2x
ES reload-redirection path, `ES_EmulateIoctlv` can save configuration and call
`__ES_CustomLaunch` for the configured cIOS. `__DI_InitDriveEmulation` restores
WBFS or fragment state. Reloading the same cIOS slot still creates a new owner
lifetime. [IOS reload][reload] · [ES launch][es] · [DI restore][restore]

**Patched comparison only.** When mounts remain, Riivolution's
`ApplyBinaryPatches` changes matching game startup and cleanup code. Its
comment gives interference with its sockets as the reason. In the HAI fork,
`RVL_Unmount` requests KD cleanup when no mounts remain. These choices explain
why a Riivolution session cannot settle any same-IOS cell above. [Game patch conditions][riipatch] ·
[Unmount conditions][unmount]

## Missing observation and smallest distinguishing test

The source investigation stops at the IOS57 v5918 resource-manager boundary.
The decisive observation is a **peer-confirmed exchange from the actual DI
callback or the DIP-invoked service** across each event. Does SO still route
traffic for that caller's existing socket, and can the same identity create a
usable socket once the old one fails? Neither a PPC probe nor an emulator's
socket table answers this.

**Proposed synthetic test, unrun and subject to separate approval.**

1. Use one original Wii, one recorded adapter/port attached before IOS starts, a
   wired-only LAN, and a peer at a fixed address. Use a synthetic PPC title with
   ordinary, unmodified network startup/cleanup calls and a local boot path so a
   missing network reply cannot prevent the next observation. Exercise one
   candidate per run through a synthetic DI request. For the service run, have
   DIP issue the request and the service perform all socket operations.
2. Establish a baseline **before GX calls the cleanup helper**. Have the peer assign each
   accepted TCP connection a unique ID and echo a new unpredictable challenge
   per request. Require exact challenge and connection ID back at the owner and
   verify traffic on the wired link. Record the IOS instance, owner, SO handle
   and socket. At the helper call, record the KD open result. A failed open
   means GX skipped ioctl 7. If sent, record the ioctl return and KD service
   result separately wherever observable.
3. Repeat immediately after no-reload handoff, after successful game startup
   while its own connection works, and after game cleanup. At each checkpoint
   first send a new challenge on the pre-event socket with reconnect disabled.
   Independently try a fresh socket/connect and challenge. If that fails, try
   once after reopening services and repeating network startup. Check for a live
   exchange immediately before each event. If the previous event killed it,
   record survival as untestable until a new baseline succeeds. Use a matched
   run if the recovery probe would perturb the next event. For a true same-slot
   reload, confirm a new IOS/owner instance, track the original connection at
   the peer, retire the old handles, and test a new accept and exchange from
   the restarted owner.
4. Set a deadline for each phase before testing (for example, 5 seconds for an
   exchange and 30 seconds for bring-up). **Survival** requires new bytes on the
   peer's original connection ID. **Fresh access** requires a new accept, new ID
   and exact reply even if the old socket also works. If only the second probe
   passes, record **reconnection only**, including whether restart was needed.
   If neither passes within the bounds with a healthy peer and verified wired
   path, record **loss of access for that owner at that event**, with the first
   failing operation. A failed baseline, failed game transition, or failed link
   control leaves that lifecycle result indeterminate. A game startup failure
   while the runtime still works is a coexistence failure in its own right.
5. Report **socket survived handoff** when the original connection passes the
   challenge before the helper and again after same-IOS handoff. Report
   **socket survived confirmed KD cleanup** only when the same interval also
   contains a successful ioctl 7 IPC return and a KD reply confirming cleanup
   success. If the cleanup result is unavailable, report the observed TCP
   outcome and leave the effect of KD cleanup unknown. This applies equally to
   survival, reconnection and loss of access.

[map]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/data/ciosmaps.xml#L250-L302
[emain]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/ehci-module/main.c#L35
[ehci]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/ehci-module/tinyehci.c#L61
[ports]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/ehci-module/tinyehci/ehci.c#L1025-L1042
[ios57]: https://wiibrew.org/w/index.php?title=IOS57&oldid=118201
[iosmodules]: https://wiibrew.org/w/index.php?title=IOS&oldid=123340#SO
[usbeth]: https://wiibrew.org/w/index.php?title=/dev/net/usbeth/top&oldid=122454
[ppcinit]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/network_wii.c#L273-L465
[ppcsock]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/network_wii.c#L701-L939
[close]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/network_wii.c#L975
[cleanup]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/network_wii.c#L588-L611
[dip]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/patches.c#L132-L146
[rights]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.c#L775
[wbfs]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/wbfs.c#L41-L96
[layout]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/link.ld#L6-L10
[riidip]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/dipmodule/source/dip.cpp#L551-L596
[loop]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/proxiios.cpp#L12-L61
[fsread]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/source/module.cpp#L372
[riifs]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/source/file_riifs.cpp#L20-L268
[identity]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/source/crt0.s#L7
[arminit]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L301-L411
[boot]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/usbloader/GameBooter.cpp#L558-L579
[app]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/sys.cpp#L86-L123
[deinit]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/network/networkops.cpp#L79-L87
[jump]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/usbloader/disc.c#L388-L400
[subclose]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/ios.c#L94-L109
[gameup]: https://github.com/doldecomp/mkw/blob/8b9b5ee653da28663e498039e52f5d19f929a011/lib/rvl/so/soCommon.c#L90-L242
[gamedown]: https://github.com/doldecomp/mkw/blob/8b9b5ee653da28663e498039e52f5d19f929a011/lib/rvl/so/soCommon.c#L262-L316
[reload]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/ios.c#L361-L400
[es]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/es-plugin/plugin.c#L457-L480
[restore]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.c#L167-L195
[riipatch]: https://github.com/AerialX/rawksd/blob/4ef79e2e234d7c2f19d030c2d9440852b5c73b7a/launcher/source/launcher.cpp#L437-L460
[unmount]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/launcher/source/riivolution.cpp#L656-L675
