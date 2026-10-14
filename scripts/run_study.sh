#!/usr/bin/env bash
# Run a multi-seed training study from a git worktree pinned to one commit (D-61),
# so switching branches in the main checkout can't change the code mid-study.
#
#   scripts/run_study.sh <study-tag> [train.py args...]
#   scripts/run_study.sh loss-balanced --loss balanced --augment
#   SEEDS="42 43" COMMIT=abc1234 scripts/run_study.sh arch-resnet34 --arch resnet34 --augment
#
# The worktree shares the main checkout's PTB-XL data, signal cache and MLflow store,
# and gets its own venv from the pinned uv.lock. Remove it when the study is done:
#   git worktree remove ../ecg-study-<sha>
set -euo pipefail

study=${1:?usage: run_study.sh <study-tag> [train.py args...]}
shift
repo=$(git rev-parse --show-toplevel)
commit=$(git -C "$repo" rev-parse "${COMMIT:-HEAD}")
wt="$(dirname "$repo")/ecg-study-${commit:0:7}"

if [ ! -d "$wt" ]; then
  git -C "$repo" worktree add --detach "$wt" "$commit"
fi
ln -sfn "$repo/data/ptb-xl" "$wt/data/ptb-xl"
ln -sfn "$repo/data/cache" "$wt/data/cache"
export MLFLOW_TRACKING_URI="sqlite:///$repo/mlflow.db"

cd "$wt"
for seed in ${SEEDS:-42 43 44}; do
  echo "== $study seed $seed @ $(git rev-parse --short HEAD) ($(date '+%F %T'))"
  uv run --frozen python scripts/train.py --seed "$seed" --tag "study=$study" \
    --run-name "$study-$seed" "$@"
done
echo "== $study done ($(date '+%F %T'))"
