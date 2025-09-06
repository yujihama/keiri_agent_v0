from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "tests" / "data" / "nlp_compare"
    data_dir.mkdir(parents=True, exist_ok=True)

    a_text = (
        "Apple releases new iPhone with improved camera and battery life. "
        "It features A18 chip and iOS 18. Pricing starts at $799. Availability next month."
    )
    b_text = (
        "Samsung unveils new Galaxy phone with enhanced camera and longer battery life. "
        "It runs Exynos 2500 and Android 15. Price begins at $749. Shipping next month."
    )

    (data_dir / "A.txt").write_text(a_text, encoding="utf-8")
    (data_dir / "B.txt").write_text(b_text, encoding="utf-8")

    files_cfg = {
        "file_a": "tests/data/nlp_compare/A.txt",
        "file_b": "tests/data/nlp_compare/B.txt",
    }
    cfg_dir = root / "headless" / "configs"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "files_nlp_compare.json").write_text(
        json.dumps(files_cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("Created test files and headless/configs/files_nlp_compare.json")


if __name__ == "__main__":
    main()


