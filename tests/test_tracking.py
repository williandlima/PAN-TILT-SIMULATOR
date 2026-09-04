"""Testes do rastreamento de antena por GPS (geodesia WGS84 real).

Os casos de referência abaixo foram conferidos à mão (ver o raciocínio no
histórico de desenvolvimento): um alvo a 0,001° de longitude a leste do
observador, no equador, fica a ~111,32 m de distância quase exatamente no
azimute 90° — 111,32 m/° é a conversão padrão de grau de longitude para
metros no equador (2*pi*raio_da_Terra/360).
"""

import pytest

from pantiltsim.config import build_device
from pantiltsim.tracking import GeoPoint, GeoTracker, LinearTrajectory, look_angles


def test_target_due_east_at_equator():
    observer = GeoPoint(lat_deg=0.0, lon_deg=0.0, alt_m=0.0)
    target = GeoPoint(lat_deg=0.0, lon_deg=0.001, alt_m=0.0)

    look = look_angles(observer, target)

    assert look.azimuth_deg == pytest.approx(90.0, abs=0.01)
    assert look.range_m == pytest.approx(111.32, abs=0.5)
    # A curvatura da Terra faz um ponto no horizonte leste aparecer
    # ligeiramente ABAIXO do plano tangente local — não é ruído numérico,
    # é o comportamento físico correto do método ECEF/ENU.
    assert -0.01 < look.elevation_deg <= 0.0


def test_target_due_north_at_equator():
    observer = GeoPoint(lat_deg=0.0, lon_deg=0.0, alt_m=0.0)
    target = GeoPoint(lat_deg=0.001, lon_deg=0.0, alt_m=0.0)

    look = look_angles(observer, target)

    assert look.azimuth_deg == pytest.approx(0.0, abs=0.01)
    # No elipsoide WGS84, um grau de LATITUDE no equador equivale a
    # ~110,57 km — diferente dos ~111,32 km de um grau de LONGITUDE
    # (testado acima), porque o raio de curvatura meridional (norte-sul)
    # e o transversal (leste-oeste) não são iguais num elipsoide
    # achatado. Se este teste desse 111,32 km, seria sinal de uma
    # implementação esférica (errada), não elipsoidal.
    assert look.range_m == pytest.approx(110.57, abs=0.5)


def test_target_directly_overhead_is_90_degrees_elevation():
    observer = GeoPoint(lat_deg=-23.5, lon_deg=-46.6, alt_m=760.0)
    target = GeoPoint(lat_deg=-23.5, lon_deg=-46.6, alt_m=10_760.0)  # 10 km acima

    look = look_angles(observer, target)

    assert look.elevation_deg == pytest.approx(90.0, abs=1e-6)
    assert look.range_m == pytest.approx(10_000.0, abs=0.5)


def test_target_behind_is_at_180_degrees_or_negative_pan_normalization():
    from pantiltsim.tracking import _normalize_signed_degrees

    assert _normalize_signed_degrees(0.0) == 0.0
    assert _normalize_signed_degrees(90.0) == 90.0
    assert _normalize_signed_degrees(180.0) == 180.0
    assert _normalize_signed_degrees(270.0) == pytest.approx(-90.0)
    assert _normalize_signed_degrees(359.0) == pytest.approx(-1.0)


def test_symmetry_azimuth_is_reciprocal_plus_180_on_a_sphere_like_pair():
    """Ida e volta entre dois pontos próximos: os azimutes devem ser ~opostos."""
    a = GeoPoint(lat_deg=10.0, lon_deg=20.0, alt_m=0.0)
    b = GeoPoint(lat_deg=10.05, lon_deg=20.05, alt_m=0.0)

    look_ab = look_angles(a, b)
    look_ba = look_angles(b, a)

    raw_diff = abs((look_ab.azimuth_deg - look_ba.azimuth_deg + 180.0) % 360.0)
    circular_diff = min(raw_diff, 360.0 - raw_diff)
    assert circular_diff < 1.0  # tolerância pela diferença de referencial ENU entre os dois pontos


