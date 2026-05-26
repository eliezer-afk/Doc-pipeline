from __future__ import annotations

import getpass
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class VaultConfig:
    path: str = ""
    pipelines_folder: str = "Pipelines"


@dataclass
class VertexConfig:
    project_id: str = ""
    region: str = "us-east5"
    model: str = "claude-sonnet-4-6"


@dataclass
class DefaultsConfig:
    owner: str = field(default_factory=getpass.getuser)
    tags: list[str] = field(default_factory=lambda: ["pipeline", "data"])
    language: str = "es"


@dataclass
class Config:
    vault: VaultConfig = field(default_factory=VaultConfig)
    vertex: VertexConfig = field(default_factory=VertexConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(cli_overrides: dict | None = None) -> Config:
    global_path = Path.home() / ".docpipe.yaml"
    local_path = Path.cwd() / ".docpipe.yaml"

    data = _deep_merge(_load_yaml(global_path), _load_yaml(local_path))
    if cli_overrides:
        data = _deep_merge(data, {k: v for k, v in cli_overrides.items() if v is not None})

    vault_data = data.get("vault", {})
    vertex_data = data.get("vertex", {})
    defaults_data = data.get("defaults", {})

    return Config(
        vault=VaultConfig(
            path=vault_data.get("path", ""),
            pipelines_folder=vault_data.get("pipelines_folder", "Pipelines"),
        ),
        vertex=VertexConfig(
            project_id=vertex_data.get("project_id", ""),
            region=vertex_data.get("region", "us-east5"),
            model=vertex_data.get("model", "claude-sonnet-4-6"),
        ),
        defaults=DefaultsConfig(
            owner=defaults_data.get("owner", getpass.getuser()),
            tags=defaults_data.get("tags", ["pipeline", "data"]),
            language=defaults_data.get("language", "es"),
        ),
    )


def save_config(data: dict, path: Path | None = None) -> None:
    target = path or (Path.home() / ".docpipe.yaml")
    existing = _load_yaml(target)
    merged = _deep_merge(existing, data)
    with open(target, "w", encoding="utf-8") as f:
        yaml.dump(merged, f, allow_unicode=True, default_flow_style=False)
