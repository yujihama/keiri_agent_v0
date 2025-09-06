"""
フロー図の統合テストスクリプト
実際のアプリケーションで新しいフロー図表示をテストします
"""
import subprocess
import sys
import os
from pathlib import Path

# プロジェクトルートを取得
project_root = Path(__file__).parent.parent
os.chdir(project_root)

print("=== D3.js フロー図表示テスト ===")
print(f"作業ディレクトリ: {os.getcwd()}")

# テストモード選択
print("\nテストモードを選択してください:")
print("1. 標準D3.js表示（デフォルト）")
print("2. 開発モード（サイドバーでレガシー切り替え可能）")
print("3. レガシー表示のみ（エラー発生時の緊急用）")

choice = input("選択 (1-3): ").strip()

# 環境変数設定
env = os.environ.copy()

if choice == "1":
    print("\n→ 標準D3.js表示で起動します")
elif choice == "2":
    env["KEIRI_DEV_MODE"] = "true"
    print("\n→ 開発モードで起動します（サイドバーでレガシー切り替え可能）")
elif choice == "3":
    env["KEIRI_USE_LEGACY_FLOW"] = "true"
    print("\n→ レガシー表示モードで起動します")
else:
    print("\n→ デフォルト設定（D3.js自由配置）で起動します")

# Streamlitアプリを起動
print("\nStreamlitアプリを起動中...")
print("ブラウザが自動的に開きます。")
print("\n【確認ポイント】")
print("1. 業務実施タブでプランを選択")
print("2. フロー図にエッジ（接続線）が表示されるか確認")
print("3. 実行ボタンを押して自動スクロールを確認")
print("\n終了するには Ctrl+C を押してください。")

cmd = [sys.executable, "-m", "streamlit", "run", "app.py"]
subprocess.run(cmd, env=env)
