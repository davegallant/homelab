#!/usr/bin/env python3
"""Cron-friendly GasBuddy price watcher with Gotify notifications.

Alerts are drop-based: gaswatch records the cheapest observed price on every
run and notifies when it falls a configured amount below its recent high, so
there is no manual price threshold to maintain.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import tempfile
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

import aiohttp
from dotenv import load_dotenv
from py_gasbuddy import APIError, CloudflareBlocked, GasBuddy, LibraryError


MILES_TO_KM = 1.609344
MIN_PRICE_CPL = 50.0
MAX_PRICE_CPL = 300.0
FUTURE_TOLERANCE = timedelta(minutes=5)
STATE_VERSION = 2
MAX_OBSERVATIONS = 500
FUEL_GRADES = {
    "regular": (1, "regular_gas"),
    "midgrade": (2, "midgrade_gas"),
    "premium": (3, "premium_gas"),
    "diesel": (4, "diesel"),
    "e85": (5, "e85"),
    "unl88": (12, "unl88"),
}


class ConfigError(ValueError):
    """Raised when environment configuration is missing or invalid."""


class StateError(ValueError):
    """Raised when persisted alert state is unreadable or invalid."""


class GaswatchError(RuntimeError):
    """Raised for operational failures safe to show to an operator."""


class AlertAction(str, Enum):
    """Action selected for the current price observation."""

    ALERT = "alert"
    SUPPRESSED = "suppressed"
    WATCHING = "watching"


class Mode(str, Enum):
    """Requested command-line operating mode."""

    NORMAL = "normal"
    DRY_RUN = "dry-run"
    LIST = "list"


@dataclass(frozen=True)
class Config:
    """Validated gaswatch configuration."""

    location: str
    latitude: float
    longitude: float
    radius_km: float
    fuel_grade: str
    drop_cpl: float
    drop_lookback: timedelta
    hysteresis_cpl: float
    quiet_hours: tuple[int, int] | None
    max_price_age: timedelta
    gotify_url: str | None
    gotify_token: str | None
    state_file: Path
    gasbuddy_cache_file: Path
    timeout_seconds: float
    favourite_station_ids: frozenset[str]

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        require_gotify: bool,
    ) -> Config:
        """Build and validate configuration from environment variables."""
        values = os.environ if env is None else env

        def required(name: str) -> str:
            value = values.get(name, "").strip()
            if not value:
                raise ConfigError(f"{name} is required")
            return value

        def finite_float(name: str, *, positive: bool = False) -> float:
            raw = required(name)
            try:
                value = float(raw)
            except ValueError as exc:
                raise ConfigError(f"{name} must be a number") from exc
            if not math.isfinite(value) or (positive and value <= 0):
                qualifier = "a positive finite number" if positive else "finite"
                raise ConfigError(f"{name} must be {qualifier}")
            return value

        def optional_float(name: str, default: float) -> float:
            raw = values.get(name, "").strip()
            if not raw:
                return default
            try:
                value = float(raw)
            except ValueError as exc:
                raise ConfigError(f"{name} must be a number") from exc
            if not math.isfinite(value) or value <= 0:
                raise ConfigError(
                    f"{name} must be a positive finite number"
                )
            return value

        location = required("GASWATCH_LOCATION")
        latitude = finite_float("GASWATCH_LATITUDE")
        longitude = finite_float("GASWATCH_LONGITUDE")
        if not -90 <= latitude <= 90:
            raise ConfigError("GASWATCH_LATITUDE must be between -90 and 90")
        if not -180 <= longitude <= 180:
            raise ConfigError("GASWATCH_LONGITUDE must be between -180 and 180")

        fuel_grade = values.get("GASWATCH_FUEL_GRADE", "regular").strip().lower()
        if fuel_grade not in FUEL_GRADES:
            supported = ", ".join(FUEL_GRADES)
            raise ConfigError(f"GASWATCH_FUEL_GRADE must be one of: {supported}")

        gotify_url = values.get("GASWATCH_GOTIFY_URL", "").strip() or None
        gotify_token = values.get("GASWATCH_GOTIFY_TOKEN", "").strip() or None
        if require_gotify and (gotify_url is None or gotify_token is None):
            raise ConfigError(
                "GASWATCH_GOTIFY_URL and GASWATCH_GOTIFY_TOKEN are required"
            )

        quiet_raw = values.get("GASWATCH_QUIET_HOURS", "").strip()
        quiet_hours = _parse_quiet_hours(quiet_raw) if quiet_raw else None

        max_age_hours = finite_float(
            "GASWATCH_MAX_PRICE_AGE_HOURS", positive=True
        )
        timeout_raw = values.get("GASWATCH_TIMEOUT_SECONDS", "20").strip()
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise ConfigError("GASWATCH_TIMEOUT_SECONDS must be a number") from exc
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ConfigError(
                "GASWATCH_TIMEOUT_SECONDS must be a positive finite number"
            )

        cache_path = values.get(
            "GASWATCH_GASBUDDY_CACHE_FILE", ".gasbuddy-token.json"
        ).strip()
        if not cache_path:
            raise ConfigError("GASWATCH_GASBUDDY_CACHE_FILE cannot be blank")

        favourites_raw = values.get("GASWATCH_FAVOURITE_STATION_IDS", "").strip()
        favourite_station_ids: frozenset[str] = frozenset()
        if favourites_raw:
            favourite_parts = [part.strip() for part in favourites_raw.split(",")]
            if any(not part or not part.isdecimal() for part in favourite_parts):
                raise ConfigError(
                    "GASWATCH_FAVOURITE_STATION_IDS must be comma-separated "
                    "numeric station IDs"
                )
            favourite_station_ids = frozenset(favourite_parts)

        return cls(
            location=location,
            latitude=latitude,
            longitude=longitude,
            radius_km=finite_float("GASWATCH_RADIUS_KM", positive=True),
            fuel_grade=fuel_grade,
            drop_cpl=optional_float("GASWATCH_DROP_CPL", 4.0),
            drop_lookback=timedelta(
                hours=optional_float("GASWATCH_DROP_LOOKBACK_HOURS", 24.0)
            ),
            hysteresis_cpl=optional_float("GASWATCH_HYSTERESIS_CPL", 2.0),
            quiet_hours=quiet_hours,
            max_price_age=timedelta(hours=max_age_hours),
            gotify_url=gotify_url,
            gotify_token=gotify_token,
            state_file=Path(required("GASWATCH_STATE_FILE")),
            gasbuddy_cache_file=Path(cache_path),
            timeout_seconds=timeout_seconds,
            favourite_station_ids=favourite_station_ids,
        )


def _parse_quiet_hours(raw: str) -> tuple[int, int]:
    """Parse a "23-7" style quiet-hours range into a (start, end) hour pair."""
    parts = raw.split("-")
    if len(parts) != 2:
        raise ConfigError('GASWATCH_QUIET_HOURS must look like "23-7"')
    try:
        start = int(parts[0].strip())
        end = int(parts[1].strip())
    except ValueError as exc:
        raise ConfigError(
            "GASWATCH_QUIET_HOURS hours must be integers"
        ) from exc
    if not 0 <= start <= 23 or not 0 <= end <= 23:
        raise ConfigError(
            "GASWATCH_QUIET_HOURS hours must be between 0 and 23"
        )
    if start == end:
        raise ConfigError("GASWATCH_QUIET_HOURS start and end must differ")
    return (start, end)


def in_quiet_hours(now: datetime, quiet_hours: tuple[int, int] | None) -> bool:
    """Check quiet hours against the timezone of the given timestamp.

    Callers pass a local timestamp; run() converts with astimezone() first.
    """
    if quiet_hours is None:
        return False
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    hour = now.hour + now.minute / 60 + now.second / 3600
    start, end = quiet_hours
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _local_now(moment: datetime) -> datetime:
    """Return the machine-local time for a timestamp (split out for tests)."""
    return moment.astimezone()


def lookback_label(lookback: timedelta) -> str:
    """Render a lookback window as a short label like "24h"."""
    hours = lookback.total_seconds() / 3600
    return f"{int(hours)}h" if hours.is_integer() else f"{hours:.1f}h"


@dataclass(frozen=True)
class Station:
    """A valid, normalized Canadian station price."""

    station_id: str
    name: str
    address: str
    price_cpl: float
    updated_at: datetime | None
    distance_km: float | None


@dataclass(frozen=True)
class Observation:
    """One recorded cheapest-price observation."""

    observed_at: datetime
    price_cpl: float
    station: str


@dataclass(frozen=True)
class AlertRecord:
    """The most recent alert that was sent (or deferred)."""

    observed_at: datetime
    price_cpl: float
    station: str
    drop_cpl: float


@dataclass(frozen=True)
class PendingAlert:
    """An alert held back by quiet hours, to be delivered later."""

    title: str
    message: str
    price_cpl: float
    station: str
    observed_at: datetime


@dataclass(frozen=True)
class WatchState:
    """Persisted watcher state (version 2)."""

    observations: tuple[Observation, ...]
    armed: bool
    last_alert: AlertRecord | None
    pending: PendingAlert | None


@dataclass(frozen=True)
class Decision:
    """Outcome of evaluating one price observation."""

    action: AlertAction
    drop_cpl: float
    reference_cpl: float | None
    armed: bool
    last_alert: AlertRecord | None


class PriceProvider(Protocol):
    """Replaceable station-price source."""

    async def fetch(self, config: Config) -> list[Station]:
        """Fetch valid stations sorted from cheapest to most expensive."""


Notifier = Callable[[Config, str, str], Awaitable[None]]


def decide_alert(
    price_cpl: float,
    station: str,
    history: Sequence[Observation],
    state: WatchState,
    now: datetime,
    *,
    drop_threshold_cpl: float,
    lookback: timedelta,
    hysteresis_cpl: float,
) -> Decision:
    """Decide whether a price observation should alert.

    ``history`` holds pruned observations *excluding* the current one. An
    alert fires when the price sits at least ``drop_threshold_cpl`` below the
    highest price seen inside ``lookback``. After an alert the watcher
    disarms until the price climbs ``hysteresis_cpl`` back above the alert
    price, or drops a further ``drop_threshold_cpl`` below it.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    current = now.astimezone(UTC)
    window = [item for item in history if item.observed_at >= current - lookback]
    if not window:
        # Warming up: not enough history to measure a drop against.
        return Decision(AlertAction.WATCHING, 0.0, None, state.armed, state.last_alert)

    reference_cpl = max(item.price_cpl for item in window)
    drop_cpl = reference_cpl - price_cpl
    armed = state.armed
    last_alert = state.last_alert

    if not armed and last_alert is not None:
        if price_cpl >= last_alert.price_cpl + hysteresis_cpl:
            armed = True
        elif last_alert.price_cpl - price_cpl >= drop_threshold_cpl:
            # Another full leg down while still disarmed: alert again.
            leg = last_alert.price_cpl - price_cpl
            new_alert = AlertRecord(current, price_cpl, station, leg)
            return Decision(AlertAction.ALERT, leg, reference_cpl, False, new_alert)

    if armed and drop_cpl >= drop_threshold_cpl:
        new_alert = AlertRecord(current, price_cpl, station, drop_cpl)
        return Decision(AlertAction.ALERT, drop_cpl, reference_cpl, False, new_alert)

    action = AlertAction.WATCHING if armed else AlertAction.SUPPRESSED
    return Decision(action, drop_cpl, reference_cpl, armed, last_alert)


