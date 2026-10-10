from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "gigaset_gateway" / "gigaset_gateway.py"
SPEC = importlib.util.spec_from_file_location("gigaset_gateway_module", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
gateway = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gateway)


class FakeMqttClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, bool]] = []
        self.subscribed: list[str] = []

    def publish(self, topic: str, payload: str, retain: bool = True) -> None:
        self.published.append((topic, payload, retain))

    def subscribe(self, topic: str) -> None:
        self.subscribed.append(topic)


def bridge(command_handler=None):
    instance = gateway.MqttBridge(
        {"enabled": False, "base_topic": "gigaset", "discovery_prefix": "homeassistant"},
        command_handler,
    )
    instance.client = FakeMqttClient()
    return instance


class PlugGatewayTests(unittest.TestCase):
    def test_sp01_discovery_creates_switch(self) -> None:
        mqtt = bridge()
        mqtt.publish_event(
            {
                "device_type": "sp01",
                "device_id": "02d5244d61",
                "sink": "ver",
                "payload": "00150000102700000110",
            },
            "192_168_178_172",
        )
        topics = {topic: json.loads(payload) for topic, payload, _retain in mqtt.client.published if topic.endswith("/config")}
        switch_topic = "homeassistant/switch/gigaset_sp01_02d5244d61_switch/config"
        self.assertIn(switch_topic, topics)
        config = topics[switch_topic]
        self.assertEqual(config["command_topic"], "gigaset/sp01/02d5244d61/set")
        self.assertEqual(config["state_topic"], "gigaset/sp01/02d5244d61/state")
        self.assertEqual(config["payload_on"], "ON")
        self.assertEqual(config["payload_off"], "OFF")

    def test_sp01_state_reporting(self) -> None:
        mqtt = bridge()
        mqtt.publish_event(
            {
                "device_type": "sp01",
                "device_id": "02d5244d61",
                "sink": "state",
                "payload": "1",
            },
            "192_168_178_172",
        )
        published = {topic: payload for topic, payload, _retain in mqtt.client.published}
        self.assertEqual(published.get("gigaset/sp01/02d5244d61/state"), "ON")

        mqtt.publish_event(
            {
                "device_type": "sp01",
                "device_id": "02d5244d61",
                "sink": "state",
                "payload": "0",
            },
            "192_168_178_172",
        )
        published = {topic: payload for topic, payload, _retain in mqtt.client.published}
        self.assertEqual(published.get("gigaset/sp01/02d5244d61/state"), "OFF")

    def test_mqtt_command_handler(self) -> None:
        commands = []
        def handler(action, dev_type, dev_id, base, command=""):
            commands.append((action, dev_type, dev_id, base, command))

        mqtt = bridge(handler)
        mqtt._on_message(
            None,
            None,
            SimpleNamespace(topic="gigaset/sp01/02d5244d61/set", payload=b"ON", retain=False),
        )
        self.assertEqual(commands, [("plug_on", "sp01", "02d5244d61", "", "")])
        published = {topic: payload for topic, payload, _retain in mqtt.client.published}
        self.assertEqual(published.get("gigaset/sp01/02d5244d61/state"), "ON")

        mqtt._on_message(
            None,
            None,
            SimpleNamespace(topic="gigaset/sp01/02d5244d61/set", payload=b"OFF", retain=False),
        )
        self.assertEqual(commands[-1], ("plug_off", "sp01", "02d5244d61", "", ""))
        published = {topic: payload for topic, payload, _retain in mqtt.client.published}
        self.assertEqual(published.get("gigaset/sp01/02d5244d61/state"), "OFF")

    def test_control_poll_line_generation(self) -> None:
        poll_line_on = gateway.control_poll_line(
            {
                "id": "req-1",
                "action": "plug_on",
                "device_id": "02d5244d61",
                "device_type": "sp01",
            }
        )
        self.assertEqual(poll_line_on, "endnode|req-1/plug_on|on|02d5244d61|sp01")

        poll_line_off = gateway.control_poll_line(
            {
                "id": "req-2",
                "action": "plug_off",
                "device_id": "02d5244d61",
                "device_type": "sp01",
            }
        )
        self.assertEqual(poll_line_off, "endnode|req-2/plug_off|off|02d5244d61|sp01")


if __name__ == "__main__":
    unittest.main()
