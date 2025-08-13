# Keiri Agent ビジネスユースケース詳細

本書は、各ユースケースを省略せず具体化し、Plan骨子（ノード概要）を付記する。YAML完全生成は不要のため、ノードの役割・入出力・制御構造にフォーカスして記述する。最後に、すべてのユースケースを実現するための抽象的な新規ブロック案を整理する。

---

## 1) 財務会計/経理（Record-to-Report）

### 1-1. 3-way/2-way 突合 例外トリアージ
- 目的: PO/検収/請求書の差異抽出と分類、承認のうえレポート出力
- 入力: PO/GRN/Invoice（CSV/ZIP/XLSX）、マスタ、閾値
- 処理: 正規化→キー付与→照合（ルール/ファジー）→例外分類（LLM）→承認
- 出力: 例外一覧、承認記録、Excel/CSV、実行証跡
- Plan骨子（ノード概要）:
  - `collect_inputs`: `ui.interactive_input(mode=collect)` → `collected`
  - `parse_po/grn/inv`: `file.read_csv`/`excel.read_data` → `tables`
  - `join_and_match`: `control.reconciliation` or `matching.record_linkage` → `matches`, `exceptions`
  - `classify_exceptions`: `ai.process_llm` → `exceptions_labeled`
  - `approve_exceptions`: `ui.interactive_input(mode=confirm)` → `approved`
  - `write_outputs`: `excel.write`/`excel.update_workbook` (when `approved`) → `artifact`

### 1-2. 銀行照合（Bank Reconciliation）
- 目的: 銀行明細とGL/補助元帳の一致確認、未達/未収/未払の抽出
- 入力: Bank statement（CSV/OFX）、GL/SL、期間、閾値
- 処理: 正規化→キー生成→一致/ズレ検出→例外分類→承認
- 出力: 照合レポート、調整仕訳案、証跡
- Plan骨子:
  - `collect`: `ui.interactive_input`
  - `read_bank/gl`: `file.read_csv`/`excel.read_data`
  - `normalize`: `transforms.map_fields`/`transforms.schema_validate`
  - `match`: `matching.record_linkage`（exact/fuzzy）→ `matches`, `outstanding`
  - `propose_adjustments`: `ai.process_llm`（調整案・根拠）
  - `approve`: `ui.interactive_input(mode=confirm)`
  - `write`: `excel.update_workbook` or `external.api.http`

### 1-3. 仕訳提案と承認（規程整合）
- 目的: 明細から仕訳案を規程に照らして生成・承認
- 入力: 明細、勘定科目規程、閾値、補足根拠
- 処理: ルール/LLMで勘定・部門・税区分割付→規程適合チェック→承認
- 出力: 仕訳案（Excel/API）、承認証跡
- Plan骨子:
  - `collect`: `ui.interactive_input`
  - `read_items`: `file.read_csv`/`excel.read_data`
  - `map_accounts`: `ai.process_llm`（構造化仕訳）
  - `policy_check`: `control.policy_enforce`（規程YAML）
  - `approve`: `ui.interactive_input(mode=confirm)`
  - `export`: `excel.write` or `external.api.http`

### 1-4. 固定資産ロールフォワード/棚卸差異分析
- 目的: 期首→期末の増減分析、棚卸差異抽出
- 入力: 固定資産台帳、減価償却表、棚卸実査結果
- 処理: ロールフォワード計算→差異抽出→原因分類→承認
- 出力: ロールフォワード表、差異一覧、証跡
- Plan骨子:
  - `collect`: `ui.interactive_input`
  - `read_fa/surv`: `excel.read_data`
  - `compute_rollforward`: `transforms.compute_metrics`
  - `diff`: `transforms.diff` → `variances`
  - `explain`: `ai.process_llm`（差異理由）
  - `approve_write`: `ui.interactive_input` → `excel.update_workbook`

---

## 2) 調達-to-支払（P2P）

