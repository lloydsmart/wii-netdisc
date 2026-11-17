# Repository conventions review

Inspected on **17 November 2026** through the GitHub connection. This review covers
the named repositories and selected relevant files at the revisions below; it is
not a complete security audit. No GitHub state was changed.

This is a snapshot from before publication. The setup-state statements and
remaining decisions below describe that point in time. For current contribution
and reporting guidance, see [CONTRIBUTING.md](../CONTRIBUTING.md),
[SECURITY.md](../SECURITY.md) and the [code of conduct](../CODE_OF_CONDUCT.md).

## Inspected revisions

| Repository | Default branch | Revision |
| --- | --- | --- |
| [retromount](https://github.com/lloydsmart/retromount/tree/9846a41edb82320594ef817ec1604a83db0664c2) | develop | `9846a41edb82320594ef817ec1604a83db0664c2` |
| [chdtool](https://github.com/lloydsmart/chdtool/tree/aaa588f59aeeea54ad6aba659610e73f7e6f94fa) | develop | `aaa588f59aeeea54ad6aba659610e73f7e6f94fa` |
| [chd2iso-fuse](https://github.com/lloydsmart/chd2iso-fuse/tree/001be525309154d1bbba6038d8fa2e6432a3e9c8) | develop | `001be525309154d1bbba6038d8fa2e6432a3e9c8` |
| [aruba-cert-renewer](https://github.com/lloydsmart/aruba-cert-renewer/tree/e1b14489b3ca031b81c464685b0d7ec63b6bf8bb) | main | `e1b14489b3ca031b81c464685b0d7ec63b6bf8bb` |
| [unifi-cert-renewer](https://github.com/lloydsmart/unifi-cert-renewer/tree/39016f5ea2aeb6fc161ee49d135437e40b1f1b58) | main | `39016f5ea2aeb6fc161ee49d135437e40b1f1b58` |

## Patterns and differences

| Area | Observed conventions | Wii NetDisc treatment |
| --- | --- | --- |
| Branches | Disc utilities integrate on develop and promote to main; renewers use main/topic branches | Owner selected develop/main |
| CI | Markdown and Actions lint recur; language checks reflect actual source | One small documentation/hygiene/workflow job |
| Actions | Newer workflows pin SHAs and use read-only permissions; chd2iso-fuse also uses version tags | Immutable Action SHAs and actionlint image digest |
| Markdown | Disc utilities disable MD013; renewers use 120-character lines | MD013 disabled; normal prose wrapped for review |
| Gitignore | Editor, cache, generated output and project-specific private files | Small research-focused list, including local archive and console/disc payloads |
| Docs | README/contributor/security/release material varies with maturity | README, CONTRIBUTING, AGENTS, research, boundaries and ADRs |
| ADRs | RetroMount has numbered architecture ADRs; no ADR directory in the other inspected trees | Small numbered decision directory |
| Agent rules | AGENTS.md in both renewers; absent from the complete inspected disc-utility trees | Explicit local research and approval instructions |
| Licence | Full GPLv3 across all five; Rust metadata explicitly says GPL-3.0-only | Owner confirmed GPL-3.0-only |
| Releases | Mature projects have packaging, signing, promotion or container workflows | Deferred until an implementation and release need exist |

Representative evidence:

- RetroMount: [contributing](https://github.com/lloydsmart/retromount/blob/9846a41edb82320594ef817ec1604a83db0664c2/CONTRIBUTING.md),
  [boundaries](https://github.com/lloydsmart/retromount/blob/9846a41edb82320594ef817ec1604a83db0664c2/docs/architecture/boundaries.md),
  [ADRs](https://github.com/lloydsmart/retromount/blob/9846a41edb82320594ef817ec1604a83db0664c2/docs/architecture/README.md),
  [Markdown checks](https://github.com/lloydsmart/retromount/blob/9846a41edb82320594ef817ec1604a83db0664c2/.github/workflows/lint-docs.yml).
- chdtool: [contributing](https://github.com/lloydsmart/chdtool/blob/aaa588f59aeeea54ad6aba659610e73f7e6f94fa/CONTRIBUTING.md),
  [release flow](https://github.com/lloydsmart/chdtool/blob/aaa588f59aeeea54ad6aba659610e73f7e6f94fa/RELEASING.md),
  [Actions checks](https://github.com/lloydsmart/chdtool/blob/aaa588f59aeeea54ad6aba659610e73f7e6f94fa/.github/workflows/lint-actions.yml).
- chd2iso-fuse: [Git Flow](https://github.com/lloydsmart/chd2iso-fuse/blob/001be525309154d1bbba6038d8fa2e6432a3e9c8/RELEASING.md),
  [CI](https://github.com/lloydsmart/chd2iso-fuse/blob/001be525309154d1bbba6038d8fa2e6432a3e9c8/.github/workflows/ci.yml),
  [security checks](https://github.com/lloydsmart/chd2iso-fuse/blob/001be525309154d1bbba6038d8fa2e6432a3e9c8/.github/workflows/security-audit.yml).
- Aruba: [agent rules](https://github.com/lloydsmart/aruba-cert-renewer/blob/e1b14489b3ca031b81c464685b0d7ec63b6bf8bb/AGENTS.md),
  [CI orchestrator](https://github.com/lloydsmart/aruba-cert-renewer/blob/e1b14489b3ca031b81c464685b0d7ec63b6bf8bb/.github/workflows/pull-request-ci.yml).
- UniFi: [contributing](https://github.com/lloydsmart/unifi-cert-renewer/blob/39016f5ea2aeb6fc161ee49d135437e40b1f1b58/CONTRIBUTING.md),
  [agent rules](https://github.com/lloydsmart/unifi-cert-renewer/blob/39016f5ea2aeb6fc161ee49d135437e40b1f1b58/AGENTS.md).

## Live protections versus written policy

Both renewers currently have active default-branch rules requiring PRs, resolved
conversations, signed commits, strict/up-to-date `Required CI gate`, a CodeQL
medium-or-higher threshold, and no force pushes or deletion. They require zero
approvals and expose no bypass actors. Their `v*` tag rules prohibit updates and
deletion. The older `docs/ci-gate-policy.md` descriptions do not fully match this
live state.

Sources: [Aruba main](https://github.com/lloydsmart/aruba-cert-renewer/rules/21924705),
[Aruba tags](https://github.com/lloydsmart/aruba-cert-renewer/rules/21924739),
[UniFi main](https://github.com/lloydsmart/unifi-cert-renewer/rules/22136773),
[UniFi tags](https://github.com/lloydsmart/unifi-cert-renewer/rules/22136780).

RetroMount reports main/develop as protected, but its ruleset list is empty and
the detailed branch-protection API was inaccessible (403). Requirements are
therefore unknown. chd2iso-fuse has an active
[main/develop deletion and force-push protection rule](https://github.com/lloydsmart/chd2iso-fuse/rules/22981093);
four older rulesets are disabled. Its detailed protection API also returned 403.

chdtool reports main/develop as protected. Its visible
[active ruleset](https://github.com/lloydsmart/chdtool/rules/7712858) prevents deletion
and non-fast-forward updates on the default branch and allows an admin-role bypass.
This is not evidence of all legacy branch-protection requirements.

Checked-in hooks in RetroMount and the renewers block direct long-lived-branch
commits, but their presence does not prove local installation. No hooks or Git
configuration were installed here.

## Minimal baseline selected

- Complete GPLv3 text with an explicit GPL-3.0-only project declaration.
- UTF-8/LF conventions, scoped ignore rules and preservation of the local JSON.
- Markdown lint, actionlint and a standard-library repository hygiene check.
- One stable `Repository checks` job without path filters; read-only token,
  credentials not persisted, explicit timeout and cancellation of superseded runs.
- Weekly grouped GitHub Actions updates targeting develop.
- A focused PR template, evidence labels, architecture boundaries and two ADRs.

Action pins are taken from the inspected current renewer/chdtool workflows.
Markdownlint Action v25.0.0 embeds
[markdownlint-cli2 0.24.0](https://github.com/DavidAnson/markdownlint-cli2-action/blob/696eb3f2509270d7b882d2aa68347bc676e7af34/package.json).
The actionlint image is version/digest pinned. Its digest needs deliberate review
when updated; it is not assumed that Dependabot will refresh every Docker reference.

The full LICENSE is the unmodified Ubuntu
`/usr/share/common-licenses/GPL-3` text, SHA-256
`3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`.

No application source, language manifest, dummy test, build job, CodeQL job,
container deployment, release automation or speculative hardware test is included.
The validator checks hygiene and payload filenames; it is not a content secret
scanner. Publication review remains necessary.

Do not copy the reference repositories' stale security contact addresses,
unverified support promises, ignored-but-tracked Cargo.lock behaviour, or generated
package files. Their maturity-specific tooling is not a requirement for this project.

## Remaining decisions

The owner has confirmed GPL-3.0-only and develop/main, and requires every commit
to be signed with their GPG key. On 17 November 2026, the owner authorised the
initial signed commit on main and creation/switching to develop, excluding the
raw archive and with no push.

Before publication:

1. Choose whether/where to create a GitHub repository, its visibility and remote.
   None is currently configured locally.
2. Decide PR review, merge rules and remote enforcement of GPG signing. Suggested
   starting point: protect
   both long-lived branches against deletion/force pushes, require PRs and resolved
   conversations, and require `Repository checks` after a real run establishes its
   check name. No protections are currently configured by this skeleton.
3. Choose a real private security-reporting channel before public publication.
4. Approve a separate source-research task, then review its proposed technical ADR
   before implementation, devkitPro setup or hardware/cIOS work.

The bootstrap authorisation does not authorise pushing, remote creation, settings
changes or deletion. Further consequential work requires explicit permission.

## Local validation before bootstrap

Completed on 17 November 2026, before the initial commit:

- Repository hygiene, licence integrity and local Markdown file links: passed for 20 scaffold files.
- markdownlint-cli2 0.24.0: passed for all 12 Markdown files, including the GitHub template.
- actionlint 1.7.12: passed for the prepared workflow.
- Independent read-only review: no substantive defect; one test-scope wording inconsistency corrected.
- Historical JSON checksum unchanged; archive remains local and ignored.
- Git was unborn main, with no staged files, commits or configured remotes.

Validators ran locally, with Markdown/workflow linters in temporary containers using
read-only repository mounts. No GitHub Actions run or upstream feasibility/hardware
test was performed. No devkitPro or cIOS was installed.
