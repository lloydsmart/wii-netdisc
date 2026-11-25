# Unmodified d2x DIP build baseline for IOS57 v5918

**R0-03 / R0-05, 24 November 2026. Build blocked before compilation.**
The pinned linker script gives DIP 8,192 bytes for executable code. The number
of bytes available to the proposed probe remains **unmeasured**. The PC run
verified the source and toolchain inputs. Automatic approval review rejected
the Docker invocation that would install container dependencies and execute the
upstream build, citing the repository's research-stage toolchain and execution
restrictions. There were no compiler, linker or stripios diagnostics. Neither
clean build ran, so there are no output sizes, hashes or reproducibility result.
The [IOS57 experiment plan](ios57-baseline-plan.md) remains at its build gate.

**25 November 2026 update.** [ADR 0003](../docs/decisions/0003-stock-dip-build-strategy.md)
selects Make and a GitHub-hosted runner as the preferred approach, superseding
the container recipe below. The recipe and pending-decision wording record the
blocked 24 November attempt. The ADR sets the conditions for a subsequent run.

## Run the stock measurement

From the Wii NetDisc repository root, use a normal x86-64 Linux account and
an independently provisioned Buster devkitARM r32 installation. The shared
target needs Python 3.11+, Git, GNU Make 4+, native g++, GNU tar, diffutils,
binutils, glibc/ldd and the host libraries listed below. On Ubuntu 24.04 the
runtime packages are libfl2, libelf1t64, libmpc3, libmpfr6, libgmp10 and zlib1g.
Use absolute paths and a toolchain path without whitespace (upstream Makefile
constraint). The original release archive serves as the installation reference.

```sh
set -eu
scratch=$(mktemp -d /tmp/stock-dip.XXXXXXXX)
git init -q "$scratch/d2x"
git -C "$scratch/d2x" fetch --depth=1 --no-tags https://github.com/wiidev/d2x-cios.git \
  33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7
release=https://github.com/Leseratte10/compile-devkitARM-r32/releases/download/2020-02-20
curl -fLsS "$release/devkitARM-r32-linux_debian-buster.tar.gz" -o "$scratch/r32.tar.gz"
DEVKITARM=/opt/devkitARM D2X_REPO="$scratch/d2x" R32_ARCHIVE="$scratch/r32.tar.gz" \
  WORK_DIR="$scratch/measurement" make stock-dip-baseline
```

Point `DEVKITARM` at the existing installation. The target generates the selected
source tar from the pinned Git object in `D2X_REPO`, checks the tree, epoch and
both archive hashes, then extracts r32 in scratch. It compares the installation
to those verified files before invoking any r32 program. With `DEVKITARM`
unset, the hosted runner uses that private extraction directly. `WORK_DIR`
must be a fresh path outside the input trees and Wii NetDisc, with an existing
parent. Supply the root of the upstream worktree as `D2X_REPO`. The target
resolves symlinks and checks the worktree and Git directories before creating
output. It checks executable permissions and shared libraries for gcc, cc1,
collect2 and the required binutils. The driver's resolved cc1, collect2,
assembler and linker paths must identify executable files in the verified tree. A mismatch stops preparation. Use the recorded Git 2.43.0 archive as
the reference when investigating a source tar mismatch.

Both fresh builds retain their binaries in scratch. Each original ELF is
checked against its map and load segments independently of the byte comparison.
The occupied span ends at the highest nonempty allocated section in the
executable region. The check reconciles nonempty map outputs with ELF sections,
including non-allocated sections, and checks the placement of the stock sections
against [the pinned linker script][layout]. Memory-only BSS must reside in RAM
and be clear of file-backed load bytes. A segment can include padding between
sections. An unexplained load extent in the proposed headroom or a contradictory
map entry fails measurement before the report gives a headroom figure. Actual
r32 section placement and map formatting await the approved build.
Review `WORK_DIR/evidence/result.txt`, the two footprint reports, maps, ELF
listings, build logs, sorted path inventories, sizes, SHA-256 hashes and the
comparison log. Preparation records the tool versions, resolved shared libraries
and, on Debian-family systems, installed package versions. A partial run can
leave partial evidence. A nonzero Make exit requires inspection of the logs.
The paired builds measure repeatability within the recorded environment.
Any trailing executable space is a linker measurement. DI caller stack, heap,
IPC permissions and runtime behaviour still require independent evidence.

