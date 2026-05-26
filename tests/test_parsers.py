from pathlib import Path

import pytest

from docpipe.parsers import DbtParser, AirflowParser, PythonParser
from docpipe.detector import detect_type

FIXTURES = Path(__file__).parent / "fixtures"


class TestDbtParser:
    def test_parse_returns_pipeline_info(self):
        parser = DbtParser()
        info = parser.parse(FIXTURES / "dbt")
        assert info.type == "dbt"
        assert info.name == "ventas_pipeline"
        assert len(info.metadata["models"]) == 2
        assert len(info.metadata["sources"]) > 0

    def test_model_has_columns(self):
        parser = DbtParser()
        info = parser.parse(FIXTURES / "dbt")
        stg_orders = next(m for m in info.metadata["models"] if m["name"] == "stg_orders")
        assert len(stg_orders["columns"]) > 0

    def test_source_code_not_empty(self):
        parser = DbtParser()
        info = parser.parse(FIXTURES / "dbt")
        assert len(info.source_code) > 0


class TestAirflowParser:
    def test_parse_dag_id(self):
        parser = AirflowParser()
        info = parser.parse(FIXTURES / "airflow" / "example_dag.py")
        assert info.type == "airflow"
        assert info.metadata["dag_id"] == "ventas_diarias_ingesta"

    def test_parse_schedule(self):
        parser = AirflowParser()
        info = parser.parse(FIXTURES / "airflow" / "example_dag.py")
        assert info.metadata["schedule_interval"] == "0 6 * * *"

    def test_parse_tasks(self):
        parser = AirflowParser()
        info = parser.parse(FIXTURES / "airflow" / "example_dag.py")
        task_ids = [t["task_id"] for t in info.metadata["tasks"]]
        assert "extract_sales" in task_ids
        assert "transform_data" in task_ids
        assert "load_to_bq" in task_ids

    def test_parse_description(self):
        parser = AirflowParser()
        info = parser.parse(FIXTURES / "airflow" / "example_dag.py")
        assert "ventas" in info.metadata.get("description", "").lower()


class TestPythonParser:
    def test_parse_functions(self):
        parser = PythonParser()
        info = parser.parse(FIXTURES / "python" / "etl_clientes.py")
        assert info.type == "python"
        func_names = [f["name"] for f in info.metadata["functions"]]
        assert "extract_customers" in func_names
        assert "transform_customers" in func_names
        assert "load_to_bigquery" in func_names

    def test_parse_imports(self):
        parser = PythonParser()
        info = parser.parse(FIXTURES / "python" / "etl_clientes.py")
        assert any("pandas" in i for i in info.metadata["imports"])

    def test_parse_module_docstring(self):
        parser = PythonParser()
        info = parser.parse(FIXTURES / "python" / "etl_clientes.py")
        assert info.metadata["description"] is not None


class TestDetector:
    def test_detect_dbt(self):
        assert detect_type(FIXTURES / "dbt") == "dbt"

    def test_detect_airflow(self):
        assert detect_type(FIXTURES / "airflow" / "example_dag.py") == "airflow"

    def test_detect_python(self):
        assert detect_type(FIXTURES / "python" / "etl_clientes.py") == "python"
