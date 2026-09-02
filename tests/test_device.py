from pantiltsim.config import build_device
from pantiltsim.device import AxisSpec, ControlMode, LimitMode, PanTiltDevice, StepMode


def run_ticks(device, dt=0.02, n=200):
    for _ in range(n):
        device.tick(dt)


def test_resolution_matches_step_mode():
    device = build_device()
    axis = device.pan
    assert axis.arcsec_per_count == axis.spec.full_step_arcsec / 8  # eighth step (padrão)

    axis.set_step_mode(StepMode.FULL)
    assert axis.arcsec_per_count == axis.spec.full_step_arcsec

    axis.set_step_mode(StepMode.QUARTER)
    assert axis.arcsec_per_count == axis.spec.full_step_arcsec / 4


def test_step_mode_change_preserves_physical_angle():
    device = build_device()
    axis = device.pan
    axis.set_target_position(axis.deg_to_counts(45.0))
    run_ticks(device, n=600)
    assert abs(axis.counts_to_deg(axis.position) - 45.0) < 0.05

    axis.set_step_mode(StepMode.QUARTER)
    # Muda a unidade (contagens), mas o ângulo físico continua o mesmo.
    assert abs(axis.counts_to_deg(axis.position) - 45.0) < 0.05


def test_position_move_reaches_target():
    device = build_device()
    target = device.pan.deg_to_counts(60.0)
    device.pan.set_target_position(target)
    run_ticks(device, n=1000)
    assert device.pan.position == target
    assert not device.pan.is_in_motion()


def test_factory_limits_clamp_target():
    device = build_device()
    device.pan.set_target_position(device.pan.deg_to_counts(500.0))
    assert device.pan.target_position == device.pan.factory_max


def test_user_limits_are_used_only_in_user_mode():
    device = build_device()
    axis = device.pan
    axis.set_user_min(axis.deg_to_counts(-10.0))
    axis.set_user_max(axis.deg_to_counts(10.0))

    axis.set_target_position(axis.deg_to_counts(90.0))
    assert axis.counts_to_deg(axis.target_position) > 10.0  # ainda em limites de fábrica

    device.set_limit_mode(LimitMode.USER)
    axis.set_target_position(axis.deg_to_counts(90.0))
    assert abs(axis.counts_to_deg(axis.target_position) - 10.0) < 0.05


def test_disabled_limits_allow_out_of_range_target():
    device = build_device()
    device.set_limit_mode(LimitMode.DISABLED)
    target = device.pan.deg_to_counts(400.0)
    device.pan.set_target_position(target)
    assert device.pan.target_position == target


def test_velocity_mode_moves_continuously_until_halted():
    device = build_device()
    device.control_mode = ControlMode.VELOCITY
    device.pan.set_desired_speed(device.pan.deg_to_counts(10.0))

    run_ticks(device, n=100)
    first = device.pan.position
    assert first > 0

    run_ticks(device, n=100)
    assert device.pan.position > first

    device.pan.halt()
    stopped_at = device.pan.position
    run_ticks(device, n=50)
    assert device.pan.position == stopped_at


def test_velocity_mode_stops_at_limit():
    device = build_device()
    device.control_mode = ControlMode.VELOCITY
    device.pan.set_desired_speed(device.pan.deg_to_counts(120.0))
    run_ticks(device, dt=0.05, n=400)
    assert device.pan.position == device.pan.effective_max


def test_slaved_execution_defers_moves_until_await():
    device = build_device()
    device.slaved_execution = True
    device.request_target("pan", device.pan.deg_to_counts(30.0))
    device.request_target("tilt", device.tilt.deg_to_counts(20.0))

    assert device.pan.target_position == 0
    assert device.tilt.target_position == 0
    assert device.has_pending_targets()

    device.apply_pending_targets()
    assert device.pan.target_position != 0
    assert device.tilt.target_position != 0


def test_monitor_mode_sweeps_between_limits():
    device = build_device()
    device.monitor.enabled = True
    run_ticks(device, dt=0.05, n=40)
    assert device.pan.is_in_motion()
    assert device.pan.target_position != 0


def test_reset_per_axis_only_touches_that_axis():
    device = build_device()
    device.pan.set_target_position(1000)
    device.tilt.set_target_position(1000)
    run_ticks(device, n=200)

    device.reset(pan=True, tilt=False)
    assert device.pan.position == 0
    assert device.tilt.position != 0


def test_custom_axis_spec_from_config():
    device = PanTiltDevice(
        pan_spec=AxisSpec(name="pan", full_step_arcsec=360.0, factory_min_deg=-45, factory_max_deg=45),
        tilt_spec=AxisSpec(name="tilt"),
    )
    assert device.pan.arcsec_per_count == 45.0
    assert device.pan.counts_per_degree == 80.0
    assert device.pan.factory_max == device.pan.deg_to_counts(45)
