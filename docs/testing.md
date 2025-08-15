# 監査・内部統制機能テストガイド

## 概要

Keiri Agentの監査・内部統制機能（Evidence Vault、Control Blocks、Policy-as-Code、Reviewer Workspace）の包括的なテストスイートです。

## テスト構造

### 1. テストカテゴリ

#### 単体テスト (Unit Tests)
- **Evidence Vault**: 暗号化、メタデータ管理、証跡保存・取得
- **Control Blocks**: 承認統制、職務分掌、サンプリング
- **Policy Engine**: ポリシー評価、違反検知
- **認証システム**: ロールベースアクセス制御

#### 統合テスト (Integration Tests)
- コンポーネント間連携
- Evidence Vault + Policy Engine
- Control Blocks + Evidence Vault
- Reviewer Workspace全体

#### E2Eテスト (End-to-End Tests)
- 完全な監査ワークフロー
- 高額購買申請シナリオ
- コンプライアンス違反検知

#### セキュリティテスト (Security Tests)
- 暗号化・復号化
- アクセス制御
- データ漏洩防止

#### パフォーマンステスト (Performance Tests)
- 大量データ処理
- 並行アクセス
- レスポンス時間

## テスト実行方法

### 基本実行

```bash
# 全テスト実行
python scripts/run_tests.py

# 特定カテゴリのみ
python scripts/run_tests.py --type unit
python scripts/run_tests.py --type integration
python scripts/run_tests.py --type e2e
python scripts/run_tests.py --type security

# カバレッジ付き実行
python scripts/run_tests.py --coverage

# 高速実行（slowテストスキップ）
python scripts/run_tests.py --fast
```

### pytest直接実行

```bash
# マーカー別実行
pytest -m unit tests/
pytest -m integration tests/
pytest -m e2e tests/
pytest -m security tests/
pytest -m audit tests/

# 特定ファイル実行
pytest tests/test_evidence_vault.py -v
pytest tests/test_control_blocks.py -v
pytest tests/test_policy_engine.py -v
pytest tests/test_integration.py -v

# カバレッジレポート生成
pytest --cov=core --cov-report=html --cov-report=term-missing
```

## テストファイル構成

```
tests/
├── conftest.py                 # 共通フィクスチャ・設定
├── test_evidence_vault.py      # Evidence Vault単体テスト
├── test_control_blocks.py      # Control Blocks単体テスト
├── test_policy_engine.py       # Policy Engine単体テスト
├── test_integration.py         # 統合・E2E・セキュリティテスト
└── data/                       # テストデータ
```

## 主要テストケース

### Evidence Vault

#### 暗号化機能
- AES-256暗号化・復号化
- HMAC-SHA256改ざん検知
- パスワード派生機能
- 不正データ処理

#### 証跡管理
- 証跡保存・取得
- メタデータ管理
- 検索・フィルタリング
- 監査証跡作成

#### セキュリティ
- 暗号化状態での保存
- 不正アクセス防止
- データ整合性検証

### Control Blocks

#### 承認統制ブロック
- 単一・多段承認フロー
- 金額別承認レベル
- タイムアウト・エスカレーション
- 承認履歴管理

#### 職務分掌チェックブロック
- 同一人物検知
- ロール競合チェック
- 例外処理
- 複数違反検知

#### サンプリングブロック
- 統計的サンプリング
- リスクベースサンプリング
- 系統的・ランダムサンプリング
- サンプルサイズ計算

### Policy Engine

#### ポリシー管理
- ポリシー作成・保存・読み込み
- ライフサイクル管理
- バージョン管理

#### ルール評価
- 閾値ルール
- 式ルール
- 承認必須ルール
- 職務分掌ルール

#### 違反検知
- 違反タイプ別検知
- 重要度判定
- 複数違反処理

### 統合テスト

#### 完全監査ワークフロー
1. 承認プロセス実行
2. 職務分掌チェック
3. ポリシー検証
4. サンプリング実行
5. 証跡保存確認

#### E2Eコンプライアンスシナリオ
- 正常申請フロー
- 違反検知フロー
- 複数違反ケース
- 証跡生成確認

#### セキュリティ統制
- 機密データ暗号化
- 不正アクセス防止
- 改ざん検知

## テスト環境設定

### 必要な依存関係

```txt
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-mock>=3.11.1
pytest-asyncio>=0.21.1
freezegun>=1.2.2
```

### 環境変数

```bash
# テスト専用設定
KEIRI_TEST_MODE=true
KEIRI_LOG_LEVEL=DEBUG
```

### フィクスチャ

#### 共通フィクスチャ
- `temp_workspace`: テスト用一時ディレクトリ
- `evidence_vault`: テスト用Evidence Vault
- `policy_engine`: テスト用Policy Engine
- `block_context`: テスト用ブロックコンテキスト