To check the measurement logic with synthetic data, run
`python3 -B -m unittest discover -s tests -p 'test_stock_dip.py' -v`.

### Hosted initiation and evidence

The remote's default branch was verified as `develop` on 25 November 2026.
GitHub requires the manually dispatched workflow to exist on the default
branch. The first run therefore requires a separately reviewed and authorised
merge of the [measurement workflow](../.github/workflows/stock-dip.yml) to
`develop`. PR events, pushes and the merge itself do not start compilation.
[GitHub dispatch event](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)

For each separately authorised execution, the owner reviews the exact current
`develop` commit, including the workflow and its build and publication scripts.
Select **Run workflow** on `develop` and enter that commit's full lowercase
40-digit SHA in `approved_sha`. The job checks the repository, owner, event,
branch, first attempt, workflow path, workflow commit and event commit before
checkout. It checks the detached checkout against the same input before
provisioning. A moved branch requires review of the new tip and a fresh
dispatch. For a subsequent attempt at the same tip, dispatch again with its
approved SHA. GitHub reruns increment the attempt counter and fail the gate.
[GitHub workflow variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables)

These checks rely on GitHub's event metadata, control of the owner's account
and review of code accepted on `develop`. Someone able to replace that
workflow can also replace its checks. This procedure requires no approval
variable, environment or change of repository settings.

The hosted Ubuntu 24.04 runner retains provisioning diagnostics in the job log.
On success or failure after checkout verification, a collector selects only the
named runner, preparation, build, inventory, comparison and measurement reports.
It checks the actual bytes for printable UTF-8 text and permitted whitespace,
and checks maps against the original ELF again. A rejected file fails collection
while valid diagnostics remain eligible. Only the collector's fresh directory
is uploaded as `stock-dip-evidence` (run ID and attempt) for 30 days. Original
inputs and compiled artifacts stay in runner scratch.
Review and record experimental numbers here following an approved run.

## Inputs inspected on the PC

| Experimentally verified input | Identity |
| --- | --- |
| Wii NetDisc base | `5d6241a2c9d4b80d04eb44c73b1283862bc9874e`, PR #9 merge at fetched `origin/develop` |
| Public d2x checkout in scratch | `33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7`, tree `b8e661b6535beb1d777ac21d25d25623bb5f0668`, clean detached HEAD |
| Selected source tar from Git 2.43.0 | 327,680 bytes, SHA-256 `b6c8bd6cbe179a7155879fa3eace86af475fe80146b7bab9f2647f6f2303575c` |
| devkitARM r32 Debian Buster archive | 35,805,906 bytes, SHA-256 `7ca6fafef13876e2e565b4421e2d240c4532c7f0d15f4ffe1e2ed3c485748cd6` |
| Container selected and pulled | Docker Engine 29.1.3 on x86-64 WSL2, Ubuntu 24.04 image digest `sha256:562111b88caa79c71391c0c4d3c2114a7d5c35915c20561fd893cb1e07929e6b` |

**Tool versions.** The downloaded archive identifies GCC **4.5.1** and GNU
binutils **2.20.1.20100303** in its binaries. Static inspection of the compiler
found the target `arm-eabi` and package label `devkitARM release 32`. The archive
contains a Thumb big-endian libgcc multilib. The multilib’s `crtbegin.o` has ELF32
big-endian ARM EABI version 5 flags. The DIP recipe omits startup files. Its own ELF
attributes still need measurement. The host-side `arm-eabi-ar` declares dependencies on
`libfl.so.2`, `libz.so.1` and `libc.so.6`. The archived C frontend
`libexec/gcc/arm-eabi/4.5.1/cc1` declares `libelf.so.1`, `libmpc.so.3`,
`libmpfr.so.6`, `libgmp.so.10`, `libdl.so.2`, `libz.so.1` and `libc.so.6`
in its ELF dynamic section. Ubuntu 24.04 supplies `libelf.so.1` in
`libelf1t64`. These are static observations. Dependency resolution in the
proposed container remains unverified. No downloaded program was executed.
The SHA-256 above identifies the retrieved bytes. The release API supplied
neither an asset digest nor a separate checksum asset. [Toolchain release][release]

## Public build path

- **Source-verified, CI.** The upstream workflow downloads the Buster **ARM**
  archive despite its step label saying PPC. It builds stripios with native
  `g++`, installs `libfl2`, then calls the distribution driver on
  `ubuntu-latest`. The native compiler, make and Ubuntu package versions are
  unpinned. Ubuntu 24.04 was the local selection. Exact native dependency
  versions would need to be recorded in a running container. [CI build job][ci]
