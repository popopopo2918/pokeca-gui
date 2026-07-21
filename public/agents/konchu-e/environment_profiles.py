from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


DATA_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "top200_environment_2026-07-18.json"
)

ADOPTION_EVIDENCE_KEYS = frozenset({
    "adopting_decks",
    "decks_in_denominator",
    "evidence_scope",
})
BENCH_PRESSURE_EVIDENCE_KEYS = frozenset({
    "adopting_decks",
    "decks_in_denominator",
    "observed_matches",
    "observed_bench_attack_uses",
    "observed_counter_pressure_plays",
    "evidence_scope",
})
PROFILE_REQUIRED_KEYS = frozenset({
    "key",
    "label",
    "teams",
    "rank_band_team_counts",
    "recent_game_team_count",
    "games_observed",
    "missing_games",
    "identifying_sets",
    "identifying_attacker_ids",
    "primary_lines",
    "observed_attacker_ids",
    "observed_attack_counts",
    "mist_energy_counts",
    "rock_fighting_energy_counts",
    "immunity_energy_observation_complete",
    "uses_xerosic",
    "uses_unfair_stamp",
    "bench_damage",
    "source_urls",
})


def _fail(field: str, expected: str) -> ValueError:
    return ValueError(f"{field} must be {expected}")


def _require_object(value: object, *, field: str) -> dict[str, object]:
    if type(value) is not dict:
        raise _fail(field, "an object")
    if any(type(key) is not str for key in value):
        raise _fail(field, "an object with string keys")
    return value


def _require_list(value: object, *, field: str) -> list[object]:
    if type(value) is not list:
        raise _fail(field, "a list")
    return value


def _require_string(value: object, *, field: str) -> str:
    if type(value) is not str or not value:
        raise _fail(field, "a non-empty string")
    return value


def _require_int(value: object, *, field: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        qualifier = "positive" if minimum == 1 else f">= {minimum}"
        raise _fail(field, f"an integer {qualifier}")
    return value


def _require_optional_int(
    value: object,
    *,
    field: str,
    minimum: int = 0,
) -> int | None:
    if value is None:
        return None
    return _require_int(value, field=field, minimum=minimum)


def _require_bool(value: object, *, field: str) -> bool:
    if type(value) is not bool:
        raise _fail(field, "a boolean")
    return value


def _require_keys(
    value: dict[str, object],
    required: frozenset[str],
    *,
    field: str,
) -> None:
    missing = required - value.keys()
    if missing:
        raise ValueError(f"{field} is missing keys: {sorted(missing)}")


def _require_public_kaggle_url(value: object, *, field: str) -> str:
    url = _require_string(value, field=field)
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.kaggle.com"
        or not parsed.path.startswith("/competitions/pokemon-tcg-ai-battle")
    ):
        raise _fail(field, "a public pokemon-tcg-ai-battle Kaggle URL")
    return url


@dataclass(frozen=True)
class AdoptionEvidence:
    adopting_decks: int | None
    decks_in_denominator: int | None
    evidence_scope: str

    def __post_init__(self) -> None:
        adopting = _require_optional_int(
            self.adopting_decks,
            field="adopting_decks",
        )
        denominator = _require_optional_int(
            self.decks_in_denominator,
            field="decks_in_denominator",
            minimum=1,
        )
        _require_string(self.evidence_scope, field="evidence_scope")
        if adopting is not None and denominator is not None and adopting > denominator:
            raise ValueError("adopting_decks cannot exceed decks_in_denominator")

    @property
    def rate(self) -> float | None:
        if self.adopting_decks is None or self.decks_in_denominator is None:
            return None
        return self.adopting_decks / self.decks_in_denominator

    @property
    def presence(self) -> bool | None:
        if self.adopting_decks is None or self.decks_in_denominator is None:
            return None
        if self.adopting_decks == 0:
            return False
        if self.adopting_decks == self.decks_in_denominator:
            return True
        return None


