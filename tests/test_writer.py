from pathlib import Path
import tempfile

from docpipe.config import Config, VaultConfig, VertexConfig, DefaultsConfig
from docpipe.generator import GeneratedDoc
from docpipe.parsers.base import PipelineInfo
from docpipe import writer


def _make_config(vault_path: str) -> Config:
    return Config(
        vault=VaultConfig(path=vault_path, pipelines_folder="Pipelines"),
        vertex=VertexConfig(project_id="test", region="us-east5"),
        defaults=DefaultsConfig(owner="test-user", tags=["pipeline"], language="es"),
    )


def _make_pipeline() -> PipelineInfo:
    return PipelineInfo(
        name="test_pipeline",
        type="python",
        source_path="/path/to/script.py",
        source_code="print('hello')",
        metadata={"functions": [], "imports": [], "classes": [], "description": None},
    )


def _make_doc() -> GeneratedDoc:
    return GeneratedDoc(
        overview="Pipeline de prueba.",
        sources=[{"name": "fuente", "type": "Postgres", "description": "Datos crudos"}],
        transformations="Limpieza de datos.",
        destination=[{"name": "destino", "type": "BigQuery", "description": "Tabla final"}],
        mermaid_diagram="graph LR\n  A --> B",
        quality_checks="Sin checks definidos.",
        notes="Notas de prueba.",
    )


class TestWriter:
    def test_render_returns_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config(tmpdir)
            content, path = writer.render(_make_pipeline(), _make_doc(), config)
            assert "# test_pipeline" in content
            assert "## Resumen" in content
            assert "## Arquitectura" in content
            assert "mermaid" in content

    def test_render_path_correct(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config(tmpdir)
            _, path = writer.render(_make_pipeline(), _make_doc(), config)
            assert path.name == "test_pipeline.md"
            assert "Pipelines" in str(path)

    def test_render_with_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config(tmpdir)
            _, path = writer.render(_make_pipeline(), _make_doc(), config, folder="Clientes/Acme")
            assert "Clientes" in str(path)
            assert "Acme" in str(path)

    def test_write_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config(tmpdir)
            content, path = writer.render(_make_pipeline(), _make_doc(), config)
            writer.write(content, path)
            assert path.exists()
            assert "test_pipeline" in path.read_text(encoding="utf-8")

    def test_write_preserves_created_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config(tmpdir)
            content, path = writer.render(_make_pipeline(), _make_doc(), config)
            writer.write(content, path)

            # Segunda escritura — created no debe cambiar
            content2, path2 = writer.render(_make_pipeline(), _make_doc(), config)
            assert path == path2
            # Extrae created de ambos
            created1 = next(l for l in content.splitlines() if l.startswith("created:"))
            created2 = next(l for l in content2.splitlines() if l.startswith("created:"))
            assert created1 == created2
