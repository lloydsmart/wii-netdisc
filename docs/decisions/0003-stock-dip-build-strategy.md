# ADR 0003: Use Make and authorise PC-only stock DIP measurement

- Status: Accepted
- Date: 2026-11-25
- Decision owner: Lloyd Smart
- Basis: Explicit owner decision under [ADR 0001](0001-research-first.md).

## Context

The [stock DIP baseline](../../research/d2x-build-baseline.md) verified the public
inputs and identified an 8 KiB executable region. The attempted container run
stopped before compilation. Measuring stock occupancy will inform R0-03 and R0-05.

## Decision

Make is the public build interface. The subsequent task may add minimal shared
Make targets and supporting scripts. Document the prerequisites so local users
can run `make` with a compatible toolchain they already have. Keep compilation
independent of GitHub Actions and separate from packaging and hardware installation.

GitHub Actions is the preferred automated build environment. A dedicated stock
DIP measurement workflow may use an ephemeral GitHub-hosted Ubuntu 24.04 runner.
The workflow YAML provisions the environment, installs required public build
dependencies on the runner, invokes Make, validates results and collects
artifacts. Pin action dependencies to full commit SHAs.

The compilation authorisation takes effect after review and merge of this
record. Actual runner operations require separate execution approval. The
subsequent task may:

1. Retrieve and verify unmodified public d2x revision
   `33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7` and the devkitARM r32
   Debian Buster archive with SHA-256
   `7ca6fafef13876e2e565b4421e2d240c4532c7f0d15f4ffe1e2ed3c485748cd6`.
2. Build stock DIP twice from fresh source extractions in the same prepared
   environment. Inspect and compare intermediate objects, archives, linker maps
   and ELFs. Use the original ELF and map to measure executable occupancy and
   remaining headroom as defined in the baseline.
3. Record resolved dependency versions, artifact hashes, build logs and observed
   experimental results. A hosted Ubuntu 24.04 label can resolve to different
   environments over time. The paired builds test same-environment repeatability.
   Cross-environment reproducibility remains a separate question.

Keep generated binaries and toolchains out of Git. Any workflow artifact
publication must follow existing provenance and artifact restrictions.

## Alternatives

Docker is optional. The project prefers hosted runners and will maintain custom
images, Dockerfiles or a container registry only if a concrete future requirement
justifies revisiting this decision.

## Consequences

The stock compilation task excludes installing toolchains or build dependencies on the local host,
privileged execution, sensitive host-directory mounts, changes to approval
settings and circumvention of execution restrictions. It excludes changes to
upstream source or USB Loader GX, experimental DIP networking and NBD implementation.

Proprietary IOS firmware, console keys, NAND backups, installable cIOS packages,
console installation and hardware access are outside the authorisation. The Wii
must remain powered off. R0 remains open. Occupancy and headroom remain unmeasured.

## Evidence

Owner decision of 25 November 2026 and the
[build baseline merged in PR #10](../../research/d2x-build-baseline.md).
