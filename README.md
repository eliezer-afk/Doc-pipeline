# docpipe

CLI que analiza pipelines de datos (dbt, Airflow, Prefect, Python) y genera documentación automática en español, guardándola directamente en tu vault de Obsidian usando Gemini via Vertex AI.

---

## Cómo funciona

El único argumento obligatorio es la **ruta al pipeline** — puede ser un archivo o una carpeta:

```powershell
# Un DAG de Airflow
python -m docpipe generate D:/repos/mi-proyecto/dags/mi_dag.py

# Una carpeta de dbt completa
python -m docpipe generate D:/repos/mi-proyecto/dbt/models/ventas/

# Un script Python
python -m docpipe generate D:/repos/mi-proyecto/scripts/etl_clientes.py
```

La herramienta **detecta el tipo automáticamente** — si ve `dbt_project.yml` es dbt, si ve `@task` o `DAG(` es Airflow, si no, lo trata como Python genérico.

El flujo interno es:

```
vos pasás una ruta
      ↓
detector.py → identifica el tipo (dbt / airflow / prefect / python)
      ↓
parser correspondiente → extrae tareas, fuentes, schedule, etc. del código con AST/YAML
      ↓
generator.py → arma un prompt con el código + metadatos y llama a Gemini en Vertex AI
      ↓
writer.py → renderiza el template Jinja2 y escribe el .md en el vault de Obsidian
```

Lo único que Vertex AI recibe es el **código fuente del pipeline** (máx. 12.000 caracteres) y los metadatos extraídos. No necesita acceso al repo ni a ninguna credencial de tu infraestructura — solo lee los archivos localmente.

---

## Parámetros disponibles

| Parámetro | Para qué sirve | Ejemplo |
|-----------|---------------|---------|
| `--folder` | Subcarpeta dentro de `Pipelines/` en el vault | `--folder "Clientes/Acme"` |
| `--dry-run` | Imprime el markdown sin escribir al vault | `--dry-run` |
| `--type` | Forzar el tipo si la detección automática falla | `--type airflow` |
| `--owner` | Sobreescribir el owner del frontmatter | `--owner "matias"` |
| `--open` | Abre el archivo en Obsidian al terminar | `--open` |
| `--vault` | Usar un vault distinto al de la config | `--vault "D:/otro/vault"` |

---

## Dónde guarda el archivo

Toma la ruta del vault de tu `.docpipe.yaml` y construye la ruta así:

```
{vault.path} / {vault.pipelines_folder} / {--folder} / {nombre_pipeline}.md
```

Ejemplo con una config típica:

```
D:/repos/data-oilers/pandora-refinery / Pipelines / enterprise-ai-platform / rag_indexing.md
```

Si el `.md` ya existe, **preserva la fecha `created`** y solo actualiza `updated` y el contenido.

---

## Instalación

**Requisitos:** Python 3.10+, gcloud CLI autenticado con ADC.

```bash
git clone https://github.com/eliezer-afk/Doc-pipeline.git
cd Doc-pipeline
pip install -e .
```

---

## Configuración

```bash
python -m docpipe config init
```

O creá `.docpipe.yaml` en tu home (`~/.docpipe.yaml`) o en el directorio del proyecto:

```yaml
vault:
  path: "D:/repos/mi-vault/Obsidian"
  pipelines_folder: "Pipelines"

vertex:
  project_id: "mi-proyecto-gcp"
  region: "us-central1"
  model: "gemini-2.5-pro"

defaults:
  owner: "mi-nombre"
  tags:
    - pipeline
    - data
  language: "es"
```

**Prioridad de configuración** (mayor a menor): flags del CLI → `.docpipe.yaml` local → `~/.docpipe.yaml` global.

> **Importante:** `.docpipe.yaml` está en `.gitignore`. Nunca subas este archivo al repo — contiene datos de tu proyecto GCP.

---

## Tipos de pipeline soportados

| Tipo | Detecta automáticamente | Extrae |
|------|------------------------|--------|
| **dbt** | `dbt_project.yml` en la carpeta | Models, sources, columnas, tests |
| **Airflow** | `from airflow` o `DAG(` o `@task` | DAG id, schedule, tasks (Operator y TaskFlow API) |
| **Prefect** | `@flow` o `from prefect` | Flows, tasks decoradas |
| **Python** | Cualquier `.py` sin framework | Funciones públicas, imports, clases, docstrings |

---

## Formato del archivo generado

Cada pipeline genera un `.md` con frontmatter YAML compatible con Obsidian:

```markdown
---
pipeline: rag_indexing
type: airflow
owner: Eliezer
tags: ["pipeline", "data", "airflow"]
created: 2026-05-26
updated: 2026-05-26
status: active
source: D:/repos/.../rag_indexing.py
---

# rag_indexing

## Resumen
## Arquitectura        ← diagrama Mermaid del flujo real
## Fuentes de Datos   ← tabla con nombre, tipo y descripción
## Transformaciones   ← paso a paso de lo que hace el pipeline
## Destino            ← tabla con nombre, tipo y descripción
## Schedule
## Checks de Calidad
## Pipelines Relacionados
## Notas
```

---

## Gestión de configuración

```bash
python -m docpipe config show                            # Ver config actual
python -m docpipe config set vault.path "D:/nuevo/path"
python -m docpipe config set vertex.project_id "otro-proyecto"
```

---

## Tests

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

---

## Stack

- [google-genai](https://googleapis.github.io/python-genai/) — Gemini via Vertex AI
- [Typer](https://typer.tiangolo.com/) — CLI
- [Jinja2](https://jinja.palletsprojects.com/) — Templates markdown
- [PyYAML](https://pyyaml.org/) — Parsing de dbt y configuración
- [Rich](https://rich.readthedocs.io/) — Output en terminal
