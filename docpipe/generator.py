from __future__ import annotations

import json
import re
from dataclasses import dataclass

from google import genai
from google.genai import types

from .config import Config
from .parsers.base import PipelineInfo

_PROMPT = """Sos un experto en ingeniería de datos. Tu única tarea es analizar el código de un pipeline y devolver un JSON con su documentación.

REGLAS ESTRICTAS:
- Respondé ÚNICAMENTE con el JSON. Sin texto antes, sin texto después, sin bloques markdown.
- Todos los campos son OBLIGATORIOS. Nunca dejes un campo vacío o como null.
- Si no tenés información suficiente para un campo, inferila del código o escribí "No especificado".
- El campo "mermaid_diagram" SIEMPRE debe tener un diagrama válido basado en el flujo real del pipeline.
- Los campos "sources" y "destination" SIEMPRE deben tener al menos un elemento.

TIPO DE PIPELINE: {type}

CÓDIGO FUENTE:
{source_code}

METADATOS EXTRAÍDOS:
{metadata}

FORMATO DE RESPUESTA (JSON puro, sin markdown):
{{
  "overview": "2 a 4 oraciones describiendo qué hace este pipeline, de dónde toma datos y qué produce",
  "sources": [
    {{"name": "nombre exacto de la fuente", "type": "BigQuery|Postgres|API|GCS|CSV|S3|otro", "description": "qué datos contiene esta fuente"}}
  ],
  "transformations": "Descripción detallada de cada transformación aplicada a los datos: limpieza, filtros, agregaciones, joins, cálculos, etc.",
  "destination": [
    {{"name": "nombre exacto del destino", "type": "BigQuery|Postgres|GCS|archivo|otro", "description": "qué datos escribe y en qué formato"}}
  ],
  "mermaid_diagram": "graph LR\\n  A[NombreFuente] --> B[Transformación]\\n  B --> C[NombreDestino]",
  "quality_checks": "Lista de validaciones, tests o checks de calidad definidos. Si no hay ninguno, escribí: Sin checks de calidad definidos.",
  "notes": "Observaciones técnicas relevantes: frecuencia de ejecución, dependencias externas, consideraciones de performance, etc."
}}"""

_RETRY_PROMPT = """Tu respuesta anterior no era JSON válido. Debés corregirla.

REGLAS:
- Respondé ÚNICAMENTE con el JSON. Sin texto antes ni después, sin bloques de código markdown.
- Todos los campos son obligatorios.

JSON inválido que generaste:
{bad_json}

Error de parsing: {error}

Corregí el JSON y respondé solo con el JSON válido:"""


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
