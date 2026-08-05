from pathlib import Path

from src.agents.verifier import deterministic_checks
from src.tools.datastore import DataStore


def test_verifier_rejects_invalid_evidence_and_history_leak():
    candidate = {
        "case_id": "EC_001",
        "case_assessment": {"case_status": "no_action", "confidence": 0.8},
        "affected_entities": {"order_ids": ["9b75cdaf2d85857ef023980e15d01546"], "item_ids": [], "seller_ids": [], "payment_ids": []},
        "customer_context": {"related_order_ids": ["9b75cdaf2d85857ef023980e15d01546"]},
        "product_context": {"product_ids": [], "category_names": []},
        "delivery_analysis": {}, "payment_reconciliation": {}, "root_cause_analysis": {},
        "evidence_ids": ["seller:not-real"],
        "financial_resolution": {"recommended_refund_brl": 0}, "resolution_actions": [],
    }
    defects = deterministic_checks(candidate, DataStore(Path("data")))
    codes = {defect["code"] for defect in defects}
    assert "INVALID_EVIDENCE" in codes
    assert "SCHEMA_OR_LIMIT" in codes
