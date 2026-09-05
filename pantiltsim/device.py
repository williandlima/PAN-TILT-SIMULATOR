"""Núcleo de simulação do PTU-D300E: máquina de estados dos eixos pan/tilt.

Este módulo não conhece nada sobre serial nem sobre o protocolo ASCII —
ele modela o comportamento mecânico/elétrico do pan-tilt:

    - posição em *contagens* (a unidade nativa do protocolo do
      fabricante), com resolução expressa em segundos de arco por
      contagem (é exatamente isso que o comando ``PR``/``TR`` do
      fabricante devolve, e é assim que os drivers reais convertem
      graus <-> contagens);
    - velocidade, aceleração e velocidade base, com perfil trapezoidal;
    - limites de curso de fábrica e limites de usuário (``PN``/``PX`` e
      ``PNU``/``PXU``), com os três modos de limite do protocolo
      (``LE`` fábrica, ``LU`` usuário, ``LD`` desabilitado);
    - modo de controle posição/velocidade (``CI``/``CV``);
    - modo de execução imediato/slaved (``I``/``S``), em que os comandos
      de posição ficam pendentes até um ``A`` (await), fazendo pan e
      tilt partirem juntos;
    - modo monitor / auto-scan (``ME``/``MD``);
    - modos de micropasso e de potência (registrados e reportados; o
      micropasso altera de fato a resolução, como no hardware real).

Os valores default de resolução, curso e velocidade estão em
`AxisSpec` e são configuráveis (ver `pantiltsim/config.py`), porque
variam conforme a opção de redução/encoder com que a unidade foi
encomendada. Ajuste-os conforme a etiqueta/datasheet do seu PTU-D300E.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger(__name__)

ARCSEC_PER_DEGREE = 3600.0


class ControlMode(Enum):
    """Modo de controle de movimento (comandos ``CI`` / ``CV``)."""

    POSITION = "position"
    VELOCITY = "velocity"


class LimitMode(Enum):
    """Modo de limites de curso (comandos ``LE`` / ``LU`` / ``LD``)."""

    FACTORY = "factory"
    USER = "user"
    DISABLED = "disabled"


class StepMode(Enum):
    """Modo de micropasso. Altera a resolução efetiva do eixo."""

    FULL = "full"
    HALF = "half"
    QUARTER = "quarter"
    EIGHTH = "eighth"
    AUTO = "auto"

    @property
    def divisor(self) -> int:
        return {
            StepMode.FULL: 1,
            StepMode.HALF: 2,
            StepMode.QUARTER: 4,
            StepMode.EIGHTH: 8,
            StepMode.AUTO: 8,
        }[self]


class PowerMode(Enum):
    """Modo de potência de parada (hold) ou de movimento (move)."""

    OFF = "off"
    LOW = "low"
    REGULATED = "regulated"
    HIGH = "high"


@dataclass
class AxisSpec:
    """Especificação de hardware de um eixo (imutável durante a operação).

    Os ângulos e velocidades são declarados em graus (grandeza física
    invariante); as contagens são derivadas da resolução vigente, que
    depende do modo de micropasso — igual ao hardware real.
    """

    name: str
    full_step_arcsec: float = 185.1428
    default_step_mode: StepMode = StepMode.EIGHTH
    factory_min_deg: float = -159.0
    factory_max_deg: float = 159.0
    max_speed_deg_per_sec: float = 60.0
    min_speed_deg_per_sec: float = 0.0
    default_speed_deg_per_sec: float = 20.0
    default_base_speed_deg_per_sec: float = 5.0
    default_accel_deg_per_sec2: float = 60.0


class Axis:
    """Estado dinâmico de um eixo (pan ou tilt)."""

    def __init__(self, spec: AxisSpec):
        self.spec = spec
        self.step_mode = spec.default_step_mode
        self.hold_power = PowerMode.LOW
        self.move_power = PowerMode.REGULATED

        self.position = 0
        self.target_position = 0
        self.current_speed = 0.0
        self._velocity_sign = 0
        self.halted = False

        self.limit_mode = LimitMode.FACTORY
        self._user_min: int | None = None
        self._user_max: int | None = None

        self._apply_defaults()

    # -- resolução -----------------------------------------------------
    @property
    def arcsec_per_count(self) -> float:
        """Resolução vigente, em segundos de arco por contagem (comando ``PR``/``TR``)."""
        return self.spec.full_step_arcsec / self.step_mode.divisor

    @property
    def counts_per_degree(self) -> float:
        return ARCSEC_PER_DEGREE / self.arcsec_per_count

    def deg_to_counts(self, deg: float) -> int:
        return round(deg * self.counts_per_degree)

    def counts_to_deg(self, counts: float) -> float:
        return counts / self.counts_per_degree

    def set_step_mode(self, mode: StepMode) -> None:
        """Troca o micropasso preservando os ângulos físicos já ajustados."""
        if mode == self.step_mode:
            return
        old_ratio = self.counts_per_degree
        self.step_mode = mode
        scale = self.counts_per_degree / old_ratio

        self.position = round(self.position * scale)
        self.target_position = round(self.target_position * scale)
        self.desired_speed = round(self.desired_speed * scale)
        self.base_speed = round(self.base_speed * scale)
        self.acceleration = round(self.acceleration * scale)
        self.upper_speed_limit = round(self.upper_speed_limit * scale)
        self.lower_speed_limit = round(self.lower_speed_limit * scale)
        if self._user_min is not None:
            self._user_min = round(self._user_min * scale)
        if self._user_max is not None:
            self._user_max = round(self._user_max * scale)
        log.debug("%s: step mode -> %s (%.4f arcsec/count)", self.spec.name, mode.value, self.arcsec_per_count)

    # -- limites -------------------------------------------------------
    @property
    def factory_min(self) -> int:
        return self.deg_to_counts(self.spec.factory_min_deg)

    @property
    def factory_max(self) -> int:
        return self.deg_to_counts(self.spec.factory_max_deg)

    @property
    def user_min(self) -> int:
        return self._user_min if self._user_min is not None else self.factory_min

    @property
    def user_max(self) -> int:
        return self._user_max if self._user_max is not None else self.factory_max

    def set_user_min(self, counts: int) -> None:
        self._user_min = counts

    def set_user_max(self, counts: int) -> None:
        self._user_max = counts

    @property
    def effective_min(self) -> int:
        if self.limit_mode == LimitMode.USER:
            return self.user_min
        return self.factory_min

    @property
    def effective_max(self) -> int:
        if self.limit_mode == LimitMode.USER:
            return self.user_max
        return self.factory_max

    def clamp(self, counts: int) -> int:
        if self.limit_mode == LimitMode.DISABLED:
            return counts
        return max(self.effective_min, min(self.effective_max, counts))

    # -- comandos de movimento ------------------------------------------
    def set_target_position(self, counts: int) -> None:
        self.target_position = self.clamp(counts)
        self.halted = False

    def offset_target_position(self, delta_counts: int) -> None:
        self.set_target_position(self.target_position + delta_counts)

    def set_desired_speed(self, counts_per_sec: int) -> None:
        self.desired_speed = counts_per_sec
        self.halted = False

    def offset_desired_speed(self, delta: int) -> None:
        self.set_desired_speed(self.desired_speed + delta)

    def halt(self) -> None:
        self.halted = True
        self.target_position = self.position
        self.current_speed = 0.0
        self._velocity_sign = 0

    def is_in_motion(self) -> bool:
        if self.halted:
            return False
        return self.position != self.target_position or self.current_speed != 0.0

    def reset(self) -> None:
        """Equivalente ao comando ``RP``/``RT``: recalibra o eixo na origem."""
        self.position = 0
        self.target_position = 0
        self.current_speed = 0.0
        self._velocity_sign = 0
        self.halted = False
        self.limit_mode = LimitMode.FACTORY
        self._user_min = None
        self._user_max = None
        self.step_mode = self.spec.default_step_mode
        self.hold_power = PowerMode.LOW
        self.move_power = PowerMode.REGULATED
        self._apply_defaults()

    def _apply_defaults(self) -> None:
        self.desired_speed = self.deg_to_counts(self.spec.default_speed_deg_per_sec)
        self.base_speed = self.deg_to_counts(self.spec.default_base_speed_deg_per_sec)
        self.acceleration = self.deg_to_counts(self.spec.default_accel_deg_per_sec2)
        self.upper_speed_limit = self.deg_to_counts(self.spec.max_speed_deg_per_sec)
        self.lower_speed_limit = self.deg_to_counts(self.spec.min_speed_deg_per_sec)

    # -- integração de movimento -----------------------------------------
    def update(self, dt: float, mode: ControlMode) -> None:
        if self.halted:
            return
        if mode == ControlMode.VELOCITY:
            self._update_velocity_mode(dt)
        else:
            self._update_position_mode(dt)

    def _effective_speed_cap(self) -> float:
        cap = max(abs(self.desired_speed), self.base_speed)
        return max(self.lower_speed_limit, min(self.upper_speed_limit, cap))

    def _update_velocity_mode(self, dt: float) -> None:
        target_speed = self._effective_speed_cap()
        self._velocity_sign = 1 if self.desired_speed > 0 else (-1 if self.desired_speed < 0 else 0)
        if self._velocity_sign == 0:
            target_speed = 0.0

        self.current_speed = self._ramp(self.current_speed, target_speed, dt)
        new_position = self.position + self._velocity_sign * self.current_speed * dt

        if self.limit_mode != LimitMode.DISABLED:
            if new_position <= self.effective_min:
                new_position = self.effective_min
                self.current_speed = 0.0
            elif new_position >= self.effective_max:
                new_position = self.effective_max
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
        cap = self._effective_speed_cap()

        stopping_distance = (self.current_speed ** 2) / (2 * max(self.acceleration, 1))
        target_speed = 0.0 if remaining <= stopping_distance else cap

        self.current_speed = self._ramp(self.current_speed, target_speed, dt)
        step = direction * self.current_speed * dt

        if abs(step) >= remaining:
            self.position = self.target_position
            self.current_speed = 0.0
        else:
            self.position = round(self.position + step)

    def _ramp(self, current: float, target: float, dt: float) -> float:
        max_delta = max(self.acceleration, 1) * dt
        if current < target:
            return min(current + max_delta, target)
        if current > target:
            return max(current - max_delta, target)
        return current


@dataclass
class MonitorState:
    """Estado do modo monitor / auto-scan (comandos ``ME`` / ``MD``)."""

    enabled: bool = False
    pan_direction: int = 1
    tilt_direction: int = 1
    margin_deg: float = 5.0


class PanTiltDevice:
    """Modelo completo do PTU-D300E: eixos pan + tilt e estado global."""

    def __init__(
        self,
        pan_spec: AxisSpec | None = None,
        tilt_spec: AxisSpec | None = None,
        update_hz: float = 50.0,
        model_name: str = "PTU-D300E",
    ):
        self.pan = Axis(pan_spec or AxisSpec(name="pan"))
        self.tilt = Axis(
            tilt_spec
            or AxisSpec(
                name="tilt",
                factory_min_deg=-90.0,
                factory_max_deg=30.0,
                max_speed_deg_per_sec=40.0,
            )
        )
        self.model_name = model_name
        self.control_mode = ControlMode.POSITION
        self.echo_enabled = True
        self.verbose_feedback = True
        self.slaved_execution = False
        self.monitor = MonitorState()
        self.host_baudrate = 9600

        self.firmware_version = f"{model_name} Simulator v0.2.0 - DPCL compatible"

        self.lock = threading.RLock()
        self._pending_targets: dict[str, int] = {}
        self._update_hz = update_hz
        self._thread: threading.Thread | None = None
        self._running = False

        # Import tardio para evitar dependência circular (tracking.py usa
        # apenas o dispositivo pelo lado de fora, não o contrário).
        from .tracking import GeoTracker, GpmPose, Landmark

        self.gpm_pose = GpmPose()
        self.gpm_landmarks: list[Landmark] = []
        self.geo_tracker = GeoTracker(self)

    # ------------------------------------------------------------------
    @property
    def axes(self) -> tuple[Axis, Axis]:
        return (self.pan, self.tilt)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="ptu-motion", daemon=True)
        self._thread.start()
        log.info("Motor de simulação iniciado (%.0f Hz)", self._update_hz)

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
            time.sleep(max(0.0, dt - (time.monotonic() - t0)))

    def tick(self, dt: float) -> None:
        with self.lock:
            if self.monitor.enabled:
                self._tick_monitor()
            for axis in self.axes:
                axis.update(dt, self.control_mode)

    def _tick_monitor(self) -> None:
        """Auto-scan: varre pan e tilt entre os limites, invertendo nas pontas."""
        for axis, attr in ((self.pan, "pan_direction"), (self.tilt, "tilt_direction")):
            margin = axis.deg_to_counts(self.monitor.margin_deg)
            low = axis.factory_min + margin
            high = axis.factory_max - margin
            if high <= low:
                continue
            direction = getattr(self.monitor, attr)
            if axis.position >= high:
                direction = -1
            elif axis.position <= low:
                direction = 1
            setattr(self.monitor, attr, direction)
            axis.target_position = high if direction > 0 else low
            axis.halted = False

    # ------------------------------------------------------------------
    def reset(self, pan: bool = True, tilt: bool = True) -> None:
        """Comandos ``RE`` (ambos), ``RP`` (pan) e ``RT`` (tilt)."""
        with self.lock:
            if pan:
                self.pan.reset()
            if tilt:
                self.tilt.reset()
            if pan and tilt:
                self.control_mode = ControlMode.POSITION
                self.echo_enabled = True
                self.verbose_feedback = True
                self.slaved_execution = False
                self.monitor = MonitorState()
                self._pending_targets.clear()
                self.geo_tracker.reset()

    def halt_all(self) -> None:
        with self.lock:
            self.monitor.enabled = False
            self._pending_targets.clear()
            for axis in self.axes:
                axis.halt()

    def set_limit_mode(self, mode: LimitMode) -> None:
        with self.lock:
            for axis in self.axes:
                axis.limit_mode = mode

    @property
    def limit_mode(self) -> LimitMode:
        return self.pan.limit_mode

    def is_in_motion(self) -> bool:
        with self.lock:
            return any(axis.is_in_motion() for axis in self.axes)

    # -- execução slaved (comandos ``I`` / ``S`` / ``A``) -----------------
    def request_target(self, axis_name: str, counts: int) -> None:
        """Aplica agora (modo imediato) ou enfileira até o próximo ``A`` (slaved)."""
        with self.lock:
            if self.slaved_execution:
                self._pending_targets[axis_name] = counts
            else:
                self._axis_by_name(axis_name).set_target_position(counts)

    def apply_pending_targets(self) -> None:
        with self.lock:
            for axis_name, counts in self._pending_targets.items():
                self._axis_by_name(axis_name).set_target_position(counts)
            self._pending_targets.clear()

    def has_pending_targets(self) -> bool:
        with self.lock:
            return bool(self._pending_targets)

    def _axis_by_name(self, axis_name: str) -> Axis:
        return self.pan if axis_name == "pan" else self.tilt

    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        """Estado atual em um dicionário leve, para a GUI e para logs."""
        with self.lock:
            return {
                "model": self.model_name,
                "pan_deg": self.pan.counts_to_deg(self.pan.position),
                "tilt_deg": self.tilt.counts_to_deg(self.tilt.position),
                "pan_counts": self.pan.position,
                "tilt_counts": self.tilt.position,
                "pan_target_deg": self.pan.counts_to_deg(self.pan.target_position),
                "tilt_target_deg": self.tilt.counts_to_deg(self.tilt.target_position),
                "pan_speed_deg": self.pan.counts_to_deg(self.pan.current_speed),
                "tilt_speed_deg": self.tilt.counts_to_deg(self.tilt.current_speed),
                "pan_speed_counts": self.pan.current_speed,
                "tilt_speed_counts": self.tilt.current_speed,
                "pan_resolution_arcsec": self.pan.arcsec_per_count,
                "tilt_resolution_arcsec": self.tilt.arcsec_per_count,
                "pan_range_deg": (
                    self.pan.counts_to_deg(self.pan.effective_min),
                    self.pan.counts_to_deg(self.pan.effective_max),
                ),
                "tilt_range_deg": (
                    self.tilt.counts_to_deg(self.tilt.effective_min),
                    self.tilt.counts_to_deg(self.tilt.effective_max),
                ),
                "in_motion": any(axis.is_in_motion() for axis in self.axes),
                "control_mode": self.control_mode.value,
                "limit_mode": self.limit_mode.value,
                "step_mode": self.pan.step_mode.value,
                "hold_power": self.pan.hold_power.value,
                "move_power": self.pan.move_power.value,
                "monitor": self.monitor.enabled,
                "slaved": self.slaved_execution,
                "echo": self.echo_enabled,
                "verbose": self.verbose_feedback,
                "gpm_latitude_deg": self.gpm_pose.latitude_deg,
                "gpm_longitude_deg": self.gpm_pose.longitude_deg,
                "gpm_altitude_m": self.gpm_pose.altitude_m,
                "gpm_roll_deg": self.gpm_pose.roll_deg,
                "gpm_pitch_deg": self.gpm_pose.pitch_deg,
                "gpm_yaw_deg": self.gpm_pose.yaw_deg,
                "gpm_camera_pitch_offset_deg": self.gpm_pose.camera_pitch_offset_deg,
                "gpm_landmark_count": len(self.gpm_landmarks),
                "geo_tracking": self.geo_tracker.state.target is not None,
                "geo_target": self.geo_tracker.state.target,
                "geo_predicted_target": self.geo_tracker.state.predicted_target,
                "geo_velocity": self.geo_tracker.state.velocity,
                "geo_lead_seconds": self.geo_tracker.lead_seconds,
                "geo_look": self.geo_tracker.state.last_look,
            }