def prune_observations(
    observations: Sequence[Observation], now: datetime, keep: timedelta
) -> tuple[Observation, ...]:
    """Drop observations older than the retention window."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    cutoff = now.astimezone(UTC) - keep
    return tuple(item for item in observations if item.observed_at >= cutoff)


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConfigError("malformed station update timestamp") from None
    if parsed.tzinfo is None:
        raise ConfigError("station update timestamp has no timezone")
    return parsed.astimezone(UTC)


def _parse_observation(data: object) -> Observation:
    if not isinstance(data, Mapping):
        raise ValueError("observation must be an object")
    price = _finite_number(data.get("price_cpl"))
    station = data.get("station")
    observed_at = _parse_timestamp(data.get("observed_at"))
    if (
        price is None
        or not isinstance(station, str)
        or not station.strip()
        or observed_at is None
    ):
        raise ValueError("observation fields have invalid types")
    return Observation(observed_at=observed_at, price_cpl=price, station=station)


def _parse_alert_record(data: object) -> AlertRecord:
    observation = _parse_observation(data)
    drop = _finite_number(data.get("drop_cpl")) if isinstance(data, Mapping) else None
    if drop is None:
        raise ValueError("alert record drop_cpl must be a finite number")
    return AlertRecord(
        observed_at=observation.observed_at,
        price_cpl=observation.price_cpl,
        station=observation.station,
        drop_cpl=drop,
    )


def _parse_pending_alert(data: object) -> PendingAlert:
    if not isinstance(data, Mapping):
        raise ValueError("pending alert must be an object")
    title = data.get("title")
    message = data.get("message")
    price = _finite_number(data.get("price_cpl"))
    station = data.get("station")
    observed_at = _parse_timestamp(data.get("observed_at"))
    if (
        not isinstance(title, str)
        or not title.strip()
        or not isinstance(message, str)
        or not message.strip()
        or price is None
        or not isinstance(station, str)
        or not station.strip()
        or observed_at is None
    ):
        raise ValueError("pending alert fields have invalid types")
    return PendingAlert(
        title=title,
        message=message,
        price_cpl=price,
        station=station,
        observed_at=observed_at,
    )


def _migrate_v1_state(data: Mapping[str, Any]) -> WatchState:
    """Upgrade a version 1 threshold state to version 2 drop-based state."""
    below = data.get("below_threshold")
    if not isinstance(below, bool):
        raise ValueError("below_threshold must be boolean")
    price = _finite_number(data.get("price_cpl"))
    station = data.get("station")
    observed_at = _parse_timestamp(data.get("observed_at"))
    if (
        price is None
        or not isinstance(station, str)
        or not station.strip()
        or observed_at is None
    ):
        raise ValueError("state fields have invalid types")
    observation = Observation(observed_at=observed_at, price_cpl=price, station=station)
    last_alert = (
        AlertRecord(
            observed_at=observed_at, price_cpl=price, station=station, drop_cpl=0.0
        )
        if below
        else None
    )
    return WatchState(
        observations=(observation,),
        armed=not below,
        last_alert=last_alert,
        pending=None,
    )


def load_state(path: Path) -> WatchState | None:
    """Load and strictly validate persisted watcher state."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise StateError(f"cannot read state file {path}: {exc}") from exc
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("state must be a JSON object")
        version = data.get("version")
        if version == 1:
            return _migrate_v1_state(data)
        if version != STATE_VERSION:
            raise ValueError("unsupported state format or version")
        observations = tuple(
            _parse_observation(item) for item in data.get("observations", [])
        )
        armed = data.get("armed", True)
        if not isinstance(armed, bool):
            raise ValueError("armed must be boolean")
        raw_last_alert = data.get("last_alert")
        raw_pending = data.get("pending")
        return WatchState(
            observations=observations,
            armed=armed,
            last_alert=(
                _parse_alert_record(raw_last_alert)
                if raw_last_alert is not None
                else None
            ),
            pending=(
                _parse_pending_alert(raw_pending) if raw_pending is not None else None
            ),
        )
    except (KeyError, TypeError, ValueError, ConfigError) as exc:
        raise StateError(f"invalid state file {path}: {exc}") from exc


