from __future__ import annotations

from pathlib import Path


def detect_type(source: Path) -> str:
    """Detecta el tipo de pipeline a partir del path fuente."""
    if source.is_dir():
        if (source / "dbt_project.yml").exists():
            return "dbt"
        # Busca recursivamente archivos Python para clasificar la carpeta
        py_files = list(source.rglob("*.py"))
        if py_files:
            return _detect_from_python(py_files[0].read_text(encoding="utf-8", errors="ignore"))
        return "python"

    if source.suffix == ".py":
        return _detect_from_python(source.read_text(encoding="utf-8", errors="ignore"))

    if source.suffix in {".yml", ".yaml"}:
        return "dbt"

    return "python"


def _detect_from_python(source_code: str) -> str:
    if "from airflow" in source_code or "import airflow" in source_code or "DAG(" in source_code:
        return "airflow"
    if "from prefect" in source_code or "import prefect" in source_code or "@flow" in source_code:
        return "prefect"
    return "python"
