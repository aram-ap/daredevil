"""check_bracelets: spotting setup mistakes and buzzing each bracelet in turn."""

import unittest

from daredevil_link import protocol as p
from daredevil_link.bracelet import Bracelet, Identity
from examples.check_bracelets import assess, buzz_each

from fakes import FakeBracelet, FakeTransport

LEFT = Identity(p.SIDE_LEFT, "0.3", p.NUM_MOTORS)
RIGHT = Identity(p.SIDE_RIGHT, "0.3", p.NUM_MOTORS)


class AssessTest(unittest.TestCase):
    def test_both_sides_matching_firmware_is_ok(self):
        self.assertEqual(assess([("10.42.0.10", LEFT), ("10.42.0.11", RIGHT)]), [])

    def test_missing_side_is_reported(self):
        problems = assess([("10.42.0.10", LEFT)])
        self.assertEqual(len(problems), 1)
        self.assertIn("right", problems[0])
        self.assertIn("not found", problems[0])

    def test_two_boards_with_the_same_side_are_reported_with_the_fix(self):
        # Over USB both ports answer, and both say "left".
        problems = assess([("/dev/ttyACM0", LEFT), ("/dev/ttyACM1", LEFT)])
        duplicate = [m for m in problems if "both say" in m]
        self.assertEqual(len(duplicate), 1)
        self.assertIn("/dev/ttyACM0", duplicate[0])
        self.assertIn("/dev/ttyACM1", duplicate[0])
        self.assertIn("pio run -e right", duplicate[0])

    def test_hub_conflicts_are_reported_the_same_way(self):
        problems = assess([("10.42.0.10", LEFT)], conflicts={"left": {"10.42.0.10", "10.42.0.11"}})
        duplicate = [m for m in problems if "both say" in m]
        self.assertEqual(len(duplicate), 1)
        self.assertIn("10.42.0.11", duplicate[0])

    def test_wrong_motor_count_is_reported(self):
        three_motors = Identity(p.SIDE_RIGHT, "0.3", 3)
        problems = assess([("10.42.0.10", LEFT), ("10.42.0.11", three_motors)])
        self.assertEqual(len(problems), 1)
        self.assertIn("motors", problems[0])

    def test_different_firmware_versions_are_reported(self):
        old_right = Identity(p.SIDE_RIGHT, "0.2", p.NUM_MOTORS)
        problems = assess([("10.42.0.10", LEFT), ("10.42.0.11", old_right)])
        self.assertEqual(len(problems), 1)
        self.assertIn("0.2", problems[0])
        self.assertIn("0.3", problems[0])

    def test_expecting_one_side_only_checks_that_side(self):
        # Used right after flashing a single bracelet.
        self.assertEqual(assess([("/dev/ttyACM0", RIGHT)], expect=("right",)), [])
        self.assertEqual(len(assess([("/dev/ttyACM0", LEFT)], expect=("right",))), 1)


class BuzzEachTest(unittest.TestCase):
    def test_buzzes_left_then_right_and_reports_acks(self):
        fakes = {"left": FakeBracelet(side=p.SIDE_LEFT), "right": FakeBracelet(side=p.SIDE_RIGHT)}
        order = []

        def bracelet(side):
            def respond(data):
                order.append(side)
                return fakes[side](data)

            return Bracelet(FakeTransport(respond))

        bracelets = {"right": bracelet("right"), "left": bracelet("left")}  # dict order on purpose
        result = buzz_each(bracelets, repeats=1, gap_s=0, announce=lambda side: None)

        self.assertEqual(order, ["left", "right"])
        self.assertEqual(result, {"left": p.STATUS_OK, "right": p.STATUS_OK})
        self.assertEqual(fakes["left"].patterns_played, [p.PATTERN_BOOT])
        self.assertEqual(fakes["right"].patterns_played, [p.PATTERN_BOOT])


if __name__ == "__main__":
    unittest.main()
