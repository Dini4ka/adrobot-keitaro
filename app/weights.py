# -*- coding: utf-8 -*-
"""Пересчёт долей офферов в потоке.

Доли целочисленные, сумма всегда 100. Остаток от деления раздаётся
по одному проценту первым офферам в списке (как в видео автора ТЗ:
при закреплённых 25% свободные доли стали 38% и 37%).
"""


def normalize_shares(offer_ids: list[int]) -> list[dict]:
    """Распределить 100% поровну между офферами, остаток — первым.

    Возвращает список привязок в том же порядке, что и вход.
    """
    if not offer_ids:
        return []
    base, remainder = divmod(100, len(offer_ids))
    result = []
    for index, offer_id in enumerate(offer_ids):
        share = base + (1 if index < remainder else 0)
        result.append({"offer_id": offer_id, "share": share, "state": "active"})
    return result


def add_offer(offers: list[dict], offer_id: int) -> list[dict]:
    """Добавить оффер и перераспределить доли среди всех офферов."""
    ids = [binding["offer_id"] for binding in offers if binding.get("state") == "active"]
    if offer_id in ids:
        return offers
    ids.append(offer_id)
    return normalize_shares(ids)


def remove_offer(offers: list[dict], offer_id: int) -> list[dict]:
    """Убрать оффер из потока и перераспределить доли среди оставшихся."""
    ids = [binding["offer_id"] for binding in offers
           if binding.get("state") == "active" and binding["offer_id"] != offer_id]
    return normalize_shares(ids)