def _observation_json(observation: Observation) -> dict[str, Any]:
    return {
        "observed_at": observation.observed_at.astimezone(UTC).isoformat(),
        "price_cpl": observation.price_cpl,
        "station": observation.station,
    }


def _alert_record_json(record: AlertRecord) -> dict[str, Any]:
    payload = _observation_json(
        Observation(record.observed_at, record.price_cpl, record.station)
    )
    payload["drop_cpl"] = record.drop_cpl
    return payload


def _pending_json(pending: PendingAlert) -> dict[str, Any]:
    return {
        "title": pending.title,
        "message": pending.message,
        "price_cpl": pending.price_cpl,
        "station": pending.station,
        "observed_at": pending.observed_at.astimezone(UTC).isoformat(),
    }


def save_state(path: Path, state: WatchState) -> None:
    """Atomically persist watcher state."""
    payload = {
        "version": STATE_VERSION,
        "armed": state.armed,
        "observations": [_observation_json(item) for item in state.observations],
        "last_alert": (
            _alert_record_json(state.last_alert) if state.last_alert is not None else None
        ),
        "pending": _pending_json(state.pending) if state.pending is not None else None,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except OSError as exc:
        if "temporary_path" in locals():
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise StateError(f"cannot write state file {path}: {exc}") from exc


def normalize_stations(
    raw_stations: Sequence[Mapping[str, Any]],
    *,
    fuel_key: str,
    radius_km: float,
    max_age: timedelta,
    now: datetime,
) -> list[Station]:
    """Filter and normalize untrusted provider results."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    current = now.astimezone(UTC)
    valid: list[Station] = []

    for raw in raw_stations:
        name_value = raw.get("name")
        name = name_value.strip() if isinstance(name_value, str) else ""
        if not name or raw.get("unit_of_measure") != "cents_per_liter":
            continue

        price_node = raw.get(fuel_key)
        if not isinstance(price_node, Mapping):
            continue
        price = _finite_number(price_node.get("price"))
        if price is None or not MIN_PRICE_CPL <= price <= MAX_PRICE_CPL:
            continue

        timestamp_value = price_node.get("last_updated")
        try:
            updated_at = _parse_timestamp(timestamp_value)
        except ConfigError:
            continue
        if updated_at is not None:
            age = current - updated_at
            if age > max_age or age < -FUTURE_TOLERANCE:
                continue

        raw_distance = raw.get("distance")
        distance_km: float | None = None
        if raw_distance is not None:
            distance_miles = _finite_number(raw_distance)
            if distance_miles is None or distance_miles < 0:
                continue
            distance_km = distance_miles * MILES_TO_KM
            if distance_km > radius_km:
                continue

        raw_address = raw.get("address")
        line1 = raw_address.get("line1") if isinstance(raw_address, Mapping) else None
        address = line1.strip() if isinstance(line1, str) and line1.strip() else "Address unknown"

        valid.append(
            Station(
                station_id=str(raw.get("station_id", "")),
                name=name,
                address=address,
                price_cpl=price,
                updated_at=updated_at,
                distance_km=distance_km,
            )
        )

    valid.sort(
        key=lambda item: (
            item.price_cpl,
            item.distance_km if item.distance_km is not None else math.inf,
            item.name.casefold(),
        )
    )
    return valid


class GasBuddyProvider:
    """Price provider backed by py-gasbuddy's unofficial GraphQL client."""

    async def fetch(self, config: Config) -> list[Station]:
        fuel_id, fuel_key = FUEL_GRADES[config.fuel_grade]
        client_options = {
            "cache_file": str(config.gasbuddy_cache_file),
            "timeout": int(config.timeout_seconds * 1000),
        }
        client = GasBuddy(**client_options)
        try:
            response = await client.price_lookup_service(
                lat=config.latitude,
                lon=config.longitude,
                limit=50,
                fuel=fuel_id,
            )
            raw_results = response.get("results")
            if not isinstance(raw_results, list):
                raise GaswatchError("GasBuddy returned a malformed station response")

            stations_by_id: dict[str, Mapping[str, Any]] = {
                str(item.get("station_id")): item
                for item in raw_results
                if isinstance(item, Mapping) and item.get("station_id") is not None
            }
            for station_id in sorted(config.favourite_station_ids, key=int):
                if station_id in stations_by_id:
                    continue
                favourite_client = GasBuddy(
                    station_id=int(station_id), **client_options
                )
                stations_by_id[station_id] = await favourite_client.price_lookup()
        except CloudflareBlocked as exc:
            raise GaswatchError(
                "GasBuddy access was blocked by Cloudflare; no CAPTCHA or "
                "anti-bot bypass was attempted"
            ) from exc
        except (APIError, LibraryError, aiohttp.ClientError, TimeoutError) as exc:
            raise GaswatchError(f"GasBuddy lookup failed: {exc}") from exc

        return normalize_stations(
            list(stations_by_id.values()),
            fuel_key=fuel_key,
            radius_km=config.radius_km,
            max_age=config.max_price_age,
            now=datetime.now(UTC),
        )


def _age_text(updated_at: datetime | None, now: datetime) -> str:
    if updated_at is None:
        return "unknown"
    total_minutes = max(0, int((now.astimezone(UTC) - updated_at).total_seconds() / 60))
    if total_minutes < 60:
        unit = "minute" if total_minutes == 1 else "minutes"
        return f"{total_minutes} {unit} ago"
    hours = total_minutes // 60
    unit = "hour" if hours == 1 else "hours"
    return f"{hours} {unit} ago"


def build_notification(
    stations: Sequence[Station],
    now: datetime,
    favourite_station_ids: frozenset[str] = frozenset(),
    *,
    drop_cpl: float | None = None,
    reference_cpl: float | None = None,
    lookback_label_text: str = "24h",
) -> tuple[str, str]:
    """Build a Gotify title and message for up to three stations."""
    if not stations:
        raise ValueError("at least one station is required")
    cheapest = stations[0]
    title = f"Gas is {cheapest.price_cpl:.1f}¢/L"
    favourite_prefix = "★ " if cheapest.station_id in favourite_station_ids else ""
    lines = [
        f"{favourite_prefix}{cheapest.name}",
        cheapest.address,
        f"{cheapest.price_cpl:.1f}¢/L",
        f"Updated {_age_text(cheapest.updated_at, now)}",
    ]
    if drop_cpl is not None and reference_cpl is not None and drop_cpl > 0:
        lines.append(
            f"Down {drop_cpl:.1f}¢ from {lookback_label_text} high "
            f"of {reference_cpl:.1f}¢/L"
        )
    if len(stations) > 1:
        lines.extend(["", "Next cheapest:"])
        lines.extend(
            f"{'★ ' if item.station_id in favourite_station_ids else ''}"
            f"{item.name} — {item.price_cpl:.1f}¢/L"
            for item in stations[1:3]
        )
    return title, "\n".join(lines)


async def send_gotify(config: Config, title: str, message: str) -> None:
    """Send one message using Gotify's standard application endpoint."""
    if config.gotify_url is None or config.gotify_token is None:
        raise GaswatchError("Gotify configuration is missing")
    endpoint = f"{config.gotify_url.rstrip('/')}/message"
    timeout = aiohttp.ClientTimeout(total=config.timeout_seconds)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                endpoint,
                params={"token": config.gotify_token},
                data={"title": title, "message": message, "priority": "5"},
            ) as response:
                if not 200 <= response.status < 300:
                    body = (await response.text())[:200].replace("\n", " ")
                    raise GaswatchError(
                        f"Gotify rejected message with HTTP {response.status}: {body}"
                    )
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise GaswatchError(
            f"Gotify request failed ({type(exc).__name__})"
        ) from exc


