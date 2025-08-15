#!/usr/bin/env python3
"""テスト実行スクリプト

監査・内部統制機能のテストを体系的に実行します。
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd, description):
    """コマンド実行"""
    print(f"\n🔄 {description}")
    print(f"Command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"✅ {description} - 成功")
        if result.stdout:
            print(result.stdout)
    else:
        print(f"❌ {description} - 失敗")
        if result.stderr:
            print(result.stderr)
        return False
    
    return True


def main():
    parser = argparse.ArgumentParser(description="監査・内部統制機能テスト実行")
    parser.add_argument("--type", choices=["unit", "integration", "e2e", "security", "all"], 
                       default="all", help="実行するテストタイプ")
    parser.add_argument("--coverage", action="store_true", 
                       help="カバレッジレポート生成")
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="詳細出力")
    parser.add_argument("--fast", action="store_true", 
                       help="高速実行（slowテストをスキップ）")
    
    args = parser.parse_args()
    
    # プロジェクトルートに移動
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    print("🧪 Keiri Agent - 監査・内部統制機能テスト")
    print(f"📁 Project Root: {project_root}")
    print(f"🎯 Test Type: {args.type}")
    
    # pytest基本オプション
    pytest_cmd = ["python", "-m", "pytest"]
    
    if args.verbose:
        pytest_cmd.append("-v")
    
    if args.coverage:
        pytest_cmd.extend(["--cov=core", "--cov-report=html", "--cov-report=term-missing"])
    
    if args.fast:
        pytest_cmd.extend(["-m", "not slow"])
    
    # テストタイプ別実行
    success = True
    
    if args.type == "unit" or args.type == "all":
        cmd = pytest_cmd + ["-m", "unit", "tests/"]
        success &= run_command(cmd, "単体テスト実行")
    
    if args.type == "integration" or args.type == "all":
        cmd = pytest_cmd + ["-m", "integration", "tests/"]
        success &= run_command(cmd, "統合テスト実行")
    
    if args.type == "e2e" or args.type == "all":
        cmd = pytest_cmd + ["-m", "e2e", "tests/"]
        success &= run_command(cmd, "E2Eテスト実行")
    
    if args.type == "security" or args.type == "all":
        cmd = pytest_cmd + ["-m", "security", "tests/"]
        success &= run_command(cmd, "セキュリティテスト実行")
    
    if args.type == "all":
        # 特定テストファイルの実行
        test_files = [
            "tests/test_evidence_vault.py",
            "tests/test_control_blocks.py", 
            "tests/test_policy_engine.py",
            "tests/test_integration.py"
        ]
        
        for test_file in test_files:
            if Path(test_file).exists():
                cmd = pytest_cmd + [test_file]
                success &= run_command(cmd, f"{test_file} 実行")
    
    # 結果サマリ
    print("\n" + "="*60)
    if success:
        print("🎉 全テスト成功！")
        
        if args.coverage:
            print("\n📊 カバレッジレポートが htmlcov/ に生成されました")
            print("   ブラウザで htmlcov/index.html を開いて確認してください")
        
        print("\n✅ 監査・内部統制機能は正常に動作しています")
        
    else:
        print("💥 一部のテストが失敗しました")
        print("   詳細なエラー情報を確認して修正してください")
        sys.exit(1)


if __name__ == "__main__":
    main()