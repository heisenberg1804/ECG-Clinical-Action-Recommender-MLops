# Architecture & Decision Record

This document records the significant decisions in this project, in every
layer, together with the reasoning, the trade-offs, and the alternatives that
were rejected. It is versioned with the code and updated whenever a decision
is made or changed.

**How to read an entry**

- **Status**: `Accepted`, `Superseded by D-xx`, `Proposed`, or `Deprecated`.
  Decisions are superseded, never deleted, so the history stays visible.
- **Context**: the problem or constraint that forced a choice.
- **Decision**: what was chosen.
- **Why**: the reasoning.
- **Trade-offs**: what this costs or makes harder.
- **Alternatives**: options considered and why they lost.
- **Where**: the files that implement it.

**How to add one**: append it under its layer with the next free ID, add a row
to the index, and add a line to the [changelog](#changelog). If it replaces an
earlier decision, set the old one's status to `Superseded by D-xx`.

---

## Index

| ID | Decision | Layer | Status |
|---|---|---|---|
| [D-01](#d-01-portfolio-first-scope-keep-the-full-mlops-stack) | Portfolio-first scope; keep the full MLOps stack | Scope | Accepted |
| [D-02](#d-02-research-tool-not-a-medical-device) | Research tool, not a medical device | Scope | Accepted |
| [D-03](#d-03-ptb-xl-103-versioned-with-dvc-on-gcs) | PTB-XL 1.0.3, versioned with DVC on GCS | Data | Accepted |
| [D-04](#d-04-official-superclass-label-aggregation) | Official superclass label aggregation | Data | Accepted |
| [D-05](#d-05-patient-wise-strat_fold-split) | Patient-wise `strat_fold` split | Data | Accepted |
| [D-06](#d-06-decode-signals-once-into-a-float16-memmap-cache) | Decode signals once into a float16 memmap cache | Data | Accepted |
| [D-07](#d-07-one-preprocessing-function-shared-by-training-and-serving) | One preprocessing function for training and serving | Preprocessing | Accepted |
| [D-08](#d-08-1d-resnet-18) | 1D ResNet-18 | Model | Accepted |
| [D-09](#d-09-training-recipe-and-early-stopping) | Training recipe and early stopping | Training | Accepted |
| [D-10](#d-10-macro-auc-primary-thresholds-tuned-on-validation-only) | Macro AUC primary; thresholds tuned on validation only | Evaluation | Accepted |
| [D-11](#d-11-calibration-measured-on-every-run) | Calibration measured on every run | Evaluation | Accepted |
| [D-12](#d-12-fairness-as-subgroup-performance-against-labels) | Fairness as subgroup performance against labels | Evaluation | Accepted |
| [D-13](#d-13-report-the-audited-number-0910-not-the-old-9394) | Report the audited number (0.910), not the old 93–94% | Evaluation | Accepted |
| [D-14](#d-14-mlflow-with-code-and-data-lineage-on-every-run) | MLflow with code and data lineage on every run | Tracking | Accepted |
| [D-15](#d-15-registry-aliases-challenger--champion) | Registry aliases (`challenger` / `champion`) | Registry | Accepted |
| [D-16](#d-16-automated-release-gates-for-promotion) | Automated release gates for promotion | Registry | Accepted |
| [D-17](#d-17-model-identity-is-the-weights-sha256) | Model identity is the weights' sha256 | Registry | Accepted |
| [D-18](#d-18-bake-the-champion-into-the-image) | Bake the champion into the image | Serving | Accepted |
| [D-19](#d-19-explanations-grad-cam--gradient--input-no-hooks) | Explanations: Grad-CAM + gradient × input, no hooks | Explainability | Accepted |
| [D-20](#d-20-api-runtime-behaviour) | API runtime behaviour | Serving | Accepted |
| [D-21](#d-21-strict-input-contract-and-a-safe-fallback) | Strict input contract and a safe fallback | Serving | Accepted |
| [D-22](#d-22-public-unauthenticated-api) | Public, unauthenticated API | Serving | Accepted (limitation) |
| [D-23](#d-23-monitoring-prediction-log--prometheus--airflow-dags) | Monitoring: prediction log + Prometheus + Airflow DAGs | Monitoring | Accepted (rework planned) |
| [D-24](#d-24-airflow-in-local-docker-compose) | Airflow in local docker-compose | Orchestration | Accepted |
| [D-25](#d-25-ci-tests-what-would-break-a-deploy) | CI tests what would break a deploy | CI/CD | Accepted |
| [D-26](#d-26-cd-gated-switchable-smoke-tested-self-rolling-back) | CD: gated, switchable, smoke-tested, self-rolling-back | CI/CD | Accepted |
| [D-27](#d-27-keyless-github--gcp-auth) | Keyless GitHub → GCP auth | CI/CD | Accepted |
| [D-28](#d-28-two-terraform-stacks-split-by-lifetime) | Two Terraform stacks split by lifetime | Infrastructure | Accepted |
| [D-29](#d-29-hard-budget-cap-via-a-kill-switch) | Hard budget cap via a kill switch | Infrastructure | Accepted |
| [D-30](#d-30-gke-autopilot) | GKE Autopilot | Infrastructure | Accepted |
| [D-31](#d-31-one-small-cloud-sql-instance-reached-only-via-the-auth-proxy) | One small Cloud SQL instance, reached only via the Auth Proxy | Infrastructure | Accepted |
| [D-32](#d-32-secrets-never-touch-git-or-disk) | Secrets never touch git or disk | Security | Accepted |
| [D-33](#d-33-local-terraform-state) | Local Terraform state | Infrastructure | Accepted |
| [D-34](#d-34-fresh-project-bootstrap-and-an-api-readiness-gate) | Fresh-project bootstrap and an API readiness gate | Infrastructure | Accepted |
| [D-35](#d-35-teardown-order-and-a-billable-resource-audit) | Teardown order and a billable-resource audit | Infrastructure | Accepted |
| [D-36](#d-36-seed-mlflow-on-each-demo-instead-of-persisting-cloud-sql) | Seed MLflow on each demo instead of persisting Cloud SQL | Infrastructure | Accepted |
| [D-37](#d-37-project-outside-the-organization) | Project outside the organization | Infrastructure | Accepted |
| [D-38](#d-38-two-kubernetes-flavours-local-base--gke-overlay) | Two Kubernetes flavours: local base + GKE overlay | Kubernetes | Accepted |
| [D-39](#d-39-cloud-sql-auth-proxy-as-a-native-sidecar) | Cloud SQL Auth Proxy as a native sidecar | Kubernetes | Accepted |
| [D-40](#d-40-mlflow-server-image-and-sizing) | MLflow server image and sizing | Kubernetes | Accepted |
| [D-41](#d-41-measured-resource-sizing-requests--limits) | Measured resource sizing; requests == limits | Kubernetes | Accepted |
| [D-42](#d-42-deploy-time-placeholders-discovered-not-stored) | Deploy-time placeholders, discovered not stored | Kubernetes | Accepted |
| [D-43](#d-43-leaked-credentials-rotate-first-then-scrub-history) | Leaked credentials: rotate first, then scrub history | Security | Accepted |
| [D-44](#d-44-pin-everything-that-can-drift) | Pin everything that can drift | Reproducibility | Accepted |
| [D-45](#d-45-a-regression-test-for-every-bug-fixed) | A regression test for every bug fixed | Testing | Accepted |
| [D-46](#d-46-feature-branches-prs-and-merge-commits) | Feature branches, PRs, and merge commits | Workflow | Accepted |
| [D-47](#d-47-measure-seed-variance-before-claiming-improvements) | Measure seed variance before claiming improvements | Experiments | Accepted |
| [D-48](#d-48-abandon-cloud-sql-users-and-databases-on-destroy) | Abandon Cloud SQL users and databases on destroy | Infrastructure | Accepted |
| [D-49](#d-49-promotion-requires-beating-the-champion-by-more-than-seed-noise) | Promotion requires beating the champion by more than seed noise | Registry | Accepted |
| [D-50](#d-50-ensembles-are-evaluated-with-the-shared-evaluation-and-logged-as-runs) | Ensembles are evaluated with the shared evaluation and logged as runs | Experiments | Accepted |
| [D-51](#d-51-defer-serving-the-ensemble-until-the-experiment-program-finishes) | Defer serving the ensemble until the experiment program finishes | Serving | Proposed |
| [D-52](#d-52-subgroup-metrics-need-confidence-intervals) | Subgroup metrics need confidence intervals | Evaluation | Proposed |
| [D-53](#d-53-primary-users-are-medical-students-and-residents-learning-ecg-interpretation) | Primary users are medical students and residents learning ECG interpretation | Product | Accepted (design) |
| [D-54](#d-54-a-fixed-test-fold-only-case-bank-with-precomputed-model-artifacts) | A fixed, test-fold-only case bank with precomputed model artifacts | Product | Accepted (design) |
| [D-55](#d-55-frontend-preact--htm--uplot-vendored-no-build-step-served-by-fastapi) | Frontend: Preact + htm + uPlot, vendored, no build step, served by FastAPI | Frontend | Accepted (design) |
| [D-56](#d-56-the-tutor-is-a-hosted-llm-with-tool-use-grounded-in-case-bank-lookups) | The tutor is a hosted LLM with tool use, grounded in case-bank lookups | Product | Accepted (design) |
| [D-57](#d-57-answer-locking-via-signed-session-state-the-server-stays-stateless) | Answer locking via signed session state; the server stays stateless | Backend | Accepted (design) |
| [D-58](#d-58-cost-and-abuse-controls-on-the-chat-endpoint) | Cost and abuse controls on the chat endpoint | Security | Accepted (design) |
| [D-59](#d-59-llm-quality-is-tested-deterministically-in-ci-and-evaluated-on-demand) | LLM quality is tested deterministically in CI and evaluated on demand | Testing | Accepted (design) |
| [D-60](#d-60-ship-the-ui-in-two-increments) | Ship the UI in two increments | Product | Accepted (design) |
| [D-61](#d-61-long-running-studies-run-from-a-pinned-git-worktree) | Long-running studies run from a pinned git worktree | Experiments | Accepted |
| [D-62](#d-62-train-time-augmentation-is-a-consistent-but-modest-gain) | Train-time augmentation is a consistent but modest gain | Experiments | Accepted |

---

## Scope

### D-01: Portfolio-first scope; keep the full MLOps stack
- **Status**: Accepted (2026-10-10)
- **Context**: The project exists to demonstrate MLOps skills in interviews. It had grown many components, some half-built.
- **Decision**: Keep the components that show distinct, transferable skills (GKE, Cloud SQL, MLflow, Airflow, DVC, Terraform, CI/CD). Simplify or remove everything else: the ensemble, the staging overlay, unused preprocessing, and eight experiment scripts.
- **Why**: Each kept component answers an interview question ("how do you deploy, track, version, orchestrate?"). Breadth that doesn't work is a liability. A reviewer finds the one broken piece and discounts the rest.
- **Trade-offs**: A larger operational surface than the problem strictly needs. Mitigated by keeping cloud infra ephemeral (D-28).
- **Alternatives**: Collapsing to Cloud Run + SQLite would be cheaper and simpler, but it wouldn't demonstrate the target skills.

### D-02: Research tool, not a medical device
- **Status**: Accepted (2026-10-10). The action-table rewording is planned.
- **Context**: The API maps predictions to actions such as "Activate cath lab". PTB-XL's MI labels don't distinguish acute from old infarction.
- **Decision**: Label the system clearly as non-clinical (README). Explanations describe *model attention*, not ECG findings (D-19). The action table will be reworded as decision support before any UI work.
- **Why**: Overclaiming clinical capability is the fastest way to lose credibility with a technical reviewer, and it's genuinely unsafe.
- **Where**: `README.md`, `src/ml/inference/action_mapping.json`, `src/ml/explainability/explainer.py`

---

## Data

### D-03: PTB-XL 1.0.3, versioned with DVC on GCS
- **Status**: Accepted
- **Context**: Training must be reproducible from a known data version.
- **Decision**: Use PTB-XL 1.0.3 (21,799 records). Track it with DVC (`data/ptb-xl.dvc`) and push to `gs://<project>-dvc`. Record the DVC md5 on every MLflow run (D-14).
- **Why**: PTB-XL is public, well documented, has an official benchmark, and ships patient-wise folds (D-05). DVC keeps 3 GB out of git while pinning the exact version.
- **Trade-offs**: A second tool to learn. The remote must exist before `dvc pull` works. The dataset can always be re-downloaded from PhysioNet, so the remote is a convenience rather than the only copy.
- **Where**: `data/ptb-xl.dvc`, `.dvc/config`, `infra/terraform/foundation/storage.tf`

### D-04: Official superclass label aggregation
- **Status**: Accepted (2026-10-10)
- **Context**: The original code mapped SCP codes to superclasses with a hand-written dictionary that covered only some codes.
- **Decision**: Aggregate with `scp_statements.csv` (`diagnostic == 1` → `diagnostic_class`), as in the PTB-XL benchmark. Drop records with no diagnostic superclass. This leaves 21,388 records.
- **Why**: It makes results comparable to published numbers, and it's the dataset authors' own definition.
- **Where**: `src/ml/training/data.py::load_metadata`

### D-05: Patient-wise `strat_fold` split
- **Status**: Accepted (2026-10-10). Supersedes the random 80/10/10 splits.
- **Context**: The audit found that random splits put about 17% of test records next to the same patient's ECGs in training. The ensemble was re-split with different settings, so 72% of its "test" set was training data for one member model.
- **Decision**: Use PTB-XL's `strat_fold`: folds 1–8 train (17,084), fold 9 validation (2,146), fold 10 test (2,158). Every record of a patient is in one fold.
- **Why**: It's the only split that measures generalization to *new patients*, which is what the model is for. It's also the benchmark's split, so the numbers are comparable.
- **Trade-offs**: Lower headline numbers than before (D-13).
- **Where**: `src/ml/training/data.py::split_by_fold`; test: `tests/unit/test_training.py::test_patients_do_not_cross_splits`

### D-06: Decode signals once into a float16 memmap cache
- **Status**: Accepted (2026-10-10)
- **Context**: Decoding WFDB files on every epoch made I/O the training bottleneck.
- **Decision**: Decode every record once into `data/cache/signals_500hz_f16.npy` (2.6 GB memmap), keyed by an `ecg_id` index. Datasets open the memmap lazily per DataLoader worker. Decode with a thread pool, not processes.
- **Why**: About a minute once, instead of minutes every epoch. float16 halves disk use, and the precision loss is far below ECG measurement noise. Threads avoid macOS spawn issues and work inside Airflow workers.
- **Trade-offs**: 2.6 GB of local disk. The cache is rebuilt if the record set changes.
- **Where**: `src/ml/training/data.py::build_signal_cache`

---

## Preprocessing

### D-07: One preprocessing function shared by training and serving
- **Status**: Accepted (2026-10-11)
- **Context**: Training and inference preprocessed separately. A third, unused module (bandpass filter, 250 Hz) was what the tests covered.
- **Decision**: A single `prepare_ecg()` handles everything: orient to (12, n), resample by duration to 500 Hz, take the first 10 s, then per-lead z-score. Both the training dataset and the API call it. The unused module was removed.
- **Why**: Train/serve skew is one of the most common silent ML production bugs. One function makes it structurally impossible.
- **Trade-offs**: Signals shorter than 10 s are rejected rather than padded (D-21).
- **Where**: `src/ml/preprocessing/signal.py`

---

## Model & training

### D-08: 1D ResNet-18
- **Status**: Accepted
- **Context**: The original architecture. Published PTB-XL results show 1D ResNets near the top of the benchmark.
- **Decision**: Keep the 1D ResNet-18: 12 × 5000 input, 5 sigmoid outputs, about 8.7M parameters. Split `forward` into `forward_features` and `forward_head`.
- **Why**: Strong and well understood. The split lets explainability take gradients with respect to the feature maps without hooks (D-19).
- **Alternatives**: ResNet-34, InceptionTime and xresnet1d are candidates in the experiment program (D-47). They'll be adopted only if they beat the gates (D-16).
- **Where**: `src/ml/models/resnet1d.py`

### D-09: Training recipe and early stopping
- **Status**: Accepted (2026-10-10)
- **Decision**: BCE loss (focal loss as an option), AdamW (lr 1e-3, wd 1e-4), ReduceLROnPlateau on validation macro AUC, and early stopping with patience 5. Keep the best-validation checkpoint.
- **Why**: A standard, defensible baseline. Selecting on validation, never on test, keeps the test fold untouched for the final number.
- **Observed**: The champion peaked at epoch 13. Training loss kept falling afterward while validation stayed flat, a sign of overfitting that motivates augmentation (D-47).
- **Where**: `src/ml/training/train.py`

---

## Evaluation

### D-10: Macro AUC primary; thresholds tuned on validation only
- **Status**: Accepted (2026-10-10). Supersedes the global 0.3 threshold.
- **Decision**: Macro ROC AUC on the test fold is the headline metric, with per-class AUC alongside. Per-class decision thresholds are chosen to maximize F1 on the **validation** fold, then reported on test with F1, sensitivity and specificity. Thresholds ship with the model (`model_meta.json`).
- **Why**: AUC is threshold-free and matches the benchmark. A single global threshold ignored very different class prevalences: the tuned thresholds range from 0.21 (HYP) to 0.42 (NORM).
- **Trade-offs**: F1-optimal thresholds aren't clinically optimal. A real deployment would set sensitivity targets per class.
- **Where**: `src/ml/training/metrics.py`

### D-11: Calibration measured on every run
- **Status**: Accepted (2026-10-10)
- **Decision**: Log expected calibration error (ECE) per class and a reliability diagram for every run.
- **Why**: The API returns probabilities that people will read as risk. They have to mean what they say. The champion has ECE ≤ 0.04 per class.
- **Where**: `src/ml/training/metrics.py::expected_calibration_error`, `train.py::reliability_plot`

### D-12: Fairness as subgroup performance against labels
- **Status**: Accepted (2026-10-10)
- **Context**: Live monitoring used *demographic parity* of urgent actions. Disease prevalence really does differ by age and sex, so parity flags correct behaviour as bias.
- **Decision**: The evaluation-time fairness metric is macro AUC per subgroup (male/female; age < 40, 40–65, > 65) against ground truth. The release gate requires a max − min gap ≤ 0.05 (D-16).
- **Why**: Performance parity asks the right question: is the model *equally accurate* for each group?
- **Trade-offs**: It needs labels, so it can't run on live traffic. The live bias DAG still uses parity and is due for rework (D-23).
- **Where**: `src/ml/training/metrics.py::subgroup_auc`, `scripts/promote_model.py`

### D-13: Report the audited number (0.910), not the old 93–94%
- **Status**: Accepted (2026-10-11)
- **Decision**: Lead with fold-10 macro AUC **0.910**, with benchmark context (about 0.92–0.93 for the best published 1D CNNs). Explain in the README why earlier numbers were inflated.
- **Why**: A credible, comparable number beats a big, indefensible one. Finding and fixing your own leakage is itself a demonstration of MLOps judgement.
- **Where**: `README.md`

### Evaluation metrics reference

This reference describes what every model is measured on, how each metric is computed in this codebase, why it's used, and how *not* to misread it. The same code scores every training run, ensemble and experiment (`metrics.evaluate()`, D-50), so numbers are comparable across MLflow runs.

**Data the metrics are computed on**

| Split | PTB-XL folds | Records | Used for |
|---|---|---|---|
| Train | 1–8 | 17,084 | Fitting weights |
| Validation | 9 | 2,146 | Early stopping, LR schedule, **threshold tuning** |
| Test | 10 | 2,158 | **Every reported metric** |

The task is multi-label: a record can carry several superclasses (23.5% of test records do; mean 1.29 labels). Test-fold prevalence:

| NORM | MI | STTC | CD | HYP |
|---|---|---|---|---|
| 44.6% (963) | 25.5% (550) | 24.1% (521) | 23.0% (496) | **12.1% (262)** |

Subgroup sizes in the test fold: 1,110 male, 1,048 female; 284 under 40, 860 aged 40–65, 1,014 over 65.

**Metrics in use**

| Metric | Question it answers | How it's computed here | Why it's used | Read with care |
|---|---|---|---|---|
| **ROC AUC, per class** | How well does the model *rank* positives above negatives for this class, at any threshold? | `sklearn.roc_auc_score` on the sigmoid output, one class at a time. MLflow: `test_auc_<CLASS>` | Threshold-free, so it measures the model rather than a chosen operating point. It's also the standard per-class metric for PTB-XL. | Insensitive to prevalence, so a decent AUC on a rare class (HYP, 12%) can coexist with poor precision. Pair it with F1. |
| **Macro AUC** (headline) | Overall ranking quality, with every class weighted equally | Unweighted mean of the five per-class AUCs. MLflow: `test_macro_auc` | Equal weighting stops NORM (45% of records) from dominating. It's the PTB-XL benchmark's headline metric, so results are comparable to published work. | One number hides per-class weakness: 0.910 macro includes HYP at 0.83. Always read the per-class row too. |
| **F1 at tuned threshold**, per class | At the threshold we'd actually use, how well do precision and recall balance? | Threshold per class chosen on **validation** from a grid of 0.05–0.95 (step 0.01) to maximize F1, then F1 measured on test. MLflow: `test_f1_<CLASS>` | AUC alone doesn't tell you how the deployed decision rule behaves. | Depends on prevalence. F1-optimal isn't clinically optimal (a real deployment would set per-class sensitivity targets). |
| **Sensitivity / specificity**, per class | Of true positives, how many are caught? Of true negatives, how many are correctly cleared? | At the same validation-tuned thresholds, on test. MLflow: `test_sensitivity_<C>`, `test_specificity_<C>` | The language clinicians use, and they show the trade-off F1 hides. | Moves with the threshold; compare only at the stated thresholds. |
| **Tuned thresholds** | Not a metric: the decision rule that ships | Stored in `model_meta.json` and applied by the API only when its version matches the weights (D-17) | Reported because they define what the other threshold-based metrics mean | Re-tuned for every model; never copy them between models. |
| **ECE**, per class | When the model says *p*, is it right about *p* of the time? | 10 equal-width probability bins. ECE = Σ (bin share × \|observed frequency − mean predicted probability\|). MLflow: `test_ece_<CLASS>` | The API returns probabilities that people will read as risk, so they must be calibrated, not just well ranked. | Depends on the binning, and it's noisier than AUC across seeds (max per class 0.039–0.056 over 3 seeds, D-47). Read it as "roughly calibrated", not to the third decimal. |
| **Reliability diagram** | *Where* on the probability scale is the model over- or under-confident? | Observed frequency vs mean prediction per bin, per class. Artifact: `reliability.png` | ECE is one number; the plot shows the shape (e.g. HYP overconfident at 0.7–0.85). | Bins with few samples swing widely. |
| **Subgroup macro AUC** | Is the model equally *accurate* for each sex and age band? | Macro AUC restricted to each group: male/female (PTB-XL `sex` 0/1), age < 40 / 40–65 / > 65. PTB-XL encodes ages over 89 as 300, so those fall in > 65. MLflow: `test_auc_sex_*`, `test_auc_age_*` | Performance parity against ground truth is the right fairness question for diagnosis, unlike demographic parity (D-12). | **Small groups give noisy numbers.** The under-40 test group has only 7 MI and 10 HYP positives, so its per-class AUCs, and therefore its macro AUC, are unstable (D-52). |
| **Subgroup gap** | How far apart are the best- and worst-served groups? | max − min over the five subgroup macro AUCs. Release gate: ≤ 0.05 (D-16) | A single, gateable fairness number | Inherits the small-group noise above. The max − min of noisy numbers is biased upward. |
| **Seed mean ± std** | Is an observed difference larger than retraining noise? | Same recipe, seeds 42/43/44; sample std (ddof = 1). Currently 0.9114 ± 0.0018 | Defines the promotion margin (0.004 ≈ 2 std, D-49) and keeps "improvements" honest | Three seeds give a rough estimate of the std, not a precise one. |

**Considered but not used (yet)**

| Metric | Why not |
|---|---|
| Accuracy | Ill-defined for multi-label outputs, and dominated by the majority class in imbalanced data |
| Micro-averaged AUC | Pools all labels, so NORM's volume dominates and the rare classes we care about most disappear |
| PR-AUC (average precision) | **Worth adding for HYP** (12% prevalence), where precision matters and ROC AUC is flattering. A candidate for the next metrics change |
| Brier score | Overlaps with ECE plus AUC; it would be a reasonable, binning-free calibration companion to add alongside PR-AUC |

**Operational metrics (serving, not model quality)**

The API exposes these on `/metrics` (Prometheus): `ecg_prediction_latency_seconds` (histogram), `ecg_predictions_total` by primary diagnosis and urgency, `ecg_prediction_confidence` per class (histogram), and `ecg_model_loaded`. Every prediction is also logged to Postgres with its `model_version` and latency (D-23).

**Standing caveats for every number in this project**

- **Test-fold reuse:** gating many experiments on fold 10 slowly turns it into a selection set. That's acceptable at this scale; the stricter design would hold out a final fold (D-16).
- **Label noise:** PTB-XL labels carry cardiologist likelihoods (0–100), and some are uncertain, so perfect agreement isn't the ceiling.
- **One dataset:** there's no external validation yet (another hospital, another device). All numbers describe PTB-XL-like data.

### D-52: Subgroup metrics need confidence intervals
- **Status**: Proposed (2026-10-12)
- **Context**: In the test fold, the under-40 group has 7 MI and 10 HYP positives. Per-class AUCs on so few positives are unstable, and the subgroup gap (a max − min) is biased upward by that noise.
- **Decision**: Report bootstrap 95% confidence intervals for subgroup macro AUCs and the gap (resampling patients within the test fold). Gate on the gap's point estimate as now, but flag gates whose interval crosses the threshold.
- **Why**: A fairness gate is only as trustworthy as the uncertainty around the number it gates on.

---

## Experiment tracking & model registry

### D-14: MLflow with code and data lineage on every run
- **Status**: Accepted (2026-10-10)
- **Decision**: Every run logs its config, per-epoch curves, and all evaluation metrics (per class, per subgroup, calibration), plus tags for `git_commit`, `git_dirty`, `data_dvc_md5` and `split`. Lineage is captured **once at run start**.
- **Why**: Any model can be traced to the exact code and data that produced it. Capturing at the start matters: an early version re-read git at the end, so a commit made during an 85-minute run was recorded as the model's source.
- **Where**: `src/ml/training/train.py::lineage_tags`

### D-15: Registry aliases (`challenger` / `champion`)
- **Status**: Accepted (2026-10-10). Supersedes MLflow stages (`Production`).
- **Decision**: Training registers each new model as `ecg-resnet1d@challenger`. Promotion moves `@champion`.
- **Why**: Stages are deprecated in MLflow 3. Aliases are explicit, movable pointers, and "challenger vs champion" is the standard pattern.
- **Where**: `src/ml/training/train.py`, `scripts/promote_model.py`

### D-16: Automated release gates for promotion
- **Status**: Accepted (2026-10-10)
- **Decision**: `promote_model.py` promotes the challenger only if (1) its test macro AUC ≥ the champion's, and (2) its subgroup AUC gap ≤ 0.05. It then exports the challenger's exact serving artifacts to `models/`.
- **Why**: Promotion becomes a policy rather than a judgement call, and fairness can't be traded away for accuracy without it showing up.
- **Trade-offs**: Gating on the test fold reuses test data for model selection across many experiments. Acceptable at this scale; a held-out "final" fold would be the stricter design.
- **Where**: `scripts/promote_model.py`

### D-17: Model identity is the weights' sha256
- **Status**: Accepted (2026-10-10). Supersedes the hard-coded `"resnet18-v0.1.0"`.
- **Decision**: `model_version = resnet18-<first 12 hex chars of sha256(weights)>`. Every logged prediction carries it. Tuned thresholds in `model_meta.json` apply **only** if its version matches the loaded weights.
- **Why**: A version string that can't drift from the artifact. A stale metadata file can never silently apply another model's thresholds.
- **Where**: `src/ml/inference/predictor.py`; tests: `tests/unit/test_inference.py::TestModelMeta`

### D-18: Bake the champion into the image
- **Status**: Accepted
- **Decision**: The API image contains `models/best_model.pth` (Git LFS) and `model_meta.json`, exported by promotion. It does not pull from the registry at startup.
- **Why**: Image = code + model, immutable and reproducible. No runtime dependency on MLflow, and rollback is just the previous image.
- **Trade-offs**: A new model needs a new image (CD builds one on merge). The image is about 2 GB (slimming is planned).
- **Alternatives**: Loading `models:/ecg-resnet1d@champion` at startup decouples model releases from code releases, but adds a startup dependency and a moving target. It's worth revisiting if model releases become frequent.

---

## Explainability

### D-19: Explanations: Grad-CAM + gradient × input, no hooks
- **Status**: Accepted (2026-10-11). Supersedes the tiled Grad-CAM.
- **Context**: The original Grad-CAM tiled one temporal map across all 12 leads, so every ECG reported V6/V5/V4/V3 as most important. It ran on the raw signal, not the model input, and leaked a module hook per request.
- **Decision**:
  - Grad-CAM on the last block gives *when*.
  - Gradient × input per lead gives *which leads*.
  - Both come from one `torch.autograd.grad` call on the exact preprocessed tensor that was scored.
  - Heatmaps are returned at 50 Hz.
  - Descriptions describe where the model attended, not clinical findings.
- **Why**: Correct, thread-safe (no shared state on the model), and honest. On the test-fold MI example, the top leads include II and aVF (inferior leads), which is anatomically sensible.
- **Trade-offs**: About 0.9 s extra latency per explained request on GKE (backward pass).
- **Where**: `src/ml/explainability/explainer.py`. The optional local-LLM phrasing is disabled in prod (`DISABLE_LLM_EXPLANATIONS`).

---

## Serving

### D-20: API runtime behaviour
- **Status**: Accepted (2026-10-11)
- **Decisions**:
  - The model loads at startup; `/ready` returns 503 until it's loaded, while `/health` stays up.
  - CPU-bound inference runs in a threadpool, so the event loop stays responsive.
  - Prediction logging to Postgres is **best-effort**, with a 5 s connect timeout. A database outage never fails a prediction or pulls pods out of rotation.
  - The API creates its own schema (idempotent) on first connection.
- **Why**: Readiness should reflect the ability to serve. Logging is important but secondary to answering. Schema creation fixes a real bug: a fresh Cloud SQL instance had no `predictions` table, so logging failed silently.
- **Where**: `src/api/main.py`, `src/api/routes/health.py`, `src/api/routes/predict.py`, `src/db.py`

### D-21: Strict input contract and a safe fallback
- **Status**: Accepted (2026-10-11)
- **Decisions**:
  - Input: 12 leads, at least 10 s, `sampling_rate` 100–2000 Hz; resampled by duration.
  - NaN, inf or ragged leads return 400.
  - When no class exceeds its threshold, the API recommends "manual ECG review" rather than implying a normal ECG.
- **Why**: Previously `sampling_rate` was ignored, so any length was stretched to 5000 samples. The no-confident-class path crashed with a 500. "Not confident" must never be presented as "normal".

### D-22: Public, unauthenticated API
- **Status**: Accepted as a limitation
- **Decision**: The demo API has no authentication or rate limiting. CORS allows any origin but no credentials.
- **Why**: It runs only for short demos (D-28), and interviewers need to hit it without setup.
- **Trade-offs**: Not acceptable for real data. An API key or IAP would be the first change before any persistent deployment.

---

## Monitoring & orchestration

### D-23: Monitoring: prediction log + Prometheus + Airflow DAGs
- **Status**: Accepted. Rework planned.
- **Decision**: Every prediction is logged to Postgres (inputs' metadata, outputs, model version, latency). `/metrics` exposes Prometheus counters and histograms. Airflow DAGs run Evidently drift checks (hourly) and bias checks (daily) and email on alerts.
- **Known gaps**: Drift watches metadata and output distributions, not the ECG signal itself. The live bias check uses demographic parity (see D-12).
- **Planned**: Signal-level drift features, and a retraining DAG that closes the loop (drift → retrain → gates → register).
- **Where**: `src/monitoring/`, `airflow/dags/`

### D-24: Airflow in local docker-compose
- **Status**: Accepted
- **Decision**: Run Airflow locally with docker-compose. SMTP credentials and alert recipients come from a gitignored `docker/.env.airflow`.
- **Why**: It demonstrates the same skills (DAGs, operators, XCom, branching, alerting) at $0.
- **Alternatives**: Cloud Composer starts at hundreds of dollars a month. Airflow on GKE via Helm would be heavy for an ephemeral cluster.
- **Where**: `docker/docker-compose.airflow.yml`

---

## CI/CD

### D-25: CI tests what would break a deploy
- **Status**: Accepted (2026-10-11). Supersedes CI that only ran `uv sync`.
- **Decision**: On every PR and push, CI runs:
  - ruff
  - pytest against the **real** LFS model, with coverage
  - a kustomize render of both overlays, plus a guard that only the four deploy-time placeholders remain
  - `terraform fmt -check` and `validate` for both stacks
  - Docker builds of both images
- **Why**: Each job catches a class of failure that would otherwise surface during a paid deploy. CI had been reduced to dependency installation and passed without testing anything.
- **Where**: `.github/workflows/ci.yml`

### D-26: CD: gated, switchable, smoke-tested, self-rolling-back
- **Status**: Accepted (2026-10-11). Supersedes deploy-on-every-push.
- **Decision**:
  - CD runs only after CI succeeds on `main` (`workflow_run`), or manually (`workflow_dispatch`).
  - It runs only when the `DEPLOY_ENABLED` repo variable is `true`.
  - It builds the exact commit that passed, deploys with the same script used locally, smoke-tests both services, and runs `kubectl rollout undo` on failure.
- **Why**: Never deploy untested code. Never deploy to infrastructure that's torn down. Never leave a broken rollout in place.
- **Where**: `.github/workflows/cd.yml`, `scripts/deploy_gke.sh`

### D-27: Keyless GitHub → GCP auth
- **Status**: Accepted (2026-10-11). Supersedes the `GCP_SA_KEY` JSON secret.
- **Decision**: Workload Identity Federation. GitHub's OIDC token is exchanged for short-lived credentials, and only `assertion.repository == <this repo> && ref == main` qualifies. The deployer service account has the minimum roles needed: registry writer, GKE developer, Cloud SQL viewer, and accessor on two secrets.
- **Why**: There is no long-lived key to leak, which is precisely how this project's previous credentials ended up public.
- **Where**: `infra/terraform/foundation/github_wif.tf`

---

## Infrastructure

### D-28: Two Terraform stacks split by lifetime
- **Status**: Accepted (2026-10-11)
- **Decision**:
  - `foundation/` is permanent: budget and kill switch, DVC and MLflow buckets, Artifact Registry, WIF.
  - `platform/` is ephemeral: GKE, Cloud SQL, workload identities, DB secrets.
  - `make demo-up` / `make demo-down` create and destroy the platform.
- **Why**: The project is shown only in interviews. Pieces that are cheap and stateful persist; pieces that are expensive and stateless don't. A demo costs about $0.35, and idle cost is cents a month.
- **Trade-offs**: About 15 minutes to spin up. The platform's database state is lost on teardown (handled by D-36).
- **Where**: `infra/terraform/`, `Makefile`, `infra/README.md`

### D-29: Hard budget cap via a kill switch
- **Status**: Accepted (2026-10-11)
- **Context**: The original project ran an always-on Cloud SQL instance for months unnoticed, because alerts went to an unread inbox.
- **Decision**:
  - A $10/month budget, alerting at 50%, 90% and 100% of actual spend and at 100% of forecast, to the **main** inbox.
  - At 100% of actual spend, Pub/Sub triggers a gen2 Cloud Function that **unlinks billing** from the project.
  - The decision logic is a pure, unit-tested function; forecasts never trigger it.
- **Why**: GCP budgets only alert. This actually stops spending.
- **Trade-offs**: Budget data lags by hours, so spend can overshoot slightly. Disabling billing stops, and may eventually delete, billable resources. That's acceptable for ephemeral demo infrastructure.
- **Verified**: A real Cloud Billing notification and a synthetic message both reached the function in production.
- **Where**: `infra/terraform/foundation/kill_switch.tf`, `kill_switch/`

### D-30: GKE Autopilot
- **Status**: Accepted
- **Decision**: An Autopilot cluster in us-central1, REGULAR channel, deletion protection off.
- **Why**: Billed per pod request, not per node. GKE's free tier covers the cluster fee for one cluster, and there are no node pools to manage.
- **Alternatives**:
  - GKE Standard needs a node pool that bills even when idle.
  - Cloud Run is cheaper still, but doesn't demonstrate Kubernetes.

### D-31: One small Cloud SQL instance, reached only via the Auth Proxy
- **Status**: Accepted (2026-10-11)
- **Decision**:
  - Postgres 15 on db-f1-micro (Enterprise edition), zonal, 10 GB HDD.
  - Two databases (`ecg_predictions`, `mlflow`) on one instance.
  - A public IP with **no authorized networks**, so only the IAM-authenticated Auth Proxy can connect.
  - No backups, no HA, no deletion protection.
  - A random name suffix each time.
- **Why**: The cheapest tier, and one instance serves both needs. Proxy-only access gives IAM authentication without a VPC peering setup. The console's "health issues" are deliberate for an ephemeral demo: the sources of truth are git, DVC and the GCS artifacts. Instance names can't be reused for about a week, hence the suffix.
- **Where**: `infra/terraform/platform/main.tf`

### D-33: Local Terraform state
- **Status**: Accepted
- **Decision**: State lives locally (gitignored). Platform state contains generated DB passwords.
- **Why**: There's a single operator; remote state adds a bootstrap dependency without benefit.
- **Revisit when**: A second person applies, or applies run from CI. Then use a GCS backend with locking.

### D-34: Fresh-project bootstrap and an API readiness gate
- **Status**: Accepted (2026-10-12)
- **Context**: The first `apply` on a new project failed twice.
  1. With `user_project_override` (required for the Budgets API), Terraform bills its calls to the project, so it couldn't enable the very APIs it needed.
  2. Service accounts were created in parallel with enabling the IAM API.
- **Decision**: `make foundation` enables four bootstrap APIs with gcloud first. A 90 s `time_sleep` follows API enablement, and every resource depends on it.
- **Why**: Enabling an API returns before it's usable everywhere. Only a fresh project exposes this, which is exactly when you rebuild.
- **Where**: `Makefile`, `infra/terraform/foundation/apis.tf`

### D-35: Teardown order and a billable-resource audit
- **Status**: Accepted (2026-10-11)
- **Decision**: `make demo-down` deletes the app namespace on the GKE context *explicitly*, then destroys the platform, then runs `scripts/gcp_inventory.sh`.
- **Why**: Destroying a cluster can orphan the cloud load balancer created for a `LoadBalancer` Service, about $18/month that nothing would ever clean up. The audit script never prompts, never enables APIs, and never prints "(none)" when a check actually failed.
- **Amended (2026-10-12)**: The inventory now runs **even when destroy fails**, and the failure is still reported. During the first real teardown, destroy stopped partway and `make` skipped the audit, so Cloud SQL kept billing with no warning. A partial teardown is exactly when the audit matters most.
- **Where**: `Makefile`, `scripts/gcp_inventory.sh`

### D-48: Abandon Cloud SQL users and databases on destroy
- **Status**: Accepted (2026-10-12)
- **Context**: The first real `make demo-down` destroyed the cluster but failed on `google_sql_user.ecg`. Postgres refuses to drop a role that owns objects, and the API creates its tables as `ecg_user` (D-20). Terraform deletes users *before* the instance, so the Cloud SQL instance was left running.
- **Decision**: `deletion_policy = "ABANDON"` on `google_sql_user` and `google_sql_database`. On destroy, Terraform drops them from state, and deleting the instance removes them for real.
- **Why**: Deleting users or databases individually before deleting their instance is pointless work that can only fail.
- **Trade-offs**: None for an instance destroyed as a unit. If users were ever removed independently of the instance, they'd need explicit cleanup.
- **Where**: `infra/terraform/platform/main.tf`

### D-36: Seed MLflow on each demo instead of persisting Cloud SQL
- **Status**: Accepted (2026-10-12)
- **Decision**: After deploy, `make seed-mlflow` copies the champion's run (params, every metric point, lineage tags, artifacts) from the local MLflow, and registers `ecg-resnet1d@champion` under it. It's idempotent.
- **Why**: It keeps the platform fully ephemeral at $0 idle, while interviewers always see the real experiment and registry.
- **Alternatives**: Keeping Cloud SQL stopped between demos would persist history for about $1–4/month, but makes the database a pet.
- **Verified**: The model loaded from the cluster registry gives a 0.0 max logit difference vs local.
- **Where**: `scripts/seed_mlflow.py`

### D-37: Project outside the organization
- **Status**: Accepted (2026-10-12)
- **Decision**: `ecg-mlops-sm26` has no parent organization.
- **Why**: Organization policies (for example, on external load balancers or keys) could block the demo, and a single-person project gains nothing from org membership.

---

## Kubernetes

### D-38: Two Kubernetes flavours: local base + GKE overlay
- **Status**: Accepted (2026-10-11). Supersedes base + staging + prod.
- **Decision**:
  - `k8s/base` is a complete local stack (API, Postgres, MLflow) for minikube.
  - `k8s/overlays/prod` deletes the local database and volumes, and adds Cloud SQL proxies, Workload Identity and GCS.
- **Why**: The base runs anywhere for free, and it caught four MLflow bugs before any cloud spend. The staging overlay pinned a stale image and no pipeline used it.
- **Where**: `k8s/`, `scripts/deploy-minikube.sh`

### D-39: Cloud SQL Auth Proxy as a native sidecar
- **Status**: Accepted (2026-10-11)
- **Decision**: The proxy runs as an `initContainer` with `restartPolicy: Always`, pinned to `2.25.4`.
- **Why**: Native sidecars start before the app and stop after it, so the database tunnel exists at startup and outlives graceful shutdown. Pinning replaced `:latest`.

### D-40: MLflow server image and sizing
- **Status**: Accepted (2026-10-11)
- **Decision**:
  - A custom image: MLflow 3.8.0 + psycopg2 + google-cloud-storage, with **every shared dependency constrained to `uv.lock`**.
  - Postgres backend store; artifacts proxied with `--serve-artifacts` to a volume (local) or GCS (prod).
  - `MLFLOW_TRACKING_URI` pointing at the server itself.
  - `--allowed-hosts` with port wildcards; a writable `WORKDIR`; 1 worker.
- **Why**: Each item fixes a bug found on minikube:
  - An unconstrained install pulled SQLAlchemy 2.1, which MLflow 3.8 can't import.
  - The server's internal client fell back to `./mlruns` in an unwritable `/` when registering models.
  - MLflow 3 matches Host headers including the port.
- **Where**: `docker/Dockerfile.mlflow`, `k8s/base/mlflow.yaml`

### D-41: Measured resource sizing; requests == limits
- **Status**: Accepted (2026-10-11)
- **Decision**: API 500m / 1 GiB; MLflow 500m / 1 GiB; proxies 100m / 128 MiB. Requests equal limits. Both apps have startup probes.
- **Why**: Measured, not guessed. MLflow sat at about 460 MiB idle and was OOM-killed at 512 MiB; at 250m CPU half its startup was throttled and readiness flapped for minutes. Autopilot bills requests, so equal requests and limits make cost predictable.

### D-42: Deploy-time placeholders, discovered not stored
- **Status**: Accepted (2026-10-11)
- **Decision**:
  - The prod overlay contains four `${...}` placeholders (project, SQL connection, two images).
  - `deploy_gke.sh` discovers their values with gcloud, copies DB passwords from Secret Manager, and renders with `envsubst`.
  - CI fails if any other placeholder appears.
- **Why**: There are no project-specific values in git, and CD needs no Terraform state.
- **Alternatives**: Kustomize `replacements` is more native but much harder to read. Gitignored env files can't be reproduced in CI.

---

## Security

### D-32: Secrets never touch git or disk
- **Status**: Accepted (2026-10-11)
- **Decision**:
  - DB passwords are generated by Terraform and stored in Secret Manager, then copied into k8s Secrets at deploy time.
  - Locally, minikube gets a random password from the deploy script.
  - SMTP credentials live in a gitignored env file with an `.example` template.
  - `.dockerignore` keeps env files and keys out of build contexts.
  - GitGuardian scans every PR.
- **Why**: The project previously published a Gmail app password and a Cloud SQL password in a public repo.

### D-43: Leaked credentials: rotate first, then scrub history
- **Status**: Accepted (2026-10-10)
- **Decision**: Revoke the leaked Gmail app password; the leaked database disappeared with the deleted project. Then rewrite history with `git filter-repo --replace-text` and force-push.
- **Why**: Rotation is what actually removes the risk. Scrubbing is hygiene, because copies may already exist (GitHub keeps PR refs, and forks and scrapers exist).

---

## Reproducibility & engineering practice

### D-44: Pin everything that can drift
- **Status**: Accepted
- **Decision**: Pin all of these:
  - Python dependencies (`uv.lock`)
  - the uv image (`0.9.18`) and the proxy image (`2.25.4`)
  - the MLflow server dependencies (constrained by the lock)
  - Terraform providers, with multi-platform lock hashes
  - Python 3.11 everywhere
  - CPU-only torch wheels on Linux; default wheels on macOS
- **Why**: Every unpinned dependency so far caused a real failure. On macOS the CPU torch index also made every `uv run` reinstall torch, breaking any process running at the same time.

### D-45: A regression test for every bug fixed
- **Status**: Accepted (2026-10-11)
- **Decision**: Each fixed bug gets a test, and the test is checked to **fail on the old code**. The data pipeline is tested on synthetic fixtures; inference and API tests use the real model.
- **Why**: A test that passes on the buggy code proves nothing. The 10 original bug tests all fail on the pre-fix code.
- **Where**: `tests/unit/` (51 tests)

### D-46: Feature branches, PRs, and merge commits
- **Status**: Accepted
- **Decision**: All work happens on feature branches and goes through PRs with descriptive bodies. PRs are merged with merge commits (not squash), so each self-contained, explained commit survives. Commits and PRs carry no AI attribution.
- **Why**: History reads as a design narrative, which is useful in reviews and interviews.

---

## Experiments

### D-47: Measure seed variance before claiming improvements
- **Status**: Accepted (2026-10-12). Study completed.
- **Context**: Only one model had been trained on the leak-free split. Without knowing run-to-run noise, no experiment can claim an improvement.
- **Decision**: Retrain the baseline with seeds 43 and 44, which with the champion's seed 42 gives three runs. Report macro AUC as mean ± std, and group runs with `--tag study=<name>`.
- **Result (test fold 10)**:

  | | Seed 42 | Seed 43 | Seed 44 | Mean ± std |
  |---|---|---|---|---|
  | Macro AUC | 0.9098 | 0.9110 | 0.9133 | **0.9114 ± 0.0018** |
  | HYP AUC | 0.828 | 0.833 | 0.831 | 0.831 ± 0.003 |
  | Male / female AUC | 0.919 / 0.899 | 0.921 / 0.900 | 0.925 / 0.901 | 0.922 / 0.900 |
  | Best epoch | 13 | 14 | 10 | 12.3 ± 2.1 |

- **Findings**:
  - Run-to-run noise is small (std 0.0018).
  - HYP's weakness and the ~0.022 male/female gap are **systematic**: they reproduce on every seed, so they're properties of the data or model, not luck.
  - Every run peaks at epochs 10–14 and then overfits.
  - ECE varies more than AUC across seeds (max per class 0.039–0.056), so the README's "ECE ≤ 0.04" holds for the champion only.
- **Why**: Improvements smaller than seed noise aren't improvements. This measurement directly set D-49's gate.
- **Where**: `scripts/train.py --tag`; MLflow experiment `ecg-ptbxl`, `tags.study = 'seed-variance'`

### D-49: Promotion requires beating the champion by more than seed noise
- **Status**: Accepted (2026-10-12). Amends D-16.
- **Decision**: `promote_model.py --min-delta` defaults to **0.004**, about 2× the seed-to-seed std of test macro AUC (D-47).
- **Why**: With a zero margin, simply retraining the champion's recipe with a luckier seed (e.g. seed 44, +0.0035) would have been promoted. That's churn, not progress.
- **Trade-offs**: Genuine but small gains (< 0.004) are rejected. That's acceptable, because they can't be distinguished from noise with three seeds anyway.
- **Where**: `scripts/promote_model.py`

### D-50: Ensembles are evaluated with the shared evaluation and logged as runs
- **Status**: Accepted (2026-10-12)
- **Decision**: `metrics.evaluate()` is the single evaluation used by training, ensembles and future experiments, and its metric names are pinned by a test. `evaluate_ensemble.py` averages member probabilities, tunes thresholds on validation, and logs a normal MLflow run (`study=ensemble`, member IDs as params).
- **Result**: Evaluating the 3-seed ensemble reproduced each member's training-time AUC exactly.

  | | Champion | 3-seed ensemble |
  |---|---|---|
  | Macro AUC | 0.9098 | **0.9177** (+0.0079, about 4× seed noise) |
  | Per class (NORM / MI / STTC / CD / HYP) | 0.943 / 0.930 / 0.931 / 0.917 / 0.828 | 0.947 / 0.935 / 0.936 / 0.928 / 0.842 |
  | Subgroup gap | 0.024 | 0.024 |
  | Max ECE | 0.039 | 0.038 |

- **Why**: An ensemble is only comparable to a single model if both are scored by identical code on identical data.
- **Where**: `src/ml/training/metrics.py`, `scripts/evaluate_ensemble.py`

### D-51: Defer serving the ensemble until the experiment program finishes
- **Status**: Proposed (2026-10-12)
- **Context**: The ensemble passes the gates, but serving it means about 3× inference CPU (~0.8 s vs ~0.27 s), three sets of weights in the image, and averaging explanations across members.
- **Decision**: Don't change serving yet. Run the remaining experiments (augmentation, then loss and architecture), each with 3 seeds, so their ensembles come for free. Then make **one** serving change for the best final configuration.
- **Why**: Serving changes are the expensive part (code, image, latency, explanations). Changing serving once, for the final winner, beats shipping an intermediate ensemble that the next experiment might obsolete.
- **Trade-offs**: The demo keeps serving the single champion (0.910) for now.

### D-61: Long-running studies run from a pinned git worktree
- **Status**: Accepted (2026-10-13). Tooling to follow, before the next study.
- **Context**: The augmentation study ran from the main working directory. While it ran, development switched branches, so seed 44 started from a different commit (`76a8208`) than seeds 42 and 43 (`62ab6da`). The training code happened to be byte-identical between the two, and every tree was clean, so the results are valid. A different branch could have silently changed the code under a multi-hour study, though.
- **Decision**: Every study runs from a dedicated `git worktree` checked out at the study's commit, with absolute data and cache paths and the shared MLflow store.
- **Why**: Lineage tags record *what* ran. A pinned worktree guarantees that it's *what you meant to run*, for the whole study.

### D-62: Train-time augmentation is a consistent but modest gain
- **Status**: Accepted (2026-10-13)
- **Context**: Every baseline seed overfit after epochs 10–14 (D-47). D-47's experiment plan listed augmentation first.
- **Result (seeds 42/43/44, paired with the baseline)**:

  | | Baseline | Augmented | Δ | Per-seed Δ |
  |---|---|---|---|---|
  | Macro AUC | 0.9114 ± 0.0018 | **0.9147 ± 0.0026** | +0.0033 | +0.0019 / +0.0046 / +0.0034 |
  | CD AUC | 0.921 | 0.929 | +0.0085 | all positive |
  | HYP AUC | 0.831 | 0.836 | +0.0052 | all positive |
  | Female AUC | 0.900 | 0.905 | +0.0053 | all positive |
  | Best epoch | 12.3 | 15.7 | +3.3 | overfitting starts later |

  **3-seed ensembles**:

  | | Baseline ensemble | Augmented ensemble |
  |---|---|---|
  | Macro AUC | 0.9177 | **0.9199** |
  | Max ECE | 0.038 | **0.026** |
  | Female AUC | 0.906 | 0.911 |
  | Subgroup gap | 0.024 | 0.027 |
  | HYP F1 | 0.458 | 0.479 |

- **Findings**:
  - Every seed improved, but the single-model gain (+0.0033) is below the promotion margin (0.004, D-49), so augmentation alone wouldn't be promoted.
  - The augmented ensemble is the best model so far: +0.0101 over the champion, the best calibration, and closest to the published benchmark (about 0.92–0.93).
  - Its wider subgroup gap comes largely from the noisy under-40 group (D-52) and stays well inside the gate.
- **Decision**: Keep `--augment` on for the remaining experiments, and treat the augmented ensemble as the candidate to beat. Serving is still deferred to the end of the program (D-51).

---

## Product & UI

The design review that shaped these decisions checked the first proposal against the real architecture. Each entry notes what changed and why.

### D-53: Primary users are medical students and residents learning ECG interpretation
- **Status**: Accepted (design, 2026-10-12). Not yet built.
- **Context**: The model gives calibrated probabilities for five broad categories plus attributions, validated on unseen patients. It can't distinguish acute from old MI, wasn't trained on single-lead wearables, and isn't a medical device (D-02).
- **Decision**: An educational tool: "practise reading real ECGs with an AI second opinion". The student reads first, then compares with the cardiologist label and the model, and can question the model.
- **Why**: ECG reading is learned through many real cases with feedback, and that's exactly the data (PTB-XL labels) and capability (calibrated, explainable predictions) the project has. It carries no clinical liability, and the model's limitations become teaching material instead of risks.
- **Alternatives**:
  - Clinician triage: unsafe and untruthful given the labels, and it's regulated territory.
  - Patients with wearables: single-lead input doesn't match the model.
  - ML practitioners: MLflow already serves them.
- **Consequence**: The clinical action table (D-02) is **not shown** in the UI. It stays API-only until it's reworded.

### D-54: A fixed, test-fold-only case bank with precomputed model artifacts
- **Status**: Accepted (design, 2026-10-12). **Revised** from "the tutor re-runs the model live".
- **Decision**:
  - About 300 cases, drawn **only from test fold 10**, balanced across classes and deliberately including cases the model gets wrong.
  - A build step (`build_case_bank`) precomputes, for each case: the display signal (250 Hz), predictions, per-class explanations, lead-occlusion and 1 s time-window occlusion deltas for each class, model embeddings and nearest neighbours *within the bank*, and the PTB-XL label likelihoods.
  - It also stores calibration bins and the subgroup table.
  - The bank records the champion's `model_version`, and the app refuses a bank built for different weights (the same rule as D-17). The bank is rebuilt and logged to MLflow on every promotion.
- **Why**:
  - A live 12-lead occlusion sweep costs about 3 s of CPU on a 0.5 vCPU pod and would compete with `/predict`. Precomputed lookups take milliseconds, are deterministic, and are testable.
  - Test-fold-only means the model is never shown a case it trained on, so every "the model got it right" is honest (the D-05 lesson applied to the product).
- **Trade-offs**: No live "what if" beyond the precomputed occlusions (leads and 1 s windows) in v1. The bank adds about 15–25 MB to the image.

### D-55: Frontend: Preact + htm + uPlot, vendored, no build step, served by FastAPI
- **Status**: Accepted (design, 2026-10-12). **Revised** from "plain static page".
- **Decision**:
  - One page at `/app`, served by the existing FastAPI container.
  - Preact + htm (components without JSX or a bundler) and uPlot (fast canvas time series) are vendored as version-pinned files.
  - It includes a 12-lead viewer on ECG-paper grid with attribution heatmaps, a reveal state machine, a model card, and the chat panel.
- **Why**: Streaming chat plus a viewer plus phase state is beyond comfortable vanilla JS. React + Vite would add a Node toolchain to the Docker build and CI for a component that isn't the project's showcase. No new service, deploy path or infrastructure is needed.
- **Alternatives**: Streamlit (a second service, a generic look, awkward custom ECG rendering); React + Vite (the standard choice, at the cost of the toolchain).

### D-56: The tutor is a hosted LLM with tool use, grounded in case-bank lookups
- **Status**: Accepted (design, 2026-10-12)
- **Decision**:
  - A hosted LLM API with tool use (Claude). Tools are lookups into the case bank (D-54):
    - case facts (age, sex, label likelihoods after reveal)
    - prediction
    - explanation for a given class
    - lead or time-window occlusion
    - similar cases
    - calibration at a given probability
    - subgroup performance for the patient's group
  - v1 modes: Socratic reading, interrogating the model, and comparing similar cases.
  - The rules: case-specific claims come only from tool results (the UI shows source chips), and general ECG knowledge is labelled as such.
  - Responses stream to the browser over SSE.
- **Why**: The differentiator is a tutor that *operates on this case and this model* ("cover lead III — does it still call MI?"), which a general chatbot can't do. Grounding in tools keeps it truthful.
- **Alternatives**: The local BioMistral via Ollama is free but weaker at reliable tool calling. It's kept as a later offline variant.

### D-57: Answer locking via signed session state; the server stays stateless
- **Status**: Accepted (design, 2026-10-12). **Revised** from an unspecified "enforced in code".
- **Decision**:
  - The session's case and phase (`reading` → `committed` → `revealed`) live in an HMAC-signed token issued by the server.
  - Tools that would leak the answer (prediction, label, explanations, occlusion) are **refused server-side** until the token says `committed`.
  - Conversation history is held by the client and sent each turn (LLM APIs are stateless anyway).
- **Why**: An in-memory session store breaks on pod restart or with two replicas, and a database-backed one couples chat to Cloud SQL. A signed token is stateless, survives restarts, and can't be forged to skip the lock.
- **Trade-offs**: A client could edit its own history. That's acceptable, because the lock is enforced by tool gating, not by the history.

### D-58: Cost and abuse controls on the chat endpoint
- **Status**: Accepted (design, 2026-10-12). Amends D-22 for the chat endpoint.
- **Context**: The API is public and unauthenticated (D-22). An LLM endpoint there would let anyone spend the LLM bill.
- **Decision**:
  - The chat requires a **demo passcode** (given to the interviewer).
  - Per-session turn and output-token caps, plus a per-IP rate limit.
  - A global daily token budget.
  - A `CHAT_ENABLED` kill switch.
  - The API key is in Secret Manager and synced by `deploy_gke.sh`.
  - A spend limit is set in the LLM provider's console.
  - The case viewer stays open without a passcode.
- **Why**: The same principle as the GCP kill switch (D-29): spending must have a hard ceiling that doesn't rely on anyone noticing.

### D-59: LLM quality is tested deterministically in CI and evaluated on demand
- **Status**: Accepted (design, 2026-10-12). **Revised** from "prompts evaluated in CI" and "MLflow tracing on every turn".
- **Decision**:
  - **CI** runs deterministic tests against a *fake* LLM that emits scripted tool calls. They cover answer locking, tool gating, the token caps, and that every case fact in a reply is backed by a tool result. They cost nothing and never flake.
  - The **LLM eval suite** runs on demand (a `make` target or workflow_dispatch): a fixed set of student questions per case, scored for groundedness, answer leakage before commit, numeric correctness against tool outputs, and Socratic behaviour. Results and traces are logged to MLflow.
  - **Production** logs turns and tool calls best-effort to Postgres, like predictions.
- **Why**: Real LLM calls in CI cost money, need a secret, and are non-deterministic. Tracing production turns to MLflow would make serving depend on MLflow at runtime, which D-18 deliberately avoids.

### D-60: Ship the UI in two increments
- **Status**: Accepted (design, 2026-10-12)
- **Decision**:
  - **v1a**: the case bank, case viewer, reveal, and model card, with no LLM.
  - **v1b**: the tutor (D-56–D-59) on top.
- **Why**: v1a is useful and demoable on its own at no extra cost, and it builds the case bank that v1b's tools read. Each increment ships through the existing CI/CD with a small, reviewable diff.

---

## Known limitations

| Limitation | Impact | Planned response |
|---|---|---|
| HYP is weak (AUC 0.83, F1 0.46; reproduces on every seed, D-47) | Lowest-confidence class | Augmentation helps (+0.005, D-62), and the augmented ensemble reaches 0.844; loss and architecture experiments are next |
| About 2 AUC points lower for women and patients over 40 (systematic across seeds) | Fairness gap within the gate, but real | Per-class, per-sex analysis (e.g. sex-specific HYP voltage criteria); track per experiment |
| The action table reads as orders | Clinically inappropriate framing | Reword as decision support (D-02) |
| Drift monitoring ignores the signal itself | Can't detect device or population shift | Signal-level drift features (D-23) |
| Live bias check uses demographic parity | Flags real prevalence differences | Label-based checks (D-12, D-23) |
| No API auth or rate limiting | Demo-only exposure | Add API key or IAP before persistent use (D-22) |
| About 2 GB API image | Slower deploys and cold starts | Split serving, training and monitoring dependencies |
| Local Terraform state | Single operator only | GCS backend when needed (D-33) |
| Small subgroups (e.g. the under-40 test group has 7 MI and 10 HYP positives) | Noisy subgroup AUCs and fairness gap | Bootstrap confidence intervals (D-52) |
| No PR-AUC or Brier score | Rare-class precision and calibration are partly hidden | Add to `metrics.evaluate()` (see the metrics reference) |

---

## Changelog

| Date | Change |
|---|---|
| 2026-10-10 | Audit: leaked secrets, leaky splits, invalid ensemble metric, non-functional CI. D-01, D-02, D-04, D-05, D-43 |
| 2026-10-11 | PR #2: security fixes, inference/explainability fixes, training pipeline, CI/CD, README rewrite. D-06–D-21, D-25, D-26, D-32, D-44, D-45 |
| 2026-10-11 | PR #3: Terraform foundation + platform, kill switch, WIF. D-27–D-31, D-33 |
| 2026-10-11 | PR #4: k8s rewire, MLflow server, deploy script, minikube-found fixes. D-35, D-38–D-42 |
| 2026-10-12 | PR #5: fresh-project fixes, MLflow seeding, DVC on the new bucket. D-34, D-36, D-37 |
| 2026-10-12 | First live GKE deploy verified end to end. Seed-variance study started. D-47 |
| 2026-10-12 | First real teardown failed halfway on a Cloud SQL user, leaving the instance billing; `make` skipped the audit. Fixed: D-48, D-35 amended |
| 2026-10-12 | Seed-variance study: 0.9114 ± 0.0018. Promotion margin raised to 0.004. 3-seed ensemble 0.9177. D-47 completed; D-49, D-50, D-51 |
| 2026-10-12 | Evaluation metrics reference added (definitions, computation, caveats, test-fold prevalence and subgroup sizes); D-52. Product & UI design accepted after an architecture review: D-53–D-60 |
| 2026-10-13 | Augmentation study: +0.0033 single-model (all seeds), augmented 3-seed ensemble 0.9199. D-62; study-worktree lesson D-61 |
