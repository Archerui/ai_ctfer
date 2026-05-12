# Forensics Skill

Use this for disk images, memory dumps, pcaps, logs, archives, images, audio,
PDFs, stego, deleted files, coredumps, Docker layers, registry hives, and
artifact recovery. Public skill phrasing calls this "digital forensics and
signal analysis"; keep that breadth in mind.

Initial triage:
- `file *`, `ls -lah`, `sha256sum`, `xxd -l 256`, `strings -a`.
- Look for embedded magic bytes: PNG, ZIP, gzip, 7z, PDF, ELF, SQLite, pcap.
- Run metadata checks: `exiftool`, archive listing, image dimensions.
- Create `extract/` and never destroy originals.

Archives and nested files:
- List first: `unzip -l`, `7z l`, `tar -tf`.
- Extract into `extract/<name>/`.
- If password-protected, search challenge text, filenames, comments, and strings.
- Check duplicate names, alternate streams, weird permissions, symlinks, and
  archive traversal tricks.
- Script recursive extraction when many layers exist.

Images/stego:
- Check EXIF, comments, dimensions, color mode, appended data after EOF marker.
- Try `strings`, `binwalk` if installed, `xxd`, channel separation with Python/Pillow.
- Inspect LSBs, alpha channel, palette, row/column shifts, QR/barcode-like regions,
  and visual differences.
- For PNG, inspect chunks and zlib streams; for JPEG, check comments and trailing data.

PCAP/network:
- Start with `file`, packet count, conversations, protocols, DNS/HTTP/TCP streams.
- Use `tcpdump -nnr file.pcap` if tshark is absent.
- Extract HTTP objects manually from streams if tools are missing.
- Check DNS queries, ICMP payloads, TCP flags, timing channels, credentials, and
  base64/hex in payloads.
- Reassemble split archives by filenames, sequence numbers, or timestamps.

Disk/memory:
- Identify image type: raw, qcow2, vmdk, ova, zip, EWF, filesystem dump.
- Use `mmls`, `fls`, `icat`, `fsstat` if Sleuthkit exists; otherwise use `file`,
  `strings`, and loop-mount only if allowed.
- Check deleted files, recycle bins, browser history, shell history, SSH keys,
  SQLite DBs, config files, and logs.
- Memory dumps: try volatility3 if installed; otherwise search processes,
  command lines, URLs, keys, and flags with strings.

PDF/documents:
- Use `pdfinfo`, `exiftool`, `strings`, `binwalk`, and manual object inspection.
- Check embedded files, JavaScript, object streams, redacted text, metadata, and
  hidden layers.
- Office files are ZIPs; inspect `word/`, macros, media, relationships, comments.

Audio/signal:
- Inspect format and duration with `file`/`ffprobe` if present.
- Try spectrogram with Python/matplotlib if ffmpeg/sox missing.
- Check DTMF, Morse, SSTV, reversed audio, channels difference, LSB samples.

Git/Docker/source artifacts:
- If `.git` exists, inspect logs, branches, stash, deleted files, and diffs.
- Docker images/layers: list tar layers, inspect history/config, grep for secrets.
- Coredumps can contain flags, keys, TLS secrets, or program memory.

Script pattern:
- Write `triage.py` or `extract.py`.
- Walk files, run lightweight magic checks, and print candidates.
- Save decoded or carved outputs with meaningful names.

Pivot:
- If extracted content is encrypted, switch to crypto.
- If extracted executable is the challenge, switch to reverse or pwn.
- If extracted service is HTTP source, switch to web.
