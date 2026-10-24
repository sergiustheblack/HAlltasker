"""YAML configuration schema and parsing into SyncPair objects."""

from __future__ import annotations

import re
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import DEFAULT_INTERVAL, DOMAIN, MIN_INTERVAL
from .core.model import DeletePolicy, DirectionRule, Filter, SyncPair, Transform


def _valid_regex(value: str) -> str:
    re.compile(value)
    return value


def _delete_policy(value: Any) -> DeletePolicy:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value not in ("true", "false", "soft"):
        raise vol.Invalid(f"invalid delete policy: {value!r}")
    return value


_FILTER_SCHEMA = vol.Schema(
    {
        vol.Optional("title_regex"): vol.All(vol.Coerce(str), _valid_regex),
        vol.Optional("require_due", default=False): cv.boolean,
    }
)

_TRANSFORM_SCHEMA = vol.Schema(
    {
        vol.Optional("due", default="keep"): vol.In(("keep", "date_only", "drop")),
        vol.Optional("title_prefix", default=""): cv.string,
    }
)

_DIRECTION_SCHEMA = vol.Schema(
    {
        vol.Optional("create", default=True): cv.boolean,
        vol.Optional("update", default=True): cv.boolean,
        vol.Optional("complete", default=True): cv.boolean,
        vol.Optional("delete", default=True): vol.All(vol.Any(bool, "soft"), _delete_policy),
        vol.Optional("filter", default={}): _FILTER_SCHEMA,
        vol.Optional("transform", default={}): _TRANSFORM_SCHEMA,
    }
)

_PAIR_SCHEMA = vol.Schema(
    {
        vol.Required("id"): vol.All(cv.string, vol.Match(r"^[a-z0-9_]+$")),
        vol.Required("a"): cv.entity_domain("todo"),
        vol.Required("b"): cv.entity_domain("todo"),
        vol.Optional("interval", default=DEFAULT_INTERVAL): vol.All(
            cv.positive_int, vol.Range(min=MIN_INTERVAL)
        ),
        vol.Optional("conflict", default="prefer_a"): vol.In(("prefer_a", "prefer_b")),
        vol.Optional("initial_sync", default="merge"): vol.In(("merge", "dry_run")),
        vol.Optional("enabled", default=True): cv.boolean,
        vol.Optional("a_to_b", default={}): _DIRECTION_SCHEMA,
        vol.Optional("b_to_a", default={}): _DIRECTION_SCHEMA,
    }
)


def _unique_ids(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = [pair["id"] for pair in pairs]
    if len(ids) != len(set(ids)):
        raise vol.Invalid(f"pair ids must be unique: {ids}")
    return pairs


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {vol.Required("pairs"): vol.All(cv.ensure_list, [_PAIR_SCHEMA], _unique_ids)}
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def parse_pairs(conf: dict[str, Any]) -> list[SyncPair]:
    """Turn the validated `halltasker:` config dict into SyncPair objects."""
    return [_pair(raw) for raw in conf["pairs"]]


def _pair(raw: dict[str, Any]) -> SyncPair:
    return SyncPair(
        id=raw["id"],
        a=raw["a"],
        b=raw["b"],
        interval=raw["interval"],
        conflict=raw["conflict"],
        initial_sync=raw["initial_sync"],
        enabled=raw["enabled"],
        a_to_b=_rule(raw["a_to_b"]),
        b_to_a=_rule(raw["b_to_a"]),
    )


def _rule(raw: dict[str, Any]) -> DirectionRule:
    return DirectionRule(
        create=raw["create"],
        update=raw["update"],
        complete=raw["complete"],
        delete=raw["delete"],
        filter=Filter(
            title_regex=raw["filter"].get("title_regex"),
            require_due=raw["filter"]["require_due"],
        ),
        transform=Transform(
            due=raw["transform"]["due"],
            title_prefix=raw["transform"]["title_prefix"],
        ),
    )
