"""Geo Pointing Module (GPM) — Capítulo 17 do manual real da FLIR.

Todo o conteúdo deste módulo corresponde a comandos **confirmados byte a
byte** contra fotos das páginas do "E Series Pan-Tilt Command Reference
Manual, Version 6.00 (09/2014)" (páginas 99, 111 e 113):

1. ``GpmPose`` — a pose própria da unidade (onde ela está instalada:
   latitude, longitude, altitude, roll, pitch, yaw, offset de pitch da
   câmera). Comandos ``GL``/``GO``/``GA``/``GLLA`` (seção 17.3, posição) e
   ``GR``/``GP``/``GY``/``GRPY``/``GCP`` (seção 17.4, orientação).

2. ``Landmark`` — pontos de referência de posição conhecida, usados na
   calibração da unidade. Comandos ``GM``/``GMA``/``GMN``/``GMD``/``GMC``
   (seção 17.5).

3. ``GeoTracker``/``look_angles`` — aponta o PTU para uma coordenada
   geográfica **agora**, calculando azimute/elevação a partir da pose
   própria (``GpmPose``) até o alvo. Corresponde ao comando real
   ``GG<lat>,<lon>,<alt>`` (ou ``GG<índice>`` para apontar para um
   landmark salvo) — seção 17.5. É uma ação imediata (como ``PP``/``TP``),
   não um modo "ligar/desligar rastreamento": cada chamada aponta de
   novo. Rastrear um alvo em movimento é, portanto, chamar isso
   repetidamente com a posição mais recente — exatamente o que uma
   estação de solo real faz ao receber atualizações de GPS por
   telemetria (o mesmo princípio de uma estação terrena de satélite).
   ``GGD`` consulta a distância (m) até o aim point atual ou até um
   ponto informado.

4. **Predição por velocidade (rate-aided tracking)** — extensão própria
   deste simulador, **não é um comando DPCL** (o comando real ``GG`` não
   tem parâmetro de antecipação). Em sistemas reais de rastreamento de
   telemetria, decodificar o quadro de GPS recebido, calcular
   azimute/elevação e mover o pedestal levam tempo, então a antena
   sempre corre atrás da posição real do veículo. A técnica padrão
   (usada por qualquer Antenna Control Unit — ACU — de campo de provas)
   é estimar a velocidade do alvo a partir de duas posições consecutivas
   e apontar um pouco **à frente** de onde ele estava por último, não
   exatamente onde ele estava. É o mesmo princípio de um preditor α-β.
   ``GeoTracker`` faz isso quando ``lead_seconds > 0``: cada
   ``set_target`` estima a velocidade (lat/lon/alt por segundo, por
   diferença finita entre a chamada atual e a anterior) e aponta para a
   posição extrapolada ``lead_seconds`` à frente — sem nunca perder a
   posição realmente recebida, que continua disponível em
   ``state.target``. Ver ``GeoTracker.lead_seconds``.

Ver ``pantiltsim/protocol.py`` (comandos ``G...``) e ``docs/PROTOCOL.md``
para o detalhamento completo, inclusive o que do capítulo 17 **ainda não**
foi confirmado (``GC`` calibrar, ``GS`` status, ``GDR`` restaurar, ``GT``
tipo de ponto).

``LinearTrajectory`` é só uma ferramenta de demonstração deste simulador
(não é comando do fabricante): gera uma "posição de GPS" simulada de um
veículo com rumo/velocidade constantes, para exercitar ``GeoTracker`` sem
hardware GPS real.

A matemática de apontamento é geodésico -> ECEF -> ENU no elipsoide
WGS84 — o método padrão de rastreamento de antena (o mesmo do Gpredict e
de estações terrenas de satélite), não uma aproximação de Terra plana:

    1. Latitude/longitude/altitude (de cada ponto) viram coordenadas
       cartesianas ECEF (Earth-Centered, Earth-Fixed) usando o raio de
       curvatura do elipsoide na latitude local.
    2. O vetor entre as duas posições ECEF é projetado no plano tangente
       local (ENU) do observador, usando a matriz de rotação padrão para
       aquela latitude/longitude.
    3. Azimute = atan2(Leste, Norte); Elevação = atan2(Cima, distância
       horizontal).

A altitude usada é a altura elipsoidal (a que um receptor GPS entrega
antes de qualquer correção de geoide) — sistemas reais às vezes aplicam
uma correção de ondulação do geoide (EGM96/2008) para obter altitude
sobre o nível médio do mar; isso não está implementado aqui, é uma
simplificação documentada.

**Isto não é orientação de armas.** O cálculo só resolve "para onde
apontar" a partir de duas posições geográficas — a mesma matemática vale
para qualquer veículo com GPS (avião, drone, balão sonda, foguete de
sondagem). Não rastreia, identifica nem interage com o veículo de forma
alguma: apenas converte coordenadas recebidas de uma fonte externa (um
receptor GPS de verdade, ou aqui, para demonstração, o gerador de
trajetória ``LinearTrajectory``) num ângulo de apontamento de antena — a
mesma função que uma antena parabólica de estação terrena exerce ao
seguir um satélite.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

# WGS84 — o mesmo datum que o GPS usa nativamente.
WGS84_SEMI_MAJOR_AXIS_M = 6378137.0
WGS84_FLATTENING = 1 / 298.257223563
_WGS84_ECCENTRICITY_SQUARED = 2 * WGS84_FLATTENING - WGS84_FLATTENING ** 2

_METERS_PER_DEGREE_LAT = 111_320.0  # aproximação, suficiente p/ trajetórias de demonstração


@dataclass
class GpmPose:
    """Pose própria da unidade no Geo Pointing Module (calibração de instalação).

    Campos e comandos confirmados byte a byte contra o Capítulo 17 (Geo
    Pointing Module) do "E Series Pan-Tilt Command Reference Manual,
    Version 6.00 (09/2014)" da FLIR:

    - ``GL``/``GO``/``GA``/``GLLA`` (seção 17.3) -> ``latitude_deg``,
      ``longitude_deg``, ``altitude_m``.
    - ``GR``/``GP``/``GY``/``GRPY`` (seção 17.4) -> ``roll_deg``,
      ``pitch_deg``, ``yaw_deg``.
    - ``GCP`` (seção 17.4) -> ``camera_pitch_offset_deg`` (diferença entre
      a linha de mira do payload/câmera e a linha de mira do PTU).

    Ver ``pantiltsim/protocol.py`` para o dispatch dos comandos.
    """

    latitude_deg: float = 0.0
    longitude_deg: float = 0.0
    altitude_m: float = 0.0
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0
    camera_pitch_offset_deg: float = 0.0


@dataclass
class Landmark:
    """Ponto de referência salvo para calibração do GPM (comandos GM...).

    ``pan_position``/``tilt_position`` são as contagens de pan/tilt no
    momento em que o landmark foi salvo (``GMA``) — a calibração real
    consiste em apontar fisicamente o PTU para o ponto de referência
    conhecido e então salvá-lo, então este simulador captura a posição
    atual dos eixos nesse momento. O manual também lista um campo
    ``<error>`` (erro de mira) na consulta ``GM``, mas não detalha como é
    calculado — este simulador não o modela e sempre reporta 0.0.
    """

    name: str
    lat_deg: float
    lon_deg: float
    alt_m: float
    pan_position: int = 0
    tilt_position: int = 0


@dataclass(frozen=True)
class GeoPoint:
    """Posição geodésica WGS84 — a mesma que um receptor GPS entrega."""

    lat_deg: float
    lon_deg: float
    alt_m: float = 0.0


@dataclass(frozen=True)
class LookAngles:
    """Ângulos de apontamento resultantes, prontos para comandar PP/TP."""

    azimuth_deg: float    # 0-360°, 0 = norte, sentido horário
    elevation_deg: float  # -90° a +90°, 0 = horizonte, + = acima
    range_m: float         # distância em linha reta até o alvo


@dataclass(frozen=True)
class GeoVelocity:
    """Velocidade estimada do alvo, por diferença finita entre duas posições.

    Linear em graus/segundo (lat/lon) e metros/segundo (altitude) — uma
    simplificação de curto prazo (mesmo espírito de ``LinearTrajectory``),
    válida para o intervalo de poucos segundos típico entre atualizações
    de telemetria, não para extrapolações longas.
    """

    lat_deg_per_s: float
    lon_deg_per_s: float
    alt_m_per_s: float


def _estimate_velocity(
    previous: GeoPoint, previous_t: float, current: GeoPoint, current_t: float
) -> GeoVelocity | None:
    dt = current_t - previous_t
    if dt <= 0:
        return None
    return GeoVelocity(
        lat_deg_per_s=(current.lat_deg - previous.lat_deg) / dt,
        lon_deg_per_s=(current.lon_deg - previous.lon_deg) / dt,
        alt_m_per_s=(current.alt_m - previous.alt_m) / dt,
    )


def _predict_point(point: GeoPoint, velocity: GeoVelocity, lead_s: float) -> GeoPoint:
    """Extrapola ``point`` ``lead_s`` segundos à frente, à velocidade estimada."""
    return GeoPoint(
        lat_deg=point.lat_deg + velocity.lat_deg_per_s * lead_s,
        lon_deg=point.lon_deg + velocity.lon_deg_per_s * lead_s,
        alt_m=point.alt_m + velocity.alt_m_per_s * lead_s,
    )


def _geodetic_to_ecef(point: GeoPoint) -> tuple[float, float, float]:
    lat = math.radians(point.lat_deg)
    lon = math.radians(point.lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)

    radius_of_curvature = WGS84_SEMI_MAJOR_AXIS_M / math.sqrt(
        1 - _WGS84_ECCENTRICITY_SQUARED * sin_lat * sin_lat
    )

    x = (radius_of_curvature + point.alt_m) * cos_lat * math.cos(lon)
    y = (radius_of_curvature + point.alt_m) * cos_lat * math.sin(lon)
    z = (radius_of_curvature * (1 - _WGS84_ECCENTRICITY_SQUARED) + point.alt_m) * sin_lat
    return x, y, z


def _normalize_signed_degrees(deg: float) -> float:
    """Traz um ângulo para (-180, 180], o caminho mais curto até o alvo."""
    value = deg % 360.0
    if value > 180.0:
        value -= 360.0
    return value


def look_angles(observer: GeoPoint, target: GeoPoint) -> LookAngles:
    """Azimute/elevação/distância do alvo, vistos a partir do observador.

    É o cálculo padrão de rastreamento de antena: converte as duas
    posições geodésicas para ECEF, projeta o vetor entre elas no plano
    tangente local (ENU) do observador, e extrai os ângulos.
    """
    ox, oy, oz = _geodetic_to_ecef(observer)
    tx, ty, tz = _geodetic_to_ecef(target)
    dx, dy, dz = tx - ox, ty - oy, tz - oz

    lat = math.radians(observer.lat_deg)
    lon = math.radians(observer.lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)

    east = -sin_lon * dx + cos_lon * dy
    north = -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz
    up = cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz

    horizontal = math.hypot(east, north)
    azimuth = math.degrees(math.atan2(east, north)) % 360.0
    elevation = math.degrees(math.atan2(up, horizontal))
    distance = math.sqrt(east * east + north * north + up * up)

    return LookAngles(azimuth_deg=azimuth, elevation_deg=elevation, range_m=distance)


@dataclass
class LinearTrajectory:
    """Gerador de trajetória simulada em linha reta e velocidade constante.

    Só para demonstração: representa um veículo com rumo e velocidade
    constantes (ex.: uma aeronave sobrevoando em linha reta), como se o
    simulador estivesse recebendo posições de GPS em tempo real desse
    veículo. Não é parte do protocolo do fabricante — é a ferramenta de
    teste deste simulador para gerar a "posição de GPS" que, com hardware
    real, viria de um receptor GPS de verdade a bordo do veículo
    rastreado, transmitida por telemetria até a estação de solo.
    """

    start: GeoPoint
    heading_deg: float
    speed_mps: float
    climb_mps: float = 0.0

    def position_at(self, t_seconds: float) -> GeoPoint:
        heading = math.radians(self.heading_deg)
        distance = self.speed_mps * t_seconds
        north_m = distance * math.cos(heading)
        east_m = distance * math.sin(heading)

        lat_rad = math.radians(self.start.lat_deg)
        meters_per_deg_lon = _METERS_PER_DEGREE_LAT * math.cos(lat_rad)
        if abs(meters_per_deg_lon) < 1e-9:
            meters_per_deg_lon = 1e-9

        return GeoPoint(
            lat_deg=self.start.lat_deg + north_m / _METERS_PER_DEGREE_LAT,
            lon_deg=self.start.lon_deg + east_m / meters_per_deg_lon,
            alt_m=self.start.alt_m + self.climb_mps * t_seconds,
        )


@dataclass
class GeoTrackerState:
    target: GeoPoint | None = None
    """Última posição realmente recebida (verdade de telemetria)."""
    predicted_target: GeoPoint | None = None
    """Posição para onde o PTU foi de fato comandado (alvo + antecipação)."""
    velocity: GeoVelocity | None = None
    """Velocidade estimada do alvo; ``None`` até haver 2 posições."""
    last_look: LookAngles | None = None


class GeoTracker:
    """Aponta o PTU para uma coordenada geográfica agora — comando real ``GG``.

    Usa a posição própria já calibrada em ``device.gpm_pose`` (comandos
    reais ``GL``/``GO``/``GA``/``GLLA``) como estação de solo. Cada
    chamada a ``set_target`` é uma **ação imediata** (como ``PP``/``TP``):
    recalcula azimute/elevação e comanda a posição alvo de pan/tilt na
    hora — não existe um "modo de rastreamento" para ligar/desligar,
    igual ao comando real ``GG<lat>,<lon>,<alt>``. O movimento físico até
    lá usa o mesmo motor de simulação (perfil de aceleração, limites de
    velocidade) de qualquer outro comando de posição.

    Rastrear um veículo em movimento é, portanto, chamar ``set_target``
    repetidamente com a posição mais recente recebida por telemetria —
    exatamente o que uma estação de solo real faz.

    Com ``lead_seconds > 0``, cada chamada estima a velocidade do alvo
    (diferença finita entre a posição atual e a anterior) e aponta
    ``lead_seconds`` à frente — a técnica de predição/antecipação
    (rate-aided tracking) usada por antenas de rastreamento reais para
    compensar o atraso de decodificar telemetria, calcular o apontamento
    e mover o pedestal. Isto é uma extensão própria deste simulador, não
    um parâmetro do comando real ``GG`` (ver docstring do módulo).

    O alinhamento azimutal (o que "pan = 0°" significa fisicamente — via
    de regra, norte verdadeiro) é responsabilidade de quem instala a
    unidade, igual num sistema real: aqui isso é implícito na convenção
    já usada pelo resto do simulador (pan 0° = referência frontal fixa).
    """

    def __init__(self, device, lead_seconds: float = 0.0):
        self.device = device
        self.lead_seconds = lead_seconds
        self.state = GeoTrackerState()
        self._previous_target: GeoPoint | None = None
        self._previous_time: float | None = None

    def observer(self) -> GeoPoint:
        pose = self.device.gpm_pose
        return GeoPoint(
            lat_deg=pose.latitude_deg, lon_deg=pose.longitude_deg, alt_m=pose.altitude_m
        )

    def set_target(self, point: GeoPoint, at: float | None = None) -> LookAngles:
        """Aponta para ``point`` agora (comando real ``GG``).

        ``at`` é o instante (``time.monotonic()``) desta atualização —
        normalmente deixado para o relógio real; um valor explícito serve
        só para testes determinísticos da predição por velocidade.
        """
        now = time.monotonic() if at is None else at

        velocity = None
        if self._previous_target is not None and self._previous_time is not None:
            velocity = _estimate_velocity(self._previous_target, self._previous_time, point, now)
        self._previous_target = point
        self._previous_time = now

        aim_point = point
        if velocity is not None and self.lead_seconds > 0.0:
            aim_point = _predict_point(point, velocity, self.lead_seconds)

        look = look_angles(self.observer(), aim_point)
        self.state.target = point
        self.state.predicted_target = aim_point
        self.state.velocity = velocity
        self.state.last_look = look

        pan_deg = _normalize_signed_degrees(look.azimuth_deg)
        self.device.pan.set_target_position(self.device.pan.deg_to_counts(pan_deg))
        self.device.tilt.set_target_position(self.device.tilt.deg_to_counts(look.elevation_deg))
        return look

    def reset(self) -> None:
        self.state = GeoTrackerState()
        self._previous_target = None
        self._previous_time = None
