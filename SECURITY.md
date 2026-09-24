# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security or candidate-privacy vulnerability. Contact the
maintainer privately through the repository owner's GitHub profile and include reproduction steps,
affected versions, and likely impact. You should receive an acknowledgment within seven days.

Never include real API keys, resume contents, or candidate PII in a report. Rotate any credential
that may have been exposed. The project supports the latest release on the default branch.

## Threat model

JevMatch treats uploaded files and all extracted resume text as untrusted. Relevant attacks include:

- files whose extension does not match their content;
- malformed PDF/DOCX input intended to exploit or exhaust a parser;
- DOCX ZIP bombs, macros, embedded objects, XML entities, and unsafe package paths;
- PDF scripts, launch actions, embedded files, and rich media;
- white, hidden, tiny, off-page, bidirectional, or zero-width text intended to affect scoring;
- direct, obfuscated, or encoded instructions intended to manipulate the evaluator;
- non-resume documents submitted to consume model resources or pollute rankings;
- oversized requests, unbounded batches, and repeated expensive API calls.

The application does not need to execute document content. Original files are only retained when
the user explicitly enables saving, and they receive the same validation again when loaded.

## Implemented defenses

The controls are deliberately layered:

1. The API limits request bodies, files, inline text, PDF pages, resumes per match, and concurrent
   resume pipelines.
2. Ingestion allowlists PDF, DOCX, and UTF-8 TXT, verifies PDF/ZIP signatures, and rejects binary
   TXT input.
3. DOCX inspection limits member count, total expanded size, and compression ratio and rejects
   encrypted entries, unsafe paths, macros, embedded/active objects, and DTD/entity declarations.
4. PDF inspection rejects common active-content markers before parsing.
5. Extraction removes explicitly hidden/white/tiny/off-page PDF or DOCX text and strips Unicode
   format and unsafe control characters before redaction or model calls.
6. A deterministic scanner rejects high-signal evaluator-control instructions, including known
   instruction-override, role, score-manipulation, prompt-exfiltration, and base64 forms.
7. Remaining content goes through separate Jev `is_resume` and `prompt_injection` preflight
   questions. A failed check returns `status: rejected`; no requirements or evidence are scored.
8. Jev receives structured state that labels the resume as untrusted data. Every scoring,
   retrieval, and verification question repeats the rule not to follow document instructions.
9. Costly endpoints use per-client sliding-window rate limits and return HTTP `429` with
   `Retry-After` and rate-limit headers.
10. Rejected documents are displayed and exported as **not scored**, rather than as a misleading
    zero match score.

## Residual risk

No prompt-injection detector is perfect. A model-based guard can itself be attacked, and local
patterns can miss novel attacks or flag legitimate security experience. Model output must remain
advisory and reviewable.

The included parser checks are not antivirus, content disarm and reconstruction (CDR), or a process
sandbox. A vulnerability in `pdfplumber`, `pdfminer`, `lxml`, `python-docx`, or a transitive
dependency could still be exploitable before application checks complete. Rate-limit state is in
memory and is not shared between workers or servers. Client identity uses the direct peer address
and intentionally does not trust spoofable forwarding headers.

## Internet-facing deployment requirements

The default project is local-first and has no accounts. Before exposing it to untrusted users:

- require authentication and enforce per-user authorization for every saved resume;
- terminate uploads in an isolated service and scan with maintained antivirus and/or CDR;
- parse documents in a locked-down, resource-limited subprocess or container with no network;
- replace the in-memory limiter with an authenticated API gateway or Redis-backed distributed
  limiter and add concurrency, token, spend, and daily quotas;
- configure trusted-proxy handling explicitly instead of accepting arbitrary forwarded headers;
- use HTTPS, encrypted storage, retention/deletion policies, and access/audit logging that excludes
  resume contents and credentials;
- pin, monitor, and promptly update parser and model SDK dependencies;
- keep manual review and an appeal path for both match results and security rejections.

Useful baselines are the
[OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
and the
[OWASP LLM Prompt Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html).
