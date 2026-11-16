import unittest
from unittest import mock

from rfcat_cli.manufacturer import Manufacturer


def _manufacturer(**extra):
    cfg = {"name": "Test", "commands": [{"name": "cmd1", "code": "abc"}]}
    cfg.update(extra)
    return Manufacturer(cfg)


class RepeatSettingsTests(unittest.TestCase):
    def test_defaults_when_repeat_missing(self):
        repeat = _manufacturer().repeat

        self.assertEqual((repeat.count, repeat.delay, repeat.radio_on), (3, 100, False))

    def test_repeat_yaml_overrides_defaults(self):
        repeat = _manufacturer(repeat={"count": 5, "delay": 250, "radio_on": True}).repeat

        self.assertEqual((repeat.count, repeat.delay, repeat.radio_on), (5, 250, True))

    @mock.patch("rfcat_cli.manufacturer.time.sleep")
    def test_tx_cmd_uses_repeat_settings(self, sleep_mock):
        rfcat = mock.Mock()

        _manufacturer(repeat={"count": 2, "delay": 250}).tx_cmd(rfcat, "cmd1")

        self.assertEqual(rfcat.RFxmit.call_count, 2)
        sleep_mock.assert_called_once_with(0.25)


if __name__ == "__main__":
    unittest.main()
