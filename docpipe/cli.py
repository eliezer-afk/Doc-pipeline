from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.syntax import Syntax

from . import __version__
from .config import load_config, save_config
from .detector import detect_type
from .generator import generate as run_generate
from .parsers import DbtParser, AirflowParser, PythonParser
from .parsers.python_parser import PrefectParser
from . import writer
from .scanner import scan

app = typer.Typer(
    name="docpipe",
    help="Generador de documentación de pipelines para Obsidian",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Gestión de configuración")
app.add_typer(config_app, name="config")

console = Console()


@app.command(name="generate")
def generate_cmd(
    source: Path = typer.Argument(..., help="Archivo o carpeta del pipeline"),
    vault: Optional[str] = typer.Option(None, "--vault", help="Ruta raíz del vault Obsidian"),
    folder: Optional[str] = typer.Option(None, "--folder", help="Subcarpeta dentro del vault (ej: Clientes/Acme)"),
    pipeline_type: Optional[str] = typer.Option(None, "--type", help="Forzar tipo: dbt, airflow, prefect, python"),
    owner: Optional[str] = typer.Option(None, "--owner", help="Owner del pipeline"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Imprime el markdown sin escribir al vault"),
    open_file: bool = typer.Option(False, "--open", help="Abre el archivo en Obsidian al terminar"),
) -> None:
    """Genera documentación de un pipeline y la guarda en Obsidian."""
    if not source.exists():
        console.print(f"[red]Error:[/red] No existe el path '{source}'")
        raise typer.Exit(1)

    cli_overrides: dict = {}
    if vault:
        cli_overrides["vault"] = {"path": vault}

    config = load_config(cli_overrides)

    if not dry_run and not config.vault.path:
        console.print("[red]Error:[/red] No hay vault configurado. Usá --vault o ejecutá: docpipe config init")
        raise typer.Exit(1)

    if not config.vertex.project_id:
        console.print("[red]Error:[/red] No hay GCP project_id configurado. Ejecutá: docpipe config init")
        raise typer.Exit(1)

    detected_type = pipeline_type or detect_type(source)
    console.print(f"[dim]Tipo detectado:[/dim] {detected_type}")

    parser = _get_parser(detected_type)
    console.print("[dim]Parseando pipeline...[/dim]")
    pipeline_info = parser.parse(source)

    console.print("[dim]Generando documentación con Claude...[/dim]")
    doc = run_generate(pipeline_info, config)

    content, target_path = writer.render(pipeline_info, doc, config, owner=owner, folder=folder)

    if dry_run:
        console.print(Syntax(content, "markdown", theme="monokai"))
        return

    writer.write(content, target_path)
    console.print(f"[green]Documentación generada:[/green] {target_path}")

    if open_file:
        _open_in_obsidian(target_path)


@config_app.command("init")
def config_init() -> None:
    """Crea la configuración global ~/.docpipe.yaml de forma interactiva."""
    console.print("[bold]Configuración de docpipe[/bold]\n")

    vault_path = typer.prompt("Ruta del vault Obsidian", default="")
    pipelines_folder = typer.prompt("Carpeta de pipelines dentro del vault", default="Pipelines")
    project_id = typer.prompt("GCP Project ID (Vertex AI)")
    region = typer.prompt("Región de Vertex AI", default="us-east5")
    model = typer.prompt("Modelo Claude", default="claude-sonnet-4-6")
    owner = typer.prompt("Tu nombre (owner por defecto)", default="")

    data = {
        "vault": {"path": vault_path, "pipelines_folder": pipelines_folder},
        "vertex": {"project_id": project_id, "region": region, "model": model},
        "defaults": {"owner": owner, "tags": ["pipeline", "data"], "language": "es"},
    }
    save_config(data)
    console.print("\n[green]Configuración guardada en ~/.docpipe.yaml[/green]")


@config_app.command("show")
def config_show() -> None:
    """Muestra la configuración actual."""
    config = load_config()
    data = {
        "vault": {"path": config.vault.path, "pipelines_folder": config.vault.pipelines_folder},
        "vertex": {
            "project_id": config.vertex.project_id,
            "region": config.vertex.region,
            "model": config.vertex.model,
        },
        "defaults": {
            "owner": config.defaults.owner,
            "tags": config.defaults.tags,
            "language": config.defaults.language,
        },
    }
    console.print(Syntax(yaml.dump(data, allow_unicode=True), "yaml", theme="monokai"))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Clave en formato seccion.campo (ej: vertex.project_id)"),
    value: str = typer.Argument(..., help="Valor a asignar"),
) -> None:
    """Setea un valor de configuración."""
    parts = key.split(".")
    if len(parts) != 2:
        console.print("[red]Error:[/red] La clave debe ser 'seccion.campo' (ej: vertex.project_id)")
        raise typer.Exit(1)

    section, field = parts
    save_config({section: {field: value}})
    console.print(f"[green]Actualizado:[/green] {key} = {value}")


@app.command(name="scan")
def scan_cmd(
    root: Path = typer.Argument(..., help="Carpeta raíz del repositorio a escanear"),
    folder: Optional[str] = typer.Option(None, "--folder", help="Subcarpeta dentro del vault (ej: Clientes/Acme)"),
    owner: Optional[str] = typer.Option(None, "--owner", help="Owner de los pipelines"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Detecta pipelines sin generar documentación"),
) -> None:
    """Escanea un repositorio completo y documenta todos los pipelines encontrados."""
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

    if not root.exists() or not root.is_dir():
        console.print(f"[red]Error:[/red] '{root}' no es una carpeta válida")
        raise typer.Exit(1)

    config = load_config()

    if not dry_run and not config.vault.path:
        console.print("[red]Error:[/red] No hay vault configurado. Usá --vault o ejecutá: docpipe config init")
        raise typer.Exit(1)

    console.print(f"[dim]Escaneando[/dim] {root} ...")
    result = scan(root)

    if not result.pipelines:
        console.print("[yellow]No se encontraron pipelines en el repositorio.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[green]Encontrados:[/green] {len(result.pipelines)} pipelines  "
                  f"[dim]({len(result.skipped)} archivos omitidos)[/dim]\n")

    if dry_run:
        table = Table(title="Pipelines detectados", show_lines=True)
        table.add_column("Archivo", style="cyan")
        table.add_column("Tipo", style="yellow")
        for p in result.pipelines:
            table.add_row(str(p.relative_to(root)), detect_type(p))
        console.print(table)
        return

    ok, failed = [], []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Documentando...", total=len(result.pipelines))

        for source in result.pipelines:
            rel = source.relative_to(root)
            progress.update(task, description=f"[dim]{rel}[/dim]")
            try:
                detected_type = detect_type(source)
                parser = _get_parser(detected_type)
                pipeline_info = parser.parse(source)
                doc = run_generate(pipeline_info, config)
                content, target_path = writer.render(
                    pipeline_info, doc, config, owner=owner, folder=folder
                )
                writer.write(content, target_path)
                ok.append((rel, target_path))
            except Exception as exc:
                failed.append((rel, str(exc)))
            finally:
                progress.advance(task)

    # Resumen final
    console.print()
    if ok:
        table = Table(title=f"[green]{len(ok)} documentados[/green]", show_lines=False)
        table.add_column("Pipeline", style="cyan")
        table.add_column("Archivo generado", style="dim")
        for rel, target in ok:
            table.add_row(str(rel), str(target.name))
        console.print(table)

    if failed:
        console.print()
        err_table = Table(title=f"[red]{len(failed)} errores[/red]", show_lines=False)
        err_table.add_column("Pipeline", style="cyan")
        err_table.add_column("Error", style="red")
        for rel, err in failed:
            err_table.add_row(str(rel), err[:80])
        console.print(err_table)


@app.command()
def version() -> None:
    """Muestra la versión de docpipe."""
    console.print(f"docpipe {__version__}")


def _get_parser(pipeline_type: str):
    return {
        "dbt": DbtParser(),
        "airflow": AirflowParser(),
        "prefect": PrefectParser(),
        "python": PythonParser(),
    }.get(pipeline_type, PythonParser())


def _open_in_obsidian(path: Path) -> None:
    uri = f"obsidian://open?path={path.as_posix()}"
    if sys.platform == "win32":
        subprocess.run(["start", uri], shell=True, check=False)
    elif sys.platform == "darwin":
        subprocess.run(["open", uri], check=False)
    else:
        subprocess.run(["xdg-open", uri], check=False)
