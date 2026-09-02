from pantiltsim.device import AxisConfig, ControlMode, PanTiltDevice


def make_device():
    pan_cfg = AxisConfig(name="pan", counts_per_degree=100.0)
    tilt_cfg = AxisConfig(name="tilt", counts_per_degree=100.0)
    return PanTiltDevice(pan_config=pan_cfg, tilt_config=tilt_cfg)


def run_ticks(device, dt, n):
    for _ in range(n):
        device.tick(dt)


def test_position_mode_reaches_target():
    device = make_device()
    device.pan.desired_speed = 1000
    device.pan.acceleration = 5000
    device.pan.set_target_position(500)

    run_ticks(device, 0.02, 300)  # 6 segundos simulados

    assert device.pan.position == 500
    assert not device.pan.is_in_motion()


def test_position_mode_respects_position_limits():
    device = make_device()
    device.pan.min_limit = -100
    device.pan.max_limit = 100
    device.pan.desired_speed = 2000
    device.pan.acceleration = 10000

    device.pan.set_target_position(10_000)
    run_ticks(device, 0.02, 500)

    assert device.pan.position == 100


def test_halt_stops_motion_immediately():
    device = make_device()
    device.pan.desired_speed = 1000
    device.pan.acceleration = 2000
    device.pan.set_target_position(2000)

    run_ticks(device, 0.02, 10)
    assert device.pan.position != 0

    device.pan.halt()
    pos_after_halt = device.pan.position
    run_ticks(device, 0.02, 10)

    assert device.pan.position == pos_after_halt
    assert not device.pan.is_in_motion()


def test_velocity_mode_moves_continuously_until_halted():
    device = make_device()
    device.control_mode = ControlMode.VELOCITY
    device.pan.desired_speed = 500
    device.pan.acceleration = 5000
    device.pan.limits_enabled = False

    run_ticks(device, 0.02, 100)  # 2s
    pos_after_2s = device.pan.position
    assert pos_after_2s > 0

    run_ticks(device, 0.02, 100)  # +2s
    assert device.pan.position > pos_after_2s

    device.pan.halt()
    pos_after_halt = device.pan.position
    run_ticks(device, 0.02, 50)
    assert device.pan.position == pos_after_halt


def test_reset_restores_defaults():
    device = make_device()
    device.pan.set_target_position(1234)
    device.pan.desired_speed = 42
    device.control_mode = ControlMode.VELOCITY

    device.reset()

    assert device.pan.position == 0
    assert device.pan.target_position == 0
    assert device.pan.desired_speed == device.pan.config.default_speed_counts
    assert device.control_mode == ControlMode.POSITION


def test_axis_config_deg_counts_roundtrip():
    cfg = AxisConfig(name="pan", counts_per_degree=92.5714)
    counts = cfg.deg_to_counts(45.0)
    deg = cfg.counts_to_deg(counts)
    assert abs(deg - 45.0) < 0.01