# ---------------------------------------------------------------------------
def test_linear_trajectory_moves_along_heading():
    start = GeoPoint(lat_deg=0.0, lon_deg=0.0, alt_m=1000.0)
    traj = LinearTrajectory(start=start, heading_deg=90.0, speed_mps=100.0, climb_mps=5.0)

    p0 = traj.position_at(0.0)
    p10 = traj.position_at(10.0)

    assert p0.lat_deg == pytest.approx(start.lat_deg)
    assert p0.lon_deg == pytest.approx(start.lon_deg)
    # Rumo 90° (leste): longitude aumenta, latitude não muda.
    assert p10.lon_deg > start.lon_deg
    assert p10.lat_deg == pytest.approx(start.lat_deg, abs=1e-9)
    assert p10.alt_m == pytest.approx(1000.0 + 5.0 * 10.0)


def test_linear_trajectory_heading_north():
    start = GeoPoint(lat_deg=0.0, lon_deg=0.0, alt_m=0.0)
    traj = LinearTrajectory(start=start, heading_deg=0.0, speed_mps=50.0)

    p5 = traj.position_at(5.0)
    assert p5.lat_deg > start.lat_deg
    assert p5.lon_deg == pytest.approx(start.lon_deg, abs=1e-9)


# ---------------------------------------------------------------------------
# GeoTracker é um recurso de GUI/API deste simulador (não um comando DPCL):
# a estação de solo vem de device.gpm_pose, que os comandos reais e
# confirmados GL/GO/GA/GLLA (Geo Pointing Module) definem via protocolo.
def test_geo_tracker_points_device_when_enabled():
    device = build_device()
    tracker = GeoTracker(device)

    # device.gpm_pose já nasce em (0, 0, 0); explícito aqui por clareza.
    device.gpm_pose.latitude_deg = 0.0
    device.gpm_pose.longitude_deg = 0.0
    device.gpm_pose.altitude_m = 0.0
    tracker.enable()
    tracker.set_target(GeoPoint(lat_deg=0.0, lon_deg=1.0, alt_m=0.0))

    # Alvo a leste -> pan positivo (~90°), dentro da faixa de fábrica.
    pan_deg = device.pan.counts_to_deg(device.pan.target_position)
    assert pan_deg == pytest.approx(90.0, abs=0.5)


def test_geo_tracker_does_not_move_device_when_disabled():
    device = build_device()
    tracker = GeoTracker(device)

    tracker.set_target(GeoPoint(lat_deg=0.0, lon_deg=1.0, alt_m=0.0))

    assert device.pan.target_position == 0  # tracking nunca foi habilitado


def test_geo_tracker_updates_continuously_as_target_moves():
    device = build_device()
    tracker = GeoTracker(device)
    tracker.enable()

    tracker.set_target(GeoPoint(lat_deg=0.0, lon_deg=1.0, alt_m=0.0))
    first_pan = device.pan.target_position

    tracker.set_target(GeoPoint(lat_deg=1.0, lon_deg=0.0, alt_m=0.0))
    second_pan = device.pan.target_position

    assert first_pan != second_pan
    assert device.pan.counts_to_deg(second_pan) == pytest.approx(0.0, abs=0.5)


def test_geo_tracker_azimuth_wraps_to_shortest_path():
    """Alvo a oeste (azimute ~270°) deve virar pan ~ -90°, não 270°."""
    device = build_device()
    tracker = GeoTracker(device)
    tracker.enable()
    tracker.set_target(GeoPoint(lat_deg=0.0, lon_deg=-1.0, alt_m=0.0))

    pan_deg = device.pan.counts_to_deg(device.pan.target_position)
    assert pan_deg == pytest.approx(-90.0, abs=0.5)


def test_geo_tracker_uses_gpm_pose_as_moving_observer():
    """Se a posição própria (gpm_pose) mudar, o próximo apontamento reflete isso."""
    device = build_device()
    tracker = GeoTracker(device)
    tracker.enable()

    device.gpm_pose.longitude_deg = 1.0  # estação "se move" para leste do alvo
    tracker.set_target(GeoPoint(lat_deg=0.0, lon_deg=0.0, alt_m=0.0))

    pan_deg = device.pan.counts_to_deg(device.pan.target_position)
    assert pan_deg == pytest.approx(-90.0, abs=0.5)  # alvo agora a oeste
