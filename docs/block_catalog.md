## ブロックカタログ（@blocks）- 実装同期版

本ドキュメントは、`core/blocks` の実装に同期したブロック一覧です。各ブロックの役割・入出力・依存と、抽象化による統廃合や分割の改善案をまとめます。

### 基盤（共通仕様）

- **ブロック種別**: `ProcessingBlock`（非UI処理）/ `UIBlock`（Streamlit UI）。
- **コンテキスト**: `BlockContext{ run_id, workspace?, vars{} }`。ノード間の軽量な状態は `vars` に保存可能。
- **登録/解決**: `BlockRegistry` が `block_specs/*.yaml` の `BlockSpec{id,version,entrypoint,...}` を読み込み、ファイルパス/ドットパスのいずれも解決。複数バージョンはセマンティックバージョンで最大を既定選択。
- **エラーポリシー**: 外部要因エラーや未設定は原則として例外送出（自動フォールバックなし）。
- **構造化出力**: LLM関連は Pydantic による型安全な構造化出力を採用（Planの `output_schema` を強制）。

---

## UI ブロック

### ui.placeholder 0.1.0
- **ファイル**: `core/blocks/ui/placeholder.py`
- **用途**: メッセージ表示の簡易プレースホルダ。
- **入力**: `message`, `output_method`, `widget_key`。
- **出力**: `value`, `output_method`, `metadata.submitted`。
- **備考**: ヘッドレス時は入力をそのまま返す。

### ui.confirmation 0.1.0
- **ファイル**: `core/blocks/ui/confirmation.py`
- **用途**: 承認/却下とコメント入力。
- **入力**: `message`, `options=["approve","reject"]`, `widget_key`。
- **出力**: `approved`, `comment`, `metadata.submitted`。
- **備考**: ヘッドレス時は即時承認を返す。

### ui.interactive_input 0.1.0
- **ファイル**: `core/blocks/ui/interactive_input.py`
- **用途**: 統合入力UI。モード別の動作を提供。
- **モード**:
  - `collect`: 要件配列 `requirements[{id,type,label,required,hint,options,...}]` に基づくフォーム確定方式（確定まで出力抑制）。
  - `confirm`: 承認/却下とコメント。
  - `inquire`: LLMで質問生成・値抽出（必須充足まで対話）。
  - `mixed`: 収集＋確認の複合。
- **出力**: `collected_data`, `approved`, `response`, `metadata`。
- **依存**: Streamlit。`inquire` は LLM キー必須。

---

## Processing ブロック

### AI

#### ai.process_llm 1.0.0
- **ファイル**: `core/blocks/processing/ai/process_llm.py`
- **用途**: 証跡（ファイル抜粋/テーブル/rows）とプロンプトを文脈に、Plan指定の `output_schema` に厳密準拠した構造化出力を生成。
- **入力**: `evidence_data`, `prompt`/`instruction`, `system_prompt?`, `output_schema`(必須), `per_file_chars`, `per_table_rows`, `group_key`。
- **出力**: `results`（動的Pydanticモデルで構造化）, `summary{files,tables,model,temperature,group_key}`。
- **特記事項**: `evidence_data.answer` に厳密JSONがあればファストパス。LLMキー未設定は例外。

### File

#### file.parse_zip_2tier 0.1.0
- **ファイル**: `core/blocks/processing/file/parse_zip_2tier.py`
- **用途**: 2階層ZIPの解析とテキスト抜粋生成。
- **入力**: `zip_bytes`。
- **出力**: `evidence{raw_size,total_files,files[{path,name,size,ext,sha1,text_excerpt}],by_dir{top->[rel_paths]}}`。

#### file.read_csv 0.1.0
- **ファイル**: `core/blocks/processing/file/read_csv.py`
- **用途**: CSVをパスまたはバイト列から読み込み。
- **入力**: `path?`, `bytes?`, `encoding=utf-8`, `delimiter=","`, `has_header=true`。
- **出力**: `rows`, `summary{path,rows[,error]}`。

### Excel

#### excel.read_data 0.1.0
- **ファイル**: `core/blocks/processing/excel/read_data.py`
- **用途**: ワークブックからシート別に行配列へ抽出。
- **入力**: `workbook{bytes|path|{name,bytes|path}}`, `read_config{header_row,skip_empty_rows,date_as_iso,sheets[]}`, `recalc{enabled,engine:"libreoffice"|"pycel",soffice_path,timeout_sec}`。
- **出力**: `data{<sheet>->[row...]}`, `summary{sheets,rows{sheet->n},recalc{enabled,status}}`。
- **備考**: 再計算は LibreOffice/pycel に対応。失敗時は例外（フォールバックなし）。

