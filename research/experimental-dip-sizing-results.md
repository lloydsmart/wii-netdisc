# First experimental direct-DIP sizing result

**Experimentally verified on PC, 27 November 2026 (R0-03).** The matched
stock DIP linked with 1,484 executable bytes free. The complete outer-hook
TCP probe selected by ADR 0005 attempted to add 5,420 bytes to the occupied
span. GNU ld rejected the modified link with a **3,936-byte executable
overflow**. The retained journal records `region-overflow`, an explicit
stop condition in the accepted decision. [ADR 0005][adr] · [Sizing job][job]

## Execution and retained evidence

In `lloydsmart/wii-netdisc`, owner `lloydsmart` was both actor and triggering
actor for the manual `workflow_dispatch` on `refs/heads/develop`. GitHub
records **Experimental DIP sizing** (workflow ID `433194378`), run number 1,
run ID `46073829896`, attempt 1. Job `measure` (`140756822383`) ran from
21:59:57 to 22:00:33 UTC. Its approval gate verified the workflow path
`.github/workflows/experimental-dip.yml` on that ref and matched both event
and workflow SHAs to the owner's `approved_sha`,
`cd9c9357116f9ac927f159060c93546a4d8d8194` (PR #19 merge). The checkout
check passed at that same SHA, which also appears in the journal.
[Workflow run][run] · [Job log and step results][job] · [Workflow at the approved revision][workflow]

Dependency provisioning and input retrieval passed. The measurement step
returned failure at the modified link, giving the job its failure status.
The subsequent evidence selection and upload steps both succeeded. GitHub
finalised artifact `dip-sizing-evidence-46073829896-1` (ID `15234067228`)
at 22:00:32 UTC, with 30-day retention and a recorded expiry of
27 December 2026 at 22:00:31 UTC. [Job][job] · [Artifact][artifact]

At review on 27 November, the downloaded ZIP was **7,779 bytes**, SHA-256
`8a74c8e26413bed43b846e296d6df26968f6ac574febf2c088ce5dc11b823eda`,
matching the upload log and artifact metadata. The ZIP passed its CRC check.
Its sole entry, `sizing.jsonl`, was 30,348 bytes, SHA-256
`2067bc9c690500e2fef8844849df952594167ea6f4d0ddae1549576e8ec82c90`.
All 365 records passed the reviewed journal validator. The source for the
figures below is this journal. Raw build logs, maps and binaries stayed in
runner scratch. [Artifact][artifact] · [Collector and validator][collector]

## Build inputs and environment

The hosted Ubuntu 24.04.5 LTS runner used image `ubuntu24` version
`20261122.23.1`. The build ran as uid 1001 using devkitARM r32, ARM GCC
4.5.1, GNU binutils 2.20.1.20100303, GNU Make 4.3 and Python 3.12.3.
The control and probe used separate fresh extractions, the same toolchain,
stock flags and linker script, with `LC_ALL=C`, `TZ=UTC` and
`SOURCE_DATE_EPOCH=1742677801`. [Job][job] · [Stock preparation and recipes][prepare]

Preparation checked d2x commit `33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7`,
tree `b8e661b6535beb1d777ac21d25d25623bb5f0668` and committer epoch
`1742677801`. The selected tar covers `source/cios-lib`, `source/dip-plugin`
and `stripios_src`. The journal records the following verified inputs.
The five experiment-file digests also match the approved checkout.
[d2x revision][d2x] · [Input checks and patch application][build]

| Input | SHA-256 |
| --- | --- |
| Selected d2x source tar | `b6c8bd6cbe179a7155879fa3eace86af475fe80146b7bab9f2647f6f2303575c` |
| devkitARM r32 Debian Buster archive | `7ca6fafef13876e2e565b4421e2d240c4532c7f0d15f4ffe1e2ed3c485748cd6` |
| `integration.patch` | `3bd1e135d775d7e71d781bbee180369e05d50a11e2b6ba799cd6c28e70e5aa81` |
| `netdisc.c` | `94d2591c1a069c042f10122cf3588a978df906678bb35db79a5d39e50763d80b` |
| `netdisc.h` | `97ffc741725856aab42a6a6b8d9019376422c0bb64478b3447eff1afad4e8afc` |
| `netdisc_gate.s` | `02b7254907f5b3cf42dae580e98d3831c71b20818d6c3f1c22ff5aa7e16e20b4` |
| `netdisc_net.c` | `51beaa4e702fae35aed06b45db3f0dffa6a7a718b70221d0199a34374d8cee54` |
| Patched `source/dip-plugin/Makefile` | `5f38ac636c62a82ea6bf4be68db65cd51635da2d35b1ee67b192b8e2bdca7374` |
| Patched `source/dip-plugin/plugin.c` | `1538b79f79df30eb43fef4f913c3eb96a183e7ed6a905b200590ba4a0cf9367f` |

## Matched stock control

The control compiled, linked and completed the stock recipes. Its original
ELF was 84,587 bytes, SHA-256
`70623d5af228957d031691e32229b47e5bdc0b950e158d795daaba1125b7e63f`,
identical to both stock builds of 25 November. The raw control map was
26,399 bytes, SHA-256
`8027064018ade04604e2a8095c8045c627880f2cdf63d8bd10986f25c9b0f8c4`.
Replacing only the toolchain directory prefix with its historical value
reproduced the historical map SHA-256
`2edd3b7e30bfef7d4e766222d8c67c681771d4db89101971c83029f9b5c5a1ff`.
[Historical stock measurement][stock] · [`control_identity` and `layout`][inspect]

The original ELF, LOAD records and map agreed on the following control
extents. Both occupied spans and both trailing capacities match the stock
baseline. The separate table LOAD at address zero held 52 bytes.

| Region | Origin | Occupied exclusive end | LOAD file bytes | Occupied bytes | Trailing bytes |
| --- | --- | --- | ---: | ---: | ---: |
| Executable | `0x13800000` | `0x13801A34` | 6,708 | 6,708 | 1,484 |
| Static RAM | `0x13802000` | `0x1383E480` | 828 | 246,912 | 15,232 |

## Modified link and executable overflow

The patch added the outer-hook call and three ARM objects. All three objects
compiled or assembled. The modified build produced a 34,036-byte partial
linker map, SHA-256
`3e6501baa7838b086f6779713c9adc7747635406f508822edcfc37d654c75711`.
The link failed before producing a modified `dip-plugin.elf.orig`.
The journal's attempted ranges have exclusive ends. [Journal][artifact] ·
[Failed-link measurement in `measure_pair`][build]

| Attempted range | Start | Exclusive end | Bytes |
| --- | --- | --- | ---: |
| Executable region, origin to highest attempted end | `0x13800000` | `0x13802F60` | 12,128 |
| Named `.text` output | `0x13800020` | `0x13802F60` | 12,096 |
| Overlapping `.data` output | `0x13802000` | `0x138021C0` | 448 |

GNU ld named `.text` as the section that would not fit and separately
reported the `exe` region overflowed by 3,936 bytes. In the partial map,
the exclusive end of `.text` is also the exclusive end of the attempted region span.
Subtracting the permitted exclusive end `0x13802000` from `0x13802F60`
gives `0xF60`, or **3,936 bytes**. Relative to the matched control,
the attempted span grew by 12,128 − 6,708 = **5,420 bytes**, against
8,192 − 6,708 = **1,484 bytes** of headroom.

The accompanying overlap diagnostic places all 448 bytes of `.data` inside
the overrun, starting exactly at the executable limit. The parser converted
ld's inclusive overlap endpoints to exclusive ends and checked both ranges
against the map. The named section, region count and overlap describe one
boundary crossing. Counting the overlap again would overstate the excess.
[`attempted_ranges` and `overflow`][inspect]

## Relocatable objects and limits of the failed link

Summing the journal's `.text` rows for each object gives the following
pre-link totals. `partial_objects` groups the `arm-eabi-size -A` output by
section family, including function subsections. [Object measurement][build]

| Probe object | Relocatable executable bytes |
| --- | ---: |
| `netdisc.o` | 1,774 |
| `netdisc_net.o` | 3,268 |
| `netdisc_gate.o` | 16 |
| **Total** | **5,058** |

The 5,058 object bytes and 5,420 bytes of attempted growth measure different
things. The latter includes the effect of linking the whole modified DIP.
The 362-byte difference cannot be assigned to particular retained functions,
helpers, veneers or padding from the journal.

Without a modified original ELF, there is no final LOAD or static RAM span,
retained-path acceptance, veneer inventory or complete stack requirement.
The absence of a RAM overflow diagnostic leaves RAM fit open. The run also
provides no runtime evidence for IOS permissions, IPC, networking, deadlines
or recovery. [ADR 0005 acceptance and stop conditions][adr]

## Consequence for R0-03

This measurement rules out the reviewed complete probe in the stock executable
region with the measured inputs and flags. Other direct-DIP designs remain
unmeasured. **Investigate separate IOS service placement next.** Determine
what a bounded DIP request and reply would cost within the 1,484-byte stock
headroom, then examine the service's memory and stack needs, startup identity,
IPC permissions, buffer ownership and scheduling across handoff. Service
placement remains a research recommendation. Architecture selection and
implementation require a separate decision. R0 remains open and the hardware
recovery gate remains closed. [Transport ownership comparison][ownership] ·
[Feasibility plan](feasibility-plan.md)

[adr]: ../docs/decisions/0005-experimental-dip-sizing-link.md
[run]: https://github.com/lloydsmart/wii-netdisc/actions/runs/46073829896
[job]: https://github.com/lloydsmart/wii-netdisc/actions/runs/46073829896/job/140756822383
[artifact]: https://github.com/lloydsmart/wii-netdisc/actions/runs/46073829896/artifacts/15234067228
[workflow]: https://github.com/lloydsmart/wii-netdisc/blob/cd9c9357116f9ac927f159060c93546a4d8d8194/.github/workflows/experimental-dip.yml
[collector]: https://github.com/lloydsmart/wii-netdisc/blob/cd9c9357116f9ac927f159060c93546a4d8d8194/scripts/experimental_dip_evidence.py#L128-L190
[prepare]: https://github.com/lloydsmart/wii-netdisc/blob/cd9c9357116f9ac927f159060c93546a4d8d8194/scripts/stock_dip_build.py#L43-L118
[d2x]: https://github.com/wiidev/d2x-cios/tree/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7
[build]: https://github.com/lloydsmart/wii-netdisc/blob/cd9c9357116f9ac927f159060c93546a4d8d8194/scripts/experimental_dip_build.py
[inspect]: https://github.com/lloydsmart/wii-netdisc/blob/cd9c9357116f9ac927f159060c93546a4d8d8194/scripts/experimental_dip_inspect.py
[stock]: d2x-build-baseline.md#hosted-measurement-25-november-2026
[ownership]: r0-02-r0-03-ios57-v5918-network-lifecycle.md#r0-03--which-caller-would-own-the-connection
