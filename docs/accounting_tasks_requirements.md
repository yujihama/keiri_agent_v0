# 経理業務自動化のための要件整理（汎用ブロック活用版）

本ドキュメントは、経理業務を汎用的なブロックの組み合わせで実現するための要件整理です。
設計思想に基づき、業務固有のブロックは作成せず、既存の汎用ブロック（`ui.interactive_input`、`ai.process_llm`等）をパラメータ制御で活用します。

## 1. 経理業務の分類と例

### 1.1 日次業務
- **経費精算処理**: 従業員からの経費申請を確認し、勘定科目を割り当て、承認後に仕訳を作成
- **売上・仕入計上**: 請求書や納品書から売上・仕入を記録し、売掛金・買掛金を管理
- **入出金管理**: 銀行明細と帳簿の照合、未達取引の特定

### 1.2 月次業務
- **退職給付金計算業務**: 四半期ごとの入退社情報と支払いデータから退職給付金を計算・記録
- **前受収益計算業務**: 請求書と入金明細の照合により前受収益を特定・計上
- **固定資産管理**: 減価償却費の計算、資産台帳の更新
- **在庫棚卸**: 実地棚卸結果と帳簿在庫の照合、差異分析
- **予算実績差異分析**: 予算と実績の比較、差異要因の分析

### 1.3 四半期・年次業務
- **決算整理仕訳**: 未収・未払・前払・前受の計上、引当金の計算
- **税務申告準備**: 税務調整項目の抽出、申告書類の作成準備
- **財務諸表作成**: BS/PL/CFの作成、注記事項の整理

### 1.4 随時業務
- **債権債務管理**: 売掛金・買掛金の年齢分析、督促対象の特定
- **資金繰り管理**: キャッシュフロー予測、資金計画の策定

## 2. 既存UIブロックの活用方法

### 2.1 ui.interactive_input での会計期間選択
会計期間の選択は `ui.interactive_input` の select/number タイプの組み合わせで実現：

```yaml
- id: select_accounting_period
  block: ui.interactive_input
  in:
    mode: collect
    message: "処理対象の会計期間を選択してください"
    requirements:
      - id: fiscal_year
        type: number
        label: "会計年度"
        description: "処理対象の会計年度（西暦）"
        validation:
          min: 2020
          max: 2030
      - id: period_type
        type: select
        label: "期間種別"
        options: ["年度", "四半期", "月次", "カスタム期間"]
        required: true
      - id: quarter
        type: select
        label: "四半期"
        options: ["第1四半期", "第2四半期", "第3四半期", "第4四半期"]
        description: "期間種別で四半期を選択した場合のみ"
        required: false
      - id: month
        type: number
        label: "月"
        description: "期間種別で月次を選択した場合のみ（1-12）"
        validation:
          min: 1
          max: 12
        required: false
      - id: custom_start_date
        type: text
        label: "開始日"
        description: "カスタム期間の開始日（YYYY-MM-DD形式）"
        validation:
          pattern: "^\\d{4}-\\d{2}-\\d{2}$"
        required: false
      - id: custom_end_date
        type: text
        label: "終了日"
        description: "カスタム期間の終了日（YYYY-MM-DD形式）"
        validation:
          pattern: "^\\d{4}-\\d{2}-\\d{2}$"
        required: false
```

### 2.2 Excelシート選択もui.interactive_inputで実現
```yaml
- id: select_excel_sheets
  block: ui.interactive_input
  in:
    mode: inquire
    message: "処理対象のExcelシート情報を入力してください"
    context:
      available_sheets: ${parse_excel_info.sheets}  # 事前にExcel情報を解析
    requirements:
      - id: target_sheets
        type: text
        label: "対象シート名"
        description: "カンマ区切りで複数指定可能。使用可能: ${available_sheets}"
      - id: range
        type: text
        label: "セル範囲"
        description: "A1:Z100 形式で指定（省略時は全体）"
        required: false
      - id: header_row
        type: number
        label: "ヘッダー行番号"
        description: "データのヘッダーがある行番号（1始まり）"
        default: 1
```

## 3. 汎用処理ブロックの活用と必要な拡張

