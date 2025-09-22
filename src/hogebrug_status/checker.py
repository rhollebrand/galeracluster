"""Core logic for determining the Hogebrug bridge status.

The application uses the public Rotterdam open data portal. Because the data
model of the datasets on the portal can change over time, the logic in this
module is intentionally defensive: it tries to interpret a record in multiple
ways before giving up.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional
from urllib import error as _urlerror
from urllib import parse as _urlparse
from urllib import request as _urlrequest

__all__ = ["BridgeStatus", "BridgeStatusChecker", "BridgeStatusError"]


DEFAULT_DATASET = "brugopeningen"
DEFAULT_URL = "https://rotterdam.dataplatform.nl/api/records/1.0/search/"
DEFAULT_ROWS = 5
DEFAULT_TIMEOUT = 10

OPEN_KEYWORDS = {
    "open",
    "weer open",
    "openstaand",
    "open voor verkeer",
    "open voor scheepvaart",
    "vrijgegeven",
}
CLOSED_KEYWORDS = {
    "dicht",
    "gesloten",
    "afgesloten",
    "gestremd",
    "stremming",
}


class BridgeStatusError(RuntimeError):
    """Raised when the bridge status could not be determined."""


@dataclass(frozen=True)
class BridgeStatus:
    """Represents the interpreted status for a bridge."""

    is_open: Optional[bool]
    summary: str
    observed_at: Optional[_dt.datetime]
    source_url: str
    raw_fields: Mapping[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Return a serialisable representation for JSON output."""

        return {
            "is_open": self.is_open,
            "summary": self.summary,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "source_url": self.source_url,
            "raw_fields": self._json_safe(self.raw_fields),
        }

    @staticmethod
    def _json_safe(value: Any) -> Any:
        try:
            json.dumps(value)
            return value
        except TypeError:
            if isinstance(value, Mapping):
                return {k: BridgeStatus._json_safe(v) for k, v in value.items()}
            if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
                return [BridgeStatus._json_safe(v) for v in value]
            return str(value)

    @property
    def label(self) -> str:
        if self.is_open is True:
            return "open"
        if self.is_open is False:
            return "dicht"
        return "onbekend"


