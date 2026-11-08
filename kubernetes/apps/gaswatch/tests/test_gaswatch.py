from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
import aiohttp

from gaswatch import (
    AlertAction,
    AlertRecord,
    Config,
    ConfigError,
    GaswatchError,
    Mode,
    GasBuddyProvider,
    Observation,
    PendingAlert,
    Station,
    StateError,
    WatchState,
    build_notification,
    decide_alert,
    in_quiet_hours,
    load_state,
    lookback_label,
    normalize_stations,
    prune_observations,
    run,
    save_state,
    send_gotify,
)


NOW = datetime(2026, 9, 7, 22, 0, tzinfo=UTC)
EDT = timezone(timedelta(hours=-4))
LOCAL_EVENING = datetime(2026, 9, 7, 22, 0, tzinfo=EDT)
LOCAL_MORNING = datetime(2026, 9, 8, 8, 0, tzinfo=EDT)

DROP = 4.0
LOOKBACK = timedelta(hours=24)
HYSTERESIS = 2.0


def station(
    *,
    station_id: str = "123",
    name: str = "Esso",
    price: object = 149.9,
    unit: str = "cents_per_liter",
    posted: object = "2026-09-07T21:30:00Z",
    distance: object = 2.0,
) -> dict[str, object]:
    return {
        "station_id": station_id,
        "name": name,
        "unit_of_measure": unit,
        "address": {"line1": "123 Dundas St"},
        "distance": distance,
        "regular_gas": {
            "price": price,
            "last_updated": posted,
            "formatted_price": "149.9¢",
        },
    }


def base_env() -> dict[str, str]:
    return {
        "GASWATCH_LOCATION": "Test Location",
        "GASWATCH_LATITUDE": "42.9849",
        "GASWATCH_LONGITUDE": "-81.2453",
        "GASWATCH_RADIUS_KM": "15",
        "GASWATCH_FUEL_GRADE": "regular",
        "GASWATCH_MAX_PRICE_AGE_HOURS": "6",
        "GASWATCH_GOTIFY_URL": "https://gotify.example.test",
        "GASWATCH_GOTIFY_TOKEN": "secret",
        "GASWATCH_STATE_FILE": "/tmp/gaswatch-state.json",
    }


def observation(
    price: float, hours_ago: float, name: str = "Esso", at: datetime = NOW
) -> Observation:
    return Observation(at - timedelta(hours=hours_ago), price, name)


def fresh_state(**kwargs) -> WatchState:
    params = {"observations": (), "armed": True, "last_alert": None, "pending": None}
    params.update(kwargs)
    return WatchState(**params)


def decide(
    price: float,
    history: list[Observation],
    state: WatchState,
    **kwargs,
) -> Decision:
    params = {
        "drop_threshold_cpl": DROP,
        "lookback": LOOKBACK,
        "hysteresis_cpl": HYSTERESIS,
    }
    params.update(kwargs)
    return decide_alert(price, "Esso", history, state, NOW, **params)


def last_alert_at(price: float, hours_ago: float = 1.0) -> AlertRecord:
    return AlertRecord(NOW - timedelta(hours=hours_ago), price, "Esso", DROP)


def test_config_loads_valid_environment_with_drop_defaults() -> None:
    config = Config.from_env(base_env(), require_gotify=True)

    assert config.location == "Test Location"
    assert config.latitude == 42.9849
    assert config.longitude == -81.2453
    assert config.radius_km == 15.0
    assert config.fuel_grade == "regular"
    assert config.drop_cpl == 4.0
    assert config.drop_lookback == timedelta(hours=24)
    assert config.hysteresis_cpl == 2.0
    assert config.quiet_hours is None
    assert config.max_price_age == timedelta(hours=6)
    assert config.timeout_seconds == 20.0


