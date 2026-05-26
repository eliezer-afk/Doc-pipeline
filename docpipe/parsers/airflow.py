from __future__ import annotations

import ast
from pathlib import Path

from .base import BaseParser, PipelineInfo


class AirflowParser(BaseParser):
    def parse(self, source: Path) -> PipelineInfo:
        if source.is_dir():
            py_files = list(source.rglob("*.py"))
            source_code = "\n\n".join(
                f"--- {f.name} ---\n{f.read_text(encoding='utf-8', errors='ignore')}"
                for f in py_files[:10]
            )
            # Usa el primer archivo con DAG
            dag_file = next(
                (f for f in py_files if "DAG(" in f.read_text(encoding="utf-8", errors="ignore")),
                py_files[0] if py_files else source,
            )
        else:
            dag_file = source
            source_code = source.read_text(encoding="utf-8", errors="ignore")

        metadata = self._parse_dag(dag_file)

        return PipelineInfo(
            name=metadata.get("dag_id", source.stem),
            type="airflow",
            source_path=str(source),
            source_code=source_code,
            metadata=metadata,
        )

    def _parse_dag(self, path: Path) -> dict:
        source_code = path.read_text(encoding="utf-8", errors="ignore")
        metadata: dict = {
            "dag_id": path.stem,
            "schedule_interval": None,
            "tasks": [],
            "description": None,
            "start_date": None,
        }

        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return metadata

        # Extrae docstring del módulo
        if (
            tree.body
            and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
        ):
            metadata["description"] = tree.body[0].value.value

        # Busca DAG(...) y extrae argumentos
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = self._get_call_name(node)
                if func_name in {"DAG", "dag"}:
                    metadata.update(self._extract_dag_args(node))

        # Extrae tasks: asignaciones con operadores de Airflow
        metadata["tasks"] = self._extract_tasks(tree)
        return metadata

    def _get_call_name(self, node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

    def _extract_dag_args(self, node: ast.Call) -> dict:
        result = {}
        for kw in node.keywords:
            if kw.arg == "dag_id" and isinstance(kw.value, ast.Constant):
                result["dag_id"] = kw.value.value
            elif kw.arg == "schedule_interval" and isinstance(kw.value, ast.Constant):
                result["schedule_interval"] = kw.value.value
            elif kw.arg == "schedule" and isinstance(kw.value, ast.Constant):
                result["schedule_interval"] = kw.value.value
            elif kw.arg == "description" and isinstance(kw.value, ast.Constant):
                result["description"] = kw.value.value
        if node.args and isinstance(node.args[0], ast.Constant):
            result.setdefault("dag_id", node.args[0].value)
        return result

    def _extract_tasks(self, tree: ast.Module) -> list[dict]:
        tasks = []
        airflow_operators = {
            "PythonOperator", "BashOperator", "DummyOperator", "EmptyOperator",
            "BigQueryOperator", "BigQueryInsertJobOperator", "HttpOperator",
            "EmailOperator", "BranchPythonOperator", "ShortCircuitOperator",
            "SparkSubmitOperator", "KubernetesPodOperator",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                operator = self._get_call_name(node.value)
                if any(op in operator for op in airflow_operators) or "Operator" in operator or "Sensor" in operator:
                    task_id = self._get_kwarg_str(node.value, "task_id") or (
                        node.targets[0].id if isinstance(node.targets[0], ast.Name) else "unknown"
                    )
                    tasks.append({
                        "task_id": task_id,
                        "operator": operator,
                        "upstream": [],
                    })
        # Detecta dependencias via >> operator
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.BinOp):
                self._extract_dependencies(node.value, tasks)
        return tasks

    def _extract_dependencies(self, node: ast.BinOp, tasks: list[dict]) -> None:
        if not isinstance(node.op, ast.RShift):
            return
        left = self._node_to_name(node.left)
        right = self._node_to_name(node.right)
        if left and right:
            for task in tasks:
                if task["task_id"] == right:
                    task["upstream"].append(left)

    def _node_to_name(self, node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        return None

    def _get_kwarg_str(self, call: ast.Call, key: str) -> str | None:
        for kw in call.keywords:
            if kw.arg == key and isinstance(kw.value, ast.Constant):
                return str(kw.value.value)
        return None
