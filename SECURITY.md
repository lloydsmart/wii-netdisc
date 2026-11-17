# Security policy

## Project status and supported versions

Wii NetDisc is a research-stage project. There is no application implementation,
supported software release, supported build or verified hardware compatibility.

Security reports about the repository are still welcome, including its validation
scripts, GitHub Actions workflows, exposed sensitive information, or instructions
that could cause harm. Include the affected commit and file; a report does not
need to concern the latest commit to be useful. There are no release branches
receiving security maintenance.

The repository checks validate documentation and workflow hygiene. They are not a
security audit or evidence that the proposed Wii architecture is safe or feasible.

## Reporting a vulnerability

Use [GitHub's private vulnerability reporting](https://github.com/lloydsmart/wii-netdisc/security/advisories/new)
for this repository. You can also find **Report a vulnerability** under
**Security and quality → Advisories**. Private reporting is enabled.

Do not disclose suspected vulnerabilities, exploit details or sensitive
information in a public issue, pull request or discussion.

Please include:

- The affected commit, file and relevant environment.
- The problem, its likely impact and any prerequisites.
- Steps to reproduce it safely, preferably using synthetic data.
- Sanitised logs or a minimal example, if useful.

Do not include real credentials, private keys, personal information, disc images,
console dumps or the raw historical conversation archive. If a credential appears
to be exposed, identify its location without copying the secret into the report.

## Handling reports

Lloyd Smart reviews reports on a best-effort basis. There is no guaranteed
acknowledgement, fix deadline or security-maintenance period.

Use the private report to discuss findings, remediation and coordinated public
disclosure. Reporter credit should be agreed before publication.

## Other questions and concerns

Use [GitHub issues](https://github.com/lloydsmart/wii-netdisc/issues) for ordinary
research questions and documentation problems that do not disclose security or
private information. Report conduct concerns using the private contact in the
[code of conduct](CODE_OF_CONDUCT.md).
