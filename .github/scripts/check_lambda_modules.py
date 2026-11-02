#!/usr/bin/env python3
"""Detect Python import names that resolve to multiple Lambda asset paths."""

import sys
from collections import defaultdict
from pathlib import Path


EXCLUDED_DIRS = {"__pycache__", ".pytest_cache"}


def module_sources(root: Path) -> tuple[dict[str, list[Path]], set[str]]:
    modules: dict[str, list[Path]] = defaultdict(list)
    packages: set[str] = set()
    for source in sorted(root.rglob("*.py")):
        relative = source.relative_to(root)
        if any(part in EXCLUDED_DIRS for part in relative.parts) or source.name.endswith("_test.py"):
            continue
        parts = list(relative.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
            if parts:
                packages.add(".".join(parts))
        if not parts:
            continue
        modules[".".join(parts)].append(relative)
    return modules, packages


def collisions(root: Path) -> dict[str, list[Path]]:
    modules, packages = module_sources(root)
    findings = {name: paths for name, paths in modules.items() if len(paths) > 1}
    for name, paths in modules.items():
        if name in packages:
            continue
        descendants = [
            path
            for candidate, sources in modules.items()
            if candidate.startswith(f"{name}.")
            for path in sources
        ]
        if descendants:
            findings[f"{name} (module/package conflict)"] = [*paths, *descendants]
    return findings


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) == 2 else Path("lambda")
    if not root.is_dir():
        raise SystemExit(f"Lambda source directory does not exist: {root}")
    findings = collisions(root)
    if findings:
        for name, paths in sorted(findings.items()):
            print(f"{name}: " + ", ".join(path.as_posix() for path in paths), file=sys.stderr)
        raise SystemExit(1)
    print(f"No Lambda module-name collisions found in {root}.")


if __name__ == "__main__":
    main()