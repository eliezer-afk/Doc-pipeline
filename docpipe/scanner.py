from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Directorios que nunca contienen pipelines
SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "env", "node_modules",
    ".pytest_cache", "dist", "build", ".eggs", ".mypy_cache", ".ruff_cache",
    "alembic", "migrations", ".obsidian", "htmlcov",
}

# Archivos Python que no son pipelines
SKIP_FILES = {
    "conftest.py", "setup.py", "manage.py", "__init__.py", "__main__.py",
}

# Prefijos/sufijos de archivos de test
TEST_PATTERNS = ("test_", "_test.py")

# Carpetas donde sí buscamos scripts Python genéricos
PYTHON_PIPELINE_DIRS = {
    "dags", "dag", "etl", "pipelines", "pipeline",
    "scripts", "jobs", "flows", "tasks", "ingestion",
    "indexing", "evaluation", "loaders", "extractors",
}

# Imports que indican que un .py es un pipeline de datos
DATA_IMPORTS = {
    "pandas", "polars", "sqlalchemy", "psycopg", "psycopg2",
    "bigquery", "airflow", "prefect", "pyspark", "dask",
    "boto3", "google.cloud", "storage", "pyarrow",
    "requests", "httpx", "aiohttp",
}


@dataclass
class ScanResult:
    pipelines: list[Path] = field(default_factory=list)   # archivos/carpetas a documentar
    skipped: list[tuple[Path, str]] = field(default_factory=list)  # (path, motivo)


def scan(root: Path) -> ScanResult:
    """Escanea un directorio y retorna los pipelines encontrados."""
    result = ScanResult()
    visited_dbt: set[Path] = set()

    for path in _walk(root):
        # Proyecto dbt — tratar la carpeta raíz como una sola unidad
        if path.is_dir() and (path / "dbt_project.yml").exists():
            if path not in visited_dbt:
                result.pipelines.append(path)
                visited_dbt.add(path)
            continue

        if path.suffix != ".py":
            continue

        if _is_skip_file(path):
            result.skipped.append((path, "archivo de soporte"))
            continue

        if _is_test_file(path):
            result.skipped.append((path, "archivo de test"))
            continue

        source = path.read_text(encoding="utf-8", errors="ignore")

        if _is_airflow(source) or _is_prefect(source):
            result.pipelines.append(path)
        elif _is_in_pipeline_dir(path, root) and _has_data_imports(source):
            result.pipelines.append(path)
        else:
            result.skipped.append((path, "no identificado como pipeline"))

    return result


def _walk(root: Path):
    """Recorre el árbol de directorios ignorando carpetas excluidas."""
    for item in sorted(root.iterdir()):
        if item.is_dir():
            if item.name in SKIP_DIRS or item.name.endswith(".egg-info"):
                continue
            # Expone la carpeta para detección de dbt, luego sus hijos
            yield item
            yield from _walk(item)
        else:
            yield item


def _is_skip_file(path: Path) -> bool:
    return path.name in SKIP_FILES


def _is_test_file(path: Path) -> bool:
    return path.name.startswith("test_") or path.name.endswith("_test.py")


def _is_airflow(source: str) -> bool:
    return (
        "from airflow" in source
        or "import airflow" in source
        or "DAG(" in source
    )


def _is_prefect(source: str) -> bool:
    return "from prefect" in source or "import prefect" in source or "@flow" in source


def _is_in_pipeline_dir(path: Path, root: Path) -> bool:
    """True si algún directorio padre (hasta root) está en PYTHON_PIPELINE_DIRS."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return any(part.lower() in PYTHON_PIPELINE_DIRS for part in relative.parts[:-1])


def _has_data_imports(source: str) -> bool:
    return any(imp in source for imp in DATA_IMPORTS)