def format_station_table(
    stations: Sequence[Station],
    now: datetime,
    favourite_station_ids: frozenset[str] = frozenset(),
) -> str:
    """Render stations as a concise human-readable table."""
    headers = ("ID", "PRICE", "DISTANCE", "UPDATED", "STATION", "ADDRESS")
    rows = [headers]
    for item in stations:
        distance = f"{item.distance_km:.1f} km" if item.distance_km is not None else "unknown"
        rows.append(
            (
                item.station_id or "unknown",
                f"{item.price_cpl:.1f}¢/L",
                distance,
                _age_text(item.updated_at, now),
                f"{'★ ' if item.station_id in favourite_station_ids else ''}{item.name}",
                item.address,
            )
        )
    widths = [max(len(row[index]) for row in rows) for index in range(len(headers))]
    return "\n".join(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)).rstrip()
        for row in rows
    )


def _log_status(
    station: Station,
    decision: Decision,
    status: str,
    now: datetime,
    drop_label: str,
) -> None:
    stamp = now.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    safe_name = station.name.replace('"', "'")
    reference = (
        f"{decision.reference_cpl:.1f}" if decision.reference_cpl is not None else "n/a"
    )
    print(
        f'{stamp} cheapest={station.price_cpl:.1f} station="{safe_name}" '
        f"drop_{drop_label}={decision.drop_cpl:+.1f} ref={reference} status={status}"
    )


