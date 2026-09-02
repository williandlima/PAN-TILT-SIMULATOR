"""Núcleo de simulação do PTU-D300E: máquina de estados dos eixos pan/tilt.

Este módulo não conhece nada sobre serial ou sobre o protocolo ASCII —
ele apenas modela o comportamento mecânico/elétrico do pan-tilt (posição,
velocidade, aceleração, limites de curso, limites de velocidade e modo de
controle), em unidades de "posições" (contagens de encoder), que é a
unidade nativa usada pelo protocolo DPCL do fabricante.

Os valores de resolução/curso/velocidade default abaixo são parâmetros
configuráveis (ver `AxisConfig`) porque o acesso automatizado às folhas de
dados oficiais da FLIR (PTU-D300E) foi bloqueado pela política de rede
desta sessão ao tentar validar os números exatos. Ajuste-os conforme o
Command Reference Manual / datasheet do seu PTU-D300E real, se precisar de
fidelidade numérica exata. A estrutura do protocolo (comandos, respostas)
foi validada contra o driver ROS de código aberto para as unidades FLIR
E-Series (ver docs/PROTOCOL.md).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum


class ControlMode(Enum):
    POSITION = "position"  # comando "CI" - modo posição (independente)
    VELOCITY = "velocity"  # comando "CV" - modo velocidade contínua


@dataclass
class AxisConfig:
    """Parâmetros mecânicos/elétricos de um eixo (pan ou tilt)."""

    name: str
    counts_per_degree: float = 100.0
    min_position_deg: float = -159.0
    max_position_deg: float = 159.0
    max_speed_counts: int = 6000       # limite físico absoluto (PU/TU)
    min_speed_counts: int = 0          # limite físico absoluto (PL/TL)
    default_speed_counts: int = 1500
    default_base_speed_counts: int = 500
    default_accel_counts: int = 3000

    def deg_to_counts(self, deg: float) -> int:
        return round(deg * self.counts_per_degree)

    def counts_to_deg(self, counts: int) -> float:
        return counts / self.counts_per_degree


class Axis:
    """Estado dinâmico de um único eixo (pan ou tilt)."""

    def __init__(self, config: AxisConfig):
        self.config = config
        self.position = 0                      # contagens, posição atual
        self.target_position = 0               # contagens, alvo (modo posição)
        self.current_speed = 0.0               # contagens/s, velocidade instantânea (sempre >=0)
        self.desired_speed = config.default_speed_counts       # PS/TS
        self.base_speed = config.default_base_speed_counts     # PB/TB
        self.acceleration = config.default_accel_counts        # PA/TA
        self.upper_speed_limit = config.max_speed_counts       # PU/TU
        self.lower_speed_limit = config.min_speed_counts       # PL/TL
        self.min_limit = config.deg_to_counts(config.min_position_deg)  # PN/TN
        self.max_limit = config.deg_to_counts(config.max_position_deg)  # PX/TX
        self.limits_enabled = True
        self.halted = False
        self._velocity_sign = 0  # usado em modo CV (continuous velocity)

    # ---- Comandos de posição ---------------------------------------
    def set_target_position(self, counts: int) -> None:
        counts = self._clamp_to_limits(counts)
        self.target_position = counts
        self.halted = False

    def offset_target_position(self, delta_counts: int) -> None:
        self.set_target_position(self.target_position + delta_counts)

    def halt(self) -> None:
        self.halted = True
        self.target_position = self.position
        self.current_speed = 0.0
        self._velocity_sign = 0

    def is_in_motion(self) -> bool:
        return self.position != self.target_position and not self.halted

    # ---- Limites -----------------------------------------------------
    def _clamp_to_limits(self, counts: int) -> int:
        if not self.limits_enabled:
            return counts
        return max(self.min_limit, min(self.max_limit, counts))

    def set_min_limit(self, counts: int) -> None:
        self.min_limit = counts

    def set_max_limit(self, counts: int) -> None:
        self.max_limit = counts

    # ---- Integração de movimento -------------------------------------
    def update(self, dt: float, mode: ControlMode) -> None:
        if self.halted:
            return

        if mode == ControlMode.VELOCITY:
            self._update_velocity_mode(dt)
        else:
            self._update_position_mode(dt)

    def _update_velocity_mode(self, dt: float) -> None:
        # Em modo velocidade, o eixo se move continuamente no sentido de
        # desired_speed (sinal) até ser parado (H) ou trocar de modo.
        target_speed = abs(self.desired_speed)
        target_speed = max(self.lower_speed_limit, min(self.upper_speed_limit, target_speed))
        self._velocity_sign = 1 if self.desired_speed > 0 else (-1 if self.desired_speed < 0 else 0)

        self.current_speed = self._ramp(self.current_speed, target_speed, dt)

        step = self._velocity_sign * self.current_speed * dt
        new_position = self.position + step
        if self.limits_enabled:
            if new_position <= self.min_limit:
                new_position = self.min_limit
                self.current_speed = 0.0
            elif new_position >= self.max_limit:
                new_position = self.max_limit
                self.current_speed = 0.0
        self.position = round(new_position)
        self.target_position = self.position

    def _update_position_mode(self, dt: float) -> None:
        distance = self.target_position - self.position
        if distance == 0:
            self.current_speed = 0.0
            return

        direction = 1 if distance > 0 else -1
        remaining = abs(distance)

        desired = max(abs(self.desired_speed), self.base_speed)
        desired = max(self.lower_speed_limit, min(self.upper_speed_limit, desired))

        # distância necessária para desacelerar de current_speed até 0
        stopping_distance = (self.current_speed ** 2) / (2 * max(self.acceleration, 1))

        if remaining <= stopping_distance:
            target_speed = 0.0
        else:
            target_speed = desired

        self.current_speed = self._ramp(self.current_speed, target_speed, dt)
        # nunca abaixo da base_speed enquanto ainda houver deslocamento,
        # exceto na fase final de frenagem (já tratada acima via target_speed=0)
        step = direction * self.current_speed * dt

        if abs(step) >= remaining:
            self.position = self.target_position
            self.current_speed = 0.0
        else:
            new_position = self.position + step
            new_position = self._clamp_to_limits_float(new_position)
            self.position = round(new_position)

    def _clamp_to_limits_float(self, value: float) -> float:
        if not self.limits_enabled:
            return value
        return max(self.min_limit, min(self.max_limit, value))

    def _ramp(self, current: float, target: float, dt: float) -> float:
        max_delta = self.acceleration * dt
        if current < target:
            return min(current + max_delta, target)
        if current > target:
            return max(current - max_delta, target)
        return current


class PanTiltDevice:
    """Modelo completo do PTU-D300E: eixos pan + tilt e estado global."""

    def __init__(
        self,
        pan_config: AxisConfig | None = None,
        tilt_config: AxisConfig | None = None,
        update_hz: float = 50.0,
    ):
        self.pan = Axis(pan_config or AxisConfig(name="pan"))
        self.tilt = Axis(tilt_config or AxisConfig(name="tilt"))
        self.control_mode = ControlMode.POSITION
        self.echo_enabled = True
        self.verbose_feedback = False
        self.slaved_execution = False  # False = Immediate (I), True = Slaved (S)

        self.firmware_version = "PTU-D300E Simulator v0.1.0 (DPCL compatible protocol)"

        self._update_hz = update_hz
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._running = False

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="ptu-motion", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _run_loop(self) -> None:
        dt = 1.0 / self._update_hz
        while self._running:
            t0 = time.monotonic()
            self.tick(dt)
            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, dt - elapsed))

    def tick(self, dt: float) -> None:
        with self._lock:
            self.pan.update(dt, self.control_mode)
            self.tilt.update(dt, self.control_mode)

    # ------------------------------------------------------------------
    def reset(self) -> None:
        with self._lock:
            for axis in (self.pan, self.tilt):
                axis.position = 0
                axis.target_position = 0
                axis.current_speed = 0.0
                axis.halted = False
                axis.desired_speed = axis.config.default_speed_counts
                axis.base_speed = axis.config.default_base_speed_counts
                axis.acceleration = axis.config.default_accel_counts
                axis.upper_speed_limit = axis.config.max_speed_counts
                axis.lower_speed_limit = axis.config.min_speed_counts
                axis.limits_enabled = True
            self.control_mode = ControlMode.POSITION
            self.echo_enabled = True
            self.verbose_feedback = False
            self.slaved_execution = False

    def halt_all(self) -> None:
        with self._lock:
            self.pan.halt()
            self.tilt.halt()

    def is_in_motion(self) -> bool:
        with self._lock:
            return self.pan.is_in_motion() or self.tilt.is_in_motion()

    def snapshot(self) -> dict:
        """Retorna um dicionário leve com o estado atual, para a GUI."""
        with self._lock:
            return {
                "pan_deg": self.pan.config.counts_to_deg(self.pan.position),
                "tilt_deg": self.tilt.config.counts_to_deg(self.tilt.position),
                "pan_counts": self.pan.position,
                "tilt_counts": self.tilt.position,
                "pan_target_deg": self.pan.config.counts_to_deg(self.pan.target_position),
                "tilt_target_deg": self.tilt.config.counts_to_deg(self.tilt.target_position),
                "pan_speed": self.pan.current_speed,
                "tilt_speed": self.tilt.current_speed,
                "in_motion": self.is_in_motion(),
                "control_mode": self.control_mode.value,
            }