def test_config_parses_drop_and_quiet_hours() -> None:
    env = base_env()
    env["GASWATCH_DROP_CPL"] = "5.5"
    env["GASWATCH_DROP_LOOKBACK_HOURS"] = "48"
    env["GASWATCH_HYSTERESIS_CPL"] = "1.5"
    env["GASWATCH_QUIET_HOURS"] = "23-7"

    config = Config.from_env(env, require_gotify=True)

    assert config.drop_cpl == 5.5
    assert config.drop_lookback == timedelta(hours=48)
    assert config.hysteresis_cpl == 1.5
    assert config.quiet_hours == (23, 7)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("GASWATCH_DROP_CPL", "0"),
        ("GASWATCH_DROP_CPL", "-1"),
        ("GASWATCH_DROP_CPL", "nan"),
        ("GASWATCH_DROP_CPL", "plenty"),
        ("GASWATCH_DROP_LOOKBACK_HOURS", "0"),
        ("GASWATCH_DROP_LOOKBACK_HOURS", "-24"),
        ("GASWATCH_HYSTERESIS_CPL", "0"),
        ("GASWATCH_HYSTERESIS_CPL", "-2"),
        ("GASWATCH_QUIET_HOURS", "23-23"),
        ("GASWATCH_QUIET_HOURS", "24-7"),
        ("GASWATCH_QUIET_HOURS", "23"),
        ("GASWATCH_QUIET_HOURS", "late-early"),
        ("GASWATCH_QUIET_HOURS", "23-7-9"),
    ],
)
def test_config_rejects_invalid_drop_and_quiet_values(key: str, value: str) -> None:
    env = base_env()
    env[key] = value

    with pytest.raises(ConfigError):
        Config.from_env(env, require_gotify=True)


def test_config_does_not_require_gotify_for_read_only_mode() -> None:
    env = base_env()
    del env["GASWATCH_GOTIFY_URL"]
    del env["GASWATCH_GOTIFY_TOKEN"]

    config = Config.from_env(env, require_gotify=False)

    assert config.gotify_url is None
    assert config.gotify_token is None


def test_config_parses_favourite_station_ids() -> None:
    env = base_env()
    env["GASWATCH_FAVOURITE_STATION_IDS"] = " 123,456, 123 "

    config = Config.from_env(env, require_gotify=True)

    assert config.favourite_station_ids == frozenset({"123", "456"})


@pytest.mark.parametrize("value", ["123,,456", "123,not-an-id"])
def test_config_rejects_invalid_favourite_station_ids(value: str) -> None:
    env = base_env()
    env["GASWATCH_FAVOURITE_STATION_IDS"] = value

    with pytest.raises(ConfigError, match="GASWATCH_FAVOURITE_STATION_IDS"):
        Config.from_env(env, require_gotify=True)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("GASWATCH_LATITUDE", "91"),
        ("GASWATCH_LONGITUDE", "-181"),
        ("GASWATCH_RADIUS_KM", "0"),
        ("GASWATCH_MAX_PRICE_AGE_HOURS", "-1"),
        ("GASWATCH_TIMEOUT_SECONDS", "0"),
        ("GASWATCH_FUEL_GRADE", "rocket_fuel"),
    ],
)
def test_config_rejects_invalid_values(key: str, value: str) -> None:
    env = base_env()
    env[key] = value

    with pytest.raises(ConfigError):
        Config.from_env(env, require_gotify=True)


@pytest.mark.parametrize(
    ("quiet", "hour", "expected"),
    [
        ((23, 7), 22.0, False),
        ((23, 7), 23.0, True),
        ((23, 7), 2.5, True),
        ((23, 7), 6.99, True),
        ((23, 7), 7.0, False),
        ((9, 17), 8.99, False),
        ((9, 17), 9.0, True),
        ((9, 17), 16.99, True),
        ((9, 17), 17.0, False),
    ],
)
def test_in_quiet_hours(quiet: tuple[int, int], hour: float, expected: bool) -> None:
    whole, fraction = divmod(hour, 1)
    moment = datetime(2026, 9, 7, int(whole), int(fraction * 60), tzinfo=EDT)

    assert in_quiet_hours(moment, quiet) is expected


