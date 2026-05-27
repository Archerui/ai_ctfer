# AI-CTFer

`AI-CTFer` is a lightweight AI agent designed to solve individual CTF challenges. It reads an optional `challenge.yml` file, calls either DeepSeek or OpenAI API, and executes commands inside a Docker sandbox.

## Quick Start

```bash
python -m pip install -e ".[dev]"
ai-ctfer doctor
ai-ctfer init .
ai-ctfer solve .
```

Short aliases are also available: `ai-ctfer i` for `init`, `ai-ctfer s` for `solve`, and `ai-ctfer c` for `clean`.

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
# Paste statement, flag format, remote endpoints, hints, and notes here.
# Standard YAML wants indented block lines. ai-ctfer also repairs accidental
# unindented pasted lines inside this description block.
description: |-
  Paste the challenge text here.
  nc example.com 31337
  Flag format: flag{...}

limits:
  max_steps: 50
  command_timeout_sec: 600
  max_output_chars: 50000

model:
  # name options: gpt, deepseek
  # gpt => gpt-5.5 with xhigh reasoning
  # deepseek => deepseek-v4-pro
  name: gpt
```

Put raw connection text directly in `description`, such as `nc example.com
31337`, `example.com:31337`, or an HTTP URL; the agent will parse host, port,
and protocol from context.

## Model API Customization

Normal usage only needs `model.name: deepseek` or `model.name: gpt` in
`challenge.yml`.

Advanced users can add or edit model options in:

```text
model_providers.py
```

That file is intentionally small and user-facing:

- `MODEL_PROVIDERS` controls which `model.name` values are accepted.
- Each provider entry defines aliases, API-key environment variable, `base_url`,
  API model name, API style, optional reasoning effort, and generated sample
  comments.
- `api_style: "responses"` uses `client.responses.create(...)`.
- `api_style: "chat_completions"` uses
  `client.chat.completions.create(...)`.

The internal bridge remains in `src/ai_ctfer/model_interface.py`:

- It loads `model_providers.py`.
- `create_chat_client()` controls `OpenAI(...)` client construction.
- `build_responses_kwargs()` and `build_chat_completion_kwargs()` control
  request parameters for the two styles.

For example, the default DeepSeek entry looks like this:

```python
"deepseek": {
    "aliases": ["deepseek", "deepseek-v4-pro", "deepseek-v4-flash"],
    "api_key_env": "DEEPSEEK_API_KEY",
    "base_url": "https://api.deepseek.com",
    "api_model": "deepseek-v4-pro",
    "api_style": "chat_completions",
    "reasoning_effort": None,
    "sample_comment": "deepseek => deepseek-v4-pro",
},
```

The default OpenAI entry uses the Responses API:

```python
"gpt": {
    "aliases": ["gpt", "openai", "gpt-5.5", "gpt-5.5-xhigh"],
    "api_key_env": "OPENAI_API_KEY",
    "base_url": None,
    "api_model": "gpt-5.5",
    "api_style": "responses",
    "reasoning_effort": "xhigh",
    "sample_comment": "gpt => gpt-5.5 with xhigh reasoning",
},
```

Then use any configured provider without editing schema or solver code:

```yaml
model:
  name: gpt
```

This keeps the agent loop stable while still making it easy to route calls
through a proxy, local gateway, compatible third-party endpoint, or custom
OpenAI SDK options.

Each `solve` run starts with an automatic planning phase. The agent may run a few
exploratory commands, prints the selected plan, then starts execution without
waiting for confirmation. The plan is also saved as `plan.md` in the run
directory.

During solving, `ai-ctfer` maintains `ai-ctfer-notes.md` in the challenge
directory. Future runs read this notebook first, reuse useful findings, and keep
adding concise attempt/result notes. If the current `challenge.yml` contains a
new target address, old notebook target values are updated so stale remote
environment URLs do not steer the next run.

When a challenge is solved, the CLI prints the flag first, then writes
`writeup.md` and a solve/replay script such as `solve.py` or `solve.sage` into
the challenge directory. The writeup includes the elapsed solve time. Their
language follows `ai-ctfer language`.

Cleanup examples:

```bash
ai-ctfer clean .                 # default: --all
ai-ctfer clean . --runs          # only remove .ai-ctfer and ai-ctfer-notes.md
ai-ctfer clean . --image         # only remove ai-ctfer-sandbox:latest
ai-ctfer clean . --docker-cache  # only prune Docker build cache
```

Cleanup does not remove `writeup.md` or generated solve scripts.

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

## Q&A

### Why does Docker say permission denied?

`ai-ctfer` uses the current user to run Docker. It does not use `sudo` or do
any privilege escalation internally. If this fails:

```bash
docker run --rm hello-world
```

then Docker-backed commands will fail too, including:

- `ai-ctfer solve .`
- `ai-ctfer smoke --fake-llm`
- `ai-ctfer clean . --image`
- `ai-ctfer clean . --docker-cache`
- `ai-ctfer clean . --all`

Local cleanup still works without Docker permission:

```bash
ai-ctfer clean . --runs
```

The usual fix is to add your user to the `docker` group:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
docker run --rm hello-world
```

If `newgrp docker` does not refresh the session cleanly, log out and log back
in, then rerun:

```bash
ai-ctfer doctor --strict
```

Running `sudo ai-ctfer solve .` can work, but it is not recommended because
generated files may become owned by `root`.

### Why does `clean` fail with `unable to delete ai-ctfer-sandbox:latest`?

This means Docker still has a container that references the sandbox image. The
container may be stopped, but Docker still keeps the image locked until that
container is removed.

Check which containers are using the image:

```bash
docker ps -a --filter ancestor=ai-ctfer-sandbox:latest
```

If the listed containers are old `ai-ctfer` sandbox containers and you do not
need them anymore, remove them and rerun image cleanup:

```bash
docker rm -f <container-id>
ai-ctfer clean . --image
```

For a one-shot cleanup of all containers based on this image:

```bash
docker ps -aq --filter ancestor=ai-ctfer-sandbox:latest | xargs -r docker rm -f
ai-ctfer clean . --image
```

`ai-ctfer clean . --runs` is already done before this point, so this error does
not mean your run logs or `ai-ctfer-notes.md` are still present. It only means
Docker refused to remove the reusable sandbox image.
