from __future__ import annotations

import json
import re
from dataclasses import dataclass

from google import genai
from google.genai import types

from .config import Config
from .parsers.base import PipelineInfo

_PROMPT = """Sos un experto en ingeniería de datos. Generás documentación técnica clara y concisa en español para pipelines de datos.
Tu output es SIEMPRE JSON válido con exactamente los campos especificados. No agregues texto fuera del JSON.

Analizá el siguiente pipeline de tipo '{type}' y generá documentación.

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

_RETRY_PROMPT = """El JSON que generaste no es válido. Corregilo y respondé SOLO con el JSON, sin texto adicional ni bloques de código markdown.

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
    client = genai.Client(
        vertexai=True,
        project=config.vertex.project_id,
        location=config.vertex.region,
    )

    gen_config = types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=2048,
    )

    prompt = _PROMPT.format(
        type=pipeline.type,
        source_code=pipeline.source_code[:12000],
        metadata=json.dumps(pipeline.metadata, ensure_ascii=False, indent=2),
    )

    response = client.models.generate_content(
        model=config.vertex.model,
        contents=prompt,
        config=gen_config,
    )
    raw = response.text.strip()

    return _parse_response(raw, client, config, gen_config)


def _parse_response(
    raw: str,
    client: genai.Client,
    config: Config,
    gen_config: types.GenerateContentConfig,
) -> GeneratedDoc:
    text = _extract_json(raw)
    try:
        return _dict_to_doc(json.loads(text))
    except json.JSONDecodeError as e:
        retry_prompt = _RETRY_PROMPT.format(bad_json=text[:2000], error=str(e))
        retry_response = client.models.generate_content(
            model=config.vertex.model,
            contents=retry_prompt,
            config=gen_config,
        )
        retry_text = _extract_json(retry_response.text.strip() if retry_response.text else "")
        try:
            return _dict_to_doc(json.loads(retry_text))
        except json.JSONDecodeError:
            return _dict_to_doc({})


def _extract_json(raw: str) -> str:
    """Extrae JSON de una respuesta que puede venir con markdown u otro texto."""
    # 1. Bloque ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        return match.group(1)

    # 2. Busca el primer { y el último } del texto
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start:end + 1]

    return raw


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
