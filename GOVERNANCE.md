# Governance

## Project stewardship

EgoFlow Python Client is maintained by the EgoFlow GitHub organization. Organization owners
designate maintainers, repository administrators, security coordinators, and release managers.

## Contributions and decisions

Routine decisions are made through public Issues and pull requests. Maintainers seek consensus and
record material API, compatibility, dependency, security, privacy, and release decisions in
repository documentation. When consensus is not possible, the maintainers responsible for the
affected area make the decision and record the rationale.

Contributions use the repository's MIT License and the [Developer Certificate of Origin 1.1](DCO).
Every contributed commit must include a `Signed-off-by` line created with `git commit -s`. The
sign-off is a public, persistent record of the certification in `DCO`.

At least one maintainer approval, DCO sign-off, and passing required checks are expected before
merge. Public API, server-contract, dependency, cache, token, and data-handling changes receive
explicit compatibility and security review.

## Releases

PyPI `ego-flow==0.0.1` is already immutable. Its packaged code, metadata, and included documents are
frozen during the current repository-policy work; new governance, security, support, CI, and SBOM
files must remain outside the wheel and sdist. Any required packaged-content change triggers a new
version decision.

Release managers verify tests/builds, compatibility, license, SBOM data, security findings,
documentation, and artifact hashes. The Git candidate is finalized as a single `v0.0.1` commit;
`main`, the `v0.0.1` branch, and the annotated tag must identify the reviewed tree.

## Changes to governance

Propose governance changes through a public Issue and pull request unless doing so would disclose a
security or conduct matter. Material changes require maintainer consensus and a documented reason.
