"""Deterministic interaction checking backed only by approved DB rows."""

from __future__ import annotations

import sqlite3

from .models import CheckResult, IngredientResult


SEVERITY_RANK = {"contraindicated": 0, "caution": 1, "not_listed": 2}
NOT_LISTED_EFFECT = "確認した資料上、クラリスロマイシンとの相互作用記載はありません。"
NOT_LISTED_MECHANISM = "相互作用が存在しないことを保証する結果ではありません。"
NOT_LISTED_ACTION = "最新の電子添文、患者背景、用量、腎・肝機能を別途確認してください。"


def check_drug(
    connection: sqlite3.Connection,
    input_name: str,
    drug_id: str,
    dataset_updated_at: str,
) -> CheckResult:
    drug = connection.execute("SELECT * FROM drugs WHERE id = ?", (drug_id,)).fetchone()
    if drug is None:
        raise KeyError(drug_id)
    ingredient_rows = connection.execute(
        """SELECT d.* FROM product_ingredients pi
           JOIN drugs d ON d.id = pi.ingredient_id
           WHERE pi.product_id = ? ORDER BY d.display_name""",
        (drug_id,),
    ).fetchall()
    if not ingredient_rows:
        ingredient_rows = [drug]

    ingredient_results: list[IngredientResult] = []
    for ingredient in ingredient_rows:
        interaction = connection.execute(
            "SELECT * FROM interactions WHERE ingredient_id = ? AND verified = 1",
            (ingredient["id"],),
        ).fetchone()
        if interaction:
            ingredient_results.append(
                IngredientResult(
                    drug_id=ingredient["id"],
                    generic_name=ingredient["generic_name"] or ingredient["display_name"],
                    status=interaction["severity"],
                    effect=interaction["effect"],
                    mechanism=interaction["mechanism"],
                    action=interaction["action"],
                    source_url=interaction["source_url"],
                    source_revision=interaction["source_revision"],
                )
            )
        else:
            ingredient_results.append(
                IngredientResult(
                    drug_id=ingredient["id"],
                    generic_name=ingredient["generic_name"] or ingredient["display_name"],
                    status="not_listed",
                    effect=NOT_LISTED_EFFECT,
                    mechanism=NOT_LISTED_MECHANISM,
                    action=NOT_LISTED_ACTION,
                )
            )

    decisive = min(ingredient_results, key=lambda item: SEVERITY_RANK[item.status])
    return CheckResult(
        input_name=input_name,
        drug_id=drug_id,
        display_name=drug["display_name"],
        generic_name=drug["generic_name"],
        category=drug["category"],
        ingredients=[item.generic_name for item in ingredient_results],
        status=decisive.status,
        effect=decisive.effect or NOT_LISTED_EFFECT,
        mechanism=decisive.mechanism or NOT_LISTED_MECHANISM,
        action=decisive.action or NOT_LISTED_ACTION,
        source_url=decisive.source_url,
        source_revision=decisive.source_revision,
        dataset_updated_at=dataset_updated_at,
        ingredient_results=ingredient_results,
    )

