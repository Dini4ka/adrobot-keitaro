# -*- coding: utf-8 -*-
"""Пересчёт долей: сумма всегда 100, остаток — первым по порядку."""
import pytest

from app.weights import add_offer, normalize_shares, remove_offer


def _sum(items):
    return sum(item["share"] for item in items)


def test_normalize_one():
    assert normalize_shares([1]) == [{"offer_id": 1, "share": 100, "state": "active"}]


def test_normalize_two_equal():
    items = normalize_shares([1, 2])
    assert _sum(items) == 100
    assert items[0]["share"] == 50
    assert items[1]["share"] == 50


def test_normalize_three_remainder_goes_first():
    items = normalize_shares([10, 20, 30])
    assert [item["share"] for item in items] == [34, 33, 33]
    assert _sum(items) == 100


def test_normalize_four_equal():
    items = normalize_shares([1, 2, 3, 4])
    assert [item["share"] for item in items] == [25, 25, 25, 25]


def test_normalize_empty():
    assert normalize_shares([]) == []


def test_add_offer_rebalances():
    start = normalize_shares([1, 2, 3])  # 34/33/33
    after = add_offer(start, 4)
    assert _sum(after) == 100
    assert [item["share"] for item in after] == [25, 25, 25, 25]


def test_add_existing_offer_is_noop():
    start = normalize_shares([1, 2])
    assert add_offer(start, 1) == start


def test_remove_offer_rebalances_and_drops():
    start = normalize_shares([1, 2, 3, 4])
    after = remove_offer(start, 2)
    ids = [item["offer_id"] for item in after]
    assert 2 not in ids
    assert _sum(after) == 100
    assert [item["share"] for item in after] == [34, 33, 33]


def test_remove_last_offer_gives_empty():
    start = normalize_shares([7])
    assert remove_offer(start, 7) == []


def test_shares_stay_in_input_order():
    items = normalize_shares([50, 10, 90])
    assert [item["offer_id"] for item in items] == [50, 10, 90]