- **Source-verified, compile and link.** Both Makefiles default `DEVKITARM` to
  `/opt/devkitARM`. GCC targets ARM926EJ-S (ARMv5TEJ), Thumb with ARM/Thumb
  interworking, big-endian. It compiles freestanding C with `-Os`,
  `-ffunction-sections` and `-fno-builtin`, and preprocesses the assembly.
  DIP's entry stub uses ARM instructions. The library build archives its
  objects, including libwbfs, with `arm-eabi-ar rcs`. DIP links through the
  GCC driver with `cios-lib.a`, `-lgcc`, `link.ld`, section garbage collection,
  static linkage and no standard libraries or startup files. The link already
  emits both `dip-plugin.elf.orig` and `dip-plugin.map` with upstream flags.
  The commit timestamp supplies the date/time macros embedded in DIP's version
  string. [Library Makefile][lib] · [DIP Makefile][dip] · [Entry][start] · [main][main]
- **Source-verified, conversion and packaging boundary.** Native
  `stripios_src/main.cpp:main` reads the original ELF's program headers,
  turns the zero-address table into IOS headers, rewrites segment offsets and
  flags, and omits the section-header table. Its output is `dip-plugin.elf`.
  Compilation, linking and this conversion take only public inputs. The Linux
  driver's `do_make` then copies the converted ELF to `DIPP.app`;
  `make_modules` also builds other modules and prepares maps and distribution
  files. That staging can use public source too. The IOS57 v5918 map assigns
  the common DIPP to content ID `0x20`. The base selection happens downstream
  of this plugin build. Assembling a complete title needs original base
  contents and belongs outside this measurement. [stripios][strip] ·
  [Linux driver][driver] · [IOS57 map][map] · [Windows distribution path][dist]

The [earlier source investigation](r0-01-r0-02-source-investigation.md)
records the mixed per-file provenance of DIP and cios-lib. The native stripios
source carries a GPL-2.0-or-later notice. Only findings are included here.

## Executable and data budget

**Source-verified.** Ranges below are half-open. The linker aligns the end of
each named code and RAM output section to four bytes. Input alignment can
introduce further padding. [DIP linker script, MEMORY and SECTIONS][layout]

| Region | Start | Exclusive end | Capacity | Assigned sections |
| --- | ---: | ---: | ---: | --- |
| IOS table | `0x00000000` | `0x00004000` | 16 KiB | `.ios_info_table`, handled separately by stripios |
| Executable | `0x13800000` | `0x13802000` | 8 KiB | `.init`, `.text`, including interworking glue |
| RAM | `0x13802000` | `0x13842000` | 256 KiB | `.data`, `.rodata`, `.bss`, including kept `.ios_bss` |

- **Static RAM commitments.** The fragment list alone declares three 32-bit
  header fields and 20,000 triples of 32-bit fields (240,012 bytes of fields).
  Its index declares another 640 16-bit entries (1,280 bytes). Both are
  zero-initialised. These source counts explain why a 256 KiB RAM region gives
  a misleading impression of spare capacity. Placement, padding and total
  retained BSS await the map. [FragList][fragh] · [fraglist_data and frag_idx][frag]
- **Stack and heap.** The module startup record declares a 4,096-byte
  descending stack and reserves it in `.ios_bss`. The proposed read probe
  runs on the hooked DI caller. Its stack extent, high-water mark and remaining
  call depth are unknown. Existing reads request 32-byte-aligned buffers via
  the base-specific `DI_Alloc` function pointer. Neither the heap capacity nor
  its free space during a request follows from the linker RAM range.
  [Startup record][start] · [Patch_DipModule][patch] · [Frag_Init][fragalloc] ·
  [Caller and lifecycle](r0-02-r0-03-ios57-v5918-network-lifecycle.md)
- **Measurement still needed.** On the original ELF, find the highest
  exclusive end of every allocated section placed in `exe`, including glue,
  alignment and any linker-created sections. Subtract `0x13800000` for the
  occupied span and subtract that end from `0x13802000` for contiguous trailing
  headroom. Cross-check the map and load segments. Report RAM sections with
  their addresses, sizes and alignment, including memory-only BSS. The
  converted file size cannot supply these numbers.

## Reproduction

