from pantiltsim.device import ControlMode, PanTiltDevice
from pantiltsim.protocol import DPCLProtocol


def make_protocol():
    device = PanTiltDevice()
    protocol = DPCLProtocol(device)
    return device, protocol


def feed(protocol, text: str) -> str:
    return protocol.feed(text.encode("ascii")).decode("ascii")


def test_set_and_query_pan_position():
    device, protocol = make_protocol()
    device.echo_enabled = False

    resp = feed(protocol, "PP1000 ")
    assert resp.startswith("*")

    device.pan.position = 1000  # simula o movimento já concluído
    resp = feed(protocol, "PP ")
    assert resp.strip() == "*p1000"


def test_query_tilt_speed_default():
    device, protocol = make_protocol()
    device.echo_enabled = False

    resp = feed(protocol, "TS ")
    assert resp.strip() == f"*t{device.tilt.desired_speed}"


def test_reset_response_matches_hardware_reference():
    device, protocol = make_protocol()
    device.echo_enabled = False
    resp = feed(protocol, "R ")
    assert resp.strip() == "!T!T!P!P*"


def test_control_mode_switch():
    device, protocol = make_protocol()
    device.echo_enabled = False

    feed(protocol, "CV ")
    assert device.control_mode == ControlMode.VELOCITY

    feed(protocol, "CI ")
    assert device.control_mode == ControlMode.POSITION


def test_limits_enable_disable():
    device, protocol = make_protocol()
    device.echo_enabled = False

    feed(protocol, "LD ")
    assert device.pan.limits_enabled is False
    assert device.tilt.limits_enabled is False

    feed(protocol, "LE ")
    assert device.pan.limits_enabled is True


def test_unknown_command_returns_error():
    device, protocol = make_protocol()
    device.echo_enabled = False

    resp = feed(protocol, "ZZ ")
    assert resp.startswith("!")


def test_invalid_value_returns_error():
    device, protocol = make_protocol()
    device.echo_enabled = False

    resp = feed(protocol, "PPabc ")
    assert resp.startswith("!")


def test_echo_prefixes_response_when_enabled():
    device, protocol = make_protocol()
    device.echo_enabled = True

    resp = feed(protocol, "PS500 ")
    lines = resp.strip().splitlines()
    assert lines[0] == "PS500"


def test_multiple_commands_in_single_feed():
    device, protocol = make_protocol()
    device.echo_enabled = False

    resp = feed(protocol, "PA3000 TA3000 PS800 TS800 ")
    assert resp.count("*") == 4
    assert device.pan.acceleration == 3000
    assert device.tilt.acceleration == 3000
    assert device.pan.desired_speed == 800
    assert device.tilt.desired_speed == 800


def test_version_query():
    device, protocol = make_protocol()
    device.echo_enabled = False
    resp = feed(protocol, "V ")
    assert "PTU-D300E" in resp


def test_axis_offset_moves_target_relative():
    device, protocol = make_protocol()
    device.echo_enabled = False

    feed(protocol, "PP1000 ")
    feed(protocol, "PO500 ")
    assert device.pan.target_position == 1500


def test_partial_stream_is_buffered_until_terminator():
    device, protocol = make_protocol()
    device.echo_enabled = False

    resp1 = protocol.feed(b"PP10")
    assert resp1 == b""
    resp2 = protocol.feed(b"00 ")
    assert resp2 != b""
    assert device.pan.target_position == 1000
