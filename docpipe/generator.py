from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import anthropic

from .config import Config
from .parsers.base import PipelineInfo

_SYSTEM_PROMPT = """Sos un experto en ingeniería de datos. Generás documentación técnica \
clara, concisa y en {language} para pipelines de datos.
Tu output es SIEMPRE JSON válido con exactamente los campos especificados. \
No agregues texto fuera del JSON."""

_USER_PROMPT = """Analizá el siguiente pipeline de tipo '{type}' y generá documentación.

## Código fuente:
{source_code}

## Metadatos extraídos:
{metadata}

## Output requerido — respondé SOLO con este JSON válido:
{{
  "overview": "Descripción clara del pipeline en 2-4 oraciones",
  "sources": [{{"name": "nombre_fuente", "type": "BigQuery|Postgres|API|CSV|otro", "description": "qué contiene"}}],
  "transformations": "Descripción de las transformaciones aplicadas",
  "destination": [{{"name": "nombre_destino", "type": "BigQuery|Postgres|archivo|otro", "description": "qué produce"}}],
  "mermaid_diagram": "graph LR\\n  A[Fuente] --> B[Transform] --> C[Destino]",
  "quality_checks": "Descripción de los checks de calidad y tests definidos",
  "notes": "Observaciones adicionales relevantes"
}}"""

_RETRY_PROMPT = """El JSON que generaste no es válido. Corregilo y respondé SOLO con el JSON, \
sin texto adicional ni bloques de código markdown.

JSON inválido recibido:
{bad_json}

Error: {error}"""


@dataclass
class GeneratedDoc:
    overview: str
    sources: list[dict]
    transformations: str
    destination: list[dict]
    mermaid_diagram: str
    quality_checks: str
    notes: str = ""


def generate(pipeline: PipelineInfo, config: Config) -> GeneratedDoc:
    client = anthropic.AnthropicVertex(
        project_id=config.vertex.project_id,
        region=config.vertex.region,
    )

    system = _SYSTEM_PROMPT.format(language=config.defaults.language)
    user = _USER_PROMPT.format(
        type=pipeline.type,
        source_code=pipeline.source_code[:12000],  # límite de contexto razonable
        metadata=json.dumps(pipeline.metadata, ensure_ascii=False, indent=2),
    )

    response = client.messages.create(
        model=config.vertex.model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    raw = response.content[0].text.strip()
    return _parse_response(raw, client, config, system)


def _parse_response(raw: str, client: anthropic.AnthropicVertex, config: Config, system: str) -> GeneratedDoc:
    # Intenta extraer JSON aunque venga envuelto en ```json ... ```
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    text = json_match.group(1) if json_match else raw

    try:
        data = json.loads(text)
        return _dict_to_doc(data)
    except json.JSONDecodeError as e:
        # Reintento con prompt de corrección
        retry_response = client.messages.create(
            model=config.vertex.model,
            max_tokens=2048,
            system=system,
            messages=[
                {"role": "user", "content": _RETRY_PROMPT.format(bad_json=text[:2000], error=str(e))},
            ],
        )
        retry_raw = retry_response.content[0].text.strip()
        data = json.loads(retry_raw)
        return _dict_to_doc(data)


def _dict_to_doc(data: dict) -> GeneratedDoc:
    return GeneratedDoc(
        overview=data.get("overview", ""),
        sources=data.get("sources", []),
        transformations=data.get("transformations", ""),
        destination=data.get("destination", []),
        mermaid_diagram=data.get("mermaid_diagram", "graph LR\n  A --> B"),
        quality_checks=data.get("quality_checks", ""),
        notes=data.get("notes", ""),
    )