### 3.1 excel.read_data
```yaml
id: excel.read_data
version: 1.0.0
description: Excelから構造化データを読み取る
inputs:
  workbook:
    type: string
    format: binary
  read_config:
    type: object
    properties:
      sheets:
        type: array
        items:
          type: object
          properties:
            name: { type: string }
            range: { type: string }
            header_row: { type: integer }
            data_types: { type: object }  # カラム名: 型のマッピング
      parse_dates:
        type: boolean
        default: true
      skip_empty_rows:
        type: boolean
        default: true
outputs:
  data:
    type: object
    description: シート名をキーとした構造化データ
  metadata:
    type: object
    properties:
      total_rows: { type: integer }
      total_sheets: { type: integer }
      sheets_info: { type: array }
```

### 3.2 excel.update_workbook
```yaml
id: excel.update_workbook
version: 1.0.0
description: 既存Excelワークブックを更新（シート追加、セル更新、テーブル追記）
inputs:
  workbook:
    type: string
    format: binary
  operations:
    type: array
    items:
      type: object
      properties:
        type:
          type: string
          enum: ["add_sheet", "copy_sheet", "update_cells", "append_table", "insert_rows", "update_formula"]
        sheet_name: { type: string }
        target: { type: string }  # セル範囲やテーブル名
        data: { type: object }
        options: { type: object }
outputs:
  updated_workbook:
    type: string
    format: binary
  operation_results:
    type: array
    items:
      type: object
      properties:
        operation_index: { type: integer }
        status: { type: string }
        affected_range: { type: string }
```

### 3.3 ai.process_llm での取引照合
請求書と入金明細の照合などは、`ai.process_llm` で実現：

```yaml
- id: match_transactions
  block: ai.process_llm
  in:
    evidence_data:
      invoices: ${read_invoices.data}
      payments: ${read_payments.data}
    instruction: |
      請求書データと入金明細データを照合してください。
      照合ルール：
      - 金額が完全一致するもの
      - 日付が3日以内の差異のもの
      - 参照番号が一致または部分一致するもの
    output_schema:
      matched_pairs:
        type: array
        items:
          type: object
          properties:
            invoice_id: { type: string }
            payment_id: { type: string }
            amount: { type: number }
            match_confidence: { type: number }
      unmatched_invoices:
        type: array
        items:
          type: object
      unmatched_payments:
        type: array
        items:
          type: object
      summary:
        type: object
        properties:
          total_matched: { type: integer }
          match_rate: { type: number }
```

### 3.4 汎用フィルタリング（transforms.filter_items の新設提案）
期間フィルタリングなどの汎用的なフィルタ処理：

```yaml
id: transforms.filter_items
version: 1.0.0
description: 条件に基づいてアイテムをフィルタリング
inputs:
  items:
    type: array
    items: { type: object }
  conditions:
    type: array
    description: フィルタ条件の配列（AND条件）
    items:
      type: object
      properties:
        field: { type: string }
        operator: 
          type: string
          enum: ["eq", "ne", "gt", "gte", "lt", "lte", "contains", "in", "between"]
        value: { }  # 任意の型
        value2: { }  # betweenの場合の第2値
outputs:
  filtered:
    type: array
  excluded:
    type: array
  summary:
    type: object
```

使用例：
```yaml
- id: filter_by_period
  block: transforms.filter_items
  in:
    items: ${employee_data}
    conditions:
      - field: "退職日"
        operator: "between"
        value: ${period.start_date}
        value2: ${period.end_date}
```

### 3.5 ai.process_llm での会計計算
退職金計算、減価償却計算などは `ai.process_llm` で実現：

```yaml
- id: calculate_retirement_benefits
  block: ai.process_llm
  in:
    evidence_data:
      employees: ${filtered_employees}
      payment_history: ${payment_data}
      calculation_rules: ${config.retirement_benefit_rules}
    instruction: |
      退職者の退職金を計算してください。
      計算ルール：
      - 基本退職金 = 最終基本給 × 勤続年数 × 支給率
      - 勤続年数に応じた支給率を適用
      - 早期退職の場合は加算あり
    output_schema:
      results:
        type: array
        items:
          type: object
          properties:
            employee_id: { type: string }
            employee_name: { type: string }
            retirement_date: { type: string }
            years_of_service: { type: number }
            final_salary: { type: number }
            basic_benefit: { type: number }
            adjustments: { type: number }
            total_benefit: { type: number }
            calculation_details: { type: object }
      summary:
        type: object
        properties:
          total_employees: { type: integer }
          total_amount: { type: number }
```

### 3.6 ai.process_llm でのデータ検証
会計データの整合性チェックも `ai.process_llm` で実現：

```yaml
- id: validate_accounting_data
  block: ai.process_llm
  in:
    evidence_data: ${data_to_validate}
    instruction: |
      以下の観点で会計データを検証してください：
      1. 借方・貸方の一致確認
      2. 重複取引のチェック
      3. 金額の妥当性確認（異常値検出）
      4. 必須項目の欠損チェック
      5. 日付の整合性確認
    output_schema:
      validation_results:
        type: array
        items:
          type: object
          properties:
            check_type: { type: string }
            status: { type: string, enum: ["passed", "failed", "warning"] }
            details: { type: string }
            affected_records: { type: array }
      is_valid: { type: boolean }
      summary:
        type: object
        properties:
          total_checks: { type: integer }
          passed: { type: integer }
          failed: { type: integer }
          warnings: { type: integer }
```

### 3.7 transforms.aggregate_by_key
```yaml
id: transforms.aggregate_by_key
version: 1.0.0
description: キーごとにデータを集約
inputs:
  data:
    type: array
    items: { type: object }
  group_by:
    type: array
    items: { type: string }
    description: グループ化するキー
  aggregations:
    type: object
    description: 集約定義（カラム名: 集約方法）
    additionalProperties:
      type: string
      enum: ["sum", "avg", "count", "min", "max", "concat", "first", "last"]
outputs:
  aggregated_data:
    type: array
  summary:
    type: object
```

## 4. 汎用ブロックで経理業務を実現するための仕組み

### 4.1 設定管理（Configuration）による業務固有情報の外部化
業務固有の情報はPlanのvarsやconfigで管理し、ブロック自体は汎用性を保つ：

```yaml
# Plan内のvars定義例
vars:
  # 会計期間設定
  fiscal_year_start: 4  # 4月開始
  
  # 計算ルール
  retirement_benefit_rules:
    rate_table:
      - { min_years: 0, max_years: 5, rate: 0.5 }
      - { min_years: 5, max_years: 10, rate: 1.0 }
      - { min_years: 10, max_years: 999, rate: 1.5 }
    early_retirement_bonus: 0.2
  
  # マスタデータ参照
  master_files:
    accounts: "masters/勘定科目マスタ.xlsx"
    departments: "masters/部門マスタ.xlsx"
    employees: "masters/従業員マスタ.xlsx"
  
  # 検証ルール
  validation_rules:
    amount_limit: 10000000  # 1千万円以上は要確認
    date_tolerance: 3       # 日付の許容差異日数
```

### 4.2 ai.process_llm の活用パターン
経理業務の多くは `ai.process_llm` の instruction と output_schema の組み合わせで実現：

#### パターン1: データ照合・マッチング
```yaml
instruction: "AデータとBデータを照合し、一致/不一致を特定"
output_schema: { matched: [], unmatched_a: [], unmatched_b: [] }
```

#### パターン2: 計算・集計
```yaml
instruction: "指定のルールに従って金額を計算"
output_schema: { results: [{id, amount, details}], summary: {} }
```

#### パターン3: 検証・チェック
```yaml
instruction: "データの整合性を検証"
output_schema: { validation_results: [], is_valid: boolean }
```

#### パターン4: 分類・仕訳
```yaml
instruction: "取引を勘定科目に分類"
output_schema: { classified_items: [{transaction, account_code}] }
```

### 4.3 HITLのためのui.interactive_input活用
異常値や不明点が発生した場合の人間への確認：

```yaml
- id: confirm_anomalies
  block: ui.interactive_input
  when:
    expr: "${validation_result.is_valid} == false"
  in:
    mode: inquire
    message: "以下の異常が検出されました。対処方法を選択してください。"
    context:
      anomalies: ${validation_result.validation_results}
    requirements:
      - id: action
        type: select
        label: "対処方法"
        options: ["修正して続行", "スキップ", "処理を中止"]
      - id: correction
        type: text
        label: "修正内容"
        description: "修正して続行を選択した場合、修正内容を入力"
        required: false
```

