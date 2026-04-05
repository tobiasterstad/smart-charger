from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from smart_charger.chargers import (
    ChargerStatus,
    CtekCharger,
    CtekClient,
    CtekOperatingMode,
    CtekSettings,
)
from smart_charger.lib.ctek.exceptions import InvalidTokenException
from smart_charger.zaptec import OperatingMode


class TestCtekOperatingMode:
    def test_from_connector_status_charging(self):
        assert (
            CtekOperatingMode.from_connector_status("Charging")
            == CtekOperatingMode.Connected_Charging
        )

    def test_from_connector_status_disconnected(self):
        assert (
            CtekOperatingMode.from_connector_status("Disconnected")
            == CtekOperatingMode.Disconnected
        )

    def test_from_connector_status_available(self):
        assert (
            CtekOperatingMode.from_connector_status("Available")
            == CtekOperatingMode.Connected_Requesting
        )

    def test_from_connector_status_finished(self):
        assert (
            CtekOperatingMode.from_connector_status("Finished")
            == CtekOperatingMode.Connected_Finished
        )

    def test_from_connector_status_faulted(self):
        assert (
            CtekOperatingMode.from_connector_status("Faulted")
            == CtekOperatingMode.Error
        )

    def test_from_connector_status_unknown(self):
        assert (
            CtekOperatingMode.from_connector_status("UnknownState")
            == CtekOperatingMode.Unknown
        )

    def test_from_connector_status_with_spaces(self):
        assert (
            CtekOperatingMode.from_connector_status("Suspended EV")
            == CtekOperatingMode.Connected_Requesting
        )

    def test_to_operating_mode_charging(self):
        assert (
            CtekOperatingMode.Connected_Charging.to_operating_mode()
            == OperatingMode.Connected_Charging
        )

    def test_to_operating_mode_disconnected(self):
        assert (
            CtekOperatingMode.Disconnected.to_operating_mode()
            == OperatingMode.Disconnected
        )

    def test_to_operating_mode_error_maps_to_disconnected(self):
        assert CtekOperatingMode.Error.to_operating_mode() == OperatingMode.Disconnected