### 2-1. ベンダーオンボーディング（KYC/制裁/反社）
- 目的: 提出書類正規化、KYC/制裁/反社スクリーニング、リスクスコア、承認
- 入力: 申請フォーム、会社情報、提出証憑
- 処理: OCR/抽出→スクリーニングAPI→スコア→例外承認
- 出力: オンボード可否、証跡マニフェスト
- Plan骨子:
  - `collect_docs`: `ui.interactive_input(files)`
  - `extract`: `file.ocr_parse`/`text.extract`
  - `screen`: `risk.screening` → `hits`
  - `score`: `ai.process_llm` or `transforms.compute_metrics` → `risk_score`
  - `approve`: `ui.interactive_input(mode=confirm)`
  - `archive`: `evidence.vault.store`

### 2-2. POポリシー遵守チェック
- 目的: 事後/事前のPO閾値遵守、承認経路、例外ログ
- 入力: 発注データ、承認経路、閾値ポリシー
- 処理: ポリシー適用→違反抽出→例外申請・承認
- 出力: 違反一覧、承認証跡
- Plan骨子:
  - `collect`: `ui.interactive_input`
  - `read_po/approvers`: `file.read_csv`
  - `enforce_policy`: `control.policy_enforce` → `violations`
  - `exception_approval`: `control.approval`/`ui.interactive_input`
  - `write`: `excel.write`

### 2-3. 重複請求検知
- 目的: 近似重複（額/日付/ベンダ/テキスト類似）の検知とレビュー
- 入力: 請求データ（テキスト/画像含む）
- 処理: 前処理→特徴量→近傍探索→分類→レビュー→確定
- 出力: 重複疑いリスト、確定結果、証跡
- Plan骨子:
  - `collect_read`: `ui.interactive_input`, `file.read_csv`
  - `featurize`: `transforms.compute_features`
  - `candidate_match`: `matching.similarity_cluster` → `clusters`
  - `classify`: `ai.process_llm`（根拠要約）
  - `review`: `ui.interactive_input(mode=mixed)`
  - `export`: `excel.update_workbook`

### 2-4. 支払前コントロール
- 目的: 支払直前の最終承認・口座情報整合・SoD確認・アテステーション
- 入力: 支払バッチ、ベンダ銀行情報、承認経路
- 処理: 口座一致/変更検知→SoD→承認→署名
- 出力: 承認済み支払リスト、署名マニフェスト
- Plan骨子:
  - `collect`: `ui.interactive_input`
  - `validate_bank`: `control.reconciliation`
  - `sod_check`: `control.sod_check`
  - `approve`: `control.approval`
  - `attest`: `security.attestation.sign_manifest`

---

## 3) 受注-to-入金（O2C）

### 3-1. 入金消込
- 目的: 入金明細と売掛オープン項目の消込、差異理由収集
- 入力: 銀行入金、ARオープン、リマインドテンプレ
- 処理: マッチング→差異分類→不足情報問い合わせ→承認
- 出力: 消込結果、残高、問い合わせログ
- Plan骨子:
  - `collect`: `ui.interactive_input`
  - `read_bank/ar`: `file.read_csv`
  - `match`: `matching.record_linkage` → `matched`, `unmatched`
  - `generate_queries`: `ai.process_llm`（問い合わせ文）
  - `approve_and_send`: `ui.interactive_input` + `external.mail.send`
  - `write_back`: `excel.update_workbook` or `external.api.http`

### 3-2. クレジットリミット監視
- 目的: 与信限度超過/逼迫の検知と例外承認
- 入力: 受注/売上/与信枠、取引先属性
- 処理: 残枠計算→違反抽出→例外承認
- 出力: 警告リスト、承認証跡
- Plan骨子:
  - `collect_read`: `ui.interactive_input`, `file.read_csv`
  - `calc_exposure`: `transforms.compute_metrics`
  - `detect_breach`: `transforms.filter`
  - `exception_approval`: `control.approval`
  - `notify`: `notifier.slack`/`notifier.teams`

