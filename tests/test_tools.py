from pathlib import Path

from src.tools.calculation_tools import compare_money_with_tolerance, hours_between, sum_money
from src.tools.datastore import DataStore
from src.tools.registry import ToolRegistry


ROOT = Path(__file__).parents[1]


def test_datastore_indices_and_stable_rows():
    store = DataStore(ROOT / "data")
    order_id = "9b75cdaf2d85857ef023980e15d01546"
    assert store.order(order_id)["order_id"] == order_id
    items = store.items_for(order_id)
    assert items == store.items_for(order_id)


def test_decimal_money_and_tolerance_boundary():
    assert sum_money(["0.10", "0.20"]) == 0.3
    assert compare_money_with_tolerance("1.00", "1.10", "0.10")
    assert not compare_money_with_tolerance("1.00", "1.11", "0.10")


def test_hours_between_preserves_sign_and_rounding():
    assert hours_between("2018-03-31 15:23:33", "2018-03-28 00:00:00") == 87.39
    assert hours_between(None, "2018-03-28 00:00:00") is None


def test_restricted_registry_returns_json_serializable_records():
    registry = ToolRegistry(DataStore(ROOT / "data"))
    result = registry.get_order_payments("9b75cdaf2d85857ef023980e15d01546")
    assert result["status"] == "success"
    assert result["record_count"] == len(result["records"])


def test_evidence_validation_rejects_unknown_ids():
    store = DataStore(ROOT / "data")
    assert store.evidence_exists("order:9b75cdaf2d85857ef023980e15d01546")
    assert not store.evidence_exists("seller:not-a-seller")
    assert store.evidence_exists("policy:DELIVERY_WITHIN_ESTIMATE")
