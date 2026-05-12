# Web Skill

Use this when the main surface is HTTP, an API, browser code, identity/session
logic, template rendering, file upload, SSRF, SQLi, XSS/admin bot, or server-side
execution. Public playbooks stress: keep the first pass short.

First pass:
- `curl -i` the root and any described path.
- Preserve cookies with `curl -c cookies.txt -b cookies.txt`.
- Fetch visible JS/CSS/source maps: `grep -R` local source if provided.
- Check `robots.txt`, `sitemap.xml`, `.git/HEAD`, backup files, and obvious
  source archives only on the configured host.
- Identify stack: headers, cookies, error pages, framework names, template
  syntax, routing style, file extensions.

Mapping:
- List endpoints from HTML forms, JS fetch calls, links, and OpenAPI/GraphQL docs.
- Try method changes only on known endpoints: GET/POST/PUT/DELETE.
- Capture baseline responses and status codes.
- Freely research frameworks, CVEs, payload examples, bypasses, and writeups on
  the public internet. Keep active exploit traffic on challenge-owned surfaces.

Auth/session:
- Inspect cookies and JWTs offline.
- JWT checks: `alg=none`, weak HMAC secret, key confusion, missing verification,
  `kid` path traversal or JKU abuse when the app supports it.
- Flask/Django/Rails/Express signed cookies may use weak secrets in CTFs.
- Look for role fields, user IDs, mass assignment, reset-token predictability,
  IDOR, and host-header trust.

SQL/NoSQL/LDAP injection:
- Test quote, comment, boolean, UNION, time, and error-based behavior.
- For SQLite/MySQL/Postgres, fingerprint with errors and version functions.
- NoSQL: try JSON operators such as `$ne`, `$regex`, `$where` only when the
  backend likely parses JSON objects.
- If sqlmap is absent or too noisy, script the exact parameter with requests.

File/path bugs:
- Path traversal: `../`, encoded traversal, double encoding, absolute paths,
  Windows separators, null-byte legacy behavior.
- LFI wrappers: PHP `php://filter/convert.base64-encode/resource=...`.
- Upload bypass: extension case, double extensions, MIME mismatch, magic bytes,
  polyglots, archive extraction, image processing bugs.
- If source is leaked, read config, routes, templates, and secret keys first.

Template/code injection:
- SSTI probes: arithmetic expressions, object traversal, error differences.
- Command injection: separators, newline, shell expansions, argument injection,
  environment variables, filename injection.
- Deserialization: Java/PHP/Python signed payloads, pickle/yaml unsafe load,
  session decoding.
- XXE: local file read and OOB only against allowed challenge infrastructure.

SSRF:
- Keep targets within challenge scope.
- Try loopback forms only when the challenge itself is the target:
  `127.0.0.1`, `localhost`, IPv6, decimal/octal IP, DNS rebinding hints, redirects.
- Check cloud metadata only in CTF-local containers, never real infrastructure.

Client-side/admin bot:
- XSS needs a sink and a privileged victim path.
- Look for CSP, cookie flags, postMessage origin checks, DOM clobbering, prototype
  pollution, cache poisoning, and URL parser discrepancies.
- If an admin bot is described, craft a minimal payload that exfiltrates only the
  flag or page content to the allowed challenge receiver.

Script pattern:
- Create `solve.py` using `requests.Session()`.
- Store base URL from challenge metadata.
- Print status, small response snippets, cookies, and candidate flags.
- Automate login, exploit, and final flag retrieval.

Pivot:
- If the website only delivers a binary or pcap, switch category after download.
- If the bug is a native service behind TCP with memory corruption, use pwn.
- If a web endpoint exposes encrypted tokens and the web bug is solved, use crypto.
