#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from headless.cli_runner import main
    print("CLI runner imported successfully", file=sys.stderr)
    sys.argv = ['cli_runner.py', 'designs/text_similarity_compare_two_files.yaml', '--headless', '--files', 'headless/configs/files_nlp_compare.json', '--ui-mocks', 'headless/configs/ui_mocks.json', '--output', 'headless/output/nlp_compare', '--verbose']
    main()
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