def test_in_quiet_hours_without_configuration() -> None:
    assert in_quiet_hours(LOCAL_EVENING, None) is False


def test_in_quiet_hours_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        in_quiet_hours(datetime(2026, 9, 7, 22, 0), (23, 7))


def test_lookback_label() -> None:
    assert lookback_label(timedelta(hours=24)) == "24h"
    assert lookback_label(timedelta(hours=36)) == "36h"
    assert lookback_label(timedelta(hours=12, minutes=30)) == "12.5h"


def test_decide_warms_up_without_history() -> None:
    decision = decide(165.9, [], fresh_state())

    assert decision.action is AlertAction.WATCHING
    assert decision.reference_cpl is None
    assert decision.armed is True


def test_decide_alerts_on_drop_from_lookback_high() -> None:
    history = [observation(170.0, 20), observation(169.5, 5)]

    decision = decide(165.9, history, fresh_state())

    assert decision.action is AlertAction.ALERT
    assert decision.reference_cpl == pytest.approx(170.0)
    assert decision.drop_cpl == pytest.approx(4.1)
    assert decision.armed is False
    assert decision.last_alert is not None
    assert decision.last_alert.price_cpl == pytest.approx(165.9)


def test_decide_ignores_small_drop() -> None:
    history = [observation(170.0, 20)]

    decision = decide(167.0, history, fresh_state())

    assert decision.action is AlertAction.WATCHING
    assert decision.armed is True


def test_decide_ignores_history_outside_lookback() -> None:
    history = [observation(180.0, 30)]

    decision = decide(165.9, history, fresh_state())

    assert decision.action is AlertAction.WATCHING
    assert decision.reference_cpl is None


def test_decide_ignores_rising_prices() -> None:
    history = [observation(170.0, 20)]

    decision = decide(172.5, history, fresh_state())

    assert decision.action is AlertAction.WATCHING
    assert decision.drop_cpl == pytest.approx(-2.5)


def test_decide_suppresses_after_alert() -> None:
    state = fresh_state(armed=False, last_alert=last_alert_at(165.9))

    decision = decide(166.5, [observation(170.0, 20)], state)

    assert decision.action is AlertAction.SUPPRESSED
    assert decision.armed is False


def test_decide_rearms_after_hysteresis_climb() -> None:
    state = fresh_state(armed=False, last_alert=last_alert_at(165.9))

    decision = decide(168.0, [observation(170.0, 20)], state)

    assert decision.action is AlertAction.WATCHING
    assert decision.armed is True


def test_decide_alerts_again_after_rearm() -> None:
    state = fresh_state(armed=False, last_alert=last_alert_at(165.9))
    history = [observation(172.0, 2)]

    decision = decide(167.5, history, state)

    # Climbed 1.6 (no re-arm yet) ... use a bigger climb plus a fresh drop.
    assert decision.action is AlertAction.SUPPRESSED

    decision = decide(168.5, history, state)
    assert decision.armed is True
    assert decision.action is AlertAction.WATCHING

    rearmed = fresh_state(armed=True, last_alert=last_alert_at(165.9))
    decision = decide(167.5, history, rearmed)
    assert decision.action is AlertAction.ALERT
    assert decision.drop_cpl == pytest.approx(4.5)


def test_decide_alerts_on_further_leg_down() -> None:
    state = fresh_state(armed=False, last_alert=last_alert_at(165.9))

    decision = decide(161.8, [observation(170.0, 20)], state)

    assert decision.action is AlertAction.ALERT
    assert decision.drop_cpl == pytest.approx(4.1)
    assert decision.last_alert is not None
    assert decision.last_alert.price_cpl == pytest.approx(161.8)


def test_decide_suppresses_small_further_leg_down() -> None:
    state = fresh_state(armed=False, last_alert=last_alert_at(165.9))

    decision = decide(163.5, [observation(170.0, 20)], state)

    assert decision.action is AlertAction.SUPPRESSED
    assert decision.last_alert is not None
    assert decision.last_alert.price_cpl == pytest.approx(165.9)


