import json
from urllib import error as urlerror

import pytest

from hogebrug_status.checker import BridgeStatusChecker, BridgeStatusError


class DummyResponse:
    def __init__(self, json_data, status=200, raw_bytes=None):
        self._json_data = json_data
        self.status = status
        self._raw_bytes = raw_bytes

    def read(self):
        if self._raw_bytes is not None:
            return self._raw_bytes
        return json.dumps(self._json_data).encode("utf-8")

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DummyOpener:
    def __init__(self, response):
        self.response = response
        self.open_calls = []

    def open(self, url, timeout=None):
        self.open_calls.append({"url": url, "timeout": timeout})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def build_checker(response):
    opener = DummyOpener(response)
    checker = BridgeStatusChecker(opener=opener)
    return checker, opener


def test_textual_open_status():
    response = DummyResponse(
        {
            "records": [
                {
                    "record_timestamp": "2024-04-20T11:00:00+02:00",
                    "fields": {"melding": "Brug weer open voor verkeer"},
                }
            ]
        }
    )
    checker, opener = build_checker(response)
    status = checker.get_status()
    assert status.is_open is True
    assert "weer open" in status.summary.lower()
    assert status.observed_at.isoformat().startswith("2024-04-20")
    assert "dataset=brugopeningen" in opener.open_calls[0]["url"]


def test_textual_closed_status():
    response = DummyResponse(
        {
            "records": [
                {
                    "record_timestamp": "2024-04-21T11:00:00+02:00",
                    "fields": {"opmerking": "Brug dicht vanwege onderhoud"},
                }
            ]
        }
    )
    checker, _ = build_checker(response)
    status = checker.get_status()
    assert status.is_open is False
    assert "dicht" in status.summary.lower()


def test_boolean_status():
    response = DummyResponse(
        {
            "records": [
                {
                    "record_timestamp": "2024-04-22T08:00:00+02:00",
                    "fields": {"is_open": True},
                }
            ]
        }
    )
    checker, _ = build_checker(response)
    status = checker.get_status()
    assert status.is_open is True


def test_temporal_status_infers_open():
    response = DummyResponse(
        {
            "records": [
                {
                    "record_timestamp": "2024-04-23T10:00:00+02:00",
                    "fields": {
                        "opening_start": "2024-04-23T09:50:00+02:00",
                    },
                }
            ]
        }
    )
    checker, _ = build_checker(response)
    status = checker.get_status()
    assert status.is_open is True
    assert "geen sluitingstijd" in status.summary.lower()


def test_temporal_status_infers_closed():
    response = DummyResponse(
        {
            "records": [
                {
                    "record_timestamp": "2024-04-24T10:00:00+02:00",
                    "fields": {
                        "opening_start": "2024-04-24T09:50:00+02:00",
                        "sluiting": "2024-04-24T09:55:00+02:00",
                    },
                }
            ]
        }
    )
    checker, _ = build_checker(response)
    status = checker.get_status()
    assert status.is_open is False
    assert "sluitingstijd" in status.summary.lower()


def test_no_records_raises():
    response = DummyResponse({"records": []})
    checker, _ = build_checker(response)
    with pytest.raises(BridgeStatusError):
        checker.get_status()


def test_http_error_raises():
    response = DummyResponse({}, status=500)
    checker, _ = build_checker(response)
    with pytest.raises(BridgeStatusError):
        checker.get_status()


def test_invalid_json_raises():
    response = DummyResponse({}, raw_bytes=b"not-json")
    checker, _ = build_checker(response)
    with pytest.raises(BridgeStatusError):
        checker.get_status()


def test_network_error_raises():
    opener_error = urlerror.URLError("kapot")
    checker, _ = build_checker(opener_error)
    with pytest.raises(BridgeStatusError):
        checker.get_status()