### 3-3. 売上認識ルール準拠チェック
- 目的: 契約・POB・請求と認識タイミングの整合性評価
- 入力: 契約/POB/請求データ、ルール
- 処理: マッピング→ルール適用→逸脱抽出→承認
- 出力: 逸脱一覧、改善アクション
- Plan骨子:
  - `collect`: `ui.interactive_input`
  - `read_contracts`: `file.read_pdf`/`text.extract`
  - `extract_pobs`: `nlp.extract_fields`
  - `enforce_rules`: `control.policy_enforce`
  - `approve_write`: `ui.interactive_input` → `excel.write`

---

## 4) 給与/人事（HCM）

### 4-1. 給与異常検知
- 目的: 支給額/手当/控除の異常値・急変を検知し、理由を収集
- 入力: 給与明細、前年同月、組織情報
- 処理: 統計/ルール→異常候補→自然言語理由収集→承認
- 出力: 異常リスト、承認・差戻し記録
- Plan骨子:
  - `collect_read`: `ui.interactive_input`, `file.read_csv`
  - `detect_outliers`: `transforms.compute_metrics` + `transforms.filter`
  - `explain`: `ai.process_llm`（理由要約）
  - `approve`: `ui.interactive_input`
  - `write`: `excel.update_workbook`

### 4-2. 入退社書類の完備性チェック
- 目的: 必須書類の欠落検知、催促、完了承認
- 入力: 従業員台帳、提出書類
- 処理: 必須要件照合→不足抽出→催促→完了承認
- 出力: 完備率レポート、催促ログ
- Plan骨子:
  - `collect`: `ui.interactive_input`
  - `read_docs`: `file.parse_zip_2tier`/`file.read_pdf`
  - `validate_requirements`: `control.policy_enforce`
  - `notify_missing`: `external.mail.send`/`notifier.slack`
  - `approve`: `ui.interactive_input`

### 4-3. 権限付与/剥奪のSoD/期限管理
- 目的: JML（Joiner/Mover/Leaver）に伴う権限変更のSoD・期限管理
- 入力: HRイベント、アクセス台帳
- 処理: SoDチェック→期限設定→承認→実施
- 出力: 承認/実施証跡
- Plan骨子:
  - `collect`: `ui.interactive_input`
  - `read_access`: `file.read_csv`
  - `sod`: `control.sod_check`
  - `approval`: `control.approval`
  - `ticket`: `external.api.http`（IAM/ITSM）

---

## 5) ITGC/セキュリティ

### 5-1. User Access Review（UAR）
- 目的: 権限棚卸、オーナーレビュー、承認証跡
- 入力: アクセス台帳、所有者割当
- 処理: 割当→レビュー→差戻しループ→確定
- 出力: 承認済み台帳、差戻し理由
- Plan骨子:
  - `collect`: `ui.interactive_input`
  - `group_by_owner`: `transforms.group_evidence`
  - `review_loop`: loop.while（max_iterations）+ `ui.interactive_input`
  - `write_back`: `excel.update_workbook`

### 5-2. SoD違反検知と修復計画
- 目的: ロール/取引の組合せ違反の検出と是正タスク管理
- 入力: 権限・取引ログ、SoDマトリクス
- 処理: 検出→リスク評価→是正案→承認→実施
- 出力: 是正計画、進捗証跡
- Plan骨子:
  - `collect_read`: `ui.interactive_input`, `file.read_csv`
  - `detect`: `control.sod_check`
  - `propose`: `ai.process_llm`（是正案・優先度）
  - `approve_track`: `control.approval` + `external.api.http`（チケット）

### 5-3. 変更管理（CAB）
- 目的: PR/チケット/デプロイの整合、CAB承認
- 入力: リポジトリ、チケット、デプロイ履歴
- 処理: 関連付け→欠落検知→承認記録
- 出力: 一貫性レポート、承認証跡
- Plan骨子:
  - `fetch`: `external.api.http`（VCS/ITSM/CI）
  - `reconcile`: `control.reconciliation`
  - `approve`: `control.approval`
  - `report`: `excel.write`

