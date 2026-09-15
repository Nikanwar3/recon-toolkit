import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "sample"


@pytest.fixture(scope="session", autouse=True)
def sample_data():
    if not (DATA_DIR / "erp_orders.json").exists():
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate_sample_data.py")],
            cwd=ROOT, check=True,
        )
    return DATA_DIR
