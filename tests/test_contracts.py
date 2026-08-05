from src.models import AgentMessage, FinalCaseOutput


def test_agent_message_contract():
    message = AgentMessage(case_id="EC_001", sender="coordinator", recipient="payment_auditor", message_type="task", objective="audit")
    assert message.message_id.startswith("msg-")


def test_final_output_limits_and_history_separation():
    candidate = {
        "case_id": "EC_001",
        "case_assessment": {"primary_issue": "unsupported_late_claim", "secondary_issues": [], "case_status": "no_action", "confidence": 0.9},
        "affected_entities": {"order_ids": ["o1"], "item_ids": [], "seller_ids": [], "payment_ids": []},
        "customer_context": {"customer_unique_id": "c", "related_order_ids": ["o2"]},
        "product_context": {"product_ids": [], "category_names": []},
        "delivery_analysis": {}, "payment_reconciliation": {}, "root_cause_analysis": {},
        "evidence_ids": [], "financial_resolution": {"currency": "BRL", "recommended_refund_brl": 0.0}, "resolution_actions": [],
    }
    assert FinalCaseOutput.model_validate(candidate).validate_business_shape() == []
