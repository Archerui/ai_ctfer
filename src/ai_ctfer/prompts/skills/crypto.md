# Crypto Skill

Use this when the core blocker is encryption, hashing, signatures, PRNG, math,
or an encoding puzzle that behaves like cryptanalysis. A short phrase borrowed
from public skill style: "identify cipher type" first.

Initial triage:
- List files and inspect all text: `file *`, `cat`, `xxd`, `strings`.
- Extract numbers and labels: `n`, `e`, `c`, `p`, `q`, `iv`, `nonce`, `salt`,
  `seed`, `a`, `b`, `m`, `pubkey`, `signature`.
- Check formats: PEM, DER, JSON, Python source, Sage source, hex, base64.
- Use Python to print lengths, byte entropy, repeated blocks, and ASCII previews.
- Once `n`, `e`, and `c` have been read from source, do not re-run `cat` on the
  same source unless the file changed. Spend later turns on tests or finish.

Quick wins:
- Hex/base64: decode and grep for flag.
- XOR: try single-byte, repeating-key, and known plaintext using `flag{`.
- Classical: Caesar, Atbash, Vigenere with known prefix, substitution, Bacon,
  Morse, Polybius, rail fence, columnar transposition.
- Repeated AES-ECB blocks: split ciphertext into 16-byte chunks and count repeats.
- Many-time pad: XOR ciphertexts together and crib drag with likely plaintext.

RSA checklist:
- Parse key material: `openssl rsa -pubin -in key.pub -text -noout` when present.
- Print bit lengths for `n`, `e`, and ciphertext.
- Online first: if `n`, `e`, and `c` are available, query FactorDB before
  spending time on local factorization. Prefer the built-in helper so long
  integers are parsed from files instead of copied by hand:
  `rsa_factordb --file chall.py`.
  If the values are spread across multiple files, assign them once in
  `/work/solve.py` by parsing source text or pasting carefully, then run
  `rsa_factordb --n "$n" --e "$e" --c "$c"`.
  If the helper prints `decrypt_status: ok`, inspect `plaintext_utf8`,
  `plaintext_repr`, and any `flag:` line, then submit the flag.
- Do not manually retype large RSA constants into multiple commands. Extract
  them from files with regex or keep them in one script to avoid transcription
  mistakes.
- Direct API fallback, only if `rsa_factordb` is missing or unsuitable:
  `curl -sG --data-urlencode "query=$n" https://factordb.com/api | jq .`.
  Status `FF` with numeric factors is enough to compute phi and decrypt.
- Estimate difficulty before burning steps. A product of two random 256-bit
  primes is a 512-bit semiprime; pure Pollard rho/Fermat/trial division is not a
  realistic path unless there is a weakness.
- Check installed tools in this order: `python3 -c 'import sympy, gmpy2'`,
  `which ecm`, `which QuadraticSieve`.
- Use `sympy.factorint(n)` for small/special factors and as a quick oracle.
- Use `ecm` for medium-sized factors or smoothness; it is not a general NFS
  replacement for balanced random semiprimes.
- Ubuntu's `flintqs` package exposes the command `QuadraticSieve`; try it for
  quadratic-sieve attempts on medium composites. Keep it under the command
  timeout and report if it cannot finish or crashes on the input.
- If the modulus is a balanced random semiprime and no NFS/FactorDB/Sage/CADO
  path is available, say that the available local tools are insufficient rather
  than looping on Pollard rho.
- Command templates:
  - `timeout 20 python3 - <<'PY' ... import sympy; print(sympy.factorint(n, limit=1000000)) ... PY`
  - `printf '%s\n' "$n" | timeout 30 ecm -pm1 1000000`
  - `printf '%s\n' "$n" | timeout 30 ecm -c 20 1000000`
  - `printf '%s\n' "$n" | timeout 30 QuadraticSieve`
  - If these fail on a balanced 512-bit semiprime, finish with a clear limitation.
- Try small `n` factorization with Python/sympy if available.
- Try `e=3` low-exponent cube root when `m^e < n`.
- Try common modulus if multiple ciphertexts share `n`.
- Try Hastad broadcast for same plaintext under multiple moduli.
- Try Fermat when primes are close.
- Try Wiener when `d` may be small.
- Try shared primes by computing GCD across moduli.
- If `dp`, `dq`, `qinv`, `phi`, or leaked prime bits appear, derive the private key.
- If no library exists, implement with `pow(c, d, n)` and integer root helpers.

AES/block mode checklist:
- ECB: repeated blocks, cut-and-paste, byte-at-a-time oracle.
- CBC: IV bit flipping, padding oracle, missing MAC, controllable first block.
- CTR/OFB/stream: nonce reuse means `C1 xor C2 = P1 xor P2`.
- GCM: nonce reuse can break authentication; look for repeated nonce/tag pairs.
- Padding errors, timing differences, or distinct exception strings are oracles.

Hash/MAC checklist:
- Length extension for MD5/SHA1/SHA256 prefix MACs.
- CRC32/adler32 linearity and patching.
- Weak HMAC key, hardcoded key, truncated MAC brute force.
- Password hashes: identify with hashcat/hashid if installed; otherwise infer
  from length and alphabet.

PRNG checklist:
- LCG: recover modulus/multiplier/increment from successive outputs.
- MT19937: 624 full outputs can reconstruct state.
- Time seed: brute force timestamps around challenge creation.
- Python `random`, C `rand`, Java `Random`, xorshift, LFSR, and middle-square
  often have small state or linear structure.
- Use z3 for truncated outputs, partial bits, and modular equations.

ECC/signature checklist:
- ECDSA/DSA nonce reuse: same `r` reveals `k` and private key.
- Small subgroup/invalid curve when the service accepts arbitrary points.
- Pohlig-Hellman when group order is smooth.
- Anomalous curves or weak custom curves may need Sage; if Sage is missing,
  still inspect parameters and factor group order with Python when possible.

Lattice/math checklist:
- Subset sum/knapsack: try LLL if Sage/fpylll exists; otherwise build a Python
  basis and note the missing tool.
- Hidden number problem from biased or partial nonces.
- Coppersmith patterns: small root, partial prime bits, low exponent with padding.
- Work over the right ring: integers, mod prime, GF(2), polynomial rings.

Script pattern:
- Create `solve.py`.
- Parse inputs robustly from files.
- Print decoded bytes as hex and repr.
- Call `find flag` by printing any ASCII that matches the configured pattern.
- Keep brute force bounded; print progress only every large interval.

Pivot:
- If most work is understanding an executable, switch to reverse engineering.
- If the encrypted data is inside a pcap/disk/image, do forensics extraction first.
- If exploitation of a remote service is the real blocker, switch to web or pwn.
