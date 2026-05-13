## Triggers

**Activate when:**
- Performing a structured code review
- Checking correctness, security, performance, and maintainability

---
# Review Checklist

> [!important]
> Work through these passes in order on every code review. Framework-agnostic.

---

## Pass 1: Correctness

- Does every requirement or plan step have corresponding code? Are any skipped or partial?
- Null/empty/zero: what happens when optional values are absent, collections are empty, or numbers are zero or negative?
- Boundary values: off-by-one in loops or slices? Inclusive vs exclusive ranges?
- Are all errors checked? No ignored return values, no empty catch blocks
- Are errors caught at the right level — not too early (swallowing context) and not too late (crashing the process)?
- Do error paths clean up resources? (connections, handles, locks released on failure)
- Is mutable state shared across threads/goroutines/async tasks without synchronization?
- Could a race condition exist between a check and a subsequent action? (TOCTOU)
- Are all opened resources (files, connections, streams) closed in all code paths, including errors?

## Pass 2: Security

- Does every endpoint that accesses data verify the current user is authorized for that specific resource — not just authenticated? (BOLA/IDOR)
- Are role/permission checks server-side, not just in the UI?
- Is user input concatenated into SQL, OS commands, templates, or HTML without parameterization or escaping? (injection)
- Is user input passed to eval(), exec(), system(), or similar?
- Are API keys, passwords, tokens, or connection strings hardcoded in source?
- Is sensitive data (PII, credentials, tokens) written to logs or error responses?
- Are error responses free of stack traces, file paths, and SQL?
- Does the code bind raw request bodies to internal models without whitelisting fields? (mass assignment)
- Does the code fetch a user-supplied URL without allowlist validation? (SSRF)
- Is data from untrusted sources deserialized unsafely? (pickle, YAML.load without safe_load, Java serialization)
- Is CORS overly permissive? Are security headers present (CSP, HSTS, X-Frame-Options)?
- Are dependencies pinned to specific versions?

## Pass 3: Performance

- Is there a database query, API call, or I/O operation inside a loop? (N+1 pattern)
- Does the code load an entire collection into memory without pagination or streaming?
- Is there an O(n^2) operation where O(n log n) or O(n) is achievable?
- Are there redundant queries or computations fetching the same data in the same request?
- Is anything computed but never used?
- If caching is added, is it invalidated correctly? Could it grow unboundedly?
- Are event listeners, timers, or subscriptions created without cleanup?

## Pass 4: Maintainability

- Do names describe purpose? Are they consistent with the codebase? (fetchUser everywhere, not getUserById in one place)
- Functions over 30 lines: can they be decomposed?
- Nesting deeper than 3 levels: extract the inner block
- Is there copy-pasted code that should be extracted? (But: premature abstraction is worse than duplication)
- Does the change create circular dependencies or import from a layer it shouldn't?
- Is there commented-out code, dead code, or TODOs without a ticket reference?

## Pass 5: Testing

- Does every new public function/endpoint have at least one test?
- Do tests assert on behavior (what it does), not implementation (how it does it)?
- Are edge cases tested — empty input, error conditions, authorization failures?
- Does every test assert something meaningful — not just "it doesn't throw"?
- Were existing tests modified? If so, were assertions weakened to make them pass? (masking regressions)

## Pass 6: API Compatibility (when the change affects an API)

- Are any existing fields removed, renamed, or type-changed? (breaking)
- Are any previously optional fields now required? (breaking)
- Is the endpoint naming consistent with existing patterns?
- Is the error response format consistent with the rest of the API?

## Pass 7: Change Hygiene

- Is the change about one thing? (one feature, one fix, or one refactor — not all three)
- Are there unrelated "while I was here" changes? (separate them)
- Are there temporary workarounds with no removal plan?
- Do commit messages describe why, not just what?
