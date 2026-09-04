"""Testes do protocolo ASCII do fabricante.

Os formatos verificados aqui contra "hardware real" vêm de dois drivers
de código aberto que conversam com unidades PTU físicas — ver o
docstring de `pantiltsim/protocol.py` e `docs/PROTOCOL.md`.
"""

import pytest

from pantiltsim.config import build_device
from pantiltsim.device import ControlMode, LimitMode, StepMode


@pytest.fixture
def ptu():
    from pantiltsim.protocol import DPCLProtocol

    device = build_device()
    # Sem o motor de simulação rodando, um 'A' esperaria o timeout inteiro.
    protocol = DPCLProtocol(device, await_timeout=0.2)
    device.echo_enabled = False
    return device, protocol


# -- formato das respostas (confirmado contra drivers reais) ---------------
def test_verbose_position_strings_match_reference_driver_offsets(ptu):
    """O driver de referência fatia a resposta em offsets fixos; respeitá-los."""
    device, protocol = ptu

    assert protocol.execute_line("PP").startswith("* Current Pan position is ")
    assert protocol.execute_line("TP").startswith("* Current Tilt position is ")
    assert protocol.execute_line("PO").startswith("* Target Pan position is ")
    assert protocol.execute_line("TO").startswith("* Target Tilt position is ")

    # Os offsets exatos usados pelo driver hmorris94/FLIR-PTU-Python.
    assert len("* Current Pan position is ") == 26
    assert len("* Current Tilt position is ") == 27
    assert len("* Target Pan position is ") == 25
    assert len("* Target Tilt position is ") == 26

    device.pan.position = 1234
    assert int(protocol.execute_line("PP")[26:]) == 1234


def test_terse_format_is_asterisk_space_value(ptu):
    device, protocol = ptu
    protocol.execute_line("FT")
    device.pan.position = 4321

    response = protocol.execute_line("PP")
    assert response == "* 4321\r\n"
    # O driver C++ de referência valida buffer[0]=='*' e converte o resto.
    assert response[0] == "*"
    assert int(response[1:].strip()) == 4321


def test_reset_response_matches_reference_driver(ptu):
    device, protocol = ptu
    for command in ("R", "RE", "RP", "RT"):
        device.echo_enabled = False  # o próprio reset religa o eco de fábrica
        assert protocol.execute_line(command).strip() == "!T!T!P!P*"


def test_errors_start_with_bang(ptu):
    _, protocol = ptu
    assert protocol.execute_line("ZZ").startswith("!")
    assert protocol.execute_line("PPabc").startswith("!")
    assert protocol.execute_line("PZ").startswith("!")


# -- comandos de posição/velocidade ----------------------------------------
def test_absolute_and_relative_position(ptu):
    device, protocol = ptu
    protocol.execute_line("PP1000")
    assert device.pan.target_position == 1000

    protocol.execute_line("PO500")
    assert device.pan.target_position == 1500

    assert protocol.execute_line("PO").strip().endswith("1500")


def test_speed_target_and_current(ptu):
    device, protocol = ptu
    protocol.execute_line("FT PS2500")
    assert device.pan.desired_speed == 2500
    assert protocol.execute_line("PS") == "* 2500\r\n"

    # PD consulta a velocidade instantânea (0 parado) e ajusta por delta.
    assert protocol.execute_line("PD") == "* 0\r\n"
    protocol.execute_line("PD-500")
    assert device.pan.desired_speed == 2000


def test_acceleration_base_and_speed_limits(ptu):
    device, protocol = ptu
    protocol.execute_line("FT PA4000 PB600 PU9000 PL10")
    assert device.pan.acceleration == 4000
    assert device.pan.base_speed == 600
    assert device.pan.upper_speed_limit == 9000
    assert device.pan.lower_speed_limit == 10
    assert protocol.execute_line("PU") == "* 9000\r\n"


def test_resolution_query_is_read_only(ptu):
    device, protocol = ptu
    protocol.execute_line("FT")
    expected = round(device.pan.arcsec_per_count, 4)
    assert protocol.execute_line("PR") == f"* {expected}\r\n"
    assert protocol.execute_line("PR100").startswith("!")


