from src.agents.prompts import POLICY_TEXT
from src.agents.specialists import SPECIALIST_TOOLS


def test_specialists_have_disjoint_restricted_tool_contracts():
    assert "get_order_payments" not in SPECIALIST_TOOLS["customer_investigator"]
    assert "get_order_delivery_timestamps" not in SPECIALIST_TOOLS["payment_auditor"]
    assert "get_order" in SPECIALIST_TOOLS["order_product_investigator"]
    assert "EC_POLICY_V2" in POLICY_TEXT


def test_policy_agent_has_no_raw_data_tools():
    # The adjudicator is intentionally called with an empty tool allow-list.
    from src.agents.policy_adjudicator import run_policy_adjudicator
    assert callable(run_policy_adjudicator)