def test_prune_observations_drops_old_entries() -> None:
    observations = (observation(170.0, 50), observation(169.0, 10))

    pruned = prune_observations(observations, NOW, timedelta(hours=48))

    assert [item.price_cpl for item in pruned] == [169.0]


def test_state_round_trip_v2(tmp_path) -> None:
    path = tmp_path / "nested" / "state.json"
    pending = PendingAlert(
        title="Gas is 165.9¢/L",
        message="down 4.1",
        price_cpl=165.9,
        station="Esso",
        observed_at=NOW,
    )
    expected = WatchState(
        observations=(observation(170.0, 20), observation(165.9, 1)),
        armed=False,
        last_alert=AlertRecord(NOW, 165.9, "Esso", 4.1),
        pending=pending,
    )

    save_state(path, expected)

    assert load_state(path) == expected
    assert not list(path.parent.glob(".state.json.*.tmp"))
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 2


def test_state_migrates_v1_above_threshold_to_armed(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "below_threshold": False,
                "price_cpl": 179.9,
                "station": "Costco",
                "threshold_cpl": 170.0,
                "observed_at": "2026-10-04T13:17:43+00:00",
            }
        ),
        encoding="utf-8",
    )

    state = load_state(path)

    assert state is not None
    assert state.armed is True
    assert state.last_alert is None
    assert state.pending is None
    assert len(state.observations) == 1
    assert state.observations[0].price_cpl == 179.9


def test_state_migrates_v1_below_threshold_to_disarmed(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "below_threshold": True,
                "price_cpl": 148.9,
                "station": "Costco",
                "threshold_cpl": 150.0,
                "observed_at": "2026-10-04T13:17:43+00:00",
            }
        ),
        encoding="utf-8",
    )

    state = load_state(path)

    assert state is not None
    assert state.armed is False
    assert state.last_alert is not None
    assert state.last_alert.price_cpl == 148.9


def test_missing_state_file_returns_none(tmp_path) -> None:
    assert load_state(tmp_path / "missing.json") is None


@pytest.mark.parametrize(
    "contents",
    [
        "not json",
        "[]",
        '{"version": 99}',
        '{"version": 1, "below_threshold": "yes"}',
        '{"version": 2, "armed": "yes"}',
        '{"version": 2, "observations": [{"price_cpl": "cheap"}]}',
    ],
)
def test_load_state_rejects_malformed_or_unknown_state(
    tmp_path, contents: str
) -> None:
    path = tmp_path / "state.json"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(StateError):
        load_state(path)


def normalized_station(
    *,
    name: str = "Costco",
    price: float = 143.9,
    address: str = "693 Wonderland Rd N",
    updated_at: datetime | None = datetime(2026, 9, 7, 21, 42, tzinfo=UTC),
    distance_km: float | None = 3.2,
) -> Station:
    return Station("123", name, address, price, updated_at, distance_km)


def test_build_notification_includes_drop_line() -> None:
    title, body = build_notification(
        [normalized_station(price=165.9)],
        NOW,
        drop_cpl=4.1,
        reference_cpl=170.0,
        lookback_label_text="24h",
    )

    assert title == "Gas is 165.9¢/L"
    assert "Down 4.1¢ from 24h high of 170.0¢/L" in body


def test_build_notification_omits_drop_line_without_drop() -> None:
    _, body = build_notification([normalized_station()], NOW)

    assert "Down" not in body


def test_build_notification_includes_cheapest_and_next_two() -> None:
    stations = [
        normalized_station(),
        normalized_station(name="Esso", price=148.6, address="2 Main St"),
        normalized_station(
            name="Petro-Canada", price=149.2, address="3 Oxford St"
        ),
        normalized_station(name="Shell", price=149.5, address="4 King St"),
    ]

    title, body = build_notification(stations, NOW)

    assert title == "Gas is 143.9¢/L"
    assert body == (
        "Costco\n"
        "693 Wonderland Rd N\n"
        "143.9¢/L\n"
        "Updated 18 minutes ago\n\n"
        "Next cheapest:\n"
        "Esso — 148.6¢/L\n"
        "Petro-Canada — 149.2¢/L"
    )


