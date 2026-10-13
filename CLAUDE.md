# CLAUDE.md

Standing instructions for working in this repo (for Claude Code and human contributors).
The **why** behind every rule is in [docs/DECISIONS.md](docs/DECISIONS.md); IDs below refer to it.

## What this is

An MLOps portfolio project: a 1D ResNet classifies 12-lead ECGs (PTB-XL) into five
superclasses, served by FastAPI behind **ECG Reading Practice**, a learner UI for medical
students (D-53). Infra is Terraform on GCP (GKE Autopilot, Cloud SQL, GCS), run
**ephemerally** for interview demos only.

## Commands

```bash
make help           # every workflow target
make test           # pytest (uses the real LFS model); run before every commit
make lint           # ruff + terraform fmt check
make serve          # API + learner UI on :8000 (http://localhost:8000/)
make train / promote / case-bank   # see "Models" below
```

Use the project venv: `uv run ...` or `.venv/bin/python` (Python 3.11). Don't use the
parent `ecgEnv`.

## Git and PR workflow (owner's rules)

- **One commit per PR.** Keep commits small and self-contained, with a conventional-commit
  subject (`feat(ui): ...`, `fix(casebank): ...`) and a body that explains *why*.
- **No AI attribution:** no `Co-Authored-By` trailers and no "Generated with" footers,
  in commits or in PR descriptions.
- Branch from `main`. `main` is protected (ruleset `protect-main`): a PR plus 7 green checks
  are required, and merge commits only. Never squash, rebase-merge or force-push `main`.
- Don't make "Update branch" commits on PRs: they break the one-commit rule. The ruleset
  deliberately doesn't require branches to be up to date.
- History rewrites and force-pushes are run by the owner, not the agent.
- PR description sections: **Why**, **What**, **How verified**.

## Decision log

Every meaningful decision goes into `docs/DECISIONS.md` **in the same PR** as the change:
the next free `D-xx` under its layer, an index row, and a changelog line. Supersede old
decisions; never delete them. After editing, check that the index anchors match the
headings (GitHub slugs drop characters such as `–`, `×` and `→`).

## Models and experiments

- Leak-free evaluation only: PTB-XL `strat_fold` train 1–8 / val 9 / test 10 (D-05).
  Thresholds are tuned on validation, never on test.
- Report a study as mean ± std over seeds (`--tag study=<name>`). A challenger must beat the
  champion by ≥ 0.004 macro AUC and keep the subgroup gap ≤ 0.05 (D-16, D-49).
- **Run long studies from a pinned `git worktree`**, not the working directory (D-61), and
  don't switch branches under a running job.
- After any promotion: `make case-bank` (CI fails if the bank doesn't match the model).
- Serving changes once, at the end of the experiment program (D-51). The current candidate
  is the augmented 3-seed ensemble (D-62).

## Cloud (costs real money)

- gcloud configuration `ecg` (account `chik.sahil18@gmail.com`, project `ecg-mlops-sm26`).
- The platform is ephemeral: `make demo-up`, then always `make demo-down`, and confirm the
  inventory shows no GKE, Cloud SQL or load balancers (D-28, D-35). A $10/month budget
  kill switch is the backstop (D-29).
- CD deploys only when the repo variable `DEPLOY_ENABLED=true`. Keep it `false` unless the
  platform is up.

## Security

No secrets in git, ever. Credentials come from gitignored env files (`*.example`
templates), Secret Manager, or k8s Secrets (D-32). GitGuardian and GitHub push
protection scan every push.

## Local files to leave alone

Untracked experiments belong to the owner and stay untracked:
`src/ml/explainability/{gguf,hf_llm}_explainer.py`, `src/data/`,
`scripts/*code15*.sh`.