@dataclass(frozen=True)
class BenchPressureEvidence:
    adopting_decks: int | None
    decks_in_denominator: int | None
    observed_matches: int
    observed_bench_attack_uses: int
    observed_counter_pressure_plays: int
    evidence_scope: str

    def __post_init__(self) -> None:
        AdoptionEvidence(
            self.adopting_decks,
            self.decks_in_denominator,
            self.evidence_scope,
        )
        _require_int(self.observed_matches, field="observed_matches")
        _require_int(
            self.observed_bench_attack_uses,
            field="observed_bench_attack_uses",
        )
        _require_int(
            self.observed_counter_pressure_plays,
            field="observed_counter_pressure_plays",
        )

    @property
    def rate(self) -> float | None:
        return AdoptionEvidence(
            self.adopting_decks,
            self.decks_in_denominator,
            self.evidence_scope,
        ).rate

    @property
    def presence(self) -> bool | None:
        return AdoptionEvidence(
            self.adopting_decks,
            self.decks_in_denominator,
            self.evidence_scope,
        ).presence


@dataclass(frozen=True)
class ArchetypeProfile:
    key: str
    label: str
    identifying_sets: tuple[frozenset[int], ...]
    primary_lines: tuple[tuple[int, ...], ...]
    identifying_attacker_ids: frozenset[int]
    observed_attacker_ids: frozenset[int]
    observed_attack_counts: tuple[tuple[int, int], ...]
    mist_energy_counts: tuple[int, ...]
    rock_fighting_energy_counts: tuple[int, ...]
    xerosic_adoption: AdoptionEvidence
    unfair_stamp_adoption: AdoptionEvidence
    bench_damage: BenchPressureEvidence
    teams: int = 0
    rank_band_team_counts: tuple[tuple[str, int | None], ...] = ()
    recent_game_team_count: int = 0
    games_observed: int = 0
    missing_games: tuple[tuple[str, int | None], ...] = ()
    immunity_energy_observation_complete: bool = False
    source_urls: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_string(self.key, field="key")
        _require_string(self.label, field="label")
        _validate_profile_card_fields(self)
        _require_int(self.teams, field="teams")
        _require_int(
            self.recent_game_team_count,
            field="recent_game_team_count",
        )
        _require_int(self.games_observed, field="games_observed")
        _require_bool(
            self.immunity_energy_observation_complete,
            field="immunity_energy_observation_complete",
        )
        if type(self.xerosic_adoption) is not AdoptionEvidence:
            raise _fail("xerosic_adoption", "AdoptionEvidence")
        if type(self.unfair_stamp_adoption) is not AdoptionEvidence:
            raise _fail("unfair_stamp_adoption", "AdoptionEvidence")
        if type(self.bench_damage) is not BenchPressureEvidence:
            raise _fail("bench_damage", "BenchPressureEvidence")
        for index, url in enumerate(self.source_urls):
            _require_public_kaggle_url(url, field=f"source_urls[{index}]")

    @property
    def uses_xerosic(self) -> bool | None:
        return self.xerosic_adoption.presence

    @property
    def uses_unfair_stamp(self) -> bool | None:
        return self.unfair_stamp_adoption.presence

    @property
    def reserves_hammer_for_immunity(self) -> bool | None:
        if self.mist_energy_counts or self.rock_fighting_energy_counts:
            return True
        if self.immunity_energy_observation_complete:
            return False
        return None


@dataclass(frozen=True)
class ArchetypeAssessment:
    profile: ArchetypeProfile | None
    candidate_keys: tuple[str, ...]
    evidence_card_ids: frozenset[int]
    evidence_attacker_ids: frozenset[int]


def _validate_card_id(value: object, *, field: str) -> int:
    return _require_int(value, field=field, minimum=1)


def _validate_frozen_card_ids(
    value: object,
    *,
    field: str,
) -> frozenset[int]:
    if type(value) is not frozenset:
        raise _fail(field, "a frozenset of positive card IDs")
    for card_id in value:
        _validate_card_id(card_id, field=field)
    return value


