#!/usr/bin/env python3
"""
CLIランナーの動作確認用テストスクリプト
"""

import subprocess
import sys
from pathlib import Path


def test_basic_execution():
    """基本的な実行テスト"""
    print("=== 基本的な実行テスト ===")
    
    cmd = [
        sys.executable, "cli_runner.py",
        "designs/retirement_benefit_q1_2025.yaml",
        "--verbose"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        print(f"終了コード: {result.returncode}")
        if result.stdout:
            print("標準出力:")
            print(result.stdout)
        if result.stderr:
            print("標準エラー:")
            print(result.stderr)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("タイムアウト")
        return False
    except Exception as e:
        print(f"エラー: {e}")
        return False


def test_headless_execution():
    """ヘッドレスモードでの実行テスト"""
    print("\n=== ヘッドレスモードでの実行テスト ===")
    
    cmd = [
        sys.executable, "cli_runner.py",
        "designs/retirement_benefit_q1_2025.yaml",
        "--headless",
        "--config", "examples/execution_config.json",
        "--output", "test_output",
        "--verbose"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        print(f"終了コード: {result.returncode}")
        if result.stdout:
            print("標準出力:")
            print(result.stdout)
        if result.stderr:
            print("標準エラー:")
            print(result.stderr)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("タイムアウト")
        return False
    except Exception as e:
        print(f"エラー: {e}")
        return False


def test_variables_override():
    """変数オーバーライドのテスト"""
    print("\n=== 変数オーバーライドのテスト ===")
    
    cmd = [
        sys.executable, "cli_runner.py",
        "designs/retirement_benefit_q1_2025.yaml",
        "--headless",
        "--vars", '{"fiscal_year": "2026", "quarter": "Q2"}',
        "--verbose"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        print(f"終了コード: {result.returncode}")
        if result.stdout:
            print("標準出力:")
            print(result.stdout)
        if result.stderr:
            print("標準エラー:")
            print(result.stderr)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("タイムアウト")
        return False
    except Exception as e:
        print(f"エラー: {e}")
        return False


def test_file_inputs():
    """ファイル入力のテスト"""
    print("\n=== ファイル入力のテスト ===")
    
    cmd = [
        sys.executable, "cli_runner.py",
        "designs/retirement_benefit_q1_2025.yaml",
        "--headless",
        "--files", "examples/files_config.json",
        "--verbose"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        print(f"終了コード: {result.returncode}")
        if result.stdout:
            print("標準出力:")
            print(result.stdout)
        if result.stderr:
            print("標準エラー:")
            print(result.stderr)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("タイムアウト")
        return False
    except Exception as e:
        print(f"エラー: {e}")
        return False


def main():
    """メイン関数"""
    print("CLIランナーの動作確認テストを開始します")
    
    tests = [
        ("基本的な実行", test_basic_execution),
        ("ヘッドレスモード", test_headless_execution),
        ("変数オーバーライド", test_variables_override),
        ("ファイル入力", test_file_inputs),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        try:
            success = test_func()
            results.append((test_name, success))
            if success:
                print(f"✅ {test_name}: 成功")
            else:
                print(f"❌ {test_name}: 失敗")
        except Exception as e:
            print(f"❌ {test_name}: エラー - {e}")
            results.append((test_name, False))
    
    # 結果サマリー
    print("\n=== テスト結果サマリー ===")
    success_count = sum(1 for _, success in results if success)
    total_count = len(results)
    
    for test_name, success in results:
        status = "✅ 成功" if success else "❌ 失敗"
        print(f"{test_name}: {status}")
    
    print(f"\n成功率: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")
    
    if success_count == total_count:
        print("🎉 すべてのテストが成功しました！")
        return 0
    else:
        print("⚠️  一部のテストが失敗しました")
        return 1


if __name__ == "__main__":
    sys.exit(main())