### 4.4 処理履歴の記録
Runner の構造化ログ（JSONL）が自動的に監査証跡として機能：
- 実行者、実行時刻、入力パラメータ、適用ルール、出力結果がすべて記録される
- `runs/{plan_id}/{timestamp}.jsonl` に永続化

## 5. 必要な汎用ブロックの整理

### 5.1 既存ブロックの活用
- **ui.interactive_input**: すべてのUI入力（ファイル選択、期間選択、確認画面等）
- **ai.process_llm**: 照合、計算、検証、分類などの業務ロジック
- **file.parse_zip_2tier**: ZIP形式の証跡ファイル解析
- **transforms.group_evidence**: データのグループ化

### 5.2 新規作成が必要な汎用ブロック
1. **excel.read_data**: Excel読み込み（構造化データ抽出）
2. **excel.update_workbook**: Excel更新（シート追加、セル更新、テーブル追記）
3. **transforms.filter_items**: 条件によるフィルタリング
4. **transforms.aggregate_by_key**: キーによる集約（既存？要確認）

### 5.3 実装優先順位
1. **Phase 1**: Excel操作の基本機能
   - excel.read_data（新規）
   - excel.update_workbook（新規）

2. **Phase 2**: データ変換の汎用機能
   - transforms.filter_items（新規）
   - transforms.aggregate_by_key の拡張

3. **Phase 3**: 業務フローの構築
   - 各種経理業務のPlanサンプル作成
   - ai.process_llm の活用パターン集

## 6. 汎用ブロックを活用したPlan例

### 6.1 退職給付金計算業務
```yaml
apiVersion: v1
id: retirement_benefit_calculation
version: 1.0.0
vars:
  fiscal_year_start: 4
  retirement_benefit_rules:
    rate_table:
      - { min_years: 0, max_years: 5, rate: 0.5 }
      - { min_years: 5, max_years: 10, rate: 1.0 }
      - { min_years: 10, max_years: 999, rate: 1.5 }
  
graph:
  # 期間と入力ファイルの収集
  - id: collect_inputs
    block: ui.interactive_input
    in:
      mode: collect
      message: "退職給付金計算の対象期間とファイルを指定してください"
      requirements:
        - id: year
          type: number
          label: "対象年度"
          validation: { min: 2020, max: 2030 }
        - id: quarter
          type: select
          label: "対象四半期"
          options: ["第1四半期", "第2四半期", "第3四半期", "第4四半期"]
        - id: employee_file
          type: file
          label: "社員マスタ（Excel）"
          accept: ".xlsx"
        - id: payment_file
          type: file
          label: "給与・支払データ（Excel）"
          accept: ".xlsx"
        - id: output_file
          type: file
          label: "出力先ワークブック"
          accept: ".xlsx"
  
  # 社員データの読み込み
  - id: read_employees
    block: excel.read_data
    in:
      workbook: ${collect_inputs.collected.employee_file}
      read_config:
        sheets:
          - name: "社員マスタ"
            header_row: 1
  
  # 支払データの読み込み
  - id: read_payments
    block: excel.read_data
    in:
      workbook: ${collect_inputs.collected.payment_file}
      read_config:
        sheets:
          - name: "給与データ"
            header_row: 1
  
  # 期間計算（LLMで四半期から日付範囲を導出）
  - id: calculate_period
    block: ai.process_llm
    in:
      evidence_data:
        year: ${collect_inputs.collected.year}
        quarter: ${collect_inputs.collected.quarter}
        fiscal_year_start: ${vars.fiscal_year_start}
      instruction: |
        会計年度開始月が${fiscal_year_start}月の場合、
        ${year}年度の${quarter}の開始日と終了日を計算してください。
      output_schema:
        period:
          type: object
          properties:
            start_date: { type: string, format: date }
            end_date: { type: string, format: date }
            label: { type: string }
  
  # 退職者のフィルタリング
  - id: filter_retirees
    block: transforms.filter_items
    in:
      items: ${read_employees.data.社員マスタ}
      conditions:
        - field: "退職日"
          operator: "between"
          value: ${calculate_period.period.start_date}
          value2: ${calculate_period.period.end_date}
  
  # 退職金計算
  - id: calculate_benefits
    block: ai.process_llm
    in:
      evidence_data:
        retirees: ${filter_retirees.filtered}
        payment_data: ${read_payments.data.給与データ}
        calculation_rules: ${vars.retirement_benefit_rules}
      instruction: |
        各退職者の退職金を計算してください。
        計算手順：
        1. 退職者の最終基本給を支払データから特定
        2. 勤続年数を入社日と退職日から計算
        3. 勤続年数に応じた支給率を適用
        4. 退職金 = 最終基本給 × 勤続年数 × 支給率
      output_schema:
        results:
          type: array
          items:
            type: object
            properties:
              employee_id: { type: string }
              employee_name: { type: string }
              retirement_date: { type: string }
              years_of_service: { type: number }
              final_salary: { type: number }
              rate: { type: number }
              benefit_amount: { type: number }
        summary:
          type: object
          properties:
            total_retirees: { type: integer }
            total_amount: { type: number }
  
  # 結果確認
  - id: confirm_results
    block: ui.interactive_input
    in:
      mode: confirm
      message: "計算結果を確認してください"
      context:
        results: ${calculate_benefits.results}
        summary: ${calculate_benefits.summary}
      requirements:
        - id: approved
          type: boolean
          label: "この結果でワークブックを更新しますか？"
  
  # Excelへの書き込み
  - id: update_workbook
    block: excel.update_workbook
    when:
      expr: "${confirm_results.collected.approved} == true"
    in:
      workbook: ${collect_inputs.collected.output_file}
      operations:
        - type: copy_sheet
          sheet_name: "テンプレート"
          target: ${calculate_period.period.label}
        - type: update_cells
          sheet_name: ${calculate_period.period.label}
          target: "B2"
          data: ${calculate_period.period.label}
        - type: append_table
          sheet_name: ${calculate_period.period.label}
          target: "A10"
          data: ${calculate_benefits.results}
```

