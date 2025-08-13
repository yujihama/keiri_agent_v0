# Keiri Agent ビジネスユースケース集

本書は、UI/Processブロックが段階的に拡張される前提で、ドメインに依存しすぎない「汎用・抽象」ユースケースを整理する。各ユースケースは、Plan DSL と BlockSpec による宣言的再現性、Evidence-first の実行証跡、型安全LLMによる合成を活用する。

## カテゴリ別ユースケース

### 1) 財務会計/経理（Record-to-Report）
- 3-way/2-way 突合（PO/GRN/Invoice）例外トリアージ
- 銀行照合（Bank Reconciliation）
- 仕訳提案と承認（規程整合チェック）
- 固定資産ロールフォワード/棚卸差異分析

### 2) 調達-to-支払（P2P）
- ベンダーオンボーディング（KYC/制裁/反社チェック）
- POポリシー遵守チェック（閾値、例外承認、SoD）
- 重複請求検知（ファジーマッチ＋LLM理由付け）
- 支払前コントロール（承認・例外ログ・証跡封緘）

### 3) 受注-to-入金（O2C）
- 入金消込（差異理由の説明収集）
- クレジットリミット監視（違反検知と例外承認）
- 売上認識ルール準拠チェック（契約との整合）

### 4) 給与/人事（HCM）
- 給与異常検知（しきい値/統計/ルール）
- 入社/退社書類の完備性チェック
- 権限付与/剥奪のSoD/期限管理

### 5) ITGC/セキュリティ
- User Access Review（UAR）
- SoD違反検知と修復計画トラッキング
- 変更管理（CAB承認、PR/チケット/デプロイ証跡の突合）
- バックアップ/DRテストの証跡収集

### 6) 内部監査（Internal Audit）
- PBC依頼自動化（収集→不足催促→封緘）
- サンプリング抽出（属性/統計）とテスト結果収集・指摘管理
- ウォークスルー記録（チャット/フォーム→手順/図解生成）

### 7) コンプライアンス/規制
- AMLトランザクションのサンプリング・例外レビュー
- 制裁/PEP/反社スクリーニングの証跡化
- 電帳法/適格請求書等の整合性チェック

### 8) データガバナンス/品質
- スキーマドリフト検知と影響評価（再実行シミュレーション）
- データ品質（DQ）ルールの定期検査、逸脱アラート、証跡
- 系譜（Lineage）/来歴（Provenance）の要約と可視化

### 9) ESG/サステナビリティ
- ESG書類収集（不足催促、改ざん検知）
- 排出量データ統合と検証、集計の証跡化

### 10) 予算/FP&A
- 予実差異の説明収集（自然言語→構造化メタ→証跡）
- whileループで承認が出るまで差戻し

### 11) 法務/契約
- 契約条文抽出とリスクタグ付け、レビュー・承認・証跡
- 契約台帳の整合性と更新差分のアテステーション

### 12) 税務
- 間接税（VAT/消費税）整合性チェック（帳票/GL/補助簿の突合）
- 移転価格文書化の資料収集・差分要約・封緘

---

## 代表シナリオ詳細

### A. 3-way 突合 例外トリアージ（P2P）
- 概要: PO/検収/請求書の差異を抽出し、例外を分類・説明・承認のうえ、Excelレポートへ出力。
- ブロック（例）: `ui.interactive_input`, `file.read_csv`, `excel.read_data`, `transforms.*`, `ai.process_llm`, 将来: `control.*`, `excel.write`
- Plan骨子（例）:
```yaml
apiVersion: v1
id: p2p_3way_exception_triage
version: "1.0"
ui:
  layout: [collect_inputs, preview_exceptions, approve]
vars:
  threshold_amount: 1000
policy:
  on_error: halt
  retries: 0
  timeout_ms: 300000
  concurrency:
    default_max_workers: 4
graph:
  - id: collect_inputs
    block: ui.interactive_input
    in:
      mode: collect
      requirements:
        - {id: po, type: file, label: "POファイル"}
        - {id: grn, type: file, label: "検収ファイル"}
        - {id: inv, type: file, label: "請求書ファイル"}
        - {id: th, type: number, label: "金額閾値", default: ${vars.threshold_amount}}
    out:
      collected: collected
  - id: build_exceptions
    block: ai.process_llm
    when:
      expr: "${collect_inputs.collected.submitted} == true"
    in:
      prompt: "3-way差異を抽出し、閾値超過のみを分類・要約して返す"
      evidence_data: ${collect_inputs.collected}
      output_schema:
        exceptions: array
    out:
      data: exceptions
  - id: approve
    block: ui.interactive_input
    in:
      mode: confirm
      message: "例外一覧を承認してください"
    out:
      approved: approved
  - id: write
    block: excel.write
    when:
      expr: "${approve.approved} == true"
    in:
      workbook_path: "runs/p2p/output.xlsx"
      sheet_name: "exceptions"
      values: ${build_exceptions.exceptions}
```

### B. User Access Review（UAR）
- 概要: 権限台帳を取り込み、オーナー別にサンプリング/全件レビュー、承認証跡と差戻しループを管理。
- ブロック（例）: `ui.interactive_input`, `file.read_csv`, 将来: `control.sod_check`, `control.sampling`, `control.approval`, 出力: `excel.update_workbook`
- Plan骨子（例）:
```yaml
apiVersion: v1
id: itgc_uar
version: "1.0"
ui:
  layout: [collect, review_loop]
policy:
  on_error: halt
  timeout_ms: 600000
  concurrency:
    default_max_workers: 2
graph:
  - id: collect
    block: ui.interactive_input
    in:
      mode: collect
      requirements:
        - {id: users, type: file, label: "ユーザ権限台帳"}
        - {id: owners, type: file, label: "オーナー割当表"}
  - id: review_loop
    type: loop
    while:
      condition:
        expr: "${review_status.approved} != true"
      max_iterations: 5
    body:
      plan:
        graph:
          - id: assign_and_sample
            block: ai.process_llm
            in:
              prompt: "オーナー別にレビュー対象を割り当て、必要に応じてサンプリングする"
              evidence_data: ${collect.collected}
              output_schema: { assignments: array }
          - id: review_ui
            block: ui.interactive_input
            in:
              mode: mixed
              requirements:
                - {id: review_result, type: select, options: [approve, reject, request_change]}
          - id: review_status
            block: transforms.pick
            in:
              obj: ${review_ui.collected}
              key: review_result
            out:
              value: approved
```

---

## 必要となるブロック拡張（例）
- Control: `control.approval`, `control.sod_check`, `control.sampling`, `control.reconciliation`
- 外部I/F: `external.api.http`, `external.mail.send`, `db.query`
- 文書処理: `file.read_pdf`, `file.ocr_parse`, `text.extract`
- 運用: `scheduler.trigger`, `notifier.slack`/`notifier.teams`
- LLM: 参照制約付き生成、スキーマレジストリ連携、プロンプトのEvidence化

## 運用モデル（概略）
- Business-as-Code: Plan/BlockSpec/Policyをリポジトリ管理し、PRレビュー/署名。
- ロール: Owner（業務）、Approver（統制/監査）、Operator（実行）、Reviewer（内部監査）。
- KPI: 例外率、承認TAT、再現成功率、証跡完全性、手戻り率。

---

## 参考リンク
- 詳細版（各ユースケースの具体化・Plan骨子・抽象ブロック案）: `docs/use_cases_detailed.md`


