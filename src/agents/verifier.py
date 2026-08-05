from __future__ import annotations

import json
from typing import Any

from src.agents.prompts import VERIFIER_OUTPUT_RULES
from src.agents.runtime import AgentRuntime
from src.models import FinalCaseOutput, VerificationDefect, VerificationResult


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
    system = f"""You are an independent Verifier Agent. Review the candidate against the dossier and EC_POLICY_V2. You may not query raw CSVs. Do not silently repair. Validate only IDs explicitly present in candidate.evidence_ids or a specialist report's evidence array; never construct an ID by appending ':1' to an order ID and never report IDs that are not emitted by the candidate or reports. Call lookup_evidence_id once per distinct emitted evidence ID and validate_array_limits once. Never repeat a successful tool call. After these checks, immediately emit the verification JSON. {VERIFIER_OUTPUT_RULES}"""
    user = json.dumps({"case": case, "dossier": dossier, "candidate": candidate}, ensure_ascii=False)
    runtime.handoff(case_id, "policy_adjudicator", "verifier", "verification_result", "Independently verify proposed output", {"candidate_keys": list(candidate)})
    try:
        model_result = runtime.run_json(case_id=case_id, agent="verifier", system=system, user=user, allowed_tools=["lookup_evidence_id", "validate_array_limits"], validator=VerificationResult.model_validate, max_rounds=8)
        verified = VerificationResult.model_validate(model_result)
    except Exception as exc:
        verified = VerificationResult(case_id=case_id, status="REVISION_REQUIRED", defects=[VerificationDefect(code="VERIFIER_FAILURE", description=str(exc), responsible_agent="verifier", required_action="retry verifier")], checks=[])
    hard_defects = deterministic_checks(candidate, runtime.tools.store)
    if hard_defects:
        verified.status = "REVISION_REQUIRED"
        verified.defects.extend(VerificationDefect.model_validate(defect) for defect in hard_defects)
    runtime.trace.write("verification_completed", case_id, "verifier", status=verified.status, defect_count=len(verified.defects))
    return verified.model_dump()


async def run_verifier_async(runtime: AgentRuntime, case: dict[str, Any], dossier: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    case_id = case["case_id"]
    candidate = decision.get("final_output", {})
    system = f"""You are an independent Verifier Agent. Review the candidate against the dossier and EC_POLICY_V2. You may not query raw CSVs. Do not silently repair. Validate only IDs explicitly present in candidate.evidence_ids or a specialist report's evidence array; never construct an ID by appending ':1' to an order ID and never report IDs that are not emitted by the candidate or reports. Call lookup_evidence_id once per distinct emitted evidence ID and validate_array_limits once. Never repeat a successful tool call. After these checks, immediately emit the verification JSON. {VERIFIER_OUTPUT_RULES}"""
    user = json.dumps({"case": case, "dossier": dossier, "candidate": candidate}, ensure_ascii=False)
    runtime.handoff(case_id, "policy_adjudicator", "verifier", "verification_result", "Independently verify proposed output", {"candidate_keys": list(candidate)})
    try:
        model_result = await runtime.run_json_async(case_id=case_id, agent="verifier", system=system, user=user, allowed_tools=["lookup_evidence_id", "validate_array_limits"], validator=VerificationResult.model_validate, max_rounds=8)
        verified = VerificationResult.model_validate(model_result)
    except Exception as exc:
        verified = VerificationResult(case_id=case_id, status="REVISION_REQUIRED", defects=[VerificationDefect(code="VERIFIER_FAILURE", description=str(exc), responsible_agent="verifier", required_action="retry verifier")], checks=[])
    hard_defects = deterministic_checks(candidate, runtime.tools.store)
    if hard_defects:
        verified.status = "REVISION_REQUIRED"
        verified.defects.extend(VerificationDefect.model_validate(defect) for defect in hard_defects)
    runtime.trace.write("verification_completed", case_id, "verifier", status=verified.status, defect_count=len(verified.defects), mode="async")
    return verified.model_dump()
