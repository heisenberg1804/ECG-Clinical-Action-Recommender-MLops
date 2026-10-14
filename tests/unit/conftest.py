from importlib.util import find_spec

# CI also runs this suite with only the serving dependencies installed (D-67), to
# prove the API needs nothing more. These modules test training-side code (the
# case-bank builder, the training pipeline), so they are skipped there.
TRAINING_STACK = all(find_spec(m) for m in ("pandas", "wfdb", "mlflow"))
collect_ignore = [] if TRAINING_STACK else ["test_casebank.py", "test_training.py"]
