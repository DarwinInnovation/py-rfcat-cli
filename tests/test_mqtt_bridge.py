import json
import os
import tempfile
import unittest
from unittest import mock

from rfcat_cli.mqtt_bridge import Bridge, discovery_messages, load_command_catalog, parse_tx_topic


EXAMPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "manufacturers")


class CatalogTests(unittest.TestCase):
    def test_loads_example_manufacturer(self):
        catalog = load_command_catalog(EXAMPLE_DIR)

        self.assertEqual(catalog["example"]["name"], "Example")
        self.assertEqual(catalog["example"]["freq"], 868960000)
        self.assertEqual(catalog["example"]["commands"], {"cmd1": "Command One", "cmd2": "Command Two"})

    def test_desc_defaults_to_name_and_non_yaml_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "fan.yaml"), "w", encoding="utf-8") as fh:
                fh.write("name: Ceiling Fan\ncommands:\n  - name: light\n    code: abc\n")
            with open(os.path.join(tmp, "notes.txt"), "w", encoding="utf-8") as fh:
                fh.write("ignore me")

            catalog = load_command_catalog(tmp)

        self.assertEqual(list(catalog), ["ceiling fan"])
        self.assertEqual(catalog["ceiling fan"]["commands"], {"light": "light"})

    def test_unquoted_boolean_command_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "fan.yaml"), "w", encoding="utf-8") as fh:
                fh.write("name: Fan\ncommands:\n  - name: off\n    code: abc\n")

            with self.assertRaisesRegex(ValueError, "quote it"):
                load_command_catalog(tmp)


class DiscoveryTests(unittest.TestCase):
    def test_one_button_per_command(self):
        catalog = load_command_catalog(EXAMPLE_DIR)

        messages = dict(discovery_messages(catalog))

        self.assertEqual(
            sorted(messages),
            ["homeassistant/button/rfcat_example_cmd1/config", "homeassistant/button/rfcat_example_cmd2/config"],
        )
        cmd1 = messages["homeassistant/button/rfcat_example_cmd1/config"]
        self.assertEqual(cmd1["name"], "Command One")
        self.assertEqual(cmd1["command_topic"], "rfcat/tx/example/cmd1")
        self.assertEqual(cmd1["availability_topic"], "rfcat/status")
        self.assertEqual(cmd1["device"]["identifiers"], ["rfcat_example"])
        self.assertEqual(cmd1["device"]["model"], "868.96 MHz")

    def test_ids_are_slugged_but_topics_keep_lookup_keys(self):
        catalog = {"ceiling fan": {"name": "Ceiling Fan", "freq": None, "commands": {"light": "Light"}}}

        (topic, payload), = discovery_messages(catalog, topic_prefix="rf", discovery_prefix="ha")

        self.assertEqual(topic, "ha/button/rfcat_ceiling_fan_light/config")
        self.assertEqual(payload["command_topic"], "rf/tx/ceiling fan/light")
        self.assertNotIn("model", payload["device"])


class TopicTests(unittest.TestCase):
    def test_parse_tx_topic(self):
        self.assertEqual(parse_tx_topic("rfcat/tx/example/cmd1"), ("example", "cmd1"))
        self.assertEqual(parse_tx_topic("rfcat/tx/example"), (None, None))
        self.assertEqual(parse_tx_topic("rfcat/tx/a/b/c"), (None, None))
        self.assertEqual(parse_tx_topic("other/tx/a/b"), (None, None))


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.client = mock.Mock()
        self.transmit = mock.Mock()
        self.bridge = Bridge(self.client, load_command_catalog(EXAMPLE_DIR), self.transmit)

    def _last_result(self):
        topic, payload = self.client.publish.call_args.args[:2]
        self.assertEqual(topic, "rfcat/result")
        return json.loads(payload)

    def test_on_connect_publishes_discovery_subscribes_and_goes_online(self):
        self.bridge.on_connect(self.client, None, None, mock.Mock(is_failure=False))

        topics = [c.args[0] for c in self.client.publish.call_args_list]
        self.assertIn("homeassistant/button/rfcat_example_cmd1/config", topics)
        self.assertEqual(topics[-1], "rfcat/status")
        self.assertEqual(self.client.publish.call_args_list[-1].args[1], "online")
        self.client.subscribe.assert_called_once_with("rfcat/tx/+/+", qos=1)

    def test_on_message_queues_without_transmitting(self):
        self.bridge.on_message(self.client, None, mock.Mock(topic="rfcat/tx/example/cmd1"))
        self.bridge.on_message(self.client, None, mock.Mock(topic="rfcat/status"))

        self.transmit.assert_not_called()
        self.assertEqual(self.bridge.jobs.get_nowait(), ("example", "cmd1"))
        self.assertTrue(self.bridge.jobs.empty())

    def test_process_transmits_known_command(self):
        self.bridge.process_one("example", "cmd1")

        self.transmit.assert_called_once_with("example", "cmd1")
        self.assertEqual(self._last_result()["status"], "sent")

    def test_process_rejects_unknown_command(self):
        self.bridge.process_one("example", "nope")

        self.transmit.assert_not_called()
        self.assertEqual(self._last_result()["status"], "error")

    def test_process_reports_transmit_failure(self):
        self.transmit.side_effect = RuntimeError("tx CLI failed (1)")

        with self.assertLogs(level="ERROR"):
            self.bridge.process_one("example", "cmd1")

        self.assertEqual(self._last_result()["error"], "tx CLI failed (1)")


if __name__ == "__main__":
    unittest.main()
