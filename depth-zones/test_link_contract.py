"""Contract test: haptic_map output is accepted by daredevil_link (Ilya, source/jetson/).

Checks the seam between two people's code without hardware: the vectors that
HapticMapper produces must go through Bracelet.set_motors() and arrive on the
wire as the same bytes, for the side names the link layer uses.

Skipped when source/jetson/ is not next to this folder (i.e. outside the repo).
"""
import sys
from pathlib import Path

import pytest

JETSON = Path(__file__).resolve().parents[1] / "source" / "jetson"
if not (JETSON / "daredevil_link").is_dir():
    pytest.skip("source/jetson not found next to depth-zones/", allow_module_level=True)
sys.path.insert(0, str(JETSON))

from daredevil_link import protocol as p  # noqa: E402
from daredevil_link.bracelet import Bracelet, Identity  # noqa: E402

import haptic_map as hm  # noqa: E402


class RecordingTransport:
    """Minimal stand-in for a serial port or UDP link: remembers what was written."""

    def __init__(self):
        self.written = b""

    def write(self, data):
        self.written += bytes(data)

    def read(self):
        return b""

    def close(self):
        pass


def bracelet(side):
    return Bracelet(RecordingTransport(), Identity(side, "0.2", p.NUM_MOTORS))


def test_motor_count_matches_the_protocol():
    assert hm.NUM_MOTORS == p.NUM_MOTORS


def test_mapper_keys_are_the_link_layers_side_names():
    names = {bracelet(p.SIDE_LEFT).identity.side_name, bracelet(p.SIDE_RIGHT).identity.side_name}
    assert set(hm.HapticMapper().map({})) == names == {"left", "right"}


@pytest.mark.parametrize("zones", [
    {"Left": None, "Center": None, "Right": None},
    {"Left": 0.6, "Center": None, "Right": None},
    {"Left": None, "Center": 1.5, "Right": None},
    {"Left": 0.5, "Center": 2.0, "Right": 3.0},
])
@pytest.mark.parametrize("mapper", [hm.HapticMapper(), hm.HapticMapper(bands=hm.DEFAULT_BANDS)],
                         ids=["linear", "banded"])
def test_vectors_arrive_on_the_wire_unchanged(zones, mapper):
    for side_const, key in ((p.SIDE_LEFT, "left"), (p.SIDE_RIGHT, "right")):
        vec = mapper.map(zones)[key]
        b = bracelet(side_const)
        b.set_motors(vec)                       # raises if the vector is invalid
        frames = p.FrameParser().feed(b.transport.written)
        assert len(frames) == 1
        assert frames[0].type == p.MSG_SET_MOTORS
        assert list(frames[0].payload) == vec
