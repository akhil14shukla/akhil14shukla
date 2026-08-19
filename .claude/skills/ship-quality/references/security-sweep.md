# Security and safety sweep

Read this before committing anything that touches input handling,
authentication, money, personal data, or a new dependency.

Run through this before committing anything that touches input handling,
authentication, money, personal data, or a new dependency. Most items take
seconds to check and are expensive to miss.

## The sweep

Most of these take seconds to check and are expensive to miss.

- **Secrets**: no keys, tokens, passwords, connection strings, or private keys
  in the diff — including in tests, fixtures, comments, and example config.
  `git diff | grep -Ei "api[_-]?key|secret|password|token|BEGIN .*PRIVATE KEY"`
  is a cheap first pass. If a secret was ever committed, it must be **rotated**,
  not just removed — the history keeps it.
- **Injection**: parameterised SQL only, never string-built queries. No shell
  command built from user input (`shell=True`, string concatenation into
  `exec`). No `eval` of anything that came from outside.
- **Input validation at the boundary**: every external input — request bodies,
  query params, file uploads, webhook payloads, environment — is validated
  before use, with size limits.
- **Authorisation on every path**: not just the UI, and not just the happy path.
  Check that the *object* belongs to the requesting user, not merely that the
  user is logged in — the most common real vulnerability is a missing ownership
  check on an id from the URL.
- **Output**: no personal data, tokens, or full payloads in logs or error
  messages returned to callers. Escape anything rendered into HTML.
- **Dependencies**: if you added one, is it maintained, popular enough to be
  scrutinised, appropriately licensed, and pinned in the lockfile?
- **Resource limits**: pagination on anything that can grow, timeouts on every
  network call, bounded concurrency, bounded caches, a size limit on uploads.
