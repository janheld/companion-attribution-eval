# CLAUDE.md

Working rules for Claude Code in this repository.

## Scope and isolation

- This repository is self-contained. Do not read, search or import anything outside this folder.
- All data here is synthetic. Never add real conversations, real names, real places tied to real people, or data from other projects.
- Read BRIEF.md for the task and CONTEXT.md for the observed failure modes before planning anything.

## Secrets and cost

- API keys come only from environment variables. Never write keys into code, config, logs or commits. `.env` stays git-ignored.
- Before any run that calls a model API, print the estimated cost and respect the limit in the run config. Cache every model response on disk so runs are reproducible and nothing is paid twice.

## Way of working

- Plan first, then wait for approval. Then a small dry run, then wait for approval again. Only then the full run.
- Freeze generated scenarios before evaluation runs. Never regenerate them silently.
- Keep the hypothesis section in README.md unchanged once results exist. Add findings below it instead.

## Code style

- Code, comments, README and report in English. Simulated conversations in German.
- Plain Python, small modules, short functions, no unnecessary abstractions.
- Comment where a methodological decision is made (why this condition, why this label, why this sample size), not what the code obviously does.
- The repository owner must be able to read and explain every part of the code.
