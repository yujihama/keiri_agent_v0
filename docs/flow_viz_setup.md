# D3.js フロー図表示設定ガイド

## 概要

keiri_agentはD3.jsベースの高機能フロー図表示を採用しています。

## 主な機能

1. **エッジ（接続線）の表示** - ノード間の依存関係が視覚的に表示されます
2. **自動スクロール機能** - 実行中のノードが自動的に画面中央に表示されます
3. **物理シミュレーション** - 自然でインタラクティブなノード配置
4. **ドラッグ＆ドロップ** - ノードを自由に移動できます
5. **ズーム機能** - マウスホイールで拡大縮小

## 設定方法

### 環境変数で設定

`.env`ファイルに以下の設定を追加：

```env
# フロー図のサイズ
KEIRI_FLOW_WIDTH=800
KEIRI_FLOW_HEIGHT=400

# 物理シミュレーションパラメータ
KEIRI_FLOW_NODE_RADIUS=65
KEIRI_FLOW_LINK_DISTANCE=150
KEIRI_FLOW_CHARGE=-600

# 開発モード（レガシー切り替えオプション表示）
KEIRI_DEV_MODE=false
```

### コマンドラインで一時的に設定

PowerShell:
```powershell
# フロー図サイズの変更
$env:KEIRI_FLOW_WIDTH = "1000"
$env:KEIRI_FLOW_HEIGHT = "600"
streamlit run app.py

# レガシー表示に戻す（エラー時）
$env:KEIRI_USE_LEGACY_FLOW = "true"
streamlit run app.py
```

## トラブルシューティング

### エラー: ModuleNotFoundError

フロー図の新機能でエラーが発生した場合：

1. 依存関係を確認：
   ```bash
   pip install streamlit networkx matplotlib
   ```

2. プロジェクトルートから実行：
   ```bash
   cd C:\Users\nyham\work\keiri_agent
   streamlit run app.py
   ```

### 表示が崩れる場合

1. ブラウザのキャッシュをクリア
2. 別の表示方法を試す
3. `KEIRI_FLOW_HEIGHT`を調整

## 既存システムへの影響

- **後方互換性あり** - `KEIRI_USE_LEGACY_FLOW=true`で既存表示に戻せます
- **パフォーマンス** - D3.jsは高機能でインタラクティブです
- **API変更なし** - 既存のコードを変更する必要はありません

## D3.js実装の利点

- **インタラクティブ**: ノードのドラッグ、ズーム、ホバー
- **物理シミュレーション**: 自然で美しいレイアウト
- **重複回避**: ノード同士が重ならない
- **拡張性**: 将来的な機能追加が容易

## 今後の拡張予定

- [ ] ノードのカスタムスタイル
- [ ] アニメーション効果
- [ ] フロー図のエクスポート機能（PNG/SVG）
- [ ] カスタムテーマ対応

## 参考ファイル

- `ui/flow_viz.py` - メインの表示関数
- `ui/flow_viz_d3.py` - D3.js実装
- `ui/flow_viz_config.py` - 設定管理
- `scripts/debug_flow_viz.py` - デバッグツール
