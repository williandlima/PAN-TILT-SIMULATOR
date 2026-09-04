"""Geo Pointing Module (GPM) e rastreamento de antena por telemetria GPS.

Este módulo tem duas partes distintas — não confunda uma com a outra:

1. ``GpmPose`` — a pose própria da unidade (onde ela está instalada:
   latitude, longitude, altitude, roll, pitch, yaw, offset de pitch da
   câmera). Isto é o recurso **real e confirmado** da FLIR, "Geo Pointing
   Module", Capítulo 17 do "E Series Pan-Tilt Command Reference Manual,
   Version 6.00 (09/2014)": os comandos ``GL``/``GO``/``GA``/``GLLA``
   (posição) e ``GR``/``GP``/``GY``/``GRPY``/``GCP`` (orientação) foram
   verificados **byte a byte** contra fotos das páginas 99 e 111 desse
   manual, incluindo o formato exato de resposta. Ver
   ``pantiltsim/protocol.py`` (comandos ``G...``) e ``docs/PROTOCOL.md``.

   Repare que isto é a posição de **instalação** da própria unidade — o
   mesmo que a FLIR documenta em suas páginas de suporte como exigindo
   calibração prévia contra pontos de referência conhecidos, para uso em
   **instalações fixas**. Não é um comando para informar a posição de um
   alvo em movimento.

2. ``GeoTracker``/``LinearTrajectory``/``look_angles`` — o cálculo de
   apontamento (azimute/elevação/distância) de um alvo a partir de duas
   posições geodésicas, e uma ferramenta de demonstração deste simulador
   que usa esse cálculo para apontar o pan-tilt continuamente para um
   alvo em movimento (ex.: um veículo transmitindo sua própria posição
   por telemetria GPS) — o mesmo princípio de uma estação terrena de
   rastreamento de satélite. **Isto não é um comando do protocolo DPCL**:
   nenhuma fonte confirmou um comando ASCII de "aqui está a posição atual
   de um alvo em movimento, aponte para lá agora" na família de comandos
   GPM da FLIR (que, pelo contrário, é documentada como não recomendada
   para plataformas móveis). Por isso esta parte é exposta só pela
   GUI/API Python do simulador — não inventa mais sintaxe de fio para não
   repetir o erro das versões anteriores desta funcionalidade, que
   propunham ``GO``/``GX``/``GE``/``GD``/``GA`` como comandos, colidindo
   inclusive com os nomes reais confirmados depois (``GO`` é longitude,
   ``GA`` é altitude).

A matemática de apontamento (item 2) é geodésico -> ECEF -> ENU no
elipsoide WGS84 — o método padrão de rastreamento de antena (o mesmo do
Gpredict e de estações terrenas de satélite), não uma aproximação de
Terra plana:

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
    enabled: bool = False
    target: GeoPoint | None = None
    last_look: LookAngles | None = None


class GeoTracker:
    """Ferramenta de demonstração da GUI: rastreamento contínuo de um alvo.

    Usa a posição própria já calibrada em ``device.gpm_pose`` (comandos
    reais ``GL``/``GO``/``GA``/``GLLA``) como estação de solo, e aponta o
    pan-tilt para um alvo em movimento (``target``, tipicamente atualizado
    por um feed de GPS externo a cada nova posição recebida). Quando
    habilitado, cada atualização de alvo recalcula azimute/elevação e
    comanda a posição alvo de pan/tilt. O movimento físico até lá usa o
    mesmo motor de simulação (perfil de aceleração, limites de
    velocidade) de qualquer outro comando de posição.

    **Isto não é um comando do protocolo DPCL** — é lógica de aplicação
    exposta só pela GUI/API Python deste simulador (ver módulo docstring
    para o porquê). Os comandos DPCL reais e confirmados ficam em
    ``GpmPose``/``pantiltsim/protocol.py``.

    O alinhamento azimutal (o que "pan = 0°" significa fisicamente — via
    de regra, norte verdadeiro) é responsabilidade de quem instala a
    unidade, igual num sistema real: aqui isso é implícito na convenção
    já usada pelo resto do simulador (pan 0° = referência frontal fixa).
    """

    def __init__(self, device):
        self.device = device
        self.state = GeoTrackerState()

    def _observer(self) -> GeoPoint:
        pose = self.device.gpm_pose
        return GeoPoint(
            lat_deg=pose.latitude_deg, lon_deg=pose.longitude_deg, alt_m=pose.altitude_m
        )

    def set_target(self, point: GeoPoint) -> None:
        self.state.target = point
        if self.state.enabled:
            self._point_at_target()

    def enable(self) -> None:
        self.state.enabled = True
        if self.state.target is not None:
            self._point_at_target()

    def disable(self) -> None:
        self.state.enabled = False

    def current_look_angles(self) -> LookAngles:
        if self.state.target is None:
            raise ValueError("Defina o alvo primeiro (GeoTracker.set_target)")
        return look_angles(self._observer(), self.state.target)

    def _point_at_target(self) -> None:
        look = self.current_look_angles()
        self.state.last_look = look

        pan_deg = _normalize_signed_degrees(look.azimuth_deg)
        self.device.pan.set_target_position(self.device.pan.deg_to_counts(pan_deg))
        self.device.tilt.set_target_position(self.device.tilt.deg_to_counts(look.elevation_deg))
