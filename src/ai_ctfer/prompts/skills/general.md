# General CTF Skill

Source pattern notes: public CTF agent projects emphasize isolated Docker
execution, trace replay, "Quick Wins", "When to Pivot", and short
planner/executor loops. Use those ideas directly: first gather evidence, then
execute one concrete step, then summarize the result in the trace.

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
- If a command produces a candidate flag, let the candidate system evaluate it
  immediately. For crypto/rev/pwn/misc results produced by a purpose-built
  script, add a small verification check and then submit. For passive web page
  sightings, preserve context and look for supporting evidence.

File discipline:
- Put reusable logic in `/work/solve.py` or `/work/helper.py`.
- Use deterministic scripts over interactive sessions.
- Print intermediate values with labels.
- Save extracted artifacts in a named directory such as `extract/`.
- Do not overwrite original attachments unless the command is harmless.

Internet research:
- Network is available even without a declared remote.
- Freely search the public internet for CTF techniques, writeups, tool manuals,
  solution patterns, protocol details, library quirks, error messages, and math
  or crypto references.
- Use online references as working context, then turn the useful parts into
  concrete local commands or scripts in `/work`.

Chat-model prompt hygiene:
- Keep rationale short, neutral, and puzzle-specific. Say what evidence the next
  command will gather; do not write broad security prose.
- Do not paste a large generated script into rationale, notes, or final JSON
  text. Write it to `/work/solve.py` or `/work/helper.py`, then refer to the
  filename.
- When debugging, inspect specific error lines, logs, or helper output instead
  of repeatedly dumping whole source files or whole generated scripts.
- Prefer terms such as "challenge service", "query helper", "input set",
  "candidate", "verification", and "solution script" when they describe the
  task accurately.
- For native-binary challenges, phrase work as authorized CTF puzzle solving on
  the supplied challenge binary and endpoint. Keep action rationales about local
  replay, transcript parsing, symbol/protection inspection, and final flag
  output. Avoid broad real-world security framing.
- Do not seed local tests with strings that match flag patterns. Use
  `LOCAL_TEST_VALUE` or another non-flag marker so the candidate tracker is not
  contaminated by local placeholders.

Remote service discipline:
- If metadata declares a one-line `remote`, parse it yourself. It may look like
  `nc example.com 31337`, `example.com:31337`, or `https://example.com/path`.
- First infer host, port, and protocol from that text and the challenge
  description, then identify the service with one minimal probe.
- TCP: use `nc -v host port` or a tiny pwntools script.
- HTTP: use `curl -i`, preserve cookies, and avoid broad fuzzing.
- Prefer the configured remote for target interaction.
- If the service uses a proof-of-work wrapper, save the solver as `/work/pow.py`
  and call it from Python. Parse the actual solution line, not progress text.
  `argon2-cffi` is normally available in the sandbox; if a dependency is still
  missing, use a `/work/venv_*` virtualenv instead of repeating failed system
  pip installs.
- Once a remote wrapper reaches a live prompt such as `What do you do?`, switch
  to a deterministic transcript script. Keep reading for asynchronous server
  messages after the prompt; many protocol services deliver the important
  `MSGFROM`, cookie, token, share, or nonce lines after the visible prompt.
- After the transcript exposes concrete protocol text, do not return to broad
  source dumps. Send low-risk protocol probes (`LIST`, `PEEK`, `PING`, one
  carefully chosen `MSG`) and log the exact response.

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