def _validate_profile_card_fields(profile: ArchetypeProfile) -> None:
    if type(profile.identifying_sets) is not tuple:
        raise _fail("identifying_sets", "a tuple of frozensets")
    if len(set(profile.identifying_sets)) != len(profile.identifying_sets):
        raise ValueError("identifying_sets cannot contain duplicates")
    for index, signature in enumerate(profile.identifying_sets):
        _validate_frozen_card_ids(
            signature,
            field=f"identifying_sets[{index}]",
        )
        if not signature:
            raise _fail(f"identifying_sets[{index}]", "non-empty")

    if type(profile.primary_lines) is not tuple or not profile.primary_lines:
        raise _fail("primary_lines", "a non-empty tuple of card ID tuples")
    for line_index, line in enumerate(profile.primary_lines):
        if type(line) is not tuple or not line:
            raise _fail(f"primary_lines[{line_index}]", "a non-empty tuple")
        if len(set(line)) != len(line):
            raise ValueError(f"primary_lines[{line_index}] contains duplicates")
        for card_index, card_id in enumerate(line):
            _validate_card_id(
                card_id,
                field=f"primary_lines[{line_index}][{card_index}]",
            )

    identifying = _validate_frozen_card_ids(
        profile.identifying_attacker_ids,
        field="identifying_attacker_ids",
    )
    observed = _validate_frozen_card_ids(
        profile.observed_attacker_ids,
        field="observed_attacker_ids",
    )
    if not identifying <= observed:
        raise ValueError("identifying_attacker_ids must be observed attackers")

    if type(profile.observed_attack_counts) is not tuple:
        raise _fail("observed_attack_counts", "a tuple of card/count pairs")
    count_ids: set[int] = set()
    for index, pair in enumerate(profile.observed_attack_counts):
        if type(pair) is not tuple or len(pair) != 2:
            raise _fail(
                f"observed_attack_counts[{index}]",
                "a card/count pair",
            )
        card_id = _validate_card_id(
            pair[0],
            field=f"observed_attack_counts[{index}].card_id",
        )
        _require_int(
            pair[1],
            field=f"observed_attack_counts[{index}].count",
            minimum=1,
        )
        if card_id in count_ids:
            raise ValueError("observed_attack_counts contains duplicate card IDs")
        count_ids.add(card_id)
    if count_ids != observed:
        raise ValueError(
            "observed_attacker_ids must equal positive observed_attack_counts keys"
        )

    for field, counts in (
        ("mist_energy_counts", profile.mist_energy_counts),
        ("rock_fighting_energy_counts", profile.rock_fighting_energy_counts),
    ):
        if type(counts) is not tuple:
            raise _fail(field, "a tuple of positive counts")
        for index, count in enumerate(counts):
            _require_int(count, field=f"{field}[{index}]", minimum=1)


def _parse_card_id_list(
    value: object,
    *,
    field: str,
    allow_empty: bool = True,
) -> tuple[int, ...]:
    values = _require_list(value, field=field)
    if not allow_empty and not values:
        raise _fail(field, "a non-empty list")
    card_ids = tuple(
        _validate_card_id(card_id, field=f"{field}[{index}]")
        for index, card_id in enumerate(values)
    )
    if len(set(card_ids)) != len(card_ids):
        raise ValueError(f"{field} contains duplicate card IDs")
    return card_ids


def _parse_identifying_sets(
    value: object,
    *,
    field: str,
) -> tuple[frozenset[int], ...]:
    rows = _require_list(value, field=field)
    signatures = tuple(
        frozenset(
            _parse_card_id_list(
                row,
                field=f"{field}[{index}]",
                allow_empty=False,
            )
        )
        for index, row in enumerate(rows)
    )
    if len(set(signatures)) != len(signatures):
        raise ValueError(f"{field} contains duplicate signatures")
    return signatures


def _parse_primary_lines(
    value: object,
    *,
    field: str,
) -> tuple[tuple[int, ...], ...]:
    rows = _require_list(value, field=field)
    if not rows:
        raise _fail(field, "a non-empty list")
    return tuple(
        _parse_card_id_list(
            row,
            field=f"{field}[{index}]",
            allow_empty=False,
        )
        for index, row in enumerate(rows)
    )