def test_step_mode_changes_resolution(ptu):
    device, protocol = ptu
    protocol.execute_line("WPF")
    assert device.pan.step_mode == StepMode.FULL
    assert device.pan.arcsec_per_count == device.pan.spec.full_step_arcsec

    protocol.execute_line("WPQ")
    assert device.pan.step_mode == StepMode.QUARTER


# -- limites ---------------------------------------------------------------
def test_user_limits_and_limit_modes(ptu):
    device, protocol = ptu
    protocol.execute_line("FT PNU-2000 PXU2000")
    assert device.pan.user_min == -2000
    assert device.pan.user_max == 2000
    assert protocol.execute_line("PNU") == "* -2000\r\n"

    protocol.execute_line("LU")
    assert device.limit_mode == LimitMode.USER
    assert protocol.execute_line("PX") == "* 2000\r\n"

    protocol.execute_line("LD")
    assert device.limit_mode == LimitMode.DISABLED

    protocol.execute_line("LE")
    assert device.limit_mode == LimitMode.FACTORY


def test_limits_are_enforced_on_position_command(ptu):
    device, protocol = ptu
    protocol.execute_line("PNU-1000 PXU1000 LU PP5000")
    assert device.pan.target_position == 1000


# -- modos e controle -------------------------------------------------------
def test_control_mode_commands(ptu):
    device, protocol = ptu
    protocol.execute_line("CV")
    assert device.control_mode == ControlMode.VELOCITY
    protocol.execute_line("CI")
    assert device.control_mode == ControlMode.POSITION
    assert "position" in protocol.execute_line("C")


def test_echo_and_feedback_modes(ptu):
    device, protocol = ptu
    protocol.execute_line("EE")
    assert device.echo_enabled is True
    response = protocol.execute_line("PS")
    assert response.startswith("PS\r\n")

    protocol.execute_line("ED")
    assert device.echo_enabled is False
    assert not protocol.execute_line("PS").startswith("PS")


def test_halt_commands(ptu):
    device, protocol = ptu
    protocol.execute_line("PP5000 TP3000")
    protocol.execute_line("HP")
    assert device.pan.target_position == device.pan.position
    assert device.tilt.target_position == 3000

    protocol.execute_line("H")
    assert device.tilt.target_position == device.tilt.position


def test_monitor_mode_commands(ptu):
    device, protocol = ptu
    protocol.execute_line("ME")
    assert device.monitor.enabled is True
    protocol.execute_line("MD")
    assert device.monitor.enabled is False


def test_slaved_execution_and_await(ptu):
    device, protocol = ptu
    protocol.execute_line("S PP800 TP600")
    assert device.pan.target_position == 0  # aguardando o 'A'

    protocol.execute_line("A")
    assert device.pan.target_position == 800
    assert device.tilt.target_position == 600


def test_combined_move_command(ptu):
    device, protocol = ptu
    assert protocol.execute_line("B1500,-900,2000,2500") == "*\r\n"
    assert device.pan.target_position == 1500
    assert device.tilt.target_position == -900
    assert device.pan.desired_speed == 2000
    assert device.tilt.desired_speed == 2500

    assert protocol.execute_line("B1,2").startswith("!")


def test_host_port_configuration_command(ptu):
    device, protocol = ptu
    assert protocol.execute_line("@(38400,0,F)") == "*\r\n"
    assert device.host_baudrate == 38400
    assert protocol.execute_line("@(oops)").startswith("!")


def test_power_mode_commands(ptu):
    device, protocol = ptu
    protocol.execute_line("PHO TMH")
    assert device.pan.hold_power.value == "off"
    assert device.tilt.move_power.value == "high"
    assert protocol.execute_line("PHZ").startswith("!")


def test_save_and_restore_defaults(ptu):
    device, protocol = ptu
    protocol.execute_line("FT PS1234 DS PS4321")
    assert device.pan.desired_speed == 4321
    protocol.execute_line("DR")
    assert device.pan.desired_speed == 1234


def test_version_query(ptu):
    device, protocol = ptu
    assert device.model_name in protocol.execute_line("V")


# -- tratamento do fluxo serial ---------------------------------------------
def test_multiple_commands_in_one_line(ptu):
    device, protocol = ptu
    response = protocol.execute_line("FT PA3000 TA3000 PS800 TS800")
    assert response.count("*") == 5
    assert device.tilt.acceleration == 3000
    assert device.tilt.desired_speed == 800


