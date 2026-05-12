# AI-CTFer

`AI-CTFer` is a small, single-challenge CTF agent. It reads an optional
`challenge.yml`, calls either DeepSeek or OpenAI, and executes commands inside a
Docker sandbox.

## Quick Start

```bash
python -m pip install -e ".[dev]"
ai-ctfer doctor
ai-ctfer init .
ai-ctfer solve .
```

Set `DEEPSEEK_API_KEY` for `model.name: deepseek`, or `OPENAI_API_KEY` for
`model.name: gpt`, before solving real challenges.

The normal workflow is to install this CLI once, then run `ai-ctfer solve .`
inside a challenge directory containing only that challenge's attachments and
optional `challenge.yml`.

Minimal `challenge.yml`:

```yaml
name: example-challenge
# category options: pwn, rev, crypto, web, forensics, misc, unknown
category: crypto
description: |
  Paste the challenge text here.
flag_format: "flag{...}"
remote: "nc example.com 31337"

limits:
  max_steps: 50
  command_timeout_sec: 600
  max_output_chars: 50000

model:
  # name options: deepseek, gpt
  # deepseek => deepseek-v4-pro
  # gpt => gpt-5.5 with xhigh reasoning
  name: deepseek
  temperature: 0.1
```

`remote` is intentionally one line. Put the raw connection text there, such as
`nc example.com 31337`, `example.com:31337`, or an HTTP URL; the agent will parse
host, port, and protocol from context.

Each `solve` run starts with an automatic planning phase. The agent may run a few
exploratory commands, prints the selected plan, then starts execution without
waiting for confirmation. The plan is also saved as `plan.md` in the run
directory.

## Docker

The solver is Docker-only. On Ubuntu, install Docker Engine with:

```bash
bash scripts/install_docker_ubuntu.sh
```

After installing Docker, verify the sandbox path:

```bash
ai-ctfer doctor --strict
```

The sandbox has network access enabled for both remote and no-remote challenges.
For RSA triage it includes `rsa_factordb`, a small helper that queries FactorDB
and decrypts when `n`, `e`, and `c` are available.

## Smoke Tests

After Docker is available, run a free fake-LLM smoke test:

```bash
ai-ctfer smoke --fake-llm
```

To verify the configured real LLM path:

```bash
ai-ctfer smoke --real-llm
```