def _parse_attack_counts(
    value: object,
    *,
    field: str,
) -> tuple[tuple[int, int], ...]:
    values = _require_object(value, field=field)
    result: list[tuple[int, int]] = []
    for key, value_count in values.items():
        if not key.isascii() or not key.isdecimal() or key.startswith("0"):
            raise _fail(f"{field} key", "a positive decimal card ID")
        card_id = int(key)
        count = _require_int(
            value_count,
            field=f"{field}.{key}",
            minimum=1,
        )
        result.append((card_id, count))
    return tuple(sorted(result))


def _parse_band_counts(
    value: object,
    *,
    field: str,
) -> tuple[tuple[str, int | None], ...]:
    values = _require_object(value, field=field)
    expected = {"1-100", "101-200"}
    if set(values) != expected:
        raise ValueError(f"{field} must have rank bands {sorted(expected)}")
    return tuple(
        (
            rank_band,
            _require_optional_int(
                values[rank_band],
                field=f"{field}.{rank_band}",
            ),
        )
        for rank_band in ("1-100", "101-200")
    )


def _parse_adoption(value: object, *, field: str) -> AdoptionEvidence:
    values = _require_object(value, field=field)
    _require_keys(values, ADOPTION_EVIDENCE_KEYS, field=field)
    return AdoptionEvidence(
        adopting_decks=_require_optional_int(
            values["adopting_decks"],
            field=f"{field}.adopting_decks",
        ),
        decks_in_denominator=_require_optional_int(
            values["decks_in_denominator"],
            field=f"{field}.decks_in_denominator",
            minimum=1,
        ),
        evidence_scope=_require_string(
            values["evidence_scope"],
            field=f"{field}.evidence_scope",
        ),
    )


def _parse_bench_pressure(
    value: object,
    *,
    field: str,
) -> BenchPressureEvidence:
    values = _require_object(value, field=field)
    _require_keys(values, BENCH_PRESSURE_EVIDENCE_KEYS, field=field)
    return BenchPressureEvidence(
        adopting_decks=_require_optional_int(
            values["adopting_decks"],
            field=f"{field}.adopting_decks",
        ),
        decks_in_denominator=_require_optional_int(
            values["decks_in_denominator"],
            field=f"{field}.decks_in_denominator",
            minimum=1,
        ),
        observed_matches=_require_int(
            values["observed_matches"],
            field=f"{field}.observed_matches",
        ),
        observed_bench_attack_uses=_require_int(
            values["observed_bench_attack_uses"],
            field=f"{field}.observed_bench_attack_uses",
        ),
        observed_counter_pressure_plays=_require_int(
            values["observed_counter_pressure_plays"],
            field=f"{field}.observed_counter_pressure_plays",
        ),
        evidence_scope=_require_string(
            values["evidence_scope"],
            field=f"{field}.evidence_scope",
        ),
    )


def _parse_urls(value: object, *, field: str) -> tuple[str, ...]:
    values = _require_list(value, field=field)
    if not values:
        raise _fail(field, "a non-empty list")
    return tuple(
        _require_public_kaggle_url(url, field=f"{field}[{index}]")
        for index, url in enumerate(values)
    )


