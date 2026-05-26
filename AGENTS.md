# Agent guide for `ignitetech-group/ecs-deploy`

Onboarding notes for AI coding agents (Cursor, Claude Code, Codex) and humans
working on this fork. Read this before opening a PR.

This is a **security-hardened fork** of
[`fabfuel/ecs-deploy`](https://github.com/fabfuel/ecs-deploy). The fork's
purpose, deviations from upstream, and pin-to-SHA install instructions live
at the top of [`README.rst`](./README.rst). This file covers the engineering
contract for changes.

---

## What this repo is

The `ecs` CLI for managing ECS deployments, scaling, and one-off task runs.
Pure-Python, packaged via `setup.py`, distributed by:

1. **Direct `pip install` from a 40-character commit SHA on `main`** — the
   primary consumer pattern. The
   [`ignitetech-group/action-ecs-deploy`](https://github.com/ignitetech-group/action-ecs-deploy)
   wrapper installs this repo via
   `pip install git+https://github.com/ignitetech-group/ecs-deploy@<SHA>`
   from inside its Docker build.
2. **Local `docker build .`** — the `Dockerfile` produces a slim runtime
   image with the CLI on `PATH`.

We do **not** publish to PyPI or Docker Hub; both upstream workflows that
did so were removed at fork bootstrap (see fork notice in `README.rst`).

---

## Fork invariants (don't regress these)

| # | Invariant |
|---|---|
| 1 | Build from source. No third-party prebuilt artifact at consumer runtime. (`Dockerfile` builds fully from `setup.py` + the hashed lockfile.) |
| 2 | No `secrets: inherit` to third-party reusable workflows. |
| 3 | All `uses:` in `.github/workflows/*.yml` pinned to 40-character commit SHAs with a tag-comment on the line above. |
| 4 | Every workflow declares `permissions: contents: read` at the workflow level; widen only per-job, with rationale. |
| 5 | No deprecated CLIs and no shell-eval of user input anywhere in the codebase. |
| 6 | `CODEOWNERS` and `dependabot.yml` point at the fork's maintainers. |
| 7 | `README.rst` documents the fork's deviation from upstream at the top. |

These invariants come from the
[`github-actions-fork`](https://github.com/ignitetech-group/action-pull-request)
skill (Phase 0 bootstrap). Every PR (including dependabot bumps) must
preserve them.

---

## Quality gates (always run before a PR)

Every change must pass these scanners locally before push. Server-side review
(CodeRabbit + CI) re-runs them; landing a clean PR keeps the round-trip
short.

| Layer | Tool | Command |
|---|---|---|
| Python lint | `ruff check` | `ruff check ecs_deploy tests` |
| Python format | `ruff format --check` | `ruff format --check ecs_deploy tests` |
| Python types | `pyright` | `pyright ecs_deploy` |
| Python tests | `pytest` | `pytest --cov ecs_deploy` |
| Dockerfile | `hadolint` | `hadolint Dockerfile` |
| Workflows | `actionlint` | `actionlint` |
| YAML | `yamllint` | `yamllint .github/` |

### One-shot install

```bash
# Python toolchain (uv handles ruff and pyright cleanly)
uv tool install ruff
uv tool install pyright

# Dockerfile + workflow lint
brew install hadolint actionlint yamllint
```

### Pre-PR script

```bash
# From the repo root, with a fresh venv:
uv venv --python 3.13 .venv
. .venv/bin/activate
uv pip sync requirements.txt
uv pip install --no-deps .
uv pip install -r requirements-test.txt

# Run all gates
ruff check ecs_deploy tests \
  && ruff format --check ecs_deploy tests \
  && pyright ecs_deploy \
  && pytest --cov ecs_deploy \
  && hadolint Dockerfile \
  && actionlint \
  && yamllint .github/
```

---

## Dependency management

Dependencies live in two files:

- `requirements.in` — **hand-edited.** Direct, top-level deps only. Mirrors
  `setup.py`'s `install_requires`.
- `requirements.txt` — **generated.** Fully-pinned, hashed lockfile. Used
  by the `Dockerfile` (`uv pip sync requirements.txt`) and recommended for
  consumers who want reproducible installs.

### Regenerating the lockfile (with cooldown)

We apply a **7-day cooldown** to all dependency upgrades — fresh package
releases must sit in the wild for at least a week before our builds adopt
them. This is a supply-chain control: a malicious package release that gets
caught by PyPI within 24h will be yanked before we ever install it.

```bash
# macOS
CUTOFF="$(date -v-7d +%Y-%m-%d)"
# Linux
# CUTOFF="$(date -d '7 days ago' +%Y-%m-%d)"

uv pip compile requirements.in \
  --python-version 3.13 \
  --generate-hashes \
  --exclude-newer "$CUTOFF" \
  --output-file requirements.txt
```

### CVE-driven cooldown bypass

If a critical CVE is published in a direct dep and the fix is < 7 days old,
add a per-package override:

```bash
uv pip compile requirements.in \
  --python-version 3.13 \
  --generate-hashes \
  --exclude-newer "$CUTOFF" \
  --exclude-newer-package "<vulnerable-pkg>=$(date +%Y-%m-%d)" \
  --output-file requirements.txt
```

Document the bypass in `requirements.in` with a comment naming the CVE,
mirroring the
[gfi-mcp pattern](https://github.com/ignitetech-group/gfi-mcp/blob/main/requirements.in).

---

## Common pitfalls (what agents repeatedly get wrong)

- **Don't bump `requirements.txt` manually.** Always re-run `uv pip
  compile` with the cooldown flag. Manual edits desync the lockfile from
  `requirements.in`.
- **Don't drop the `--generate-hashes` flag.** Hashes are the supply-chain
  control for transitive deps. A lockfile without hashes is a list of
  un-verified versions.
- **Don't introduce `actions/checkout@v4` (or any unpinned action).**
  Every `uses:` line in `.github/workflows/` is SHA-pinned with a trailing
  `# vX.Y.Z` comment. Bumping is fine; unpinning is not.
- **Don't add a top-level dep without the user's nod.** New deps expand
  the supply-chain surface. Justify them.
- **Don't switch the Docker base image without re-running the Dockerfile
  smoke-test locally.** Upstream tags occasionally regress (e.g. 3.13.x
  point releases that break wheel compat); test before pushing.
- **Don't restore the deleted `release.yml` / `docker.yml` workflows.**
  We don't publish to PyPI or Docker Hub from this fork — those were
  upstream-personal pipelines using secrets we don't own. (See the fork
  notice in `README.rst`.)

---

## Reading order for new contributors

1. [`README.rst`](./README.rst) — fork notice + upstream's user-facing CLI docs.
2. This file (you are here) — engineering contract.
3. [`setup.py`](./setup.py) — package metadata + declared deps.
4. [`ecs_deploy/cli.py`](./ecs_deploy/cli.py) — the click command tree (one
   command per ECS action).
5. [`tests/test_cli.py`](./tests/test_cli.py) — smoke + integration tests
   for the CLI surface.
