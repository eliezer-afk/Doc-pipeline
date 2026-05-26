from __future__ import annotations

import ast
from pathlib import Path

from .base import BaseParser, PipelineInfo


class PythonParser(BaseParser):
    def parse(self, source: Path) -> PipelineInfo:
        if source.is_dir():
            py_files = list(source.rglob("*.py"))
            source_code = "\n\n".join(
                f"--- {f.name} ---\n{f.read_text(encoding='utf-8', errors='ignore')}"
                for f in py_files[:10]
            )
            name = source.name
            combined_code = "\n".join(
                f.read_text(encoding="utf-8", errors="ignore") for f in py_files
            )
            metadata = self._analyze_code(combined_code)
        else:
            source_code = source.read_text(encoding="utf-8", errors="ignore")
            name = source.stem
            metadata = self._analyze_code(source_code)

        return PipelineInfo(
            name=name,
            type="python",
            source_path=str(source),
            source_code=source_code,
            metadata=metadata,
        )

    def _analyze_code(self, source_code: str) -> dict:
        metadata: dict = {
            "functions": [],
            "imports": [],
            "classes": [],
            "description": None,
        }

        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return metadata

        # Docstring del módulo
        if (
            tree.body
            and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
        ):
            metadata["description"] = tree.body[0].value.value

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    metadata["imports"].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [alias.name for alias in node.names]
                metadata["imports"].append(f"{module}.{', '.join(names)}")
            elif isinstance(node, ast.FunctionDef):
                if not node.name.startswith("_"):  # Solo funciones públicas
                    metadata["functions"].append({
                        "name": node.name,
                        "args": [a.arg for a in node.args.args],
                        "docstring": ast.get_docstring(node),
                    })
            elif isinstance(node, ast.ClassDef):
                metadata["classes"].append(node.name)

        # Deduplica imports
        metadata["imports"] = list(dict.fromkeys(metadata["imports"]))
        return metadata


class PrefectParser(PythonParser):
    """Parser para flows de Prefect — extiende PythonParser agregando metadatos de flow/task."""

    def parse(self, source: Path) -> PipelineInfo:
        info = super().parse(source)
        info.type = "prefect"

        source_code = info.source_code
        try:
            tree = ast.parse(
                source.read_text(encoding="utf-8", errors="ignore")
                if source.is_file()
                else source_code
            )
        except SyntaxError:
            return info

        flow_name = None
        schedule = None
        tasks = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                decorators = [self._get_decorator_name(d) for d in node.decorator_list]
                if "flow" in decorators:
                    flow_name = node.name
                elif "task" in decorators:
                    tasks.append({"name": node.name, "upstream": []})

        info.name = flow_name or info.name
        info.metadata.update({
            "flow_name": flow_name or info.name,
            "schedule": schedule,
            "tasks": tasks,
            "description": info.metadata.get("description"),
        })
        return info

    def _get_decorator_name(self, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return node.func.id
        return ""
