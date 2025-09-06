import pandas as pd
import json
import os

# Excel file path
excel_path = "headless/output/nlp_compare/text_similarity_compare_two_files/2025-09-05T02-01-03/artifacts/text_compare.xlsx"

# Read all sheets
print(f"Inspecting: {excel_path}\n")

try:
    # Load Excel file
    xl = pd.ExcelFile(excel_path)
    print(f"Available sheets: {xl.sheet_names}\n")
    
    # Read each sheet
    for sheet_name in xl.sheet_names:
        print(f"--- Sheet: {sheet_name} ---")
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        print(f"Shape: {df.shape}")
        print(f"Columns: {list(df.columns)}")
        print(f"\nFirst 10 rows:")
        print(df.head(10))
        print(f"\n")
        
except Exception as e:
    print(f"Error reading Excel file: {e}")

# Also check the flatten_rows output to understand the data
print("\n--- Checking flatten_rows output ---")
flatten_rows_path = "headless/output/nlp_compare/text_similarity_compare_two_files/2025-09-05T02-01-03/artifacts/flatten_rows_outputs.json"
try:
    with open(flatten_rows_path, 'r', encoding='utf-8') as f:
        flatten_data = json.load(f)
        if 'items' in flatten_data:
            print(f"Total items: {len(flatten_data['items'])}")
            print("\nFirst 3 items:")
            for i, item in enumerate(flatten_data['items'][:3]):
                print(f"\nItem {i+1}:")
                print(json.dumps(item, ensure_ascii=False, indent=2))
except Exception as e:
    print(f"Error reading flatten_rows output: {e}")
