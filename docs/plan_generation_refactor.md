## プラン生成 リファクタリング計画（段階生成方式）

### 目的・範囲
- **目的**: 誤設計を低減し、UXを向上させるため、LLMによるプラン生成を「段階的生成＋段階検証」にリファクタリングする。
- **範囲**: 業務概要→概要プラン→詳細プラン→登録 の4段階設計、各段での入力強化（Specスライス）、構造化出力、検証/自己修復、UI連携。

---

## 段階フロー（4ステップ）

### 1. 業務概要作成（Business Overview）
- **入力**: 指示テキスト、参考文書（txt/md/pdf/docx/xlsx）
- **出力モデル（BusinessOverview）**
```json
{
  "title": "string",
  "inputs": [
    { "id": "files", "channel": "file|chat|api", "count": "one|many", "kinds": ["excel|csv|pdf|..."], "notes": "string?" }
  ],
  "processes": [
    { "id": "reconcile", "description": "自然文", "rules": ["optional short rules"], "dependencies": ["optional"] }
  ],
  "outputs": [
    { "id": "report", "type": "ui|excel|json|pdf", "description": "自然文", "sheet": "string" }
  ],
  "assumptions": ["string"],
  "open_points": ["string"]
}
```
- **特徴**: ブロックは参照しない。構造は固定。画面で編集可能。

### 2. 概要プラン作成（Plan Skeleton）
- **トリガ**: ユーザーが「プラン生成」押下（テンプレート複数選択可）
- **入力**: `BusinessOverview` + 選択テンプレ要約 + 全ブロックの内容と概要
- **出力モデル（PlanSkeleton）**
```json
{
  "ui": { "layout": ["nodeId"] },
  "graph": [ { "id": "string", "block": "id?", "type": "subflow|loop|...|null" } ],
  "vars_placeholders": ["vars.*"],
  "templates_ref": ["template_id"]
}
```
- **制約**: ブロックの「名前と概要」のみを使い、入出力・引数は未定義。循環/未知ブロック/重複IDのみ検査。

### 3. 詳細プラン作成（Plan Detailing）
- **入力**: `PlanSkeleton` +（Skeletonに含まれる）ブロックの定義スライス（Spec）+ 選択テンプレの定義全文
- **出力**: 実行可能な `Plan`（in/out/when/foreach/subflow/vars/policy/ui.layout 完備）
- **検証/自己修復**: 検証→失敗→差分修正の反復（上限 N 回）。ドライラン前プレフライトでブロック固有の形・enumをチェック。
- **差分修正モデル（FixPatch）**
```json
{ "target": "node.id:path", "op": "set|add|remove", "value": "any" }
```

### 4. プラン登録
- 生成YAMLをUIで確認/編集。検証/ドライランでOKになれば `designs/<plan_id>_<ts>.yaml` へ保存。

---

## UI 連携（Designタブの導線）
- 1) 業務概要→画面で編集　※不明点ある場合は設計QAのチャットインターフェース
- 2) 概要プラン生成　※不明点ある場合は設計QAのチャットインターフェース
- 3) 詳細化　※不明点ある場合は設計QAのチャットインターフェース
- 4) 検証/ドライラン/登録
- 失敗時: 各段の `violations[{node_id, field, rule, got, expected}]` を表示。自己修復ログも展開表示。

---

## ロギング/メトリクス
- 収集項目: 段階別の検証失敗件数、自己修復回数、最終成功までの反復回数、生成時間、採用ブロック分布。
- UIで簡易表示（成功/失敗の要約、修復ログ）。

---

## 方針の確認
- 一度に全てを生成せず、段階ごとに「入力強化→構造化出力→軽量検証→必要ならその段だけ再生成」で進める。
- 失敗時は黙ってフォールバックせず、エラーを表示して自己修復する（自動/半自動）。

---

## 設計QA（Design QA）

- 目的: 設計段階で発生した不明点は`ui.interactive_input`のチャットモードと同等の機能（または流用して）で人間に問い合わせを行う。収集した回答は保持され、ブロック選定・分岐判断・テンプレ選択・引数具体化に活用する。
- 典型例:
  - CSVの形式を使う処理だが、pivot変換が必要か判断が必要→どの形式か質問→回答に応じて `table.pivot` か `table.unpivot` を選定。
  - Excelに転記する処理だが、シート名/ヘッダ行/列マッピングなどが必要→質問→回答に応じてパラメータを設定する。


