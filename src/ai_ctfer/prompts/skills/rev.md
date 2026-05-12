# Reverse Engineering Skill

Use this when the task is to understand an executable, script, bytecode, VM,
mobile artifact, or obfuscated checker. A useful public-playbook phrase is
"map control flow before modifying execution".

Initial triage:
- `file`, `sha256sum`, `strings -a`, `xxd -l 256`, `readelf -hW`, `checksec`.
- Identify language/runtime: C/C++, Go, Rust, Java, .NET, Python/PyInstaller,
  Node, Lua, WASM, Android, firmware, shell script.
- Run with simple inputs and capture messages.
- Use `ltrace`/`strace` for libc calls, file reads, network checks, and compares.
- Search for `flag`, `ctf`, `wrong`, `correct`, `password`, `secret`, `memcmp`,
  `strcmp`, `strncmp`, `scanf`, `read`, `xor`.

Quick wins:
- Plaintext flags in `strings`.
- Expected input leaked through `ltrace` strcmp/memcmp.
- Base64/hex/XOR constants in rodata.
- Python bytecode or PyInstaller extraction.
- Java/.NET decompilation with standard tools if available; otherwise use
  `strings`, `javap`, or metadata inspection.

Static analysis without a decompiler:
- Use `objdump -d -Mintel` and focus around `main`, comparisons, and calls.
- `readelf -sW` and relocation tables can reveal imported functions.
- Look for loops that transform input byte-by-byte.
- Extract constant arrays with `objdump -s -j .rodata` or `xxd`.
- Reimplement the checker in Python and invert it.

Dynamic analysis:
- Run with test input and observe branches.
- Patch simple conditional jumps only after understanding the check.
- Use gdb breakpoints on `strcmp`, `memcmp`, `puts`, `exit`, and validation
  functions.
- Print buffers before compare calls.
- If anti-debug appears, try static extraction or patching checks.

Symbolic/constraint solving:
- Convert per-byte conditions to z3.
- Use angr only if installed and the binary is a classic flag checker.
- For custom VMs, recover instruction format, dump bytecode, write an emulator,
  then solve constraints over VM state.

Common transformations:
- XOR with fixed/repeating key, add/sub/rotate, bit shuffle, S-box lookup, base
  conversion, checksum, CRC, LCG/PRNG-derived mask, permutation, endian tricks.
- Compare encoded input against constants; invert operations in reverse order.
- If operations are linear over bytes or bits, solve with Python or z3.

Packed/obfuscated binaries:
- Check UPX first.
- Look for self-modifying code, encrypted sections, high-entropy blobs, weird
  imports, or runtime unpacking.
- Dump memory after unpacking if feasible; otherwise emulate the decode loop.

Script pattern:
- Write `solve.py` that loads constants from files or pasted arrays.
- Print candidate bytes, printable preview, and regex matches.
- Keep exploratory disassembly outputs in small files such as `main.asm`.

Pivot:
- If the reversed logic is real cryptography, switch to crypto.
- If you have a bug and now need control-flow hijack, switch to pwn.
- If artifact extraction is the blocker, switch to forensics.
