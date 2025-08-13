#!/usr/bin/env python
"""
Audit Python imports in the repo and compare against declared dependencies
in requirements files and/or pyproject.toml. Exits with code 1 if missing
packages are detected.

Usage:
  python tools/req_audit.py [--root .]
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path
from typing import Iterable, Set, Dict, List, Tuple


EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "build",
    "dist",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
}


SPECIAL_IMPORT_TO_PKG: Dict[str, str] = {
    # Common exceptions where import name != package name
    "PIL": "Pillow",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "skimage": "scikit-image",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "Crypto": "pycryptodome",
    "jwt": "PyJWT",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "tomllib": "tomli; python_version<'3.11'",
    "pil": "Pillow",
    "mpl_toolkits": "matplotlib",
    "pandas_gbq": "pandas-gbq",
    "googleapiclient": "google-api-python-client",
    "google_auth_oauthlib": "google-auth-oauthlib",
    "google_auth": "google-auth",
    "skbuild": "scikit-build",
}


SPEC_SPLIT_RE = re.compile(r"(==|>=|<=|~=|!=|<|>|===)")


def canonicalize(name: str) -> str:
    return name.lower().replace("_", "-")


def discover_python_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded dirs
        parts = Path(dirpath).parts
        if any(part in EXCLUDE_DIRS for part in parts):
            # If current directory is excluded, skip walking into it
            # by clearing dirnames
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for f in filenames:
            if f.endswith(".py"):
                yield Path(dirpath) / f


def parse_imports(py_file: Path) -> Set[str]:
    try:
        src = py_file.read_text(encoding="utf-8")
    except Exception:
        return set()
    try:
        tree = ast.parse(src, filename=str(py_file))
    except SyntaxError:
        return set()
    imports: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top:
                    imports.add(top)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                if top:
                    imports.add(top)
    return imports


def stdlib_modules() -> Set[str]:
    names: Set[str] = set()
    # Python 3.10+
    std_names = getattr(sys, "stdlib_module_names", None)
    if std_names:
        names |= set(std_names)
    # Always include a few builtins and common aliases
    names |= {
        "__future__",
        "typing",
        "dataclasses",
        "pathlib",
        "asyncio",
        "concurrent",
        "contextlib",
        "functools",
        "itertools",
        "json",
        "re",
        "os",
        "sys",
        "subprocess",
        "logging",
        "argparse",
        "collections",
        "importlib",
        "pkgutil",
        "inspect",
        "unittest",
        "unittest.mock",
        "http",
        "urllib",
        "xml",
        "email",
        "sqlite3",
        "venv",
        "zipfile",
        "tarfile",
        "math",
        "statistics",
        "random",
        "time",
        "datetime",
        "zoneinfo",
        "decimal",
        "fractions",
        "hashlib",
        "hmac",
        "secrets",
        "base64",
        "getpass",
        "glob",
        "shutil",
        "tempfile",
        "uuid",
        "pprint",
        "traceback",
        "doctest",
        "io",
        "csv",
        "configparser",
        "platform",
        "copy",
        "heapq",
        "bisect",
        "asyncio",
        "threading",
        "multiprocessing",
        "resource",
    }
    return {name.split(".")[0] for name in names}


def local_top_level_modules(root: Path) -> Set[str]:
    names: Set[str] = set()
    for p in root.iterdir():
        if p.name.startswith("."):
            continue
        if p.is_dir():
            if (p / "__init__.py").exists():
                names.add(p.name)
        elif p.is_file() and p.suffix == ".py":
            names.add(p.stem)
    # Also consider common src layout
    src_dir = root / "src"
    if src_dir.exists() and src_dir.is_dir():
        for p in src_dir.iterdir():
            if p.is_dir() and (p / "__init__.py").exists():
                names.add(p.name)
    return names


def read_requirements_like(path: Path) -> Set[str]:
    reqs: Set[str] = set()
    if not path.exists():
        return reqs
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        # Handle -r includes or local paths; skip
        if s.startswith("-r ") or s.startswith("--requirement "):
            # Could follow include chain, skip for simplicity
            continue
        if s.startswith("-e ") or s.startswith("--editable "):
            # Editable install; attempt to extract name at end if present
            m = re.search(r"#egg=([A-Za-z0-9_.\-]+)", s)
            if m:
                reqs.add(canonicalize(m.group(1)))
            continue
        # Strip environment markers
        s = s.split(";")[0].strip()
        # Strip extras
        s = re.sub(r"\[.*?\]", "", s)
        # Split specifier
        parts = SPEC_SPLIT_RE.split(s, maxsplit=1)
        name = parts[0].strip()
        if name:
            reqs.add(canonicalize(name))
    return reqs


def read_pyproject_deps(pyproject: Path) -> Tuple[Set[str], Set[str]]:
    main: Set[str] = set()
    dev: Set[str] = set()
    if not pyproject.exists():
        return main, dev
    try:
        try:
            import tomllib  # type: ignore
        except Exception:
            tomllib = None
        data = None
        if tomllib is not None:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except Exception:
        data = None
    if not data:
        return main, dev

    def extract_list(dep_list: List[str] | None) -> Set[str]:
        out: Set[str] = set()
        if not dep_list:
            return out
        for s in dep_list:
            s = s.split(";")[0]
            s = re.sub(r"\[.*?\]", "", s)
            s = SPEC_SPLIT_RE.split(s, maxsplit=1)[0]
            out.add(canonicalize(s))
        return out

    # PEP 621
    main |= extract_list(
        (data.get("project") or {}).get("dependencies")  # type: ignore
    )
    # Optional dev-dependencies via project.optional-dependencies.dev
    opt = (data.get("project") or {}).get("optional-dependencies") or {}
    if isinstance(opt, dict):
        for group, deps in opt.items():
            if group.lower() in {"dev", "test", "tests"} and isinstance(deps, list):
                dev |= extract_list(deps)

    # Poetry
    poetry = (data.get("tool") or {}).get("poetry") or {}
    if poetry:
        deps = poetry.get("dependencies") or {}
        if isinstance(deps, dict):
            for k, v in deps.items():
                if k == "python":
                    continue
                main.add(canonicalize(k))
        dev_deps = (poetry.get("group") or {}).get("dev", {}).get("dependencies") or {}
        if isinstance(dev_deps, dict):
            for k in dev_deps.keys():
                dev.add(canonicalize(k))
    return main, dev


def map_import_to_pkg(name: str) -> str:
    if name in SPECIAL_IMPORT_TO_PKG:
        return SPECIAL_IMPORT_TO_PKG[name]
    return name


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Python requirements")
    parser.add_argument("--root", default=".", help="Project root to scan")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    stdlib = stdlib_modules()
    local = local_top_level_modules(root)

    all_imports: Set[str] = set()
    for f in discover_python_files(root):
        all_imports |= parse_imports(f)

    # Filter
    candidates = {
        name
        for name in all_imports
        if name not in stdlib and name not in local and not name.startswith("_")
    }

    # Declared deps
    declared: Set[str] = set()
    declared_dev: Set[str] = set()

    declared |= read_requirements_like(root / "requirements.txt")
    declared_dev |= read_requirements_like(root / "requirements-dev.txt")
    declared |= read_requirements_like(root / "requirements.in")
    # requirements/*.txt
    req_dir = root / "requirements"
    if req_dir.exists() and req_dir.is_dir():
        for p in req_dir.glob("*.txt"):
            declared |= read_requirements_like(p)

    main_deps, dev_deps = read_pyproject_deps(root / "pyproject.toml")
    declared |= main_deps
    declared_dev |= dev_deps

    # Compute missing mapping to suggested package
    missing: List[Tuple[str, str]] = []
    for imp in sorted(candidates):
        pkg = canonicalize(map_import_to_pkg(imp))
        # Some suggestions include markers; strip for membership check
        check_pkg = canonicalize(pkg.split(";")[0].strip())
        if check_pkg not in declared and check_pkg not in declared_dev:
            missing.append((imp, pkg))

    print("=== Requirement Audit Report ===")
    print(f"Project root: {root}")
    print(f"Discovered imports (non-stdlib/local): {len(candidates)}")
    print(f"Declared requirements: {len(declared)} main, {len(declared_dev)} dev")
    if missing:
        print("\nMissing packages (import -> suggested requirement):")
        for imp, pkg in missing:
            print(f"  - {imp} -> {pkg}")
        print("\nRecommendation: add missing packages to requirements.txt or pyproject.toml.")
        return 1
    else:
        print("\nNo missing packages detected. ✅")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

