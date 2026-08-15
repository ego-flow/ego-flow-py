# Security Policy

## Supported versions

The published `ego-flow==0.0.1` package and its corresponding release source receive best-effort
security review. This pre-1.0 project does not promise a fixed support lifetime or response SLA.

## Report a vulnerability privately

Do not open a public Issue for a suspected vulnerability.

1. Use [GitHub private vulnerability reporting](https://github.com/ego-flow/ego-flow-py/security/advisories/new).
2. If GitHub private reporting is unavailable, email <egoflow3@gmail.com> with the subject
   `[SECURITY][ego-flow-py]`.

Include the affected version, Python and operating-system versions, server context, prerequisites,
reproducible steps, impact, and a minimal proof of concept. Redact tokens, private endpoints,
repository names, recordings, dataset contents, and logs. Do not attach an unredacted recording or
dataset; ask the maintainers to arrange an appropriate transfer only if it is essential.

The maintainers aim to acknowledge a complete report within five business days, validate and
prioritize it, coordinate a fix and disclosure, and credit the reporter when requested and safe.

## In-scope examples

- sending a bearer token to an unintended origin;
- unauthorized access to repositories, artifacts, recordings, or live streams;
- unsafe URL, redirect, cache-path, media, or dataset handling;
- secret or personal-data exposure through errors, logs, configuration, or caches;
- dependency behavior that makes a documented client workflow exploitable.

Requests for credentials, attempts to access other users' data, denial-of-service testing against
shared infrastructure, social engineering, and publication before a fix is available are not
authorized by this policy.

Server-side vulnerabilities should be reported to the
[EgoFlow Server private channel](https://github.com/ego-flow/ego-flow-server/security/advisories/new).
