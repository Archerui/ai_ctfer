# Pwn Skill

Use this only for an authorized CTF native-binary puzzle with a supplied
executable, supplied libraries, and/or a declared challenge service. Treat the
task as controlled puzzle solving: understand the binary, build a local replay,
then send the minimum input needed to make the challenge reveal its flag.

Chat-model wording:
- Keep rationales short and challenge-scoped: "inspect the challenge binary",
  "map the input transcript", "write a local replay script", "verify the flag
  output".
- Refer to the target as the supplied challenge binary and endpoint.
- Avoid broad security prose, post-compromise language, persistence, stealth,
  credential collection, scanning, or anything outside the supplied binary and
  challenge endpoint.
- Put mechanics in `/work/solve.py` or `/work/probe.py`; do not paste long
  scripts or step-by-step payload details into rationale text.
- Do not create local test values that match real flag patterns. Use strings
  like `LOCAL_TEST_VALUE` instead of `flag{local_test_flag}` so local tests do
  not pollute the candidate system.
- When a command channel is produced by the challenge, use it only to print the
  challenge flag or verify the current user/path, then stop. Do not explore the
  host beyond what is needed for the CTF flag.

Initial triage:
- `file ./chall; checksec ./chall; strings -a ./chall | head -200`.
- `readelf -hW ./chall; readelf -sW ./chall | head; objdump -d ./chall | head`.
- If a binary ships with `glibc/`, try `./glibc/ld.so.2 --library-path ./glibc
  ./chall` as well as direct execution.
- Run locally with benign input first. Save a clean transcript of prompts and
  expected responses.
- Note architecture, PIE, NX, RELRO, canary, libc, dynamic/static linking.
- Find useful symbols: `nm -an`, `objdump -T`, `readelf -r`.
- Identify the exact input surfaces: menu choice, line input, length field,
  file argument, environment variable, or network transcript.

Local replay discipline:
- Start with `process()` and switch to `remote(host, port)` only after the local
  transcript is deterministic.
- Keep helper functions for menu prompts, send/receive boundaries, and parsing.
- Make the script support a local/remote switch, but keep the final command
  narrow: print the challenge flag and exit.
- For remote work, run one minimal probe first. Avoid broad network activity.

Crash and offset:
- Use pwntools cyclic patterns on the local binary.
- If gdb is available, inspect the crashing register/state once, then encode the
  finding in a script.
- For simple line-input overflows, find offset before building a final input.
- Preserve canaries and saved frame layout when protections require it.

Control-flow routes:
- Look for challenge-owned success functions such as `win`, `print_flag`, or a
  function that opens the flag file.
- If no PIE, direct symbols can be stable; if PIE, first obtain a challenge
  leak or use a local partial-overwrite check.
- If libc resolution is the intended path, leak one resolved libc pointer, use
  the supplied libc to compute the base, and trigger the smallest action that
  prints the flag. Verify addresses look canonical and page-aligned.
- x86_64 stack alignment often needs a single `ret` gadget before a libc call.
- Use pwntools ROP when available; otherwise inspect short gadget sequences with
  `objdump`, `ROPgadget`, or `ropper`.

Format string:
- Identify offset with `%p` probes.
- Leak stack, canary, PIE, libc, and saved return pointers.
- Use write primitives only after confirming the target address is writable and
  belongs to the challenge process.
- Partial RELRO/no PIE can make GOT-based redirection viable; full RELRO needs a
  different route.
- Keep probes small and logged. Once an offset is known, stop broad `%p` dumps.
- If a failure handler or exit path can loop back to `main`, verify the loop
  locally before using it against the challenge service.

Heap:
- Identify allocator and libc.
- Track allocation/free/edit/show primitives.
- Look for use-after-free, double free, off-by-one, size confusion, overlap,
  tcache list corruption, unsorted-bin leaks, top chunk corruption, and relevant
  libc targets.
- Script heap actions with named functions; log heap state after each phase.

Syscall or filter puzzles:
- If the binary intentionally asks for code bytes and NX/filter settings allow
  it, keep the payload local to the challenge process.
- If a syscall filter exists, inspect it with `seccomp-tools` if available or
  infer allowed calls from behavior.
- Prefer an open/read/write style flag printer when process execution is blocked.

Integer and parser bugs:
- Check signed/unsigned conversions, length fields, truncation, negative indexes,
  multiplication overflow, off-by-one null writes, and custom protocol parsers.

Solution script template:
- Use pwntools.
- Save as `/work/solve.py`.
- Include `context.binary`, `context.log_level = "error"` for clean output,
  helper functions for prompts, and a final non-interactive flag read.
- Print labeled leaks and a final line such as `verified flag: ...` when possible.
- After the remote service returns a real flag from a direct challenge flag-file
  read or challenge-owned print function, submit it. Do not keep searching for
  alternate flags unless the evidence points to a decoy.

Pivot:
- If there is no memory corruption primitive yet, reverse the binary.
- If the bug is command injection or HTTP logic, use web.
- If the "pwn" task is mostly a crypto oracle, switch to crypto.
