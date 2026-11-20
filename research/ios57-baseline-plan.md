# IOS57 v5918 baseline — one TCP exchange before GX cleanup

**Proposed measurement, unrun.** Can the hooked DI thread on an original Wii
exchange fresh bytes with a wired peer before USB Loader GX calls
`net_wc24cleanup`? Use IOS57 v5918 with d2x
`33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7`. Boot the instrumented GX locally
from SD, with the test cIOS already running. The boot path and evidence log must
work with the Ethernet cable unplugged. Stop the measurement at the helper call.
[Merged lifecycle investigation](r0-02-r0-03-ios57-v5918-network-lifecycle.md)

## Which caller to probe first

The existing call paths below are **source-verified** at the linked revisions.
Neither probe has been exercised on this target.

- **Direct DIP.** GX's `WDVD_UnencryptedRead` issues a synchronous DI request.
  The d2x `DI_EmulateCmd` hook handles that read, and `WBFS_Read` shows that DIP
  already issues storage IPC. A one-shot probe in the read handler needs ARM
  socket IPC, aligned buffers, bounded waits and a result record. Network
  permissions and available space are unknown. The linker reserves 8 KiB for
  executable sections, and a blocked call would stall DI. [GX request][request] ·
  [DI handler][handler] · [Storage IPC][storage] · [Linker layout][layout]
- **DIP-invoked service.** HAI-Riivolution provides an ARM precedent for a
  DI-to-file-service request and service-owned TCP. On this d2x base the same
  probe would also need a packaged module, a startable identity and stack, a
  registered queue, permission for DIP to open it, and a bounded IPC reply with
  clear buffer ownership. The service would need its own NCD/KD/SO access.
  [DIP::ReadFile][client] · [Service dispatch][dispatch] · [RiiHandler::Mount][mount] ·
  [Service startup][identity] · [d2x base map][map]

**Hypothesis.** Try direct DIP first. Both candidates need a working ARM socket
client. Direct DIP adds it at an existing hook and avoids introducing a second
module and IPC boundary. Reconsider the service if measured fit, permissions or
blocking rule out the direct probe. Production placement remains open.

## One run and its evidence

1. In a test build of GX, issue one tagged synthetic raw-read request immediately
   before `GameBooter::BootGame` calls `AppCleanUp`. Intercept it in the hooked
   read case before any backing-media access. Record the run tag, running slot,
   IOS instance and probe build ID. GX records dispatch, synchronous return and
   a marker immediately before the call to `net_wc24cleanup`, in sequence.
   Only the IOS caller opens the socket.
   [BootGame][boot] · [AppCleanUp][app] · [DeinitNetwork][deinit]
2. Before its first network operation, the DI handler emits a local entry record
   with the tag and executing thread ID. For a service probe, require both the
   DIP dispatch and a matching entry from the service thread. Preserve progress
   independently of the network and of DI returning. Log NCD link, SO open, KD
   startup (IPC status and service reply), SO startup and host IP, then socket,
   connect, send, receive and close. Keep the SO handle distinct from the socket
   number. Record elapsed time, byte counts, reply bytes and the first error or deadline.
   [ARM net_init][arm] · [KD reply handling in libogc][ppc]
3. Give bring-up 30 seconds and the single exchange 5 seconds, with no reconnect.
   The caller sends the run tag and a fresh challenge. On its wired interface
   the peer logs the accept, endpoints, unique connection ID, exact bytes received
   and reply sent. It echoes the challenge and tag with that ID. **Pass** requires
   an exact match in the caller's completion record and the matching DI return
   before the helper marker. This ordering needs no synchronised peer clock.
4. **Failed baseline** requires evidence that the intended caller entered before
   cleanup and its attempt failed, timed out or returned mismatched bytes, with
   the peer and wired test setup independently checked. **Probe never ran** if
   GX records a skipped dispatch or a dispatch rejected before caller entry.
   Missing entry evidence alone, a lost log, wrong IOS, uncertain ordering or
   failed controls leave the run **indeterminate**. A silent peer alone cannot
   distinguish these outcomes.

## Owner review and decision

- **Hardware.** Identify the original Wii, test slot, SD boot fixture, LAN
  adapter model/VID:PID and physical port. Attach it before IOS starts. Use
  wired-only networking and a fixed local peer. Check the listener independently
  over Ethernet. Adapter binding on this base remains unverified.
- **Build.** Review the ARM big-endian Thumb toolchain, cios-lib, linker and
  stripios, plus the PPC compiler and libogc for the GX fixture. Pin versions
  and packaging inputs. Require a link map, stack and aligned-buffer budget,
  a network-independent trace and a watchdog that can bound a stuck IOS call.
  Toolchain compatibility, spare space and effective deadlines remain open.
  [DIP Makefile][build]
- **Provenance.** Review the owner's authorised IOS57 v5918 base and its digest,
  pinned d2x/GX/libogc sources, probe diff and resulting artifact hashes. Review
  per-file licences before reusing any ARM client code. Keep firmware, keys and
  console backups private.
- **Recovery.** Confirm that the test slot leaves the known-good boot and recovery
  route usable, and that the owner has a verified private backup and a rollback
  procedure for this console. Agree how to stop on a hang or lost trace.

**Conditional go for a separately authorised direct-DIP prototype.** Proceed
only after the owner accepts the inputs, bounds, trace and recovery plan. Hold
hardware execution if caller identity, pre-cleanup ordering or recovery cannot
be demonstrated. A pass would establish one exchange on the recorded setup.

[request]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/usbloader/wdvd.c#L258-L277
[handler]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.c#L307-L323
[storage]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/wbfs.c#L71
[layout]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/link.ld#L6-L10
[client]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/dipmodule/source/dip.cpp#L551-L596
[dispatch]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/proxiios.cpp#L12-L61
[mount]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/source/file_riifs.cpp#L20
[identity]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/source/crt0.s#L7
[map]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/data/ciosmaps.xml#L250-L302
[boot]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/usbloader/GameBooter.cpp#L558-L579
[app]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/sys.cpp#L86-L123
[deinit]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/network/networkops.cpp#L79-L87
[arm]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L301-L411
[ppc]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/network_wii.c#L273-L465
[build]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/Makefile
