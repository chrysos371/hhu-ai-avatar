"""C52 case adaptation into unchanged C50 actual Avatar/SQLite sampling helpers."""
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
ASSETS = Path("/data/Users/zrh/data/hhu-ai-avatar")
PRIOR = BASE.parent / "cycle-50/审计"
sys.path.insert(0, str(PRIOR))
from sample_history import sample_trial
from verify_observations import inspect_observations

CASES = ROOT / "evals/interaction/cycle-52/correction-transfer-cases.json"
PROTOCOL = ROOT / "evals/interaction/cycle-52/correction-transfer-protocol.json"


def read(path):
    return json.loads(Path(path).read_text())


def case_for_replay(original):
    case = copy.deepcopy(original)
    case.update(group=original["family"], repeat_query_after_actor=False,
        oracle_observation={"observed_record_state": original["seed"]["status_at_query"],
            "current_record_state": original["expected_axes"]["current_record_state"]},
        review_axes=list(original["expected_axes"]))
    return case