def _profile_from_row(value: object, *, index: int) -> ArchetypeProfile:
    field = f"profiles[{index}]"
    row = _require_object(value, field=field)
    _require_keys(row, PROFILE_REQUIRED_KEYS, field=field)
    profile = ArchetypeProfile(
        key=_require_string(row["key"], field=f"{field}.key"),
        label=_require_string(row["label"], field=f"{field}.label"),
        teams=_require_int(row["teams"], field=f"{field}.teams"),
        rank_band_team_counts=_parse_band_counts(
            row["rank_band_team_counts"],
            field=f"{field}.rank_band_team_counts",
        ),
        recent_game_team_count=_require_int(
            row["recent_game_team_count"],
            field=f"{field}.recent_game_team_count",
        ),
        games_observed=_require_int(
            row["games_observed"],
            field=f"{field}.games_observed",
        ),
        missing_games=_parse_band_counts(
            row["missing_games"],
            field=f"{field}.missing_games",
        ),
        identifying_sets=_parse_identifying_sets(
            row["identifying_sets"],
            field=f"{field}.identifying_sets",
        ),
        primary_lines=_parse_primary_lines(
            row["primary_lines"],
            field=f"{field}.primary_lines",
        ),
        identifying_attacker_ids=frozenset(
            _parse_card_id_list(
                row["identifying_attacker_ids"],
                field=f"{field}.identifying_attacker_ids",
            )
        ),
        observed_attacker_ids=frozenset(
            _parse_card_id_list(
                row["observed_attacker_ids"],
                field=f"{field}.observed_attacker_ids",
            )
        ),
        observed_attack_counts=_parse_attack_counts(
            row["observed_attack_counts"],
            field=f"{field}.observed_attack_counts",
        ),
        mist_energy_counts=tuple(
            _require_int(
                count,
                field=f"{field}.mist_energy_counts[{count_index}]",
                minimum=1,
            )
            for count_index, count in enumerate(
                _require_list(
                    row["mist_energy_counts"],
                    field=f"{field}.mist_energy_counts",
                )
            )
        ),
        rock_fighting_energy_counts=tuple(
            _require_int(
                count,
                field=f"{field}.rock_fighting_energy_counts[{count_index}]",
                minimum=1,
            )
            for count_index, count in enumerate(
                _require_list(
                    row["rock_fighting_energy_counts"],
                    field=f"{field}.rock_fighting_energy_counts",
                )
            )
        ),
        immunity_energy_observation_complete=_require_bool(
            row["immunity_energy_observation_complete"],
            field=f"{field}.immunity_energy_observation_complete",
        ),
        xerosic_adoption=_parse_adoption(
            row["uses_xerosic"],
            field=f"{field}.uses_xerosic",
        ),
        unfair_stamp_adoption=_parse_adoption(
            row["uses_unfair_stamp"],
            field=f"{field}.uses_unfair_stamp",
        ),
        bench_damage=_parse_bench_pressure(
            row["bench_damage"],
            field=f"{field}.bench_damage",
        ),
        source_urls=_parse_urls(
            row["source_urls"],
            field=f"{field}.source_urls",
        ),
    )
    for name, evidence in (
        ("uses_xerosic", profile.xerosic_adoption),
        ("uses_unfair_stamp", profile.unfair_stamp_adoption),
        ("bench_damage", profile.bench_damage),
    ):
        denominator = evidence.decks_in_denominator
        if denominator is not None and denominator != profile.teams:
            raise ValueError(f"{field}.{name} denominator must equal teams")
    return profile


def _validate_int_fields(
    values: dict[str, object],
    names: tuple[str, ...],
    *,
    field: str,
) -> None:
    _require_keys(values, frozenset(names), field=field)
    for name in names:
        _require_int(values[name], field=f"{field}.{name}")


def _validate_evidence_scopes(value: object) -> None:
    scopes = _require_object(value, field="evidence_scopes")
    names = frozenset({
        "current_top200_metadata",
        "current_partial_replay_scan",
        "verified_legacy_top100_snapshot",
    })
    _require_keys(scopes, names, field="evidence_scopes")

    current = _require_object(
        scopes["current_top200_metadata"],
        field="evidence_scopes.current_top200_metadata",
    )
    _validate_int_fields(
        current,
        (
            "leaderboard_teams",
            "teams_with_safe_active_submissions",
            "safe_active_submissions_per_team",
            "safe_active_submissions",
        ),
        field="evidence_scopes.current_top200_metadata",
    )

    replay = _require_object(
        scopes["current_partial_replay_scan"],
        field="evidence_scopes.current_partial_replay_scan",
    )
    _validate_int_fields(
        replay,
        (
            "maximum_replays_per_team",
            "requested_replay_slots",
            "replays_scanned",
            "unscanned_replay_slots",
            "teams_with_at_least_one_replay",
            "teams_with_five_replays",
            "rank_1_71_requested_slots",
            "rank_1_71_replays_scanned",
        ),
        field="evidence_scopes.current_partial_replay_scan",
    )
    for name in (
        "rank_72_200_team_name_quote_matching_issue",
        "rank_101_200_archetypes_classified",
        "rank_101_200_latest_decks_classified",
    ):
        _require_bool(
            replay[name],
            field=f"evidence_scopes.current_partial_replay_scan.{name}",
        )

    verified = _require_object(
        scopes["verified_legacy_top100_snapshot"],
        field="evidence_scopes.verified_legacy_top100_snapshot",
    )
    _validate_int_fields(
        verified,
        (
            "leaderboard_teams",
            "latest_decks_parsed",
            "latest_decks_expected",
            "team_game_slots_parsed",
            "team_game_slots_expected",
            "unique_episodes",
        ),
        field="evidence_scopes.verified_legacy_top100_snapshot",
    )
    for name in ("observed_from_jst", "observed_to_jst"):
        _require_string(
            verified[name],
            field=f"evidence_scopes.verified_legacy_top100_snapshot.{name}",
        )
    _require_bool(
        verified["profile_statistics_source"],
        field=(
            "evidence_scopes.verified_legacy_top100_snapshot."
            "profile_statistics_source"
        ),
    )