def test_partial_stream_is_buffered(ptu):
    device, protocol = ptu
    assert protocol.feed(b"PP10") == b""
    assert protocol.feed(b"00 ") != b""
    assert device.pan.target_position == 1000


def test_commands_are_case_insensitive(ptu):
    device, protocol = ptu
    protocol.execute_line("pp750")
    assert device.pan.target_position == 750


def test_cr_and_lf_terminators_are_accepted(ptu):
    device, protocol = ptu
    protocol.feed(b"PP100\r")
    assert device.pan.target_position == 100
    protocol.feed(b"PP200\r\n")
    assert device.pan.target_position == 200


# -- Geo Pointing Module: GL/GO/GA/GLLA (posição) e GR/GP/GY/GRPY/GCP
# (orientação) — confirmados byte a byte contra fotos das páginas 99 e 111
# do "E Series Pan-Tilt Command Reference Manual, Version 6.00 (09/2014)".
def test_gpm_position_query_and_set(ptu):
    device, protocol = ptu
    assert protocol.execute_line("GL-23.5") == "* -23.500000\r\n"
    assert protocol.execute_line("GO-46.6") == "* -46.600000\r\n"
    assert protocol.execute_line("GA760") == "* 760.000000\r\n"
    assert protocol.execute_line("GL") == "* -23.500000\r\n"
    assert device.gpm_pose.latitude_deg == -23.5
    assert device.gpm_pose.longitude_deg == -46.6
    assert device.gpm_pose.altitude_m == 760.0


def test_gpm_combined_position(ptu):
    # "GLLA<lat,lon,alt>" -> "* lat,lon,alt" com 6 casas decimais (formato do manual).
    _, protocol = ptu
    assert protocol.execute_line("GLLA") == "* 0.000000,0.000000,0.000000\r\n"
    assert protocol.execute_line("GLLA-23.5,-46.6,760") == "* -23.500000,-46.600000,760.000000\r\n"


def test_gpm_orientation_matches_manual_worked_example(ptu):
    """Reproduz o exemplo da seção 17.4.3 do manual (página 111, foto real)."""
    device, protocol = ptu
    device.gpm_pose.roll_deg = -1.459233
    device.gpm_pose.pitch_deg = 3.103816
    device.gpm_pose.yaw_deg = 50.042890

    assert protocol.execute_line("GR") == "* -1.459233\r\n"
    assert protocol.execute_line("GP") == "* 3.103816\r\n"
    assert protocol.execute_line("GY") == "* 50.042890\r\n"
    assert protocol.execute_line("GRPY") == "* -1.459233,3.103816,50.042890\r\n"

    assert protocol.execute_line("GRPY-1.2,3.2,50") == "* -1.200000,3.200000,50.000000\r\n"

    protocol.execute_line("GR-1.5")
    protocol.execute_line("GY20")
    assert protocol.execute_line("GRPY") == "* -1.500000,3.200000,20.000000\r\n"


def test_gpm_camera_pitch_offset_matches_manual_example(ptu):
    _, protocol = ptu
    assert protocol.execute_line("GCP") == "* 0.000000\r\n"
    assert protocol.execute_line("GCP10.3") == "* 10.300000\r\n"


def test_gpm_rejects_malformed_value(ptu):
    _, protocol = ptu
    assert protocol.execute_line("GLnotanumber").startswith("!")
    assert protocol.execute_line("GLLA0,0").startswith("!")  # faltam campos


def test_gpm_unknown_command_is_an_error(ptu):
    _, protocol = ptu
    assert protocol.execute_line("GZ").startswith("!")


# -- aim point (GG/GGD) e landmarks (GM/GMA/GMN/GMD/GMC) — seção 17.5,
# confirmados byte a byte contra foto da página 113 do manual real.
# GG<lat,lon,alt> É o comando real de "aponte para esta coordenada agora"
# — uma ação (responde "*\r\n" seco), não um modo liga/desliga.
def test_gpm_aim_point_matches_manual_example(ptu):
    """Reproduz o exemplo da seção 17.5.3 (página 113, foto real)."""
    device, protocol = ptu
    protocol.execute_line("GLLA0,0,0")  # estação em (0,0,0)

    assert protocol.execute_line("GG-22.9,-43.2,0") == "*\r\n"
    assert protocol.execute_line("GG") == "* -22.90000,-43.20000,0.00000\r\n"


