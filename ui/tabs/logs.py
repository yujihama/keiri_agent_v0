from __future__ import annotations

from pathlib import Path
import json
from datetime import datetime

import streamlit as st


def render() -> None:
    st.subheader("ログ")

    runs_dir = Path("runs")
    if not runs_dir.exists():
        st.info("まだログがありません")
        return

    # 処理名（フォルダ名）を取得
    plan_dirs = [d for d in runs_dir.iterdir() if d.is_dir()]
    plan_dirs = sorted(plan_dirs, key=lambda x: x.stat().st_mtime, reverse=True)

    if not plan_dirs:
        st.info("まだログがありません")
        return

    # 処理名選択
    plan_options = []
    for plan_dir in plan_dirs:
        plan_name = plan_dir.name
        # フォルダの最新更新時間を取得
        try:
            mtime = max((f.stat().st_mtime for f in plan_dir.rglob("*.jsonl")), default=0)
            mtime_dt = datetime.fromtimestamp(mtime)
            label = f"{plan_name} ({mtime_dt:%Y-%m-%d %H:%M:%S})"
        except (ValueError, OSError):
            label = plan_name
        plan_options.append(label)

    selected_plan = st.selectbox("処理名", ["全て"] + [d.name for d in plan_dirs])

    # 選択された処理のログファイルを収集
    all_files = []
    if selected_plan == "全て":
        all_files = list(runs_dir.rglob("*.jsonl"))
    else:
        plan_dir = runs_dir / selected_plan
        if plan_dir.exists():
            all_files = list(plan_dir.rglob("*.jsonl"))

    if not all_files:
        st.info(f"選択した処理「{selected_plan}」のログがありません")
        return

    # ファイル選択用のラベルを作成（パスを相対パスで表示）
    file_options = []
    file_paths = []
    for file_path in sorted(all_files, key=lambda x: x.stat().st_mtime, reverse=True):
        rel_path = file_path.relative_to(runs_dir)
        # Unix タイムスタンプを datetime に変換
        mtime_dt = datetime.fromtimestamp(file_path.stat().st_mtime)
        label = f"{rel_path.parent}/{rel_path.name} ({mtime_dt:%Y-%m-%d %H:%M:%S})"
        file_options.append(label)
        file_paths.append(file_path)

    if not file_options:
        st.info("ログファイルが見つかりません")
        return

    # ファイル選択
    selected = st.selectbox("ログファイル", file_options)
    if not selected:
        return

    # 選択されたファイルのパスを取得
    file_index = file_options.index(selected)
    file_path = file_paths[file_index]

    # ファイル情報を表示
    st.write(f"**ファイル**: {file_path}")
    st.write(f"**サイズ**: {file_path.stat().st_size:,}","バイト")
    mtime_dt = datetime.fromtimestamp(file_path.stat().st_mtime)
    st.write(f"**最終更新**: {mtime_dt:%Y-%m-%d %H:%M:%S}")

    # JSONLファイルを読み込み
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 行数を表示
        st.write(f"**総行数**: {len(lines):,}")

        # 最初の数行を表示（JSONLとして解析）
        st.subheader("ログ内容（JSONL形式）")

        # 各行をJSONとしてパースして表示
        parsed_lines = []
        for i, line in enumerate(lines[:100]):  # 先頭100行を表示
            line = line.strip()
            if not line:
                continue

            try:
                parsed = json.loads(line)
                parsed_lines.append(parsed)
            except json.JSONDecodeError as e:
                st.error(f"JSONパースエラー（行 {i+1}）: {e}")
                break

        # JSONデータを表示
        if parsed_lines:
            st.json(parsed_lines)

        # 行数が多い場合は警告
        if len(lines) > 100:
            st.info(f"ログファイルが大きいため、先頭100行のみを表示しています。総行数: {len(lines):,}")

        # ダウンロードボタン
        st.download_button(
            "ログファイルダウンロード",
            data="".join(lines),
            file_name=file_path.name,
            mime="application/jsonl"
        )

    except Exception as e:
        st.error(f"ログファイルの読み込みに失敗しました: {e}")
        st.exception(e)