class BridgeStatusChecker:
    """Fetch and interpret the Hogebrug status from Rotterdam open data."""

    def __init__(
        self,
        *,
        dataset: str = DEFAULT_DATASET,
        bridge_name: str = "Hogebrug",
        base_url: str = DEFAULT_URL,
        rows: int = DEFAULT_ROWS,
        timeout: int = DEFAULT_TIMEOUT,
        opener: Optional[_urlrequest.OpenerDirector] = None,
    ) -> None:
        self.dataset = dataset
        self.bridge_name = bridge_name
        self.base_url = base_url
        self.rows = rows
        self.timeout = timeout
        self._opener = opener or _urlrequest.build_opener()
        self._last_url: Optional[str] = None

    def get_status(self) -> BridgeStatus:
        """Return the most recent known bridge status."""

        payload = self._download()
        records = self._extract_records(payload)
        if not records:
            raise BridgeStatusError("Geen gegevens ontvangen van de open-data bron.")

        statuses = [self._record_to_status(record) for record in records]
        statuses = [status for status in statuses if status is not None]
        if not statuses:
            raise BridgeStatusError("Kon de status niet interpreteren uit de brongegevens.")

        statuses.sort(key=lambda s: s.observed_at or _dt.datetime.min.replace(tzinfo=_dt.timezone.utc), reverse=True)
        for status in statuses:
            if status.is_open is not None:
                return status
        return statuses[0]

    # ------------------------------------------------------------------
    # Network helpers
    def _download(self) -> Mapping[str, Any]:
        params = {
            "dataset": self.dataset,
            "q": self.bridge_name,
            "rows": self.rows,
            "sort": "-record_timestamp",
        }
        query = _urlparse.urlencode(params, doseq=True)
        url = f"{self.base_url}?{query}" if query else self.base_url
        self._last_url = url
        try:
            with self._opener.open(url, timeout=self.timeout) as response:
                status_code = getattr(response, "status", None) or response.getcode()
                if status_code and status_code >= 400:
                    raise BridgeStatusError(
                        f"De open-data bron gaf een foutmelding ({status_code})."
                    )
                raw = response.read()
        except _urlerror.URLError as exc:
            raise BridgeStatusError(f"Netwerkfout tijdens ophalen gegevens: {exc}") from exc

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        try:
            return json.loads(text)
        except ValueError as exc:
            raise BridgeStatusError("Kon de JSON-respons niet lezen.") from exc

    def _extract_records(self, payload: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        if not isinstance(payload, Mapping):
            return []
        for key in ("records", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
        return []

    # ------------------------------------------------------------------
    # Interpretation logic
    def _record_to_status(self, record: Mapping[str, Any]) -> Optional[BridgeStatus]:
        fields = self._extract_fields(record)
        observed_at = self._determine_observed_at(record, fields)
        summary_prefix = "Brongegevens konden niet geïnterpreteerd worden"
        interpreted_status = self._interpret_status(fields)
        if interpreted_status is None:
            return None
        is_open, summary = interpreted_status
        full_summary = summary if summary else summary_prefix
        return BridgeStatus(
            is_open=is_open,
            summary=full_summary,
            observed_at=observed_at,
            source_url=self._source_url(),
            raw_fields=fields,
        )

    def _extract_fields(self, record: Mapping[str, Any]) -> Mapping[str, Any]:
        if "fields" in record and isinstance(record["fields"], Mapping):
            return record["fields"]  # type: ignore[return-value]
        return record

    def _determine_observed_at(
        self, record: Mapping[str, Any], fields: Mapping[str, Any]
    ) -> Optional[_dt.datetime]:
        candidates: List[_dt.datetime] = []
        record_timestamp = record.get("record_timestamp")
        dt = self._parse_datetime(record_timestamp)
        if dt:
            candidates.append(dt)
        for key, value in fields.items():
            dt = self._parse_datetime(value)
            if dt:
                candidates.append(dt)
        if not candidates:
            return None
        candidates.sort()
        return candidates[-1]

    def _interpret_status(self, fields: Mapping[str, Any]) -> Optional[tuple[Optional[bool], str]]:
        textual = self._status_from_textual_fields(fields)
        if textual is not None:
            return textual
        temporal = self._status_from_temporal_fields(fields)
        if temporal is not None:
            return temporal
        boolean = self._status_from_boolean_fields(fields)
        if boolean is not None:
            return boolean
        return None

    def _status_from_textual_fields(self, fields: Mapping[str, Any]) -> Optional[tuple[Optional[bool], str]]:
        for key, value in fields.items():
            if not isinstance(value, str):
                continue
            normalized = value.strip().lower()
            if not normalized:
                continue
            if any(keyword in normalized for keyword in OPEN_KEYWORDS):
                return True, f"Veld '{key}' meldt: {value}"
            if any(keyword in normalized for keyword in CLOSED_KEYWORDS):
                return False, f"Veld '{key}' meldt: {value}"
        return None

    def _status_from_temporal_fields(self, fields: Mapping[str, Any]) -> Optional[tuple[Optional[bool], str]]:
        open_candidates: List[_dt.datetime] = []
        close_candidates: List[_dt.datetime] = []
        for key, value in fields.items():
            dt = self._parse_datetime(value)
            if not dt:
                continue
            lower_key = key.lower()
            if any(token in lower_key for token in ("open", "start", "begin")):
                open_candidates.append(dt)
            if any(token in lower_key for token in ("dicht", "sluit", "eind", "close")):
                close_candidates.append(dt)
        if not open_candidates and not close_candidates:
            return None
        open_dt = max(open_candidates) if open_candidates else None
        close_dt = max(close_candidates) if close_candidates else None
        if open_dt and (not close_dt or close_dt < open_dt):
            return True, "Laatste melding bevat geen sluitingstijd."
        if close_dt and (not open_dt or close_dt >= open_dt):
            return False, "Laatste melding bevat een sluitingstijd."
        return None

    def _status_from_boolean_fields(self, fields: Mapping[str, Any]) -> Optional[tuple[Optional[bool], str]]:
        for key, value in fields.items():
            if isinstance(value, bool):
                return bool(value), f"Booleaanse status in veld '{key}'."
            if isinstance(value, (int, float)) and value in (0, 1):
                interpreted = bool(value)
                return interpreted, f"Numerieke status in veld '{key}'."
        return None

    # ------------------------------------------------------------------
    # Helpers
    def _parse_datetime(self, value: Any) -> Optional[_dt.datetime]:
        if isinstance(value, _dt.datetime):
            return value if value.tzinfo else value.replace(tzinfo=_dt.timezone.utc)
        if isinstance(value, (int, float)):
            if value > 1e12:
                value = value / 1000.0
            try:
                return _dt.datetime.fromtimestamp(value, tz=_dt.timezone.utc)
            except (OverflowError, OSError):
                return None
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        cleaned = cleaned.replace("Z", "+00:00")
        try:
            return _dt.datetime.fromisoformat(cleaned)
        except ValueError:
            pass
        fmts = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
        ]
        for fmt in fmts:
            try:
                naive = _dt.datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
            return naive.replace(tzinfo=_dt.timezone.utc)
        return None

    def _source_url(self) -> str:
        return self._last_url or self.base_url


__all__ = ["BridgeStatus", "BridgeStatusChecker", "BridgeStatusError"]