def test_gpm_aim_point_moves_pan_tilt(ptu):
    device, protocol = ptu
    protocol.execute_line("GLLA0,0,0")
    protocol.execute_line("GG0,1,0")  # alvo a leste

    pan_deg = device.pan.counts_to_deg(device.pan.target_position)
    assert pan_deg == pytest.approx(90.0, abs=0.5)


def test_gpm_aim_query_before_set_is_an_error(ptu):
    _, protocol = ptu
    assert protocol.execute_line("GG").startswith("!")
    assert protocol.execute_line("GGD").startswith("!")


def test_gpm_aim_distance_matches_look_angles(ptu):
    from pantiltsim.tracking import GeoPoint, look_angles

    device, protocol = ptu
    protocol.execute_line("GLLA0,0,0")
    protocol.execute_line("GG0,1,0")

    response = protocol.execute_line("GGD")
    expected = look_angles(GeoPoint(0, 0, 0), GeoPoint(0, 1, 0)).range_m
    assert float(response.strip().lstrip("* ")) == pytest.approx(expected, abs=0.5)


def test_gpm_aim_distance_to_arbitrary_point_does_not_move(ptu):
    """GGD<lat,lon,alt> só consulta — não altera o apontamento atual."""
    device, protocol = ptu
    protocol.execute_line("GLLA0,0,0")
    protocol.execute_line("GG0,1,0")
    pan_before = device.pan.target_position

    protocol.execute_line("GGD1,0,0")

    assert device.pan.target_position == pan_before


def test_gpm_landmark_lifecycle(ptu):
    _, protocol = ptu
    assert protocol.execute_line("GMN") == "* 0\r\n"

    assert protocol.execute_line("GMAHOTEL,37.5918,-122.3475,40") == "*\r\n"
    assert protocol.execute_line("GMAOFFICE,37.5941,-122.3656,42") == "*\r\n"
    assert protocol.execute_line("GMN") == "* 2\r\n"

    response = protocol.execute_line("GM0")
    assert response.startswith("* 0,HOTEL,37.5918,-122.3475,40.0000,")

    listing = protocol.execute_line("GM")
    assert "HOTEL" in listing and "OFFICE" in listing and ";" in listing

    assert protocol.execute_line("GMD0") == "*\r\n"
    assert protocol.execute_line("GMN") == "* 1\r\n"

    assert protocol.execute_line("GMC") == "*\r\n"
    assert protocol.execute_line("GMN") == "* 0\r\n"


def test_gpm_aim_at_landmark_by_index(ptu):
    """"GG<índice>" aponta para um landmark salvo (exemplo "GG1" do manual)."""
    device, protocol = ptu
    protocol.execute_line("GLLA0,0,0")
    protocol.execute_line("GMALANDMARK,0,1,0")  # landmark a leste

    assert protocol.execute_line("GG0") == "*\r\n"
    pan_deg = device.pan.counts_to_deg(device.pan.target_position)
    assert pan_deg == pytest.approx(90.0, abs=0.5)


def test_gpm_landmark_unknown_index_is_an_error(ptu):
    _, protocol = ptu
    assert protocol.execute_line("GM0").startswith("!")
    assert protocol.execute_line("GMD0").startswith("!")
    assert protocol.execute_line("GG0").startswith("!")


def test_geo_tracking_state_reported_in_snapshot(ptu):
    device, protocol = ptu
    protocol.execute_line("GLLA0,0,0")
    protocol.execute_line("GG0,1,0")

    snap = device.snapshot()
    assert snap["geo_tracking"] is True
    assert snap["geo_target"] is not None
    assert snap["geo_look"] is not None
    assert snap["gpm_latitude_deg"] == 0.0
    assert snap["gpm_landmark_count"] == 0


def test_reset_clears_geo_tracker_target(ptu):
    device, protocol = ptu
    protocol.execute_line("GLLA0,0,0")
    protocol.execute_line("GG0,1,0")
    assert device.geo_tracker.state.target is not None

    protocol.execute_line("RE")
    assert device.geo_tracker.state.target is None
