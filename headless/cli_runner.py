#!/usr/bin/env python3
"""
Headless CLI Runner

- デフォルトの設定・出力先は `headless/` 配下
  - 設定: `headless/configs/*.json`
  - 出力: `headless/output/`
- ランログ(JSONL)は `runs/<plan_id>/<timestamp>.jsonl`
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Any, Dict

# .env の読み込み（任意）
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# プロジェクトルートを sys.path に追加（このファイルは headless/ 配下にあるため）
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Streamlit を `streamlit run` なしで読み込むと発生する冗長な WARNING を抑止
import logging
import warnings


def _suppress_streamlit_baremode_warnings() -> None:
    """Suppress noisy Streamlit warnings when running in bare mode.

    - missing ScriptRunContext
    - Session state does not function when running a script without `streamlit run`
    """
    targets = [
        "streamlit.runtime.scriptrunner_utils.script_run_context",
        "streamlit.runtime.state.session_state_proxy",
        "streamlit.runtime.scriptrunner_utils",
    ]
    for name in targets:
        lg = logging.getLogger(name)
        try:
            lg.setLevel(logging.ERROR)
            lg.propagate = False
        except Exception:
            continue
    # Umbrella for any other Streamlit loggers
    try:
        logging.getLogger("streamlit").setLevel(logging.ERROR)
    except Exception:
        pass
    # In case some paths use warnings.warn
    try:
        warnings.filterwarnings("ignore", message=".*ScriptRunContext.*")
        warnings.filterwarnings("ignore", message=".*Session state does not function.*")
    except Exception:
        pass


# 可能な限り早い段階で抑止を適用（以降の import で Streamlit が間接的に読み込まれても静かにする）
_suppress_streamlit_baremode_warnings()

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner
from core.plan.execution_context import ExecutionContext


HEADLESS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_DIR = HEADLESS_DIR / "configs"
DEFAULT_OUTPUT_DIR = HEADLESS_DIR / "output"


def _load_json_file(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_execution_context(args) -> ExecutionContext:
    # ベース
    if args.config:
        execution_context = ExecutionContext.from_config_file(args.config)
    else:
        execution_context = ExecutionContext()

    # ヘッドレスフラグ
    execution_context.headless_mode = True if args.headless else execution_context.headless_mode

    # 出力先（未指定なら headless/output）
    if args.output:
        execution_context.output_dir = Path(args.output)
    elif execution_context.output_dir is None:
        execution_context.output_dir = DEFAULT_OUTPUT_DIR

    # 変数
    if args.vars:
        if args.vars.strip().startswith("{"):
            vars_data = json.loads(args.vars)
        else:
            vars_path = Path(args.vars)
            vars_data = _load_json_file(vars_path)
        execution_context.vars_overrides.update(vars_data)

    # ファイル入力（指定がなければ headless/configs/files_config.json を自動採用）
    files_data = None
    if args.files:
        files_data = _load_json_file(Path(args.files))
    else:
        default_files = DEFAULT_CONFIG_DIR / "files_config.json"
        if default_files.exists():
            files_data = _load_json_file(default_files)
    if isinstance(files_data, dict):
        execution_context.file_inputs.update({k: Path(v) for k, v in files_data.items()})

    # UIモック（指定がなければ headless/configs/ui_mocks.json を自動採用）
    mocks_data = None
    if args.ui_mocks:
        mocks_data = _load_json_file(Path(args.ui_mocks))
    else:
        default_mocks = DEFAULT_CONFIG_DIR / "ui_mocks.json"
        if default_mocks.exists():
            mocks_data = _load_json_file(default_mocks)
    if isinstance(mocks_data, dict):
        execution_context.ui_mock_responses.update(mocks_data)

    return execution_context


def output_results(results: dict, output_dir: Optional[Path], plan_id: str) -> None:
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        results_file = output_dir / f"{plan_id}_results.json"
        with results_file.open("w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print(f"Results saved to: {results_file}")

        # バイナリの保存（name/bytes, workbook_b64, base64 などを検出）
        import base64, ast

        def _try_write(obj: Dict[str, Any], default_name: str) -> bool:
            # bytes（本物）
            if isinstance(obj.get("bytes"), (bytes, bytearray)):
                name = obj.get("name", default_name)
                (output_dir / name).write_bytes(obj["bytes"])  # type: ignore[arg-type]
                print(f"Binary saved: {(output_dir / name)}")
                return True
            # bytes（{'__type': 'b64bytes', 'data': '...'} ラッパー）
            if isinstance(obj.get("bytes"), dict):
                bobj = obj.get("bytes") or {}
                try:
                    if isinstance(bobj, dict) and str(bobj.get("__type")).lower() == "b64bytes":
                        data = bobj.get("data")
                        if isinstance(data, str) and data:
                            raw = base64.b64decode(data)
                            name = obj.get("name", default_name)
                            (output_dir / name).write_bytes(raw)
                            print(f"Binary saved: {(output_dir / name)}")
                            return True
                except Exception:
                    pass
            # bytes（Python文字列表現 b'..'）
            if isinstance(obj.get("bytes"), str):
                s = obj.get("bytes") or ""
                try:
                    if isinstance(s, str) and s.startswith("b'") and s.endswith("'"):
                        b = ast.literal_eval(s)
                        if isinstance(b, (bytes, bytearray)):
                            name = obj.get("name", default_name)
                            (output_dir / name).write_bytes(b)  # type: ignore[arg-type]
                            print(f"Binary saved: {(output_dir / name)}")
                            return True
                except Exception:
                    pass
            # workbook_b64 / base64
            for k in ("workbook_b64", "base64"):
                if isinstance(obj.get(k), str) and obj.get(k):
                    try:
                        raw = base64.b64decode(obj[k])  # type: ignore[index]
                        name = obj.get("name", default_name)
                        (output_dir / name).write_bytes(raw)
                        print(f"Binary saved: {(output_dir / name)}")
                        return True
                    except Exception:
                        continue
            return False

        def _walk(o: Any, key_hint: str = "artifact") -> None:
            if isinstance(o, dict):
                # 該当なら保存
                _try_write(o, f"{key_hint}.bin")
                for k, v in o.items():
                    _walk(v, str(k))
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    _walk(v, f"{key_hint}_{i}")

        _walk(results, plan_id)

        # 追加: アーティファクトJSONもスキャンして保存（resultsに含まれない場合のフォールバック）
        try:
            plan_dir = output_dir / plan_id
            if plan_dir.exists() and plan_dir.is_dir():
                # 最新タイムスタンプのサブディレクトリを検出
                subdirs = [p for p in plan_dir.iterdir() if p.is_dir()]
                subdirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                latest_dir = subdirs[0] if subdirs else None
                artifacts_dir = latest_dir / "artifacts" if latest_dir else None
                if artifacts_dir and artifacts_dir.exists():
                    for jf in artifacts_dir.glob("*_outputs.json"):
                        try:
                            with jf.open("r", encoding="utf-8") as f:
                                data = json.load(f)
                            _walk(data, jf.stem)
                        except Exception:
                            continue
        except Exception:
            pass

    print("\n=== Execution Results ===")
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Headless CLI Runner")
    parser.add_argument("plan_file", help="Plan YAML file path")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--config", help="Execution config JSON file")
    parser.add_argument("--vars", help="Variables JSON file or JSON string")
    parser.add_argument("--files", help="Files config JSON file")
    parser.add_argument("--ui-mocks", help="UI mocks JSON file")
    parser.add_argument("--output", help="Output directory (default: headless/output)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    plan_path = Path(args.plan_file)
    if not plan_path.exists():
        print(f"Error: Plan file not found: {plan_path}")
        sys.exit(1)

    if args.verbose:
        print(f"Loading plan from: {plan_path}")

    plan = load_plan(plan_path)
    if args.verbose:
        print(f"Plan loaded: {plan.id} (nodes={len(plan.graph)})")

    exec_ctx = build_execution_context(args)
    if args.verbose:
        print(f"Execution context: {exec_ctx.to_dict()}")

    registry = BlockRegistry()
    registry.load_specs()
    runner = PlanRunner(registry=registry, default_ui_hitl=False)

    if args.verbose:
        print("Starting execution...")

    results = runner.run(plan, vars_overrides=exec_ctx.vars_overrides, execution_context=exec_ctx)

    if args.verbose:
        print("Execution finished.")

    output_results(results, exec_ctx.output_dir, plan.id)


if __name__ == "__main__":
    main()