### 5-4. バックアップ/DRテスト証跡
- 目的: 定期的なバックアップ/DR演習の証跡収集と評価
- 入力: バックアップログ、復旧テスト結果
- 処理: 要件照合→欠落・失敗抽出→承認
- 出力: 証跡セット、評価サマリ
- Plan骨子:
  - `schedule_collect`: `scheduler.trigger` + `external.api.http`
  - `validate`: `control.policy_enforce`
  - `approve_report`: `ui.interactive_input` + `excel.write`

---

## 6) 内部監査（Internal Audit）

### 6-1. PBC依頼自動化
- 目的: 依頼テンプレ展開→収集→不足催促→封緘
- 入力: PBCテンプレ、依頼先、期限
- 処理: 送付→受領→不足催促→完了承認→Vault保管
- 出力: 完了率、欠落、証跡
- Plan骨子:
  - `setup`: `ui.interactive_input`
  - `send_requests`: `external.mail.send`/`external.api.http`
  - `collect`: `ui.interactive_input(files)`
  - `chase_missing`: `notifier.slack`/`notifier.teams`
  - `approve_archive`: `ui.interactive_input` + `evidence.vault.store`

### 6-2. サンプリング抽出とテスト収集
- 目的: 属性/統計サンプリング→テスト実施・回収→指摘管理
- 入力: 集団データ、サンプリング設計
- 処理: 抽出→配賦→収集→評価→指摘
- 出力: サンプル台帳、テスト結果、指摘一覧
- Plan骨子:
  - `collect`: `ui.interactive_input`
  - `sample`: `control.sampling`
  - `assign`: `ai.process_llm`（配賦）
  - `gather_results`: `ui.interactive_input`
  - `issues`: `transforms.pick` + `excel.update_workbook`

### 6-3. ウォークスルー記録
- 目的: ヒアリング→手順/フロー/統制点の構造化→証跡化
- 入力: チャット/フォーム回答、添付
- 処理: 構造化抽出→ダイアグラム要約→承認
- 出力: 記録書、図、証跡
- Plan骨子:
  - `inquire`: `ui.interactive_input(mode=inquire)`
  - `extract`: `nlp.extract_fields`
  - `summarize_diagram`: `ai.process_llm`
  - `approve_store`: `ui.interactive_input` + `evidence.vault.store`

---

## 7) コンプライアンス/規制

### 7-1. AMLトランザクション サンプリング・例外レビュー
- 目的: リスクベースで抽出→レビュー→エスカレーション
- 入力: 取引ログ、スコアリングルール
- 処理: スコア→サンプル→レビュー→エスカレーション
- 出力: 対応記録、承認証跡
- Plan骨子:
  - `score`: `transforms.compute_metrics`
  - `sample`: `control.sampling`
  - `review`: `ui.interactive_input`
  - `escalate`: `notifier.slack`/`notifier.teams` or `external.api.http`

### 7-2. 制裁/PEP/反社スクリーニング証跡
- 目的: 定期/新規のスクリーニングと証跡
- 入力: 顧客/取引先リスト
- 処理: スクリーニングAPI→ヒットレビュー→承認
- 出力: ヒット対応記録
- Plan骨子:
  - `collect_read`: `ui.interactive_input`, `file.read_csv`
  - `screen`: `risk.screening`
  - `review_approve`: `ui.interactive_input`
  - `archive`: `evidence.vault.store`

### 7-3. 電帳法/適格請求書の整合性チェック
- 目的: 保管要件/メタの検証、改ざん検知、保存期間
- 入力: 請求書PDF/メタ、保管規程
- 処理: メタ検証→要件照合→欠落抽出
- 出力: 不備一覧、是正依頼
- Plan骨子:
  - `parse_docs`: `file.read_pdf`/`text.extract`
  - `validate_meta`: `data.schema.validate` + `control.policy_enforce`
  - `approve_notify`: `ui.interactive_input` + `external.mail.send`

---

## 8) データガバナンス/品質

