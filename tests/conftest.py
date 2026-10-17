import os
import tempfile
from pathlib import Path

os.environ["CB_DATA_DIR"] = tempfile.mkdtemp(prefix="claimbreaker-tests-")
os.environ["CB_DATABASE_URL"] = "sqlite:///" + str(Path(os.environ["CB_DATA_DIR"]) / "test.db")
os.environ["CB_PROVIDER"] = "deterministic"
os.environ["CB_RUNNER"] = "none"
os.environ["CB_OFFLINE"] = "true"
