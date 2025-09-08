from __future__ import annotations

from pathlib import Path
import pytest
from dotenv import load_dotenv  # type: ignore

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner
from core.plan.execution_context import ExecutionContext
from tests.utils import has_llm_keys


@pytest.mark.e2e
@pytest.mark.skipif(not has_llm_keys(), reason="LLM keys not set in environment")
def test_text_similarity_compare_two_files_minimal(tmp_path: Path):
    load_dotenv()

    plan = load_plan(Path("designs/text_similarity_compare_two_files.yaml"))
    reg = BlockRegistry(); reg.load_specs()
    runner = PlanRunner(registry=reg, runs_dir=tmp_path/"runs", default_ui_hitl=False)

    out_dir = tmp_path/"out_textsim"
    # Supply two small text files
    a = Path("tests/data/nlp_compare/A.txt")
    b = Path("tests/data/nlp_compare/B.txt")
    if not a.exists() or not b.exists():
        pytest.skip("required text files missing")

    exec_ctx = ExecutionContext(
        headless_mode=True,
        output_dir=out_dir,
        ui_mock_responses={
            "upload_files": {
                "collected_data": {
                    "file_a": a.read_bytes(),
                    "file_b": b.read_bytes(),
                },
                "approved": True,
                "metadata": {"submitted": True, "mode": "collect"},
            }
        },
    )

    res = runner.run(plan, execution_context=exec_ctx)
    # Workbook generated
    wb = res.get("wb") or res.get("workbook_updated")
    assert isinstance(wb, dict) and isinstance(wb.get("bytes"), (bytes, bytearray))

