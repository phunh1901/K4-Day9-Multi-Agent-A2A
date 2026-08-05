from __future__ import annotations

import json
from typing import Any

from src.agents.prompts import POLICY_OUTPUT_RULES, POLICY_RESPONSE_SCHEMA, POLICY_TEXT
from src.agents.runtime import AgentRuntime
from src.models import FinalCaseOutput, PolicyDecision


def _validate_policy_payload(payload: dict[str, Any]) -> PolicyDecision:
    decision = PolicyDecision.model_validate(payload)
    final_output = FinalCaseOutput.model_validate(decision.final_output)
    business_errors = final_output.validate_business_shape()
    if business_errors:
        raise ValueError("; ".join(business_errors))
    return decision


def _policy_validator(runtime: AgentRuntime):
    def validate(payload: dict[str, Any]) -> PolicyDecision:
        decision = _validate_policy_payload(payload)
        invalid = [evidence_id for evidence_id in decision.final_output.get("evidence_ids", []) if not runtime.tools.store.evidence_exists(evidence_id)]
        if invalid:
            raise ValueError(f"invalid final evidence IDs: {invalid}")
        return decision
    return validate


def run_policy_adjudicator(runtime: AgentRuntime, case: dict[str, Any], dossier: dict[str, Any], defects: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    case_id = case["case_id"]
    system = f"""You are the Policy Adjudicator Agent. You have no raw-data tools. Build a condition table from the four specialist reports, then check primary conditions 1 through 6 in order. Never infer absent facts or copy raw tool records as evidence. If facts conflict or are missing, put that in open_questions. {POLICY_OUTPUT_RULES}\n\n{POLICY_TEXT}"""
    user = json.dumps({"case": case, "dossier": dossier, "previous_defects": defects or [], "required_shape": ["case_id", "case_assessment", "affected_entities", "customer_context", "product_context", "delivery_analysis", "payment_reconciliation", "root_cause_analysis", "evidence_ids", "financial_resolution", "resolution_actions"]}, ensure_ascii=False)
    runtime.handoff(case_id, "coordinator", "policy_adjudicator", "task", "Adjudicate dossier under EC_POLICY_V2", {"report_names": list(dossier)})
    payload = runtime.run_json(case_id=case_id, agent="policy_adjudicator", system=system, user=user, allowed_tools=[], validator=_policy_validator(runtime), response_schema=POLICY_RESPONSE_SCHEMA, max_rounds=10)
    decision = PolicyDecision.model_validate(payload)
    runtime.trace.write("policy_decision_created", case_id, "policy_adjudicator", evidence_count=len(decision.evidence_ids), primary_issue=decision.decision.get("primary_issue"))
    return decision.model_dump()


async def run_policy_adjudicator_async(runtime: AgentRuntime, case: dict[str, Any], dossier: dict[str, Any], defects: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    case_id = case["case_id"]
    system = f"""You are the Policy Adjudicator Agent. You have no raw-data tools. Build a condition table from the four specialist reports, then check primary conditions 1 through 6 in order. Never infer absent facts or copy raw tool records as evidence. If facts conflict or are missing, put that in open_questions. {POLICY_OUTPUT_RULES}\n\n{POLICY_TEXT}"""
    user = json.dumps({"case": case, "dossier": dossier, "previous_defects": defects or [], "required_shape": ["case_id", "case_assessment", "affected_entities", "customer_context", "product_context", "delivery_analysis", "payment_reconciliation", "root_cause_analysis", "evidence_ids", "financial_resolution", "resolution_actions"]}, ensure_ascii=False)
    runtime.handoff(case_id, "coordinator", "policy_adjudicator", "task", "Adjudicate dossier under EC_POLICY_V2", {"report_names": list(dossier)})
    payload = await runtime.run_json_async(case_id=case_id, agent="policy_adjudicator", system=system, user=user, allowed_tools=[], validator=_policy_validator(runtime), response_schema=POLICY_RESPONSE_SCHEMA, max_rounds=10)
    decision = PolicyDecision.model_validate(payload)
    runtime.trace.write("policy_decision_created", case_id, "policy_adjudicator", evidence_count=len(decision.evidence_ids), primary_issue=decision.decision.get("primary_issue"), mode="async")
    return decision.model_dump()
