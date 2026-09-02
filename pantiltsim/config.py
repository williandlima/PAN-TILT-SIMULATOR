"""Configuração do modelo simulado (carregável de arquivo JSON).

Os parâmetros mecânicos de um pan-tilt variam conforme a redução, o
encoder e as opções com que a unidade foi encomendada — por isso os
drivers reais consultam a resolução do próprio equipamento com os
comandos ``PR``/``TR`` em vez de assumir um valor fixo. Aqui esses
parâmetros ficam em um arquivo de configuração, para que o simulador
possa ser ajustado à folha de dados da sua unidade sem alterar código.

Exemplo de arquivo::

    {
      "model_name": "PTU-D300E",
      "pan": {
        "full_step_arcsec": 185.1428,
        "default_step_mode": "eighth",
        "factory_min_deg": -159.0,
        "factory_max_deg": 159.0,
        "max_speed_deg_per_sec": 60.0
      },
      "tilt": {
        "factory_min_deg": -90.0,
        "factory_max_deg": 30.0,
        "max_speed_deg_per_sec": 40.0
      }
    }

Use ``--config meu_ptu.json`` na linha de comando. Campos omitidos
mantêm o valor default.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, fields
from pathlib import Path

from .device import AxisSpec, PanTiltDevice, StepMode

log = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "PTU-D300E"


def default_pan_spec() -> AxisSpec:
    return AxisSpec(
        name="pan",
        full_step_arcsec=185.1428,
        default_step_mode=StepMode.EIGHTH,
        factory_min_deg=-159.0,
        factory_max_deg=159.0,
        max_speed_deg_per_sec=60.0,
        default_speed_deg_per_sec=20.0,
        default_base_speed_deg_per_sec=5.0,
        default_accel_deg_per_sec2=60.0,
    )


def default_tilt_spec() -> AxisSpec:
    return AxisSpec(
        name="tilt",
        full_step_arcsec=185.1428,
        default_step_mode=StepMode.EIGHTH,
        factory_min_deg=-90.0,
        factory_max_deg=30.0,
        max_speed_deg_per_sec=40.0,
        default_speed_deg_per_sec=15.0,
        default_base_speed_deg_per_sec=4.0,
        default_accel_deg_per_sec2=50.0,
    )


def _axis_spec_from_dict(base: AxisSpec, data: dict) -> AxisSpec:
    valid = {f.name for f in fields(AxisSpec)}
    unknown = set(data) - valid
    if unknown:
        raise ValueError(f"Campos desconhecidos na configuração do eixo: {sorted(unknown)}")

    values = asdict(base)
    values.update(data)
    values["name"] = base.name
    if isinstance(values["default_step_mode"], str):
        values["default_step_mode"] = StepMode(values["default_step_mode"])
    return AxisSpec(**values)


def load_config(path: str | Path) -> dict:
    path = Path(path)
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: o arquivo de configuração deve conter um objeto JSON")
    return data


def build_device(config: dict | None = None, update_hz: float = 50.0) -> PanTiltDevice:
    """Cria o dispositivo simulado a partir de um dicionário de configuração."""
    config = config or {}
    pan_spec = _axis_spec_from_dict(default_pan_spec(), config.get("pan", {}))
    tilt_spec = _axis_spec_from_dict(default_tilt_spec(), config.get("tilt", {}))
    model_name = config.get("model_name", DEFAULT_MODEL_NAME)
    log.debug("Dispositivo %s: pan=%s tilt=%s", model_name, pan_spec, tilt_spec)
    return PanTiltDevice(
        pan_spec=pan_spec,
        tilt_spec=tilt_spec,
        update_hz=update_hz,
        model_name=model_name,
    )


def build_device_from_path(path: str | Path | None, update_hz: float = 50.0) -> PanTiltDevice:
    config = load_config(path) if path else {}
    return build_device(config, update_hz=update_hz)