#### データフィクスチャ
- `sample_policy`: サンプルポリシー
- `sample_transaction_data`: サンプル取引データ
- `approval_request_data`: 承認要求データ
- `population_data`: サンプリング用母集団データ

## CI/CD統合

### GitHub Actions

`.github/workflows/test.yml`により以下が自動実行：

1. **マルチPython環境テスト** (3.9, 3.10, 3.11)
2. **単体・統合・セキュリティテスト**
3. **E2E・パフォーマンステスト**
4. **セキュリティスキャン** (bandit, safety)
5. **カバレッジレポート生成**
6. **監査コンプライアンステスト**

### テスト成果物

- **カバレッジレポート**: `htmlcov/index.html`
- **セキュリティレポート**: `bandit-report.json`, `safety-report.json`
- **テスト証跡**: Evidence Vaultに自動保存

## カバレッジ目標

| コンポーネント | 目標カバレッジ | 現在 |
|---------------|---------------|------|
| Evidence Vault | 95%+ | ✅ |
| Control Blocks | 90%+ | ✅ |
| Policy Engine | 95%+ | ✅ |
| Reviewer Workspace | 85%+ | ✅ |
| 全体 | 90%+ | ✅ |

## パフォーマンス要件

| 項目 | 要件 | テスト |
|------|------|--------|
| 1000件証跡保存 | 60秒以内 | ✅ |
| 証跡検索 | 5秒以内 | ✅ |
| 並行アクセス | エラーなし | ✅ |
| ポリシー評価 | 1秒以内 | ✅ |

## セキュリティ要件

### 暗号化
- ✅ AES-256による証跡暗号化
- ✅ HMAC-SHA256改ざん検知
- ✅ 鍵管理・パスワード派生
- ✅ 平文データ漏洩防止

### アクセス制御
- ✅ ロールベースアクセス制御
- ✅ セッション管理
- ✅ 権限チェック
- ✅ 不正アクセス防止

### 監査証跡
- ✅ 全操作の証跡記録
- ✅ 改ざん検知
- ✅ 7年間保存
- ✅ 検索・分析機能

## トラブルシューティング

### 一般的な問題

#### 1. テスト失敗
```bash
# 詳細ログでテスト実行
pytest tests/ -v -s --tb=long

# 特定テストのみ実行
pytest tests/test_evidence_vault.py::TestEvidenceVault::test_store_evidence -v
```

#### 2. フィクスチャエラー
```bash
# フィクスチャ一覧確認
pytest --fixtures tests/

# conftest.pyの構文チェック
python -m py_compile tests/conftest.py
```

#### 3. インポートエラー
```bash
# PYTHONPATHの設定
export PYTHONPATH=/workspace:$PYTHONPATH

# パッケージインストール確認
pip list | grep -E "(pytest|cryptography|pydantic)"
```

#### 4. パフォーマンステスト失敗
```bash
# slowテストをスキップ
pytest -m "not slow" tests/

# タイムアウト調整
pytest --timeout=300 tests/
```

### Evidence Vault関連

#### 暗号化エラー
- パスワード設定確認
- cryptographyライブラリバージョン
- ファイル権限チェック

#### 証跡保存エラー
- ディスク容量確認
- ディレクトリ権限
- メタデータ整合性

### Policy Engine関連

#### ポリシー読み込みエラー
- JSON構文チェック
- ポリシーディレクトリ存在確認
- ファイル権限

#### ルール評価エラー
- 式構文確認
- データ型チェック
- パラメータ妥当性

## ベストプラクティス

### テスト作成
1. **AAA原則**: Arrange, Act, Assert
2. **独立性**: テスト間の依存関係を避ける
3. **再現性**: 同じ条件で同じ結果
4. **明確性**: テスト名で意図を表現

### フィクスチャ使用
1. **スコープ**: 適切なスコープ設定
2. **クリーンアップ**: リソース解放
3. **パラメータ化**: 複数パターンテスト
4. **モック**: 外部依存の分離

### アサーション
1. **具体的**: 期待値を明確に
2. **網羅的**: エラーケースも含む
3. **メッセージ**: 失敗時の情報提供
4. **タイムアウト**: 長時間処理の制限

## 継続的改善

### テストメトリクス
- カバレッジ率の監視
- テスト実行時間の追跡
- 失敗率の分析
- パフォーマンス指標

### 品質向上
- 定期的なテスト見直し
- 新機能への対応
- セキュリティ要件更新
- パフォーマンス最適化

## 参考資料

- [pytest公式ドキュメント](https://docs.pytest.org/)
- [cryptography文書](https://cryptography.io/)
- [セキュリティテストガイド](https://owasp.org/www-project-web-security-testing-guide/)
- [監査・内部統制詳細設計書](./detail_audit_and_controls/)


