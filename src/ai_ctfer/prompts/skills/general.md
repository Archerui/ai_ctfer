# General CTF Skill

Source pattern notes: public CTF agent projects emphasize isolated Docker
execution, trace replay, "Quick Wins", "When to Pivot", and short
planner/executor loops. Use those ideas directly.

First pass:
- Run `pwd; ls -la; find . -maxdepth 2 -type f -printf '%p %s bytes\n'`.
- Run `file` on every obvious attachment.
- Search for easy flags: `grep -RInaE 'flag\{|ctf\{|FLAG\{|picoCTF' .`.
- Check text hints: `find . -maxdepth 2 -type f -name '*readme*' -o -name '*.txt'`.
- For archives, list before extracting: `unzip -l`, `tar -tf`, `7z l`.
- For unknown binary data, use `xxd -l 256`, `strings -a`, and magic bytes.

Decision loop:
- State one hypothesis in the rationale.
- Run exactly one command that advances it.
- If output is long, rerun a narrower command instead of dumping everything.
- If a task may take minutes, start it in the background with output redirected
  to a log file, record its PID, and spend later turns on other independent
  checks before polling the log.
- If two attempts fail, pivot or inspect a different layer.
- If a command produces a candidate flag, submit immediately.

File discipline:
- Put reusable logic in `/work/solve.py` or `/work/exploit.py`.
- Use deterministic scripts over interactive sessions.
- Print intermediate values with labels.
- Save extracted artifacts in a named directory such as `extract/`.
- Do not overwrite original attachments unless the command is harmless.

Internet research:
- Network is available even without a declared remote.
- Freely search the public internet for CTF techniques, writeups, tool manuals,
  exploit patterns, protocol details, library quirks, error messages, and math or
  crypto references.
- Use online references as working context, then turn the useful parts into
  concrete local commands or scripts in `/work`.

Remote service discipline:
- If metadata declares a one-line `remote`, parse it yourself. It may look like
  `nc example.com 31337`, `example.com:31337`, or `https://example.com/path`.
- First infer host, port, and protocol from that text and the challenge
  description, then identify the service with one minimal probe.
- TCP: use `nc -v host port` or a tiny pwntools script.
- HTTP: use `curl -i`, preserve cookies, and avoid broad fuzzing.
- Prefer the configured remote for exploit traffic.

Common encodings and wrappers:
- Try base64, hex, URL encoding, rot13, gzip/zlib, repeated XOR, and nested
  archive extraction before assuming the challenge is deep.
- Check whether a "binary" is really a script, packed executable, PyInstaller
  bundle, Java jar, .NET assembly, image, pcap, SQLite DB, or git repo.

When stuck:
- Re-read the challenge description and hints.
- Summarize what is known in `notes.txt`.
- Search filenames and strings for category clues.
- Try the `unknown` routing skill mentally: classify by artifact and service.
