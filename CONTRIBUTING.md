# Contributing

The project currently accepts research, documentation and repository-quality work.
Keep changes focused, explain their purpose and distinguish evidence from proposals.
Follow the [code of conduct](CODE_OF_CONDUCT.md) when participating.

## Branch strategy

The owner selected `develop`/`main` on 17 November 2026, following the disc utility
repositories. Use short-lived `research/`, `docs/`, `chore/` or, once authorised,
`feature/` and `fix/` branches from `develop`. Target ordinary pull requests at
`develop`. Promote reviewed release work to `main` when releases exist.

Bootstrap starts with an explicitly approved, GPG-signed initial commit on `main`.
Create `develop` from that same commit afterwards, and use it for integration.
Creating either branch on GitHub, selecting the default branch and setting
protections are separate actions. Nothing in this document grants standing
authorisation for an agent to commit, push or change settings.

Commits we create locally must be signed with Lloyd Smart's GPG key, including
the initial commit. Verify the signature after creating a commit. GitHub-generated
merge commits and Dependabot commits may use their own verified signatures.
Never fall back to an unsigned commit if signing fails.

Keep commit messages clear and focused. Conventional Commit prefixes are useful,
but no mandatory title checker or DCO requirement has been added.

## Research contributions

Follow [the evidence method](research/README.md). Include pinned source references,
limitations and reproducible observations. Record consequential architecture choices
as proposed [ADRs](docs/decisions/README.md).

The raw conversation archive stays local and ignored until it has been reviewed
for private information, third-party content and relevance. Retain it unchanged.
Publish only independently checked findings and reviewed excerpts with provenance.

Do not contribute disc images, copyrighted game assets, firmware/console dumps,
private keys or credentials. Original project contributions use GPL-3.0-only;
review upstream licences before copying code or bundling dependencies.

## Local checks

Run from the repository root:

```sh
python3 scripts/check-repository.py
markdownlint-cli2
actionlint
```

The Python check uses only the standard library and includes visible untracked
files, so it also works before the initial commit. It checks text hygiene, JSON,
the canonical licence, local Markdown file links and excluded payload paths.
It does not scan file contents for secrets or validate technical claims.

Use markdownlint-cli2 0.24.0 and actionlint 1.7.12 to match the prepared CI baseline.
The Markdown configuration includes the hidden GitHub templates.
Run validators from a trusted installation or a temporary tool container; there is
no need to install Wii tooling. Changes to CI tool versions should keep these
instructions aligned.

CI runs one `Repository checks` job automatically when:

- A pull request targeting `develop` or `main` is opened, reopened or updated with new commits.
- A commit is pushed to `develop` or `main`, including a pull-request merge.

Pushing a topic branch alone does not trigger CI; opening or updating its pull
request does. Manual dispatch is available for diagnostics, but a successful
manual run does not verify the automatic push or pull-request triggers.

There are no path filters, write token permissions, deployment steps or hardware
access. Both long-lived branches require an up-to-date `Repository checks` result
from GitHub Actions before merging. This is a documentation baseline, not a
release or security certification.

## Questions and reports

Use [GitHub issues](https://github.com/lloydsmart/wii-netdisc/issues) for research
questions, documentation problems and suggestions. Check existing issues first
and include the relevant file, commit or source reference.

Report suspected vulnerabilities privately using [SECURITY.md](SECURITY.md).
For conduct concerns, use the private contact in the
[code of conduct](CODE_OF_CONDUCT.md). Keep sensitive information out of public
issues and pull requests.
