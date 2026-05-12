#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from math import prod
from pathlib import Path
from typing import Any

import requests


FLAG_RE = re.compile(rb"[A-Za-z0-9_]{2,32}\{[^}\r\n]{1,512}\}")


def int_to_bytes(value: int) -> bytes:
    return value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")


def extract_int(label: str, text: str) -> int | None:
    pattern = rf"(?:^|[^A-Za-z0-9_]){re.escape(label)}\s*=\s*(\d+)"
    matches = re.findall(pattern, text, flags=re.MULTILINE)
    if not matches:
        return None
    return int(matches[-1])


def load_values(args: argparse.Namespace) -> tuple[int, int, int]:
    n = args.n
    e = args.e
    c = args.c
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8", errors="replace")
        n = n or extract_int("n", text)
        e = e or extract_int("e", text)
        c = c or extract_int("c", text)
    if n is None or c is None:
        raise SystemExit("Need n and c, either as arguments or parseable from --file.")
    return n, e or 65537, c


def query_factordb(n: int) -> dict[str, Any]:
    response = requests.get(
        "https://factordb.com/api",
        params={"query": str(n)},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def numeric_factors(data: dict[str, Any]) -> list[int]:
    factors: list[int] = []
    for raw_value, raw_exp in data.get("factors", []):
        value = str(raw_value)
        if not value.isdigit():
            continue
        factors.extend([int(value)] * int(raw_exp))
    return factors


def decrypt(n: int, e: int, c: int, factors: list[int]) -> bytes | None:
    if not factors or prod(factors) != n:
        return None
    phi = 1
    for factor in factors:
        phi *= factor - 1
    d = pow(e, -1, phi)
    return int_to_bytes(pow(c, d, n))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Query FactorDB for RSA factors and decrypt c when possible."
    )
    parser.add_argument("--file", help="Parse n/e/c assignments from a text file.")
    parser.add_argument("--n", type=int, help="RSA modulus.")
    parser.add_argument("--e", type=int, default=None, help="RSA public exponent.")
    parser.add_argument("--c", type=int, help="RSA ciphertext.")
    args = parser.parse_args()

    n, e, c = load_values(args)
    data = query_factordb(n)
    factors = numeric_factors(data)

    print("factordb_status:", data.get("status"))
    print("factordb_id:", data.get("id"))
    print("factors_json:", json.dumps(data.get("factors", [])))
    print("numeric_factor_count:", len(factors))

    plaintext = decrypt(n, e, c, factors)
    if plaintext is None:
        print("decrypt_status: incomplete numeric factorization")
        return 2

    print("decrypt_status: ok")
    print("plaintext_hex:", plaintext.hex())
    print("plaintext_repr:", repr(plaintext))
    try:
        print("plaintext_utf8:", plaintext.decode())
    except UnicodeDecodeError:
        pass
    for match in FLAG_RE.findall(plaintext):
        print("flag:", match.decode(errors="replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
