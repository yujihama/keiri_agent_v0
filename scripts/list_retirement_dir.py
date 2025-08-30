from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    root = Path("tests/data/retirement_data")
    print("dir_exists:", root.exists())
    if root.exists():
        for name in os.listdir(root):
            try:
                print(name)
            except Exception as e:
                print("print_error:", e)


if __name__ == "__main__":
    main()