#### excel.update_workbook 0.1.0
- **ファイル**: `core/blocks/processing/excel/update_workbook.py`
- **用途**: 既存ワークブックを命令配列 `operations[]` で更新。
- **主な操作**: `add_sheet`, `copy_sheet`, `update_cells`, `append_table`, `append_rows_bottom`, `insert_rows`, `update_formula`, `update_rows_by_match`, `format_cells`, `update_cells_if`, `update_formula_range`, `replace_in_formulas`, `clear_cells`, `clear_cells_if`。
- **出力**: `workbook_updated{name,bytes}`, `workbook_b64`, `summary{operations,cells_updated,cells_formatted,rows_updated}`。

#### excel.write_results 0.1.0
- **ファイル**: `core/blocks/processing/excel/write_results.py`
- **用途**: セル更新/列更新に特化した書き込みユーティリティ。
- **入力（推奨）**:
  - `cell_updates`: `{"sheet"?, "cells": {"A1": val, ...}} | [{...}] | {"A1": val, ...}`。
  - `column_updates`: `{"sheet"?, "start_row"?, "header_row"?, "columns":[{header,path}|...], "values": list|dict|DataFrame, "write_header"?, "clear_existing"?}`（配列可）。
- **出力**: `write_summary{rows_written,sheet,workbook_name}`, `workbook_updated`, `workbook_b64`。

### Table

#### table.from_rows 0.1.0
- **ファイル**: `core/blocks/processing/table/from_rows.py`
- **用途**: `rows -> pandas.DataFrame`。
- **入力**: `rows`, `dtype?`。
- **出力**: `dataframe`（pandas未導入時は空/None）。

#### table.pandas_agent 0.1.0
- **ファイル**: `core/blocks/processing/table/df_agent.py`
- **用途**: LangChain pandas agent による DataFrame 操作（自然言語指示）。
- **入力**: `dataframes`, `instruction`, `header_type`, `flatten_multiindex=true`, `flatten_joiner="__"`, `sample_rows=1000`。
- **出力**: `answer`, `intermediate_steps?`, `summary{model,temperature,num_dataframes,...}`。
- **備考**: LLMキー必須。巨大データは先頭サンプリング。

### Transforms

#### transforms.compute_fiscal_quarter 0.1.0
- **ファイル**: `core/blocks/processing/transforms/compute_fiscal_quarter.py`
- **用途**: 会計年度/四半期から期間・対象/テンプレートシート名を算出。
- **入力**: `fiscal_year`, `quarter(Q1..Q4|1..4)`, `start_month=4`。
- **出力**: `period{start,end}`, `is_q1`, `target_sheet_name`, `template_sheet_name`, `quarter_label`。

#### transforms.filter_items 0.1.0
- **ファイル**: `core/blocks/processing/transforms/filter_items.py`
- **用途**: 条件に基づくレコードフィルタ。
- **入力**: `items`, `conditions[{field,operator,value[,value2]}]`, `options{case_insensitive=true}`。
- **演算子**: `eq, ne, gt, gte, lt, lte, contains, in, between`。
- **出力**: `filtered`, `excluded`, `summary`。

#### transforms.filter_keyword 0.1.0
- **ファイル**: `core/blocks/processing/transforms/filter_keyword.py`
- **用途**: 指定フィールド内のキーワードヒットでフィルタ。
- **入力**: `items`, `fields[]`, `keywords[]`, `case_insensitive=true`。
- **出力**: `filtered`, `excluded`, `summary`。

#### transforms.flatten_items 0.1.0
- **ファイル**: `core/blocks/processing/transforms/flatten_items.py`
- **用途**: さまざまなラッパ構造から `items` を抽出し単一の配列に結合。
- **入力**: `results_list`。
- **出力**: `items`。

#### transforms.group_evidence 0.1.0
- **ファイル**: `core/blocks/processing/transforms/group_evidence.py`
- **用途**: 証跡をディレクトリ階層等でグルーピング（foreach向け）。
- **入力**: `evidence`, `level("top_dir"|"second_dir"|"auto")`, `instruction?`。
- **出力**: `groups[{key,evidence,instruction?}]`。