**Completed input preparation.** Run in Bash. Use Git, curl, tar and SHA-256 tools for retrieval,
plus native binutils for static inspection. Only the three public build directories enter the source tar.

```sh
set -eu
scratch=$(mktemp -d /tmp/netdisc-d2x.XXXXXXXX)
cd "$scratch"
rev=33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7
git init -q upstream
git -C upstream fetch --depth=1 --filter=blob:none --no-tags \
  https://github.com/wiidev/d2x-cios.git "$rev"
git -C upstream switch --detach FETCH_HEAD
test "$(git -C upstream rev-parse HEAD)" = "$rev"
git -C upstream archive --format=tar --output="$scratch/inputs.tar" \
  HEAD source/cios-lib source/dip-plugin stripios_src
release=https://github.com/Leseratte10/compile-devkitARM-r32/releases/download/2020-02-20
asset=devkitARM-r32-linux_debian-buster.tar.gz
curl -fsSL "$release/$asset" -o "$asset"
sha256sum -c <<SUMS
7ca6fafef13876e2e565b4421e2d240c4532c7f0d15f4ffe1e2ed3c485748cd6  $asset
b6c8bd6cbe179a7155879fa3eace86af475fe80146b7bab9f2647f6f2303575c  inputs.tar
SUMS

# Inspect archive contents as data, using the PC's strings and readelf.
tar -xOzf "$asset" devkitARM/bin/arm-eabi-gcc-4.5.1 | strings | grep 'gcc-4.5.1/configure'
tar -xOzf "$asset" devkitARM/arm-eabi/bin/ld | strings | grep -F '(GNU Binutils)' | sort -u
tar -xOzf "$asset" devkitARM/arm-eabi/bin/ar > ar-for-inspection
readelf -d ar-for-inspection
tar -xOzf "$asset" devkitARM/libexec/gcc/arm-eabi/4.5.1/cc1 > cc1-for-inspection
readelf -d cc1-for-inspection
tar -xOzf "$asset" devkitARM/lib/gcc/arm-eabi/4.5.1/thumb/be/crtbegin.o > thumb-be-example.o
readelf -h -A thumb-be-example.o
```

**Proposed container run, unexecuted.** The owner decision and runner approval
described below are prerequisites. This would measure build repeatability
across two fresh source extractions in one prepared container. The image is
digest-pinned, but APT resolves package versions at execution time. The
comparison cannot establish reproducibility across independently provisioned
environments. Both builds use
the upstream committer epoch (1742677801), and an unprivileged build user.
Only the two input archives enter from the host. The captured log includes
the native package versions, compiler messages, hashes and section evidence.

