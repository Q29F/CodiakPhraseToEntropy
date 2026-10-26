# Local application boundary

The browser interface is a single-user desktop application. Its Python process
binds only to `127.0.0.1`; it exposes no option to listen on all network interfaces.
The browser sends calculation inputs to that local process. No remote service is
used, and request contents, phrases, tokens, and exception details are not logged.

## Requests and computation

Every request must use the exact local Host. POST endpoints additionally require
the exact Origin and a random per-process session token supplied in the
`X-CSRF-Token` header. The token is compared in constant time. There is no CORS
allowance. These controls address browser cross-origin requests and DNS rebinding;
they do not isolate mutually untrusted programs on the same computer.

The transport limits the request line, headers, JSON body, active connections,
read duration, total connection duration, and response size. It rejects duplicate
framing headers, transfer-encoded or compressed bodies, malformed JSON, duplicate
JSON keys, non-finite numbers, and excessive nesting. Connections close after one
request. At most eight connection workers and one calculation callback run at a
time; calculation requests are not queued.

The application validates the exact calculation schema, finite numeric bounds,
and text length before its fixed 129-sample computation. The text path accepts
Unicode data without evaluating it. The symbolic expression is constructed from
fixed operations and a validated numeric phase, never parsed from submitted code.

## Assets, display, and export

Only an explicit set of preloaded assets is served. URLs are never mapped to
filesystem paths, and no directory listing is available. Server error responses
contain fixed public messages rather than exception details or submitted values.

The interface uses external local scripts and styles under a restrictive content
security policy. It renders text through text nodes and SVG geometry. Responses
use no-store caching, no-referrer, anti-framing, content-type protection, restricted
browser permissions, and a same-origin resource policy.

Browser downloads are explicit local actions. JSON contains calculation results;
CSV contains numerical samples with fixed column headings. Raw phrases are omitted
from both, avoiding a spreadsheet-formula surface for arbitrary text. The existing
Python CSV export accepts a caller-selected local path and writes only when called.
No browser endpoint accepts a filesystem destination.

## Operations and verification

Use Python 3.12.16 or a later security release in the 3.12 series. The
[3.12.16 security release](https://www.python.org/downloads/release/python-31216/)
blocks compromised eMudhra intermediate keys. The notebook lock also updates
certifi to address the [emSign trust-store advisory](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2).
The separate installer lock updates pip before installing application packages.

Stop the process with Ctrl+C when finished. Closing the server stops accepting
connections and closes active sockets. The application callback has bounded work;
the transport cannot forcibly interrupt arbitrary Python code supplied by a future
developer. Keep that contract when adding endpoints.

Tests cover mathematical validation, HTTP authorization and framing, resource
limits, cleanup, real browser behavior, and CSP enforcement. Dependency scans
cover the committed Python and development locks at scan time. They do not assess
unknown vulnerabilities or the security of a public hosting environment.

This loopback transport is not a public production server. Python's
[HTTP server documentation](https://docs.python.org/3.12/library/http.server.html)
describes the standard library server's production limitations. Public hosting
would require a separately designed authentication, TLS, isolation, and operations
boundary. The optional notebook and container retain Jupyter token authentication.
The notebook's default local kernel transport authenticates commands but does not
encrypt its traffic, so it also relies on this trusted-machine boundary; see
[Jupyter kernel transport security](https://jupyter-client.readthedocs.io/en/stable/security.html).
