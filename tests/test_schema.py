"""Tests for the pair-graph validation of CONFIG_SCHEMA."""

from __future__ import annotations

import pytest
import voluptuous as vol

from custom_components.halltasker.schema import CONFIG_SCHEMA


def _pair(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {"id": "p1", "a": "todo.a", "b": "todo.b"}
    raw.update(overrides)
    return raw


def _config(pairs: list[dict[str, object]]) -> dict[str, object]:
    return {"halltasker": {"pairs": pairs}}


def test_star_of_three_pairs_on_one_node_is_accepted() -> None:
    result = CONFIG_SCHEMA(
        _config(
            [
                _pair(id="p1", a="todo.hub", b="todo.a"),
                _pair(id="p2", a="todo.hub", b="todo.b"),
                _pair(id="p3", a="todo.hub", b="todo.c"),
            ]
        )
    )
    assert len(result["halltasker"]["pairs"]) == 3


def test_pair_connecting_a_node_to_itself_is_rejected() -> None:
    with pytest.raises(vol.Invalid, match=r"connects the node todo\.a to itself"):
        CONFIG_SCHEMA(_config([_pair(a="todo.a", b="todo.a")]))


def test_two_pairs_on_the_same_two_nodes_are_rejected() -> None:
    with pytest.raises(vol.Invalid, match="same two nodes twice at pair 'p2'"):
        CONFIG_SCHEMA(_config([_pair(id="p1"), _pair(id="p2", a="todo.b", b="todo.a")]))


def test_cycle_is_rejected_naming_the_third_pair() -> None:
    with pytest.raises(vol.Invalid, match=r"pairs form a cycle at pair 'p3'"):
        CONFIG_SCHEMA(
            _config(
                [
                    _pair(id="p1", a="todo.a", b="todo.b"),
                    _pair(id="p2", a="todo.b", b="todo.c"),
                    _pair(id="p3", a="todo.a", b="todo.c"),
                ]
            )
        )


def test_reversed_edge_is_still_a_duplicate() -> None:
    with pytest.raises(vol.Invalid, match="same two nodes"):
        CONFIG_SCHEMA(_config([_pair(id="p1"), _pair(id="p2", b="todo.a", a="todo.b")]))


def test_interval_below_minimum_is_rejected() -> None:
    with pytest.raises(vol.Invalid):
        CONFIG_SCHEMA(_config([_pair(interval=5)]))


def test_defaults_materialize_for_a_valid_pair() -> None:
    result = CONFIG_SCHEMA(_config([_pair()]))
    raw = result["halltasker"]["pairs"][0]
    assert raw["interval"] == 60
    assert raw["conflict"] == "prefer_a"
    assert raw["a_to_b"]["delete"] == "true"
