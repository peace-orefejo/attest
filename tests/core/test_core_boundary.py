"""Layering rules: core sits below every feature, and utils know nothing about attest types."""

import ast
from pathlib import Path

import attest

SRC = Path(attest.__file__).resolve().parent.parent

ABOVE_CORE = (
    "attest.checks",
    "attest.code_review",
    "attest.policy",
    "attest.extraction",
    "attest.adapters",
    "attest.scoring",
    "attest.api",
    "attest.cli",
)


def _modules(package: str) -> list[Path]:
    return sorted((SRC / package.replace(".", "/")).rglob("*.py"))


def _imported_names(path: Path) -> set[str]:
    parts = list(path.relative_to(SRC).with_suffix("").parts)
    package = parts if parts[-1] == "__init__" else parts[:-1]
    package = [p for p in package if p != "__init__"]
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)]
                prefix = ".".join(base + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            names.add(prefix)
            names.update(f"{prefix}.{alias.name}" for alias in node.names)
    return names


def _within(name: str, packages: tuple[str, ...]) -> bool:
    return any(name == p or name.startswith(p + ".") for p in packages)


def test_core_never_imports_from_layers_above_it():
    violations = [
        f"{path.relative_to(SRC)} imports {name}"
        for path in _modules("attest.core")
        for name in sorted(_imported_names(path))
        if _within(name, ABOVE_CORE)
    ]
    assert violations == []


def test_utils_do_not_import_attest_types():
    violations = [
        f"{path.relative_to(SRC)} imports {name}"
        for path in _modules("attest.utils")
        for name in sorted(_imported_names(path))
        if _within(name, ("attest",)) and not _within(name, ("attest.utils",))
    ]
    assert violations == []
