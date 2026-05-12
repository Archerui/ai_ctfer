# Misc Skill

Use this for puzzles, encodings, automation, pyjails, esolangs, weird protocols,
QR/barcodes, games, AI/ML toy tasks, blockchain-lite tasks, and anything that is
not clearly pwn/rev/crypto/web/forensics yet.

Classification first:
- Identify artifact type with `file`, `strings`, `xxd`, and filenames.
- If there is a service, learn the protocol with one minimal connection.
- If there are many samples, compare them with hashes, sizes, and diffs.
- If the task is interactive, script it quickly.

Encoding stack:
- Try hex, base64/base32/base85, URL, HTML entities, rot13, Caesar, Morse,
  Bacon, binary/decimal/octal ASCII, Braille, emoji alphabets, and keyboard shifts.
- Decode in layers and check after each layer for magic bytes or flag regex.
- For QR/barcodes, use available decoders if installed; otherwise inspect images
  with Python/Pillow and try visual transformations.

Pyjail/sandbox:
- Identify Python version and forbidden tokens from error messages.
- Probe allowed builtins, object graph, string construction, encoding escapes,
  format strings, imports, subclasses, and file reads.
- Keep payloads small and explain the bypass in the rationale.

Interactive protocol:
- Use pwntools or Python sockets.
- Read until prompts, parse numbers, respond deterministically.
- Log transcripts to understand state machines.
- If math questions repeat, write a solver loop.

Esolang/VM/game:
- Identify language by syntax or magic words.
- Search for interpreters only if available locally; otherwise write a small
  emulator or translator for the subset used.
- For games, inspect save files, score checks, RNG seeds, map files, and scripts.

AI/ML:
- Inspect model format, labels, preprocessing, and expected output.
- Try adversarial input only inside the provided artifact or local service.
- Search for hidden strings in weights/config/tokenizer files.

Pivot:
- Once the route is clear, use the nearest specialized skill.
- If misc is just a wrapper around crypto, web, rev, pwn, or forensics, pivot.