def _validate_special_energy_group(
    value: object,
    *,
    field: str,
    requires_all_four_flag: bool,
) -> None:
    group = _require_object(value, field=field)
    required = {
        "card_id",
        "adopting_decks",
        "copies",
        "by_profile",
    }
    if requires_all_four_flag:
        required.add("all_adoptions_are_four_copies")
    _require_keys(group, frozenset(required), field=field)
    _require_int(group["card_id"], field=f"{field}.card_id", minimum=1)
    _require_int(group["adopting_decks"], field=f"{field}.adopting_decks")
    _require_int(group["copies"], field=f"{field}.copies", minimum=1)
    if requires_all_four_flag:
        _require_bool(
            group["all_adoptions_are_four_copies"],
            field=f"{field}.all_adoptions_are_four_copies",
        )
    by_profile = _require_object(group["by_profile"], field=f"{field}.by_profile")
    for profile_key, profile_value in by_profile.items():
        profile_field = f"{field}.by_profile.{profile_key}"
        row = _require_object(profile_value, field=profile_field)
        _validate_int_fields(
            row,
            ("adopting_decks", "decks_in_denominator", "copies"),
            field=profile_field,
        )
        if row["decks_in_denominator"] == 0:
            raise _fail(f"{profile_field}.decks_in_denominator", "positive")
        if row["copies"] == 0:
            raise _fail(f"{profile_field}.copies", "positive")
        if row["adopting_decks"] > row["decks_in_denominator"]:
            raise ValueError(f"{profile_field} adoption exceeds denominator")


def _validate_special_energy(value: object) -> None:
    energy = _require_object(
        value,
        field="verified_legacy_top100_special_energy",
    )
    _require_keys(
        energy,
        frozenset({"decks_checked", "mist_energy", "rock_fighting_energy"}),
        field="verified_legacy_top100_special_energy",
    )
    _require_int(
        energy["decks_checked"],
        field="verified_legacy_top100_special_energy.decks_checked",
        minimum=1,
    )
    _validate_special_energy_group(
        energy["mist_energy"],
        field="verified_legacy_top100_special_energy.mist_energy",
        requires_all_four_flag=True,
    )
    _validate_special_energy_group(
        energy["rock_fighting_energy"],
        field="verified_legacy_top100_special_energy.rock_fighting_energy",
        requires_all_four_flag=False,
    )


