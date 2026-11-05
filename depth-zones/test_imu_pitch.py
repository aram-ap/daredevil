import math

import pytest

import imu_pitch as ip

G = 9.81


def accel_for_pitch(theta, roll=0.0):
    """Synthetic accel reading for a camera whose lens is pitched DOWN by theta."""
    return (G * math.sin(roll), -G * math.cos(theta), -G * math.sin(theta))


@pytest.mark.parametrize("theta", [0.0, 0.15, 0.5, -0.3])
def test_pitch_recovered(theta):
    assert ip.pitch_from_accel(*accel_for_pitch(theta)) == pytest.approx(theta, abs=1e-9)


def test_level_camera_is_zero_pitch():
    assert ip.pitch_from_accel(0.0, -G, 0.0) == pytest.approx(0.0)


def test_roll_detected():
    assert ip.roll_from_accel(*accel_for_pitch(0.0, roll=0.2)) == pytest.approx(0.2, abs=0.02)


def test_estimator_converges_and_smooths_noise():
    est = ip.PitchEstimator(alpha=0.05)
    true = 0.15
    for i in range(300):
        ax, ay, az = accel_for_pitch(true)
        az += 3.0 * (1 if i % 2 else -1)       # +-3 m/s^2 "footstep" noise
        est.update(ax, ay, az)
    assert est.pitch == pytest.approx(true, abs=0.05)


def test_estimator_sign_flip_and_default():
    assert ip.PitchEstimator().pitch == 0.0
    e = ip.PitchEstimator(sign=-1)
    e.update(*accel_for_pitch(0.2))
    assert e.pitch == pytest.approx(-0.2)