### 8-1. スキーマドリフト検知と影響評価
- 目的: バージョン間スキーマ差分と影響の可視化
- 入力: 過去/現行スキーマ、サンプルデータ
- 処理: 差分→影響推定→再実行シミュレーション
- 出力: 影響レポート、対応案
- Plan骨子:
  - `collect`: `ui.interactive_input`
  - `diff_schema`: `data.schema.diff`
  - `impact`: `ai.process_llm`（影響推定）
  - `simulate`: `runner.subflow`（replay）

### 8-2. データ品質（DQ）ルールの定期検査
- 目的: ルール適用→逸脱抽出→割当/承認
- 入力: DQルール、対象データ
- 処理: 検証→逸脱抽出→承認
- 出力: 逸脱台帳、是正状況
- Plan骨子:
  - `read_data`: `file.read_csv`
  - `validate`: `data.quality.validate_rules`
  - `assign_approve`: `ai.process_llm` + `ui.interactive_input`
  - `report`: `excel.write`

### 8-3. Lineage/Provenance 可視化
- 目的: 来歴/系譜の要約、露出リスクの把握
- 入力: パイプライン定義、ログ
- 処理: 解析→要約→可視化→承認
- 出力: 可視化アセット、要約
- Plan骨子:
  - `ingest_defs`: `external.api.http`
  - `build_lineage`: `data.provenance.capture`
  - `summarize`: `ai.process_llm`
  - `approve_publish`: `ui.interactive_input`

---

## 9) ESG/サステナビリティ

### 9-1. ESG書類収集
- 目的: 取引先のESG書類を収集・検証・保管
- 入力: 取引先一覧、要求テンプレ
- 処理: 依頼→収集→不足催促→検証→承認
- 出力: 収集率、検証結果、Vault保管
- Plan骨子:
  - `request`: `external.mail.send`
  - `collect`: `ui.interactive_input(files)`
  - `validate`: `control.policy_enforce`
  - `approve_store`: `ui.interactive_input` + `evidence.vault.store`

### 9-2. 排出量データ統合・検証・集計
- 目的: 複数ソースの統合、検証、集計、証跡
- 入力: 排出量データ、活動量、係数
- 処理: 正規化→検証→集計→承認
- 出力: 集計表、証跡
- Plan骨子:
  - `read_sources`: `file.read_csv`
  - `normalize`: `transforms.map_fields`
  - `validate`: `data.quality.validate_rules`
  - `aggregate`: `transforms.group_by_agg`
  - `approve_write`: `ui.interactive_input` + `excel.write`

---

## 10) 予算/FP&A

### 10-1. 予実差異の説明収集
- 目的: 差異の要因・施策・リスクの構造化と証跡
- 入力: 予実データ、担当者割当
- 処理: 差異抽出→担当者配賦→説明収集→承認
- 出力: 説明台帳、承認証跡
- Plan骨子:
  - `collect`: `ui.interactive_input`
  - `detect_variance`: `transforms.compute_metrics` + `transforms.filter`
  - `assign`: `ai.process_llm`
  - `inquire`: `ui.interactive_input(mode=inquire)`
  - `approve_write`: `ui.interactive_input` + `excel.update_workbook`

### 10-2. 承認が出るまで差戻し（while）
- 目的: 繰り返しレビューサイクルの標準化
- 入力: 下書き結果、レビュア
- 処理: 指摘→修正→再提出→承認
- 出力: 最終承認、指摘ログ
- Plan骨子:
  - `loop.while(max_iterations)`: { draft → review → fix → re-submit }

---

## 11) 法務/契約

### 11-1. 契約条文抽出とリスクタグ付け
- 目的: 条文抽出・タグ付け・リスク分類・承認
- 入力: 契約PDF、契約台帳
- 処理: OCR/抽出→条文セグメント化→分類→承認
- 出力: リスク台帳、承認証跡
- Plan骨子:
  - `read_contracts`: `file.read_pdf`/`text.extract`
  - `segment_and_tag`: `nlp.extract_fields`/`nlp.classify`
  - `approve_export`: `ui.interactive_input` + `excel.write`

