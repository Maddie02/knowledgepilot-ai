"""Architecture test: enforce the package dependency rules described in the README.

Each top-level package under `app/` may only import from the packages listed
for it. This keeps dependencies pointing one way and prevents layers from
depending on each other in both directions.
"""

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# package -> app packages it may import from (besides itself)
ALLOWED = {
    "core": set(),
    "schemas": {"core"},
    "llm": {"core"},
    "services": {"core", "llm", "schemas"},
    "api": {"core", "llm", "schemas", "services"},
}

# Inside `app.llm`, providers must not depend on the factory or the package facade.
LLM_PROVIDER_ALLOWED = {"app.llm.types", "app.llm.errors"}


def imported_app_modules(path: Path) -> set[str]:
    """All `app.*` modules imported by a file, including imports inside functions."""
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return {m for m in modules if m == "app" or m.startswith("app.")}


def package_files(package: str) -> list[Path]:
    return sorted((APP_DIR / package).rglob("*.py"))


@pytest.mark.parametrize("package", sorted(ALLOWED))
def test_package_only_imports_allowed_layers(package):
    violations = []
    for path in package_files(package):
        for module in imported_app_modules(path):
            parts = module.split(".")
            target = parts[1] if len(parts) > 1 else "app"
            if target != package and target not in ALLOWED[package]:
                violations.append(
                    f"{path.relative_to(APP_DIR.parent)} imports {module}"
                )

    assert not violations, "Layering violations:\n" + "\n".join(violations)


def test_llm_providers_only_depend_on_types_and_errors():
    violations = []
    for path in package_files("llm/providers"):
        for module in imported_app_modules(path):
            if module.startswith("app.llm") and module not in LLM_PROVIDER_ALLOWED:
                violations.append(
                    f"{path.relative_to(APP_DIR.parent)} imports {module}"
                )

    assert not violations, "Provider dependency violations:\n" + "\n".join(violations)


def test_every_app_package_has_rules():
    packages = {
        p.name for p in APP_DIR.iterdir() if p.is_dir() and (p / "__init__.py").exists()
    }

    assert packages == set(ALLOWED), "Add new packages to ALLOWED in this test"
