from __future__ import annotations

from pathlib import Path

import yaml

from .base import BaseParser, PipelineInfo


class DbtParser(BaseParser):
    def parse(self, source: Path) -> PipelineInfo:
        root = source if source.is_dir() else source.parent

        project_name = self._get_project_name(root)
        models = self._get_models(root)
        sources = self._get_sources(root)
        schedule = self._get_schedule(root)
        source_code = self._collect_source_code(root)

        return PipelineInfo(
            name=project_name,
            type="dbt",
            source_path=str(source),
            source_code=source_code,
            metadata={
                "project_name": project_name,
                "models": models,
                "sources": sources,
                "schedule": schedule,
            },
        )

    def _get_project_name(self, root: Path) -> str:
        project_file = root / "dbt_project.yml"
        if project_file.exists():
            data = yaml.safe_load(project_file.read_text(encoding="utf-8")) or {}
            return data.get("name", root.name)
        return root.name

    def _get_models(self, root: Path) -> list[dict]:
        models = []
        for schema_file in root.rglob("schema.yml"):
            data = yaml.safe_load(schema_file.read_text(encoding="utf-8")) or {}
            for model in data.get("models", []):
                models.append({
                    "name": model.get("name", ""),
                    "description": model.get("description", ""),
                    "columns": [
                        {"name": c.get("name", ""), "description": c.get("description", "")}
                        for c in model.get("columns", [])
                    ],
                    "tests": [
                        t if isinstance(t, str) else list(t.keys())[0]
                        for col in model.get("columns", [])
                        for t in col.get("tests", [])
                    ],
                })
        return models

    def _get_sources(self, root: Path) -> list[dict]:
        sources = []
        for schema_file in root.rglob("sources.yml"):
            data = yaml.safe_load(schema_file.read_text(encoding="utf-8")) or {}
            for src in data.get("sources", []):
                sources.append({
                    "name": src.get("name", ""),
                    "schema": src.get("schema", src.get("database", "")),
                    "tables": [t.get("name", "") for t in src.get("tables", [])],
                })
        # También busca sources en schema.yml
        for schema_file in root.rglob("schema.yml"):
            data = yaml.safe_load(schema_file.read_text(encoding="utf-8")) or {}
            for src in data.get("sources", []):
                sources.append({
                    "name": src.get("name", ""),
                    "schema": src.get("schema", src.get("database", "")),
                    "tables": [t.get("name", "") for t in src.get("tables", [])],
                })
        return sources

    def _get_schedule(self, root: Path) -> str | None:
        project_file = root / "dbt_project.yml"
        if project_file.exists():
            data = yaml.safe_load(project_file.read_text(encoding="utf-8")) or {}
            return data.get("schedule", None)
        return None

    def _collect_source_code(self, root: Path) -> str:
        parts = []
        for yml_file in sorted(root.rglob("*.yml")):
            parts.append(f"--- {yml_file.relative_to(root)} ---\n{yml_file.read_text(encoding='utf-8', errors='ignore')}")
        for sql_file in sorted(root.rglob("*.sql"))[:20]:  # límite para no superar el contexto
            parts.append(f"--- {sql_file.relative_to(root)} ---\n{sql_file.read_text(encoding='utf-8', errors='ignore')}")
        return "\n\n".join(parts)