def _log_deferred_delivery(pending: PendingAlert, now: datetime) -> None:
    stamp = now.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    safe_name = pending.station.replace('"', "'")
    print(
        f'{stamp} price={pending.price_cpl:.1f} station="{safe_name}" '
        "status=deferred-delivered"
    )


def _record_observation(
    previous: WatchState | None,
    cheapest: Station,
    observed_at: datetime,
    keep: timedelta,
) -> tuple[Observation, ...]:
    """Prune old history and append the current cheapest-price observation."""
    pruned = prune_observations(
        previous.observations if previous is not None else (), observed_at, keep
    )
    current = Observation(
        observed_at=observed_at.astimezone(UTC),
        price_cpl=cheapest.price_cpl,
        station=cheapest.name,
    )
    return (pruned + (current,))[-MAX_OBSERVATIONS:]


def _fresh_state() -> WatchState:
    return WatchState(observations=(), armed=True, last_alert=None, pending=None)


async def run(
    config: Config,
    mode: Mode,
    provider: PriceProvider,
    notifier: Notifier = send_gotify,
    now: datetime | None = None,
) -> int:
    """Run one lookup and optionally perform drop-based notification."""
    observed_at = now or datetime.now(UTC)
    stations = await provider.fetch(config)
    if not stations:
        stamp = observed_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{stamp} status=no-valid-prices")
        return 0

    if mode is Mode.LIST:
        print(
            format_station_table(
                stations, observed_at, config.favourite_station_ids
            )
        )
        return 0

    try:
        previous = load_state(config.state_file)
    except StateError as exc:
        if mode is Mode.DRY_RUN:
            # Diagnostics should not die on a corrupt state file.
            print(f"gaswatch: warning: {exc}", file=sys.stderr)
            previous = None
        else:
            raise
    base = previous if previous is not None else _fresh_state()

    keep = config.drop_lookback + timedelta(hours=24)
    observations = _record_observation(base, stations[0], observed_at, keep)
    history = observations[:-1]
    working = replace(base, observations=observations)
    drop_label = lookback_label(config.drop_lookback)

    if mode is Mode.DRY_RUN:
        decision = decide_alert(
            stations[0].price_cpl,
            stations[0].name,
            history,
            working,
            observed_at,
            drop_threshold_cpl=config.drop_cpl,
            lookback=config.drop_lookback,
            hysteresis_cpl=config.hysteresis_cpl,
        )
        print(
            format_station_table(
                stations, observed_at, config.favourite_station_ids
            )
        )
        status = (
            "would-alert"
            if decision.action is AlertAction.ALERT
            else "would-suppress"
            if decision.action is AlertAction.SUPPRESSED
            else "would-watch"
        )
        _log_status(stations[0], decision, status, observed_at, drop_label)
        return 0

    quiet = in_quiet_hours(_local_now(observed_at), config.quiet_hours)

    # Deliver an alert that was deferred through quiet hours.
    if working.pending is not None and not quiet:
        pending = working.pending
        await notifier(config, pending.title, pending.message)
        working = replace(working, pending=None)
        save_state(config.state_file, working)
        _log_deferred_delivery(pending, observed_at)

    decision = decide_alert(
        stations[0].price_cpl,
        stations[0].name,
        history,
        working,
        observed_at,
        drop_threshold_cpl=config.drop_cpl,
        lookback=config.drop_lookback,
        hysteresis_cpl=config.hysteresis_cpl,
    )

    if decision.action is AlertAction.ALERT:
        title, message = build_notification(
            stations,
            observed_at,
            config.favourite_station_ids,
            drop_cpl=decision.drop_cpl,
            reference_cpl=decision.reference_cpl,
            lookback_label_text=drop_label,
        )
        if quiet:
            # Hold the alert until quiet hours end; the first one wins.
            pending = working.pending or PendingAlert(
                title=title,
                message=message,
                price_cpl=stations[0].price_cpl,
                station=stations[0].name,
                observed_at=observed_at.astimezone(UTC),
            )
            working = replace(
                working,
                pending=pending,
                armed=False,
                last_alert=decision.last_alert,
            )
            save_state(config.state_file, working)
            status = "deferred"
        else:
            await notifier(config, title, message)
            working = replace(
                working, armed=False, last_alert=decision.last_alert
            )
            save_state(config.state_file, working)
            status = "alert-sent"
    else:
        working = replace(working, armed=decision.armed, last_alert=decision.last_alert)
        save_state(config.state_file, working)
        status = (
            "suppressed" if decision.action is AlertAction.SUPPRESSED else "watching"
        )
    _log_status(stations[0], decision, status, observed_at, drop_label)
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch nearby GasBuddy prices and alert through Gotify."
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and show prices/action without notification or state writes",
    )
    modes.add_argument(
        "--list",
        action="store_true",
        dest="list_stations",
        help="fetch and list valid stations without notification or state access",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point."""
    args = parse_args(argv)
    mode = (
        Mode.DRY_RUN
        if args.dry_run
        else Mode.LIST
        if args.list_stations
        else Mode.NORMAL
    )
    load_dotenv(override=False)
    if os.environ.get("GASWATCH_THRESHOLD_CPL", "").strip():
        print(
            "gaswatch: note: GASWATCH_THRESHOLD_CPL is retired; "
            "alerts are drop-based now",
            file=sys.stderr,
        )
    try:
        config = Config.from_env(require_gotify=mode is Mode.NORMAL)
        return asyncio.run(run(config, mode, GasBuddyProvider()))
    except (ConfigError, StateError, GaswatchError) as exc:
        print(f"gaswatch: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
