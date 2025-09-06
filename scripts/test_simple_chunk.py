import json

# filterブロックの出力を再現
filtered_a = [{
    "name": "A.txt", 
    "ext": ".txt", 
    "size": 146, 
    "text_excerpt": "Apple releases new iPhone with improved camera and battery life. It features A18 chip and iOS 18. Pricing starts at $799. Availability next month."
}]

print("Filter output structure:")
print(json.dumps(filtered_a, indent=2))
print(f"\nType: {type(filtered_a)}")
print(f"First item type: {type(filtered_a[0])}")
print(f"text_excerpt exists: {'text_excerpt' in filtered_a[0]}")

# chunk_textsの入力検証をシミュレート
files_in = filtered_a
texts_in = None

print(f"\nInput validation:")
print(f"files_in is list: {isinstance(files_in, list)}")
print(f"files_in length: {len(files_in)}")

# 実際のチャンク処理のロジックを再現
texts = []
if isinstance(files_in, list):
    for f in files_in:
        if not isinstance(f, dict):
            continue
        name = str(f.get("name") or f.get("path") or "file")
        s = str(f.get("text_excerpt") or f.get("text") or "")
        print(f"\nProcessing file: {name}")
        print(f"Text content: {s[:50]}...")
        if s:
            texts.append((name, s))

print(f"\nTexts collected: {len(texts)}")
print(f"Should pass validation: {len(texts) > 0}")
