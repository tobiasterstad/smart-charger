import unittest
from unittest.mock import patch

from smart_charger.chargers import ZaptecCharger, ZaptecSettings
from smart_charger.zaptec import OperatingMode


class FakeZaptecClient:
    def __init__(self, *args, **kwargs):
        self.authenticated = False

    def authenticate(self, username: str, password: str):
        self.authenticated = True
        return "fake-token"

    def update_installation(self, installation_id: str, available_current: float):
        # no-op for tests
        return None

    def send_charger_command(self, charger_id: str, command_id: object):
        # no-op
        return None

    def get_charger_details(self, charger_id: str):
        # Return a simple object with operating_mode attribute for potential future tests
        return type(
            "D", (), {"operating_mode": OperatingMode.Connected_Charging.value}
        )()


class TestZaptecChargerUpdateStatus(unittest.TestCase):
    def setUp(self):
        # Patch the ZaptecClient used in chargers to avoid real network calls
        p = patch("smart_charger.chargers.ZaptecClient", FakeZaptecClient)
        self._patch = p
        self._patcher = p.start()

        # Create basic settings for the charger
        self.settings = ZaptecSettings(
            username="u",
            password="p",
            installation_id="inst",
            charger_id="charger-1",
            base_url=None,
        )

        # Instantiate the ZaptecCharger (model_post_init will use FakeZaptecClient)
        self.charger = ZaptecCharger(id="z1", settings=self.settings)

    def tearDown(self):
        try:
            self._patch.stop()
        except Exception:
            pass

    def test_get_connected_from_status_true_for_connected_states(self):
        for name in [
            "Connected_Charging",
            "connected charging",
            "Connected-Charging",
            "charging",
            "3",  # numeric value for Connected_Charging
            "Connected_Requesting",
            "requesting",
            "Connected_Finished",
            "finished",
        ]:
            with self.subTest(name=name):
                result = ZaptecCharger.get_connected_from_status(name)
                self.assertTrue(result, msg=f"{name} should be considered connected")

    def test_get_connected_from_status_false_for_disconnected_or_unknown(self):
        for name in ["Disconnected", "disconnected", "0", "", None, "unrelated"]:
            with self.subTest(name=name):
                result = ZaptecCharger.get_connected_from_status(name)
                self.assertFalse(
                    result, msg=f"{name!r} should not be considered connected"
                )


if __name__ == "__main__":
    unittest.main()