class TestCtekClient:
    @patch("smart_charger.chargers.requests.post")
    def test_authenticate_with_password(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = (
            '{"access_token": "abc123", "refresh_token": "ref456", "expires_in": 3600}'
        )

        client = CtekClient(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
            device_id="dev1",
        )
        client.authenticate()

        assert client.access_token == "abc123"
        assert client.refresh_token == "ref456"
        assert client._is_token_valid()

    @patch("smart_charger.chargers.requests.post")
    def test_authenticate_uses_valid_token(self, mock_post):
        future = datetime.datetime.now() + datetime.timedelta(hours=1)
        client = CtekClient(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
            device_id="dev1",
            access_token="existing",
            token_expires_at=future,
        )
        client.authenticate()

        mock_post.assert_not_called()
        assert client.access_token == "existing"

    @patch("smart_charger.chargers.requests.post")
    def test_authenticate_refreshes_token(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = (
            '{"access_token": "new_token", "expires_in": 3600}'
        )

        client = CtekClient(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
            device_id="dev1",
            refresh_token="old_refresh",
        )
        client.authenticate()

        assert client.access_token == "new_token"
        assert mock_post.call_count == 1
        call_payload = mock_post.call_args.kwargs["data"]
        assert "grant_type=refresh_token" in call_payload

    @patch("smart_charger.chargers.requests.post")
    def test_authenticate_falls_back_to_password_on_invalid_refresh(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = (
            '{"access_token": "pwd_token", "expires_in": 3600}'
        )

        client = CtekClient(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
            device_id="dev1",
            refresh_token="expired",
        )
        client.authenticate()

        assert client.access_token == "pwd_token"

    @patch("smart_charger.chargers.requests.post")
    def test_on_token_refreshed_callback(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = '{"access_token": "abc", "expires_in": 7200}'
        callback = MagicMock()

        client = CtekClient(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
            device_id="dev1",
            on_token_refreshed=callback,
        )
        client.authenticate()

        callback.assert_called_once_with("abc", 7200)

    @patch("smart_charger.chargers.requests.get")
    @patch("smart_charger.chargers.requests.post")
    def test_get_status(self, mock_post, mock_get):
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = '{"access_token": "tok", "expires_in": 3600}'
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = '{"deviceId": "dev1", "device_name": "Test", "connectors": [{"id": 1, "deviceId": "dev1", "currentStatus": "Charging", "statusReason": "", "statusString": "", "status": 1}], "connected": true}'

        client = CtekClient(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
            device_id="dev1",
        )
        client.authenticate()
        info = client.get_status()

        assert info.device_id == "dev1"
        assert len(info.connectors) == 1
        assert info.connectors[0].current_status == "Charging"
        assert info.connected

    @patch("smart_charger.chargers.requests.post")
    def test_set_enable_charging(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = '{"access_token": "tok", "expires_in": 3600}'

        client = CtekClient(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
            device_id="dev1",
        )
        client.authenticate()
        mock_post.reset_mock()
        mock_post.return_value.status_code = 200

        client.set_enable_charging(True)

        call_json = mock_post.call_args.kwargs["json"]
        assert call_json["instruction"] == "RESUME_CHARGING"
        assert call_json["device_id"] == "dev1"

    @patch("smart_charger.chargers.requests.post")
    def test_set_max_current(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = '{"access_token": "tok", "expires_in": 3600}'

        client = CtekClient(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
            device_id="dev1",
        )
        client.authenticate()
        mock_post.reset_mock()
        mock_post.return_value.status_code = 200

        client.set_max_current(16)

        call_json = mock_post.call_args.kwargs["json"]
        assert call_json["CurrentMaxAssignment"] == "16"

    def test_set_max_current_invalid_value(self):
        client = CtekClient(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
            device_id="dev1",
        )
        with pytest.raises(ValueError, match="Invalid current value"):
            client.set_max_current(7)

    @patch("smart_charger.chargers.requests.post")
    def test_request_token_raises_on_failure(self, mock_post):
        mock_post.return_value.status_code = 401
        mock_post.return_value.text = '{"error": "invalid_grant"}'

        client = CtekClient(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
            device_id="dev1",
        )
        with pytest.raises(InvalidTokenException):
            client.authenticate()


class TestCtekCharger:
    def _make_charger(self, mock_client, read_only=False):
        settings = CtekSettings(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
            device_id="dev1",
        )
        with patch.object(CtekCharger, "model_post_init"):
            charger = CtekCharger(id="ctek1", settings=settings, read_only=read_only)
        charger._client = mock_client
        return charger

    def test_charger_type(self):
        settings = CtekSettings(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
            device_id="dev1",
        )
        with patch.object(CtekCharger, "model_post_init"):
            charger = CtekCharger(id="ctek1", settings=settings)
        assert charger.charger_type().value == "ctek"

    def test_set_current_valid(self):
        mock_client = MagicMock()
        charger = self._make_charger(mock_client)
        charger.set_current(16)
        assert charger.current == 16
        mock_client.set_max_current.assert_called_once_with(16)

    def test_set_current_zero(self):
        mock_client = MagicMock()
        charger = self._make_charger(mock_client)
        charger.set_current(0)
        assert charger.current == 0
        mock_client.set_max_current.assert_not_called()

    def test_set_current_invalid(self):
        mock_client = MagicMock()
        charger = self._make_charger(mock_client)
        with pytest.raises(ValueError, match="Current must be 0 or between 6 and 16 A"):
            charger.set_current(20)

    def test_set_current_read_only(self):
        mock_client = MagicMock()
        charger = self._make_charger(mock_client, read_only=True)
        charger.set_current(16)
        assert charger.current == 16
        mock_client.set_max_current.assert_not_called()

    def test_start_charging(self):
        mock_client = MagicMock()
        mock_connector = MagicMock()
        mock_connector.current_status = "Available"
        mock_device_info = MagicMock()
        mock_device_info.connectors = [mock_connector]
        mock_client.get_status.return_value = mock_device_info
        charger = self._make_charger(mock_client)
        charger.start_charging()
        assert charger.status == ChargerStatus.CHARGING
        mock_client.set_enable_charging.assert_called_once_with(True)

    def test_start_charging_already_charging(self):
        mock_client = MagicMock()
        mock_client.get_status.return_value = OperatingMode.Connected_Charging
        charger = self._make_charger(mock_client)
        charger.start_charging()
        assert charger.status == ChargerStatus.CHARGING
        mock_client.set_enable_charging.assert_not_called()

    def test_start_charging_read_only(self):
        mock_client = MagicMock()
        charger = self._make_charger(mock_client, read_only=True)
        charger.start_charging()
        assert charger.status == ChargerStatus.CHARGING
        mock_client.set_enable_charging.assert_not_called()

    def test_stop_charging(self):
        mock_client = MagicMock()
        charger = self._make_charger(mock_client)
        charger.stop_charging()
        assert charger.status == ChargerStatus.CONNECTED
        mock_client.set_enable_charging.assert_called_once_with(False)

    def test_stop_charging_read_only(self):
        mock_client = MagicMock()
        charger = self._make_charger(mock_client, read_only=True)
        charger.stop_charging()
        assert charger.status == ChargerStatus.CONNECTED
        mock_client.set_enable_charging.assert_not_called()

    def test_get_status(self):
        mock_client = MagicMock()
        mock_connector = MagicMock()
        mock_connector.current_status = "Charging"
        mock_device_info = MagicMock()
        mock_device_info.connectors = [mock_connector]
        mock_client.get_status.return_value = mock_device_info

        charger = self._make_charger(mock_client)
        result = charger.get_status()
        assert result == OperatingMode.Connected_Charging

    def test_get_status_no_connectors(self):
        mock_client = MagicMock()
        mock_device_info = MagicMock()
        mock_device_info.connectors = []
        mock_client.get_status.return_value = mock_device_info

        charger = self._make_charger(mock_client)
        result = charger.get_status()
        assert result == OperatingMode.Disconnected

    def test_get_status_no_client(self):
        charger = self._make_charger(None)
        result = charger.get_status()
        assert result == OperatingMode.Disconnected

    def test_map_status_charging(self):
        assert CtekCharger.map_status("Charging") == ChargerStatus.CHARGING

    def test_map_status_disconnected(self):
        assert CtekCharger.map_status("Disconnected") == ChargerStatus.DISCONNECTED

    def test_map_status_available(self):
        assert CtekCharger.map_status("Available") == ChargerStatus.CONNECTED

    def test_map_status_finished(self):
        assert CtekCharger.map_status("Finished") == ChargerStatus.FINISHED

    def test_get_connected_from_status(self):
        assert CtekCharger.get_connected_from_status("Charging") is True
        assert CtekCharger.get_connected_from_status("Available") is True
        assert CtekCharger.get_connected_from_status("Disconnected") is False
        assert CtekCharger.get_connected_from_status("Faulted") is False

    def test_get_charging_from_status(self):
        assert CtekCharger.get_charging_from_status("Charging") is True
        assert CtekCharger.get_charging_from_status("Available") is False
        assert CtekCharger.get_charging_from_status("Disconnected") is False
