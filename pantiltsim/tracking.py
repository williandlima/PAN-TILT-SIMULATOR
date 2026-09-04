"""Rastreamento de antena por telemetria (antenna tracking), via GPS.

Implementa o cálculo de apontamento — azimute e elevação — que um
sistema real de rastreamento de antena de telemetria faz continuamente:
dada a posição geodésica (WGS84, o mesmo datum que o GPS usa
nativamente) da estação de solo e a posição do veículo rastreado (também
vinda de GPS), calcula o vetor entre os dois pontos no referencial local
ENU (Leste-Norte-Cima, "East-North-Up") da estação e extrai os ângulos.
É exatamente o método usado por estações terrenas de rastreamento de
satélite, antenas de telemetria de aeronaves/drones/foguetes de teste, e
softwares como o Gpredict — não uma aproximação de Terra plana.

A conversão é geodésico -> ECEF -> ENU no elipsoide WGS84:

    1. Latitude/longitude/altitude (de cada ponto) viram coordenadas
       cartesianas ECEF (Earth-Centered, Earth-Fixed) usando o raio de
       curvatura do elipsoide na latitude local.
    2. O vetor entre as duas posições ECEF é projetado no plano tangente
       local (ENU) da estação de solo, usando a matriz de rotação padrão
       para aquela latitude/longitude.
    3. Azimute = atan2(Leste, Norte); Elevação = atan2(Cima, distância
       horizontal).

A altitude usada aqui é a altura elipsoidal (a que um receptor GPS
entrega antes de qualquer correção de geoide) — sistemas reais às vezes
aplicam uma correção de ondulação do geoide (EGM96/2008) para obter
altitude sobre o nível médio do mar; isso não está implementado aqui, é
uma simplificação documentada.

Este módulo só resolve "para onde apontar" a partir de duas posições
geográficas — a mesma matemática vale para qualquer veículo com GPS
(avião, drone, balão sonda, foguete de sondagem). Ele não rastreia,
identifica nem interage com o veículo de forma alguma: apenas converte
coordenadas recebidas de uma fonte externa (um receptor GPS de verdade,
ou aqui, para demonstração, um gerador de trajetória simulada) num
ângulo de apontamento de antena — a mesma função que uma antena
parabólica de estação terrena exerce ao seguir um satélite.

Os comandos DPCL usados para alimentar isto (``GO``, ``GX``, ``GE``,
``GD``, ``GA``) são uma extensão própria deste simulador, com prefixo
``G`` inspirado no que a documentação oficial da FLIR aparenta usar para
o módulo de apontamento geográfico (PTU-DGPM) — mas a sintaxe exata
oficial (``GLLA``, ``GPRY``) não pôde ser confirmada nesta sessão (ver
docs/PROTOCOL.md). Ajuste os nomes de comando aqui se conseguir acesso
ao manual oficial e quiser bater exatamente com ele.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# WGS84 — o mesmo datum que o GPS usa nativamente.
WGS84_SEMI_MAJOR_AXIS_M = 6378137.0
WGS84_FLATTENING = 1 / 298.257223563
_WGS84_ECCENTRICITY_SQUARED = 2 * WGS84_FLATTENING - WGS84_FLATTENING ** 2

_METERS_PER_DEGREE_LAT = 111_320.0  # aproximação, suficiente p/ trajetórias de demonstração


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
    observer: GeoPoint | None = None
    target: GeoPoint | None = None
    last_look: LookAngles | None = None


class GeoTracker:
    """Liga o cálculo de apontamento geográfico ao dispositivo simulado.

    Mantém a posição da estação de solo (``observer``) e a última posição
    conhecida do alvo (``target``, tipicamente atualizada por um feed de
    GPS externo a cada nova posição recebida). Quando habilitado, cada
    atualização de alvo recalcula azimute/elevação e comanda a posição
    alvo de pan/tilt — exatamente como o modo de apontamento geográfico
    faria internamente no equipamento real. O movimento físico até lá
    continua usando o mesmo motor de simulação (perfil de aceleração,
    limites de velocidade) de qualquer outro comando de posição.

    O alinhamento azimutal (o que "pan = 0°" significa fisicamente — via
    de regra, norte verdadeiro) é responsabilidade de quem instala a
    unidade, igual num sistema real: aqui isso é implícito na convenção
    já usada pelo resto do simulador (pan 0° = referência frontal fixa).
    """

    def __init__(self, device):
        self.device = device
        self.state = GeoTrackerState()

    def set_observer(self, point: GeoPoint) -> None:
        self.state.observer = point

    def set_target(self, point: GeoPoint) -> None:
        self.state.target = point
        if self.state.enabled:
            self._point_at_target()

    def enable(self) -> None:
        self.state.enabled = True
        if self.state.observer is not None and self.state.target is not None:
            self._point_at_target()

    def disable(self) -> None:
        self.state.enabled = False

    def current_look_angles(self) -> LookAngles:
        if self.state.observer is None or self.state.target is None:
            raise ValueError("Defina a estação de solo (GO) e o alvo (GX) primeiro")
        return look_angles(self.state.observer, self.state.target)

    def _point_at_target(self) -> None:
        look = self.current_look_angles()
        self.state.last_look = look

        pan_deg = _normalize_signed_degrees(look.azimuth_deg)
        self.device.pan.set_target_position(self.device.pan.deg_to_counts(pan_deg))
        self.device.tilt.set_target_position(self.device.tilt.deg_to_counts(look.elevation_deg))