### 6.2 前受収益計算業務（請求書と入金照合）- 複数セット対応版
```yaml
apiVersion: v1
id: unearned_revenue_matching
version: 1.0.0

graph:
  # ファイル収集
  - id: collect_files
    block: ui.interactive_input
    in:
      mode: collect
      message: "前受収益計算に必要なファイルをアップロードしてください"
      requirements:
        - id: evidence_zip
          type: file
          label: "証跡ファイル（請求書・入金明細のZIP）"
          description: "フォルダ構造: /顧客名/請求書と入金明細"
          accept: ".zip"
        - id: workbook
          type: file
          label: "更新対象のExcelワークブック"
          accept: ".xlsx"
  
  # ZIP解析（2階層: 顧客名/ファイル）
  - id: parse_evidence
    block: file.parse_zip_2tier
    in:
      zip_bytes: ${collect_files.collected.evidence_zip}
  
  # 顧客ごとのセットを作成
  - id: group_by_customer
    block: transforms.group_evidence
    in:
      evidence_data: ${parse_evidence.evidence_data}
      group_by: "folder"  # フォルダ名（顧客名）でグループ化
  
  # 各顧客セットに対して照合処理を実行
  - id: process_each_customer
    type: loop
    foreach:
      input: "${group_by_customer.grouped}"
      itemVar: customer_data
      indexVar: idx
      max_concurrency: 4
    body:
      plan:
        graph:
          # 顧客データから請求書と入金明細を分類
          - id: classify_documents
            block: ai.process_llm
            in:
              evidence_data: ${customer_data}
              instruction: |
                このフォルダ内のファイルを以下に分類してください：
                1. 請求書（invoice）
                2. 入金明細（payment）
                3. その他（other）
                
                ファイル名やテキスト内容から判断してください。
              output_schema:
                customer_name: { type: string }
                classified:
                  type: object
                  properties:
                    invoices: { type: array }
                    payments: { type: array }
                    others: { type: array }
          
          # 照合処理
          - id: match_transactions
            block: ai.process_llm
            in:
              evidence_data:
                customer: ${classify_documents.customer_name}
                invoices: ${classify_documents.classified.invoices}
                payments: ${classify_documents.classified.payments}
              instruction: |
                ${customer}の請求書と入金明細を照合してください。
                照合条件：
                - 金額が完全一致
                - 日付が前後30日以内
                - 摘要や参照番号の一致
                
                前受収益となるのは、入金が請求書日付より前の場合です。
              output_schema:
                customer_name: { type: string }
                matched:
                  type: array
                  items:
                    type: object
                    properties:
                      invoice_no: { type: string }
                      invoice_date: { type: string }
                      payment_no: { type: string }
                      payment_date: { type: string }
                      amount: { type: number }
                      is_unearned: { type: boolean }
                      unearned_amount: { type: number }
                      days_difference: { type: integer }
                unmatched_invoices: { type: array }
                unmatched_payments: { type: array }
        
        # foreachループの出力
        exports:
          - from: match_transactions
            as: customer_result
    
    out:
      collect: customer_result  # 全顧客の結果をリストで収集
  
  # 全体サマリーの作成
  - id: create_summary
    block: ai.process_llm
    in:
      evidence_data: ${process_each_customer.customer_result}
      instruction: |
        全顧客の照合結果をサマリーしてください。
        含める情報：
        - 処理した顧客数
        - 総照合件数
        - 前受収益の総額
        - 未照合の請求書・入金明細の件数
      output_schema:
        summary:
          type: object
          properties:
            total_customers: { type: integer }
            total_matched: { type: integer }
            total_unearned_amount: { type: number }
            total_unmatched_invoices: { type: integer }
            total_unmatched_payments: { type: integer }
        details_by_customer:
          type: array
  
  # 結果確認
  - id: confirm_results
    block: ui.interactive_input
    in:
      mode: confirm
      message: "照合結果を確認してください"
      context:
        summary: ${create_summary.summary}
        details: ${process_each_customer.customer_result}
      requirements:
        - id: approved
          type: boolean
          label: "この結果でExcelを更新しますか？"
  
  # Excel更新（各顧客の結果を順次書き込み）
  - id: update_excel_foreach
    type: loop
    when:
      expr: "${confirm_results.collected.approved} == true"
    foreach:
      input: "${process_each_customer.customer_result}"
      itemVar: result
      indexVar: idx
    body:
      plan:
        graph:
          - id: write_customer_results
            block: excel.update_workbook
            in:
              workbook: ${collect_files.collected.workbook}
              operations:
                # 顧客ごとのシートに書き込み
                - type: update_cells
                  sheet_name: "前受収益"
                  target: "A${(idx * 20) + 5}"  # 20行ずつずらして記載
                  data: |
                    顧客名: ${result.customer_name}
                - type: append_table
                  sheet_name: "前受収益"
                  target: "A${(idx * 20) + 7}"
                  data: ${result.matched}
        exports:
          - from: write_customer_results.operation_results
            as: write_result
    out:
      collect: write_result
  
  # 最終サマリーをExcelに記載
  - id: write_summary
    block: excel.update_workbook
    when:
      expr: "${confirm_results.collected.approved} == true"
    in:
      workbook: ${collect_files.collected.workbook}
      operations:
        - type: update_cells
          sheet_name: "サマリー"
          target: "A1"
          data: "前受収益計算結果サマリー"
        - type: update_cells
          sheet_name: "サマリー"
          target: "A3"
          data: ${create_summary.summary}
```

## 7. まとめ

### 7.1 汎用ブロックアプローチの利点
1. **拡張性**: 新しい経理業務も既存ブロックの組み合わせで実現可能
2. **保守性**: ブロック数を最小限に抑えることで、メンテナンスが容易
3. **再利用性**: 同じブロックを異なる業務で活用できる
4. **柔軟性**: パラメータとLLMのinstructionで多様な処理を実現

### 7.2 経理業務の実現パターン
- **データ入力**: `ui.interactive_input` で統一
- **Excel操作**: `excel.read_data` / `excel.update_workbook`
- **業務ロジック**: `ai.process_llm` のinstructionで記述
- **データ変換**: `transforms.*` シリーズで汎用的に処理
- **条件分岐**: `when` 条件とHITLで柔軟に対応

### 7.3 今後の拡張
- 経理業務特有の検証パターンをai.process_llmのテンプレートとして整備
- よく使うPlanをテンプレート化して再利用を促進
- 業務知識をconfigやvarsに外部化して、Planの汎用性を維持