def _validate_root_metadata(payload: dict[str, object]) -> list[object]:
    root_required = frozenset({
        "observed_at",
        "requested_rank_count",
        "available_team_count",
        "available_recent_game_count",
        "missing_teams",
        "missing_games",
        "rank_bands",
        "evidence_scopes",
        "verified_legacy_top100_special_energy",
        "limitations",
        "source_artifacts",
        "profiles",
    })
    _require_keys(payload, root_required, field="root")
    _require_string(payload["observed_at"], field="observed_at")
    _require_int(
        payload["requested_rank_count"],
        field="requested_rank_count",
        minimum=1,
    )
    _require_int(payload["available_team_count"], field="available_team_count")
    _require_int(
        payload["available_recent_game_count"],
        field="available_recent_game_count",
    )
    missing_teams = _require_list(payload["missing_teams"], field="missing_teams")
    for index, team in enumerate(missing_teams):
        _require_string(team, field=f"missing_teams[{index}]")
    _require_int(payload["missing_games"], field="missing_games")
    rank_bands = _require_list(payload["rank_bands"], field="rank_bands")
    for index, rank_band in enumerate(rank_bands):
        _require_string(rank_band, field=f"rank_bands[{index}]")
    _validate_evidence_scopes(payload["evidence_scopes"])
    _validate_special_energy(
        payload["verified_legacy_top100_special_energy"],
    )
    limitations = _require_list(payload["limitations"], field="limitations")
    for index, limitation in enumerate(limitations):
        item = _require_object(limitation, field=f"limitations[{index}]")
        _require_keys(item, frozenset({"code", "detail"}), field=f"limitations[{index}]")
        _require_string(item["code"], field=f"limitations[{index}].code")
        _require_string(item["detail"], field=f"limitations[{index}].detail")
    source_artifacts = _require_list(
        payload["source_artifacts"],
        field="source_artifacts",
    )
    if not source_artifacts:
        raise _fail("source_artifacts", "a non-empty list")
    for index, artifact in enumerate(source_artifacts):
        _require_string(artifact, field=f"source_artifacts[{index}]")
    return _require_list(payload["profiles"], field="profiles")


def _validate_signature_collisions(profiles: tuple[ArchetypeProfile, ...]) -> None:
    signatures = tuple(
        (profile.key, signature)
        for profile in profiles
        for signature in profile.identifying_sets
    )
    for index, (left_key, left) in enumerate(signatures):
        for right_key, right in signatures[index + 1 :]:
            if left <= right or right <= left:
                raise ValueError(
                    "identifying signature subset collision: "
                    f"{left_key} {sorted(left)} / {right_key} {sorted(right)}"
                )


def load_profiles(data_path: Path = DATA_PATH) -> tuple[ArchetypeProfile, ...]:
    if not isinstance(data_path, Path):
        raise _fail("data_path", "a pathlib.Path")
    payload = _require_object(
        json.loads(data_path.read_text(encoding="utf-8")),
        field="root",
    )
    rows = _validate_root_metadata(payload)
    profiles = tuple(
        _profile_from_row(row, index=index)
        for index, row in enumerate(rows)
    )
    keys = tuple(profile.key for profile in profiles)
    if len(set(keys)) != len(keys):
        raise ValueError("profile keys must be unique")
    _validate_signature_collisions(profiles)
    return profiles


def assess_archetype(
    public_card_ids: set[int],
    observed_attacker_ids: set[int],
    *,
    profiles: tuple[ArchetypeProfile, ...] | None = None,
) -> ArchetypeAssessment:
    available = load_profiles() if profiles is None else profiles
    if type(public_card_ids) is not set:
        raise _fail("public_card_ids", "a set of positive card IDs")
    if type(observed_attacker_ids) is not set:
        raise _fail("observed_attacker_ids", "a set of positive card IDs")
    public_evidence = frozenset(
        _validate_card_id(card_id, field="public_card_ids")
        for card_id in public_card_ids
    )
    attacker_evidence = frozenset(
        _validate_card_id(card_id, field="observed_attacker_ids")
        for card_id in observed_attacker_ids
    )
    matches = tuple(
        profile
        for profile in available
        if any(
            signature <= public_evidence
            for signature in profile.identifying_sets
        )
        or bool(profile.identifying_attacker_ids & attacker_evidence)
    )
    candidates = matches if matches else available
    unique = matches[0] if len(matches) == 1 else None
    return ArchetypeAssessment(
        profile=unique,
        candidate_keys=tuple(sorted(profile.key for profile in candidates)),
        evidence_card_ids=public_evidence,
        evidence_attacker_ids=attacker_evidence,
    )