#### transforms.pick_bytes / transforms.pick_object 各 0.1.0
- **ファイル**: `core/blocks/processing/transforms/pick_value.py`
- **用途**: `source` から `path` で値を抽出。`pick_bytes` は bytes/base64、`pick_object` は任意型を返す。
- **入力**: `source`, `path`。
- **出力**: `value`。

---

## ブロック組み合わせパターン

### 基本フロー
```
1) ui.interactive_input（ファイル/期間などの収集）
2) excel.read_data / file.parse_zip_2tier / file.read_csv（データ取り込み）
3) transforms.filter_items / filter_keyword（抽出）
4) ai.process_llm（業務ロジック/構造化出力）
5) ui.interactive_input: confirm（確認・修正）
6) excel.update_workbook / excel.write_results（成果物出力）
```

### foreach での分割処理
```
1) transforms.group_evidence（顧客/部門/月次で分割）
2) foreach(group): ai.process_llm -> 結果収集
3) transforms.flatten_items で集約
```

### HITL（Human-in-the-Loop）
```
1) 自動処理（ai.process_llm）
2) when 異常/未充足: ui.interactive_input（確認/追加情報収集）
3) 処理継続
```

---

## 改善提案（統廃合/分割/整合性）

- **Excel書き込みの統合**: `excel.update_workbook` と `excel.write_results` の操作DSLを一本化し、`excel.write`（セル/列/表/数式/装飾/条件/行マッチ更新）に集約。現ブロックは互換ラッパとして維持。
- **フィルタの統合**: `transforms.filter_items` と `transforms.filter_keyword` を `transforms.filter` に統合し、AND/OR、正規表現、配列含有、大小比較/範囲/部分一致を単一DSLで表現。
- **値抽出の統合**: `transforms.pick_bytes`/`pick_object` を `transforms.pick_value` に統合し、`as: bytes|object|string|json|number|boolean` で型変換/デコード（base64等）を指定可能に。現ファイル名とIDの不一致も解消。
- **表データI/Oの整合**: `file.read_csv` と `excel.read_data` の出力スキーマを統一（例: どちらも `rows` または `data{sheet->rows}` を返す規約）。拡張として `io.read_tabular` を提案。
- **ZIP解析の一般化**: `file.parse_zip_2tier` を `file.parse_archive` に拡張し、深さ/対応形式（zip/7z/tar）やテキスト抽出プラグインをパラメータ化。
- **UIとLLMの責務分離**: `ui.interactive_input` の `inquire` モードから質問生成/値抽出を `ai.inquire_collect`（Processing）として分離。UI側は表示とセッション管理に専念。
- **Excel再計算の分離**: `excel.read_data` の `recalc` を専用ブロック（`excel.recalc_libreoffice`/`excel.recalc_pycel`）へ分離し、読取処理を純粋化。Plan上で前段に配置して明確な失敗境界を確保。
- **標準サマリ/メタの統一**: すべてのブロックで `summary`/`metadata` の最小形を規定（例: `summary{inputs, outputs, timings?, notes?}`）。Excel系は常に `workbook_updated` と `workbook_b64` を返却。
- **dry_run の拡充**: 主要ブロックに `dry_run` を実装し、構造/スキーマの事前検証とテスト容易性を向上。
- **エラー型/コードの一貫性**: `core.errors` の `BlockException/BlockError/ErrorCode` を全ブロックで徹底利用し、`hint`/`recoverable` を付与。

---

## 実装優先度（提案）

### Phase 1（高）
- **excel.read_data**（安定化/検証強化）
- **excel.write（統合）** への移行計画と互換レイヤ
- **transforms.filter（統合）** DSL設計と実装

### Phase 2（中）
- **ai.inquire_collect**（UI分離）
- **io.read_tabular**（CSV/Excelの統一I/O）
- **file.parse_archive**（一般化）

### Phase 3（低）
- Table系のノーコード変換ブロック（`table.aggregate/join/pivot`）
- パフォーマンス最適化/並列化/メモリ効率化
- 監査・計測（実行ログ/メトリクスの標準化）

---

## 設計原則（要点）

- **汎用性**: 業務固有ロジックは `instruction`/設定に外部化し、ブロック自体は単一責務・再利用可能に保つ。
- **組み合わせやすさ**: 入出力のキー/構造を明確化し、大小文字無視のキー探索やパス解決等で堅牢性を担保。
- **型安全/構造化**: LLM出力は Plan の `output_schema` で厳密化し、Pydantic でバリデーション。
- **後方互換**: 新DSLへの移行時は互換ラッパ/自動変換を用意し、段階的に統合。