def test_build_notification_handles_unknown_update_time() -> None:
    title, body = build_notification(
        [normalized_station(updated_at=None, distance_km=None)], NOW
    )

    assert title == "Gas is 143.9¢/L"
    assert body.endswith("Updated unknown")


def test_normalize_converts_distance_and_sorts_by_price() -> None:
    results = normalize_stations(
        [station(name="Esso", price=149.9), station(name="Costco", price=143.9)],
        fuel_key="regular_gas",
        radius_km=15,
        max_age=timedelta(hours=6),
        now=NOW,
    )

    assert [item.name for item in results] == ["Costco", "Esso"]
    assert results[0].price_cpl == 143.9
    assert results[0].distance_km == pytest.approx(3.218688)
    assert results[0].updated_at == datetime(2026, 9, 7, 21, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "bad_station",
    [
        station(price=None),
        station(price=True),
        station(price="not-a-price"),
        station(price=float("nan")),
        station(price=float("inf")),
        station(price=49.9),
        station(price=300.1),
        station(unit="dollars_per_gallon"),
        station(posted="not-a-time"),
        station(posted="2026-09-07T15:59:59Z"),
        station(posted="2026-09-07T22:05:01Z"),
        station(distance=-1),
        station(distance="far"),
        station(distance=10),
        station(name=" "),
    ],
)
def test_normalize_rejects_malformed_stale_outlier_or_distant_data(
    bad_station: dict[str, object],
) -> None:
    assert normalize_stations(
        [bad_station],
        fuel_key="regular_gas",
        radius_km=15,
        max_age=timedelta(hours=6),
        now=NOW,
    ) == []


def test_normalize_keeps_missing_optional_timestamp_distance_and_address() -> None:
    raw = station(posted=None, distance=None)
    raw["address"] = {}

    results = normalize_stations(
        [raw],
        fuel_key="regular_gas",
        radius_km=15,
        max_age=timedelta(hours=6),
        now=NOW,
    )

    assert len(results) == 1
    assert results[0].updated_at is None
    assert results[0].distance_km is None
    assert results[0].address == "Address unknown"


def test_normalize_accepts_price_boundaries_and_exact_age_boundary() -> None:
    results = normalize_stations(
        [
            station(name="Low", price=50, posted="2026-09-07T16:00:00Z"),
            station(name="High", price=300),
        ],
        fuel_key="regular_gas",
        radius_km=15,
        max_age=timedelta(hours=6),
        now=NOW,
    )

    assert [(item.name, item.price_cpl) for item in results] == [
        ("Low", 50.0),
        ("High", 300.0),
    ]


def test_provider_fetches_and_merges_favourite_missing_from_area_search(
    monkeypatch, tmp_path
) -> None:
    env = base_env()
    env["GASWATCH_STATE_FILE"] = str(tmp_path / "state.json")
    env["GASWATCH_FAVOURITE_STATION_IDS"] = "123,178722"
    config = Config.from_env(env, require_gotify=True)
    favourite_lookups: list[int] = []
    # The provider normalizes against the real clock, so the fake reports
    # must be fresh; the fixed 2026-09-07 timestamps elsewhere in this file
    # would be rejected as stale.
    fresh_posted = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()

    class FakeGasBuddy:
        def __init__(self, station_id=None, **kwargs) -> None:
            self.station_id = station_id
            if station_id is not None:
                favourite_lookups.append(station_id)

        async def price_lookup_service(self, **kwargs):
            return {
                "results": [
                    station(station_id="123", price=149.9, posted=fresh_posted)
                ]
            }

        async def price_lookup(self):
            assert self.station_id == 178722
            return station(
                station_id="178722",
                name="Costco",
                price=143.9,
                distance=None,
                posted=fresh_posted,
            )

    monkeypatch.setattr("gaswatch.GasBuddy", FakeGasBuddy)

    results = asyncio.run(GasBuddyProvider().fetch(config))

    assert [(item.station_id, item.name) for item in results] == [
        ("178722", "Costco"),
        ("123", "Esso"),
    ]
    assert favourite_lookups == [178722]