### 11-2. 契約台帳の整合・アテステーション
- 目的: 契約台帳と実文書の整合確認、差分の署名封緘
- 入力: 台帳、契約PDF
- 処理: 突合→差分→承認→署名
- 出力: 整合レポート、署名マニフェスト
- Plan骨子:
  - `read_ledger/docs`: `file.read_csv` + `file.read_pdf`
  - `reconcile`: `control.reconciliation` + `transforms.diff`
  - `approve`: `control.approval`
  - `attest`: `security.attestation.sign_manifest`

---

## 12) 税務

### 12-1. 間接税（VAT/消費税）整合性チェック
- 目的: 取引・申告・総勘定・補助簿の整合
- 入力: 請求書、GL、申告データ
- 処理: マッピング→集計→整合→例外承認
- 出力: 整合レポート、是正対応
- Plan骨子:
  - `collect_read`: `ui.interactive_input`, `file.read_csv`
  - `map_tax`: `transforms.map_fields`
  - `reconcile`: `control.reconciliation`
  - `approve_write`: `ui.interactive_input` + `excel.write`

### 12-2. 移転価格文書化 収集・要約・封緘
- 目的: 資料収集→要約→整合レビュー→Vault封緘
- 入力: 契約/価格ポリシー/レポート
- 処理: 抽出→要約→不足検知→承認→保存
- 出力: 証跡セット、要約
- Plan骨子:
  - `collect_docs`: `ui.interactive_input(files)`
  - `extract_summaries`: `ai.process_llm`
  - `validate_requirements`: `control.policy_enforce`
  - `approve_store`: `ui.interactive_input` + `evidence.vault.store`

---

# 付録: 必要な新規抽象ブロック（提案）

UIブロック（抽象）
- `ui.interactive_input` 拡張モード
  - `mode=table_review`: 表形式レビュー/承認/差戻し
  - `mode=assignment`: 作業配賦/進捗更新
  - `mode=exception_triage`: 例外のタグ付け/処理キュー
- `ui.approval_flow`
  - 入力: `levels`, `approvers`, `due_date`
  - 出力: `approved(bool)`, `route(log)`
- `ui.diff_viewer`
  - 入力: `before`, `after`
  - 出力: `diffs`

Processブロック（抽象）
- `control.approval`: 多段承認（SoD連携）
- `control.sod_check`: 職務分掌チェック
- `control.sampling`: 属性/統計サンプリング
- `control.reconciliation`: 突合（キー/閾値/許容誤差/グルーピング）
- `control.policy_enforce`: ポリシーYAML適用（禁止/閾値/必須要件）
- `matching.record_linkage`: レコード照合（exact/fuzzy）
- `matching.similarity_cluster`: 近似重複候補抽出
- `transforms.join`: join/merge（キー定義）
- `transforms.group_by_agg`: 集計
- `transforms.compute_metrics`: 指標・KPI計算
- `transforms.diff`: 差分抽出
- `transforms.map_fields`: マッピング/正規化
- `transforms.schema_validate`: スキーマ検証
- `transforms.compute_features`: 文字列/数値特徴量
- `data.quality.validate_rules`: DQルール評価
- `data.schema.diff`: スキーマ差分
- `data.provenance.capture`: 来歴/証跡メタ付与
- `file.read_pdf`, `file.ocr_parse`: 文書抽出
- `external.api.http`: 外部API呼出（GET/POST）
- `external.mail.send`: メール送信
- `notifier.slack` / `notifier.teams`: 通知
- `security.attestation.sign_manifest`: マニフェスト署名
- `evidence.vault.store`: 証跡保存（暗号化・保持期間）
- `scheduler.trigger`: 定期/イベント起動
- `nlp.extract_fields` / `nlp.classify` / `nlp.summarize_structured`: 構造化抽出・分類・要約

備考
- すべて汎用/抽象用途を想定し、特定ユースケースに依存しない命名とI/Oに統一。
- 既存ブロック（`ai.process_llm`, `excel.*`, `file.*`, `transforms.*`）と組み合わせてPlanを構成可能。