```bash
set -o pipefail
image=ubuntu@sha256:562111b88caa79c71391c0c4d3c2114a7d5c35915c20561fd893cb1e07929e6b
epoch=$(git -C upstream log -1 --format=%ct)
docker run --rm -i --platform linux/amd64 --security-opt=no-new-privileges \
  --mount "type=bind,src=$scratch/inputs.tar,dst=/inputs.tar,readonly" \
  --mount "type=bind,src=$scratch/$asset,dst=/r32.tar.gz,readonly" \
  -e SOURCE_DATE_EPOCH="$epoch" "$image" bash -se <<'CONTAINER' 2>&1 | tee build.log
export LC_ALL=C TZ=UTC DEVKITARM=/opt/devkitARM DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends g++ make libfl2 libelf1t64 libmpc3 libmpfr6 libgmp10 zlib1g
dpkg-query -W
tar -xzf /r32.tar.gz -C /opt
setpriv --reuid=1000 --regid=1000 --clear-groups --no-new-privs bash -se <<'BUILD'
p="$DEVKITARM/bin/arm-eabi-"
helpers="$DEVKITARM/libexec/gcc/arm-eabi/4.5.1"
for exe in "$helpers"/{cc1,collect2} "${p}"{gcc,as,ar,ld,readelf,nm,size}; do
  test -x "$exe"
  deps=$(ldd "$exe")
  printf '%s\n' "$exe" "$deps"
  if [[ $deps == *"not found"* ]]; then exit 1; fi
done
for tool in gcc as ar ld readelf nm size; do "${p}$tool" --version; done
umask 022
for run in a b; do
  mkdir "/tmp/$run"
  cd "/tmp/$run"
  tar -xf /inputs.tar
  g++ stripios_src/main.cpp -o stripios
  make -C source/cios-lib
  make -C source/dip-plugin STRIP=../../stripios
  # Paths are relative to each fresh extraction of the pinned source.
  set -o pipefail
  required=(stripios source/cios-lib/cios-lib.a source/dip-plugin/dip-plugin.{elf.orig,map,elf})
  inventory="/tmp/$run.paths"
  find . -type f \( -name '*.o' -o -path './stripios' -o -path './source/cios-lib/cios-lib.a' \
    -o -path './source/dip-plugin/dip-plugin.elf.orig' -o -path './source/dip-plugin/dip-plugin.map' \
    -o -path './source/dip-plugin/dip-plugin.elf' \) -printf '%P\n' | LC_ALL=C sort > "$inventory"
  while IFS= read -r f; do
    stat -c '%s %n' "$f"
    sha256sum "$f"
  done < "$inventory"
done
# Unified diff shows A-only paths with '-' and B-only paths with '+'.
diff -u /tmp/{a,b}.paths
test -s /tmp/a.paths || { echo "empty artifact inventory" >&2; exit 1; }
# At this revision each C or assembly input in these directories has a required object.
shopt -s nullglob
for src in source/{dip-plugin,cios-lib,cios-lib/libwbfs}/*.{c,s}; do
  required+=("${src%.*}.o")
done
for f in "${required[@]}"; do
  test -f "$f" || { echo "missing required artifact: $f" >&2; exit 1; }
done
repeatability=0
while IFS= read -r f; do
  if cmp -s "/tmp/a/$f" "/tmp/b/$f"; then
    echo "identical $f"
  else
    status=$?
    case "$status" in
      1) echo "differs $f"; repeatability=1 ;;
      *) echo "comparison error ($status): $f" >&2; exit "$status" ;;
    esac
  fi
done < /tmp/a.paths
cd /tmp/a/source/dip-plugin
"${p}readelf" -h -SW -lW -A dip-plugin.elf.orig
"${p}nm" -nS dip-plugin.elf.orig
"${p}size" -A -x dip-plugin.elf.orig
"${p}readelf" -h -lW dip-plugin.elf
cat dip-plugin.map
exit "$repeatability"
BUILD
CONTAINER
```

## Implication and next task

**Hypothesis still open.** The 8 KiB executable limit sets a ceiling for the
existing DIP and any added code together. Until the stock link is measured,
the evidence supports neither a fit estimate for the one-shot TCP probe nor a
change of connection owner. Actual executable occupancy and headroom are unmeasured.
Neither stock build ran. Artifact repeatability, cross-environment reproducibility
and IOS57 runtime feasibility remain unverified. The hardware recovery gate remains closed.

**Proposed owner decision, pending.** The earlier owner brief requested a
stock PC-only DIP build. Standing R0 instructions restrict toolchain setup
and execution of upstream build scripts. ADR 0001 provides for a later
authorised toolchain task. A new attempt requires an explicit, scoped owner
decision under that ADR consistent with the governing instructions. Separately,
the execution environment rejected the Docker invocation. The actual runner
operation also needs approval, including on an alternative runner.
[Agent instructions](../AGENTS.md) · [R0 plan](feasibility-plan.md) ·
[ADR 0001](../docs/decisions/0001-research-first.md)

The proposed scope is to use the unmodified d2x revision and SHA-256-identified
r32 archive recorded above in an approved disposable environment. Perform two
clean stock builds, inspect and compare intermediate objects, archives, maps
and ELFs, and measure actual DIP executable occupancy and headroom. Keep
toolchains and binaries outside the repository. The proposal excludes host
toolchain installation, privileged containers, proprietary IOS inputs, cIOS
packaging or installation, experimental networking code and all Wii hardware
access.

[release]: https://github.com/Leseratte10/compile-devkitARM-r32/releases/tag/2020-02-20
[ci]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/.github/workflows/main.yml#L19-L49
[lib]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/Makefile
[dip]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/Makefile#L1-L59
[start]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/start.s#L20-L71
[main]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/main.c#L29-L40
[strip]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/stripios_src/main.cpp#L97-L339
[driver]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/maked2x.sh
[map]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/data/ciosmaps.xml#L250-L302
[dist]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/maked2x.bat#L90-L110
[layout]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/link.ld
[fragh]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/frag.h#L22-L40
[frag]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/frag.c#L32-L49
[patch]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/patches.c#L51-L146
[fragalloc]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/frag.c#L225-L266
