from __future__ import annotations

import json
from typing import Any

from src.agents.prompts import VERIFIER_OUTPUT_RULES
from src.agents.runtime import AgentRuntime
from src.models import FinalCaseOutput, VerificationResult


def deterministic_checks(candidate: dict[str, Any], store: Any) -> list[dict[str, str]]:
    defects: list[dict[str, str]] = []
    try:
        output = FinalCaseOutput.model_validate(candidate)
        for error in output.validate_business_shape():
            defects.append({"code": "SCHEMA_OR_LIMIT", "description": error, "responsible_agent": "policy_adjudicator", "required_action": "correct final output"})
        for evidence_id in output.evidence_ids:
            if not store.evidence_exists(evidence_id):
                defects.append({"code": "INVALID_EVIDENCE", "description": f"Evidence does not exist: {evidence_id}", "responsible_agent": "policy_adjudicator", "required_action": "remove or correct evidence"})
    except Exception as exc:
        defects.append({"code": "OUTPUT_SCHEMA_ERROR", "description": str(exc), "responsible_agent": "policy_adjudicator", "required_action": "return valid FinalCaseOutput"})
    return defects


def run_verifier(runtime: AgentRuntime, case: dict[str, Any], dossier: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    case_id = case["case_id"]
    candidate = decision.get("final_output", {})
    system = f"""You are an independent Verifier Agent. Review the candidate against the dossier and EC_POLICY_V2. You may not query raw CSVs. Do not silently repair. {VERIFIER_OUTPUT_RULES}"""
    user = json.dumps({"case": case, "dossier": dossier, "candidate": candidate}, ensure_ascii=False)
    runtime.handoff(case_id, "policy_adjudicator", "verifier", "verification_result", "Independently verify proposed output", {"candidate_keys": list(candidate)})
    try:
        model_result = runtime.run_json(case_id=case_id, agent="verifier", system=system, user=user, allowed_tools=["lookup_evidence_id", "validate_array_limits", "sum_money", "subtract_money", "hours_between"])
        verified = VerificationResult.model_validate(model_result)
    except Exception as exc:
        verified = VerificationResult(case_id=case_id, status="REVISION_REQUIRED", defects=[{"code": "VERIFIER_FAILURE", "description": str(exc), "responsible_agent": "verifier", "required_action": "retry verifier"}], checks=[])
    hard_defects = deterministic_checks(candidate, runtime.tools.store)
    if hard_defects:
        verified.status = "REVISION_REQUIRED"
        verified.defects.extend(hard_defects)
    runtime.trace.write("verification_completed", case_id, "verifier", status=verified.status, defect_count=len(verified.defects))
    return verified.model_dump()
