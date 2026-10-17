"""Brightness (Hue V2 dimming) through the same simulated Bridge boundary as test_api."""

import unittest
from unittest.mock import call

from test_api import APP_KEY, LIGHT_ID, SECOND_ID, resource, running_api


def dimmable(light_id=LIGHT_ID, name="Dnevna soba", on=True, brightness=40.0):
    item = resource(light_id, name, on)
    item["dimming"] = {"brightness": brightness, "min_dim_level": 0.2}
    return item


class BrightnessTests(unittest.TestCase):
    def test_get_reports_brightness_only_for_dimmable_lights(self):
        with running_api([dimmable(brightness=39.37), resource(SECOND_ID, "Utičnica")]) as (client, _, _):
            response = client.get("/api/lights")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), [
                {"id": LIGHT_ID, "name": "Dnevna soba", "on": True, "brightness": 39.37},
                {"id": SECOND_ID, "name": "Utičnica", "on": False},
            ])

    def test_brightness_and_on_are_sent_with_aiohue_and_read_back(self):
        path = f"clip/v2/resource/light/{LIGHT_ID}"
        with running_api([dimmable(on=False)]) as (client, bridge, _):
            response = client.put(f"/api/lights/{LIGHT_ID}", json={"on": True, "brightness": 75})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {
                "id": LIGHT_ID, "name": "Dnevna soba", "on": True, "brightness": 75,
            })
            response = client.put(f"/api/lights/{LIGHT_ID}", json={"brightness": 12.5})
            self.assertEqual(response.json()["brightness"], 12.5)
            self.assertEqual(bridge.request.await_args_list, [
                call("put", path, json={"on": {"on": True}, "dimming": {"brightness": 75.0}}),
                call("get", path),
                call("get", "clip/v2/resource/zigbee_connectivity"),
                call("put", path, json={"dimming": {"brightness": 12.5}}),
                call("get", path),
                call("get", "clip/v2/resource/zigbee_connectivity"),
            ])

    def test_invalid_brightness_commands_never_reach_the_bridge(self):
        invalid = [
            {}, {"brightness": 0}, {"brightness": 100.5}, {"brightness": -5},
            {"brightness": "50"}, {"brightness": True}, {"brightness": None},
            {"on": None}, {"brightness": 50, "color": "red"},
        ]
        with running_api([dimmable()]) as (client, bridge, _):
            for body in invalid:
                with self.subTest(body=body):
                    response = client.put(f"/api/lights/{LIGHT_ID}", json=body)
                    self.assertEqual(response.status_code, 422)
                    self.assertIn("brightness", response.json()["detail"])
                    self.assertNotIn(APP_KEY, response.text)
            bridge.request.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
