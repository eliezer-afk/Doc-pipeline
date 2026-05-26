from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, BaseLoader

from .config import Config
from .generator import GeneratedDoc
from .parsers.base import PipelineInfo

_TEMPLATE = """\
---
pipeline: {{ name }}
type: {{ type }}
owner: {{ owner }}
tags: {{ tags | tojson }}
created: {{ created }}
updated: {{ updated }}
status: active
source: {{ source }}
---

# {{ name }}

## Resumen
{{ doc.overview }}

## Arquitectura

```mermaid
{{ doc.mermaid_diagram }}
```

## Fuentes de Datos
| Fuente | Tipo | Descripción |
|--------|------|-------------|
{% for s in doc.sources -%}
| {{ s.name }} | {{ s.type }} | {{ s.description }} |
{% endfor %}
## Transformaciones
{{ doc.transformations }}

## Destino
| Destino | Tipo | Descripción |
|---------|------|-------------|
{% for d in doc.destination -%}
| {{ d.name }} | {{ d.type }} | {{ d.description }} |
{% endfor %}
## Schedule
{{ schedule }}

## Checks de Calidad
{{ doc.quality_checks }}
{% if related %}
## Pipelines Relacionados
{% for r in related -%}
- [[{{ r }}]]
{% endfor %}
{% endif %}
## Notas
{{ doc.notes if doc.notes else "_Sin notas adicionales._" }}
"""


def render(
    pipeline: PipelineInfo,
    doc: GeneratedDoc,
    config: Config,
    owner: str | None = None,
    folder: str | None = None,
) -> tuple[str, Path]:
    """Renderiza el markdown y retorna (contenido, ruta_destino)."""
    env = Environment(loader=BaseLoader())
    template = env.from_string(_TEMPLATE)

    today = date.today().isoformat()
    target_path = _resolve_path(pipeline.name, config, folder)

    # Preserva `created` si el archivo ya existe
    created = _read_existing_created(target_path) or today

    schedule = _extract_schedule(pipeline)
    related = _extract_related(pipeline)
    tags = list(config.defaults.tags) + [pipeline.type]

    content = template.render(
        name=pipeline.name,
        type=pipeline.type,
        owner=owner or config.defaults.owner,
        tags=tags,
        created=created,
        updated=today,
        source=pipeline.source_path,
        doc=doc,
        schedule=schedule,
        related=related,
    )
    return content, target_path


def write(content: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _resolve_path(name: str, config: Config, folder: str | None) -> Path:
    base = Path(config.vault.path) / config.vault.pipelines_folder
    if folder:
        base = base / folder
    safe_name = name.replace(" ", "_").replace("/", "-")
    return base / f"{safe_name}.md"


def _read_existing_created(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("created:"):
            return line.split(":", 1)[1].strip()
    return None


def _extract_schedule(pipeline: PipelineInfo) -> str:
    schedule = pipeline.metadata.get("schedule") or pipeline.metadata.get("schedule_interval")
    return str(schedule) if schedule else "Manual / Sin schedule definido"


def _extract_related(pipeline: PipelineInfo) -> list[str]:
    """Extrae nombres de pipelines relacionados de los metadatos."""
    related = []
    for task in pipeline.metadata.get("tasks", []):
        for upstream in task.get("upstream", []):
            if upstream not in related:
                related.append(upstream)
    return related