class FakeProvider:
    def __init__(
        self,
        stations: list[Station] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.stations = stations or []
        self.error = error

    async def fetch(self, config: Config) -> list[Station]:
        if self.error:
            raise self.error
        return self.stations


class FakeNotifier:
    def __init__(self, error: Exception | None = None) -> None:
        self.messages: list[tuple[str, str]] = []
        self.error = error

    async def __call__(self, config: Config, title: str, message: str) -> None:
        if self.error:
            raise self.error
        self.messages.append((title, message))


def config_for_path(path, **overrides) -> Config:
    env = base_env()
    env["GASWATCH_STATE_FILE"] = str(path)
    env.update(overrides)
    return Config.from_env(env, require_gotify=True)


def seed_history(path, *entries: tuple[float, float]) -> None:
    """Write a state file with observations of (price, hours_ago)."""
    save_state(
        path,
        fresh_state(
            observations=tuple(
                observation(price, hours_ago) for price, hours_ago in entries
            )
        ),
    )


def cheap_station(price: float, name: str = "Costco") -> Station:
    return Station("123", name, "693 Wonderland Rd N", price, NOW, 3.2)


def test_run_alerts_then_suppresses_then_rearms(tmp_path, capsys) -> None:
    state_path = tmp_path / "state.json"
    seed_history(state_path, (170.0, 20.0))
    config = config_for_path(state_path)
    notifier = FakeNotifier()

    result = asyncio.run(
        run(config, Mode.NORMAL, FakeProvider([cheap_station(165.9)]), notifier, NOW)
    )
    assert result == 0
    assert len(notifier.messages) == 1
    assert "Down 4.1¢ from 24h high of 170.0¢/L" in notifier.messages[0][1]
    state = load_state(state_path)
    assert state is not None and state.armed is False
    assert "status=alert-sent" in capsys.readouterr().out

    result = asyncio.run(
        run(config, Mode.NORMAL, FakeProvider([cheap_station(165.9)]), notifier, NOW)
    )
    assert result == 0
    assert len(notifier.messages) == 1
    assert "status=suppressed" in capsys.readouterr().out

    # Climbs back above the alert price + hysteresis: re-arms.
    result = asyncio.run(
        run(config, Mode.NORMAL, FakeProvider([cheap_station(168.0)]), notifier, NOW)
    )
    assert result == 0
    assert len(notifier.messages) == 1
    state = load_state(state_path)
    assert state is not None and state.armed is True
    assert "status=watching" in capsys.readouterr().out

    # Drops 4.5 from the 24h high of 170.0: alerts again.
    result = asyncio.run(
        run(config, Mode.NORMAL, FakeProvider([cheap_station(165.5)]), notifier, NOW)
    )
    assert result == 0
    assert len(notifier.messages) == 2
    assert "status=alert-sent" in capsys.readouterr().out


def test_run_alerts_on_further_leg_down_without_rearm(tmp_path, capsys) -> None:
    state_path = tmp_path / "state.json"
    seed_history(state_path, (170.0, 20.0))
    config = config_for_path(state_path)
    notifier = FakeNotifier()

    asyncio.run(
        run(config, Mode.NORMAL, FakeProvider([cheap_station(165.9)]), notifier, NOW)
    )
    assert len(notifier.messages) == 1

    asyncio.run(
        run(config, Mode.NORMAL, FakeProvider([cheap_station(161.8)]), notifier, NOW)
    )
    assert len(notifier.messages) == 2
    assert "Down 4.1¢ from 24h high" in notifier.messages[1][1]
    assert "status=alert-sent" in capsys.readouterr().out


def test_run_warms_up_without_history(tmp_path, capsys) -> None:
    state_path = tmp_path / "state.json"
    config = config_for_path(state_path)
    notifier = FakeNotifier()

    result = asyncio.run(
        run(config, Mode.NORMAL, FakeProvider([cheap_station(120.0)]), notifier, NOW)
    )

    assert result == 0
    assert notifier.messages == []
    assert "status=watching" in capsys.readouterr().out
    state = load_state(state_path)
    assert state is not None
    assert len(state.observations) == 1


def test_run_defers_alert_during_quiet_hours_and_delivers_after(
    monkeypatch, tmp_path, capsys
) -> None:
    state_path = tmp_path / "state.json"
    seed_history(state_path, (170.0, 20.0))
    config = config_for_path(state_path, GASWATCH_QUIET_HOURS="21-7")
    notifier = FakeNotifier()
    monkeypatch.setattr("gaswatch._local_now", lambda moment: LOCAL_EVENING)

    result = asyncio.run(
        run(config, Mode.NORMAL, FakeProvider([cheap_station(165.9)]), notifier, NOW)
    )

    assert result == 0
    assert notifier.messages == []
    assert "status=deferred" in capsys.readouterr().out
    state = load_state(state_path)
    assert state is not None
    assert state.pending is not None
    assert state.pending.price_cpl == pytest.approx(165.9)
    assert state.armed is False

    # Morning: the deferred alert is delivered, no new alert fires.
    monkeypatch.setattr("gaswatch._local_now", lambda moment: LOCAL_MORNING)
    result = asyncio.run(
        run(
            config,
            Mode.NORMAL,
            FakeProvider([cheap_station(166.0)]),
            notifier,
            NOW + timedelta(hours=10),
        )
    )

    assert result == 0
    assert len(notifier.messages) == 1
    assert "Down 4.1¢ from 24h high of 170.0¢/L" in notifier.messages[0][1]
    state = load_state(state_path)
    assert state is not None and state.pending is None
    output = capsys.readouterr().out
    assert "status=deferred-delivered" in output
    assert "status=suppressed" in output


def test_run_quiet_hours_keeps_first_pending_alert(monkeypatch, tmp_path) -> None:
    state_path = tmp_path / "state.json"
    seed_history(state_path, (170.0, 20.0))
    config = config_for_path(state_path, GASWATCH_QUIET_HOURS="21-7")
    notifier = FakeNotifier()
    monkeypatch.setattr("gaswatch._local_now", lambda moment: LOCAL_EVENING)

    asyncio.run(
        run(config, Mode.NORMAL, FakeProvider([cheap_station(165.9)]), notifier, NOW)
    )
    asyncio.run(
        run(
            config,
            Mode.NORMAL,
            FakeProvider([cheap_station(161.8)]),
            notifier,
            NOW + timedelta(hours=1),
        )
    )

    state = load_state(state_path)
    assert state is not None
    assert state.pending is not None
    assert state.pending.price_cpl == pytest.approx(165.9)
    assert state.last_alert is not None
    assert state.last_alert.price_cpl == pytest.approx(161.8)
    assert notifier.messages == []


def test_run_prunes_old_history(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    seed_history(state_path, (180.0, 100.0), (170.0, 20.0))
    config = config_for_path(state_path)

    asyncio.run(
        run(config, Mode.NORMAL, FakeProvider([cheap_station(169.0)]), FakeNotifier(), NOW)
    )

    state = load_state(state_path)
    assert state is not None
    assert [item.price_cpl for item in state.observations] == [170.0, 169.0]


def test_no_valid_prices_does_not_modify_existing_state(tmp_path, capsys) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text("good state remains untouched", encoding="utf-8")

    result = asyncio.run(
        run(
            config_for_path(state_path),
            Mode.NORMAL,
            FakeProvider([]),
            FakeNotifier(),
            NOW,
        )
    )

    assert result == 0
    assert state_path.read_text(encoding="utf-8") == "good state remains untouched"
    assert "status=no-valid-prices" in capsys.readouterr().out


def test_provider_failure_does_not_modify_state(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text("good state remains untouched", encoding="utf-8")

    with pytest.raises(GaswatchError, match="GasBuddy unavailable"):
        asyncio.run(
            run(
                config_for_path(state_path),
                Mode.NORMAL,
                FakeProvider(error=GaswatchError("GasBuddy unavailable")),
                FakeNotifier(),
                NOW,
            )
        )

    assert state_path.read_text(encoding="utf-8") == "good state remains untouched"


def test_gotify_failure_does_not_disarm(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    seed_history(state_path, (170.0, 20.0))
    config = config_for_path(state_path)

    with pytest.raises(GaswatchError, match="Gotify rejected message"):
        asyncio.run(
            run(
                config_for_path(state_path),
                Mode.NORMAL,
                FakeProvider([cheap_station(165.9)]),
                FakeNotifier(error=GaswatchError("Gotify rejected message")),
                NOW,
            )
        )

    state = load_state(state_path)
    assert state is not None
    assert state.armed is True
    assert state.last_alert is None
    assert state.pending is None


def test_deferred_delivery_failure_keeps_pending(monkeypatch, tmp_path) -> None:
    state_path = tmp_path / "state.json"
    seed_history(state_path, (170.0, 20.0))
    config = config_for_path(state_path, GASWATCH_QUIET_HOURS="21-7")
    monkeypatch.setattr("gaswatch._local_now", lambda moment: LOCAL_EVENING)
    asyncio.run(
        run(config, Mode.NORMAL, FakeProvider([cheap_station(165.9)]), FakeNotifier(), NOW)
    )
    state = load_state(state_path)
    assert state is not None and state.pending is not None

    monkeypatch.setattr("gaswatch._local_now", lambda moment: LOCAL_MORNING)
    with pytest.raises(GaswatchError, match="Gotify rejected message"):
        asyncio.run(
            run(
                config,
                Mode.NORMAL,
                FakeProvider([cheap_station(166.0)]),
                FakeNotifier(error=GaswatchError("Gotify rejected message")),
                NOW + timedelta(hours=10),
            )
        )

    state = load_state(state_path)
    assert state is not None and state.pending is not None


@pytest.mark.parametrize("mode", [Mode.DRY_RUN, Mode.LIST])
def test_read_only_modes_do_not_notify_or_write_state(tmp_path, capsys, mode) -> None:
    state_path = tmp_path / "state.json"
    seed_history(state_path, (170.0, 20.0))
    before = state_path.read_bytes()
    notifier = FakeNotifier()

    result = asyncio.run(
        run(
            config_for_path(state_path),
            mode,
            FakeProvider([cheap_station(165.9)]),
            notifier,
            NOW,
        )
    )

    assert result == 0
    assert state_path.read_bytes() == before
    assert notifier.messages == []
    output = capsys.readouterr().out
    assert "Costco" in output
    assert "165.9" in output
    if mode is Mode.DRY_RUN:
        assert "would-alert" in output


def test_dry_run_survives_corrupt_state(tmp_path, capsys) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text("corrupt", encoding="utf-8")

    result = asyncio.run(
        run(
            config_for_path(state_path),
            Mode.DRY_RUN,
            FakeProvider([cheap_station(165.9)]),
            FakeNotifier(),
            NOW,
        )
    )

    assert result == 0
    captured = capsys.readouterr()
    assert "would-watch" in captured.out
    assert "warning" in captured.err


def test_gotify_network_error_never_exposes_token(monkeypatch, tmp_path) -> None:
    class FailingSession:
        def __init__(self, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        def post(self, *args, **kwargs):
            raise aiohttp.ClientError(
                "failed URL https://gotify.example/message?token=secret"
            )

    monkeypatch.setattr("gaswatch.aiohttp.ClientSession", FailingSession)

    with pytest.raises(GaswatchError) as error:
        asyncio.run(
            send_gotify(config_for_path(tmp_path / "state.json"), "title", "body")
        )

    assert "secret" not in str(error.value)
    assert "ClientError" in str(error.value)
