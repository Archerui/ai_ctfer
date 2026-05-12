# Unknown Category Skill

Use this when `category: unknown` or when the metadata is misleading.

Routing pass:
- Directory shape: source tree, binary, archive, pcap, image/audio, website files,
  Dockerfile, challenge service text.
- Run `file` and `strings` on the largest or most suspicious files.
- Read challenge text, README, filenames, and comments.
- If there is a remote:
  - `http/https` points to web unless it serves artifacts.
  - raw TCP with ELF attachment often points to pwn.
  - prompt/response math often points to misc or crypto.

Signals:
- ELF/Mach-O/PE with input validation: reverse first; pwn if exploitable.
- Source code for app/API: web.
- `n/e/c`, ciphertexts, keys, nonces, signatures: crypto.
- pcap, disk image, memory dump, image/audio/pdf/archive: forensics.
- Puzzle text, encodings, pyjail, esolang, automation: misc.

After classifying:
- Follow the matching skill immediately.
- If two categories apply, extract the artifact first, then solve the core.
