# Pwn Skill

Use this when you already have a native binary or service and need memory
corruption, low-level primitives, or exploit automation. If the main blocker is
understanding program logic, do reverse engineering first.

Initial triage:
- `file ./chall; checksec ./chall; strings -a ./chall | head -200`.
- `readelf -hW ./chall; readelf -sW ./chall | head; objdump -d ./chall | head`.
- Run locally with benign input and then cyclic input.
- Note architecture, PIE, NX, RELRO, canary, libc, dynamic/static linking.
- Find useful symbols: `nm -an`, `objdump -T`, `readelf -r`.

Crash and offset:
- Use pwntools cyclic patterns.
- If gdb is available, run under gdb and inspect RIP/EIP/RSP/RBP.
- For simple stdin overflow, find offset before designing payload.
- For network-only services, script interaction first, then reproduce locally if
  binary is available.

Ret2win and ROP:
- Look for obvious `win`, `print_flag`, `system`, `execve`, `/bin/sh` strings.
- If no PIE, direct symbol addresses may work.
- If PIE, find leak or partial overwrite.
- x86_64 stack alignment often needs a single `ret` before `system`.
- Use `ROPgadget`, `ropper`, or pwntools ROP when installed; otherwise grep
  `objdump -d` for `pop rdi; ret`, `syscall`, `leave; ret`.

ret2libc:
- Leak libc address through GOT/PLT or format string.
- Calculate libc base, then `system("/bin/sh")` or one-gadget if constraints fit.
- With full RELRO, do not rely on GOT overwrite; use ROP call chain.
- With no leak, consider partial overwrite, known remote libc, or ret2dlresolve.

Format string:
- Identify offset with `%p` probes.
- Leak stack, canary, PIE, libc, and saved return pointers.
- Use `%n`, `%hn`, `%hhn` only after confirming writable target.
- GOT overwrite requires no/full RELRO check.
- Blind format strings need small, logged probes and stable offsets.

Canary:
- Look for leaks before brute force.
- Forking servers sometimes allow byte-by-byte brute force.
- Preserve null byte and saved frame layout.

Heap:
- Identify allocator and libc.
- Track allocation/free/edit/show primitives.
- Look for UAF, double free, off-by-one, size confusion, overlap, tcache poisoning,
  unsorted-bin leaks, top chunk corruption, and hook/IO_FILE targets.
- Script heap actions with named functions; log heap state after each phase.

Shellcode/seccomp:
- If NX is off, shellcode may be simplest.
- If seccomp exists, inspect with `seccomp-tools` if available or infer allowed
  syscalls from behavior.
- Try ORW shellcode (`open`, `read`, `write`) when `execve` is blocked.

Integer and parser bugs:
- Check signed/unsigned conversions, length fields, truncation, negative indexes,
  multiplication overflow, off-by-one null writes, and custom protocol parsers.

Exploit script template:
- Use pwntools.
- Start with `process()` locally; switch to `remote(host, port)` only when stable.
- Add `context.binary`, `context.log_level`, helper functions for menu actions,
  and a final `io.interactive()` or flag read.
- Save as `exploit.py` and run it repeatedly.

Pivot:
- If there is no memory corruption primitive yet, reverse the binary.
- If the bug is command injection or HTTP logic, use web.
- If the "pwn" task is mostly a crypto oracle, switch to crypto.
