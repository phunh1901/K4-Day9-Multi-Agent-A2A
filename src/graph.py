from __future__ import annotations

import json
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.agents.policy_adjudicator import run_policy_adjudicator, run_policy_adjudicator_async
from src.agents.runtime import AgentRuntime
from src.agents.specialists import run_specialist, run_specialist_async
from src.agents.verifier import run_verifier, run_verifier_async
from src.models import FinalCaseOutput
from src.state import InvestigationState


SPECIALISTS = ["customer_investigator", "order_product_investigator", "payment_auditor", "delivery_investigator"]


def _dossier(state: InvestigationState) -> dict[str, Any]:
    return {name: state[f"{name}_report"] for name in ("customer", "order_product", "payment", "delivery")}


def run_case(runtime: AgentRuntime, case: dict[str, Any], max_revisions: int = 2, max_concurrency: int = 4) -> InvestigationState:
    state: InvestigationState = {"case": case, "revision_count": 0, "errors": [], "assignments": [{"agent": name, "order_id": case["customer_request"]["claimed_order_id"]} for name in SPECIALISTS]}
    runtime.trace.write("case_started", case["case_id"], "coordinator", order_id=case["customer_request"]["claimed_order_id"])
    with ThreadPoolExecutor(max_workers=max_concurrency) as pool:
        futures = {pool.submit(run_specialist, runtime, agent, case): agent for agent in SPECIALISTS}
        for future in as_completed(futures):
            agent = futures[future]
            key = agent.removesuffix("_investigator").replace("_auditor", "") + "_report"
            if agent == "order_product_investigator":
                key = "order_product_report"
            elif agent == "customer_investigator":
                key = "customer_report"
            elif agent == "payment_auditor":
                key = "payment_report"
            elif agent == "delivery_investigator":
                key = "delivery_report"
            try:
                state[key] = future.result()
            except Exception as exc:
                state["errors"].append({"agent": agent, "error": str(exc)})
    if state["errors"]:
        runtime.trace.write("case_failed", case["case_id"], "coordinator", errors=state["errors"])
        return state
    state["investigation_dossier"] = _dossier(state)
    runtime.trace.write("agent_handoff", case["case_id"], "coordinator", recipient="policy_adjudicator", message_type="finding", objective="Complete investigation dossier", report_names=list(state["investigation_dossier"]))
    defects: list[dict[str, Any]] = []
    for attempt in range(max_revisions + 1):
        state["revision_count"] = attempt
        if attempt and defects:
            responsible = {defect.get("responsible_agent") for defect in defects}
            for specialist in SPECIALISTS:
                if specialist in responsible:
                    try:
                        key = {"customer_investigator": "customer_report", "order_product_investigator": "order_product_report", "payment_auditor": "payment_report", "delivery_investigator": "delivery_report"}[specialist]
                        state[key] = run_specialist(runtime, specialist, case)
                        state["investigation_dossier"] = _dossier(state)
                    except Exception as exc:
                        state["errors"].append({"agent": specialist, "error": str(exc)})
        try:
            state["policy_decision"] = run_policy_adjudicator(runtime, case, state["investigation_dossier"], defects)
        except Exception as exc:
            state["errors"].append({"agent": "policy_adjudicator", "error": str(exc)})
            runtime.trace.write("case_failed", case["case_id"], "policy_adjudicator", error=str(exc))
            return state
        candidate = state["policy_decision"].get("final_output", {})
        try:
            FinalCaseOutput.model_validate(candidate)
        except Exception:
            pass
        try:
            state["verifier_result"] = run_verifier(runtime, case, state["investigation_dossier"], state["policy_decision"])
        except Exception as exc:
            state["errors"].append({"agent": "verifier", "error": str(exc)})
            runtime.trace.write("case_failed", case["case_id"], "verifier", error=str(exc))
            return state
        if state["verifier_result"]["status"] == "VERIFIED":
            state["final_output"] = candidate
            runtime.trace.write("case_completed", case["case_id"], "coordinator", revision_count=attempt)
            return state
        defects = state["verifier_result"]["defects"]
        if attempt < max_revisions:
            runtime.trace.write("revision_requested", case["case_id"], "verifier", defects=defects, revision_count=attempt + 1)
    state["errors"].append({"agent": "verifier", "error": "revision limit exceeded", "defects": defects})
    runtime.trace.write("case_failed", case["case_id"], "coordinator", errors=state["errors"])
    return state


async def run_case_async(runtime: AgentRuntime, case: dict[str, Any], max_revisions: int = 1) -> InvestigationState:
    """Async case graph: specialist calls fan out, then policy and verification are sequenced."""
    state: InvestigationState = {"case": case, "revision_count": 0, "errors": [], "assignments": [{"agent": name, "order_id": case["customer_request"]["claimed_order_id"]} for name in SPECIALISTS]}
    case_id = case["case_id"]
    runtime.trace.write("case_started", case_id, "coordinator", order_id=case["customer_request"]["claimed_order_id"], mode="async")
    results = await asyncio.gather(*(run_specialist_async(runtime, agent, case) for agent in SPECIALISTS), return_exceptions=True)
    keys = {"customer_investigator": "customer_report", "order_product_investigator": "order_product_report", "payment_auditor": "payment_report", "delivery_investigator": "delivery_report"}
    for agent, result in zip(SPECIALISTS, results):
        if isinstance(result, Exception):
            state["errors"].append({"agent": agent, "error": str(result)})
        else:
            state[keys[agent]] = result
    if state["errors"]:
        runtime.trace.write("case_failed", case_id, "coordinator", errors=state["errors"], mode="async")
        return state
    state["investigation_dossier"] = _dossier(state)
    defects: list[dict[str, Any]] = []
    for attempt in range(max_revisions + 1):
        state["revision_count"] = attempt
        try:
            state["policy_decision"] = await run_policy_adjudicator_async(runtime, case, state["investigation_dossier"], defects)
            state["verifier_result"] = await run_verifier_async(runtime, case, state["investigation_dossier"], state["policy_decision"])
        except Exception as exc:
            state["errors"].append({"agent": "policy_or_verifier", "error": str(exc)})
            runtime.trace.write("case_failed", case_id, "coordinator", errors=state["errors"], mode="async")
            return state
        if state["verifier_result"]["status"] == "VERIFIED":
            state["final_output"] = state["policy_decision"].get("final_output", {})
            runtime.trace.write("case_completed", case_id, "coordinator", revision_count=attempt, mode="async")
            return state
        defects = state["verifier_result"]["defects"]
        if attempt < max_revisions:
            runtime.trace.write("revision_requested", case_id, "verifier", defects=defects, revision_count=attempt + 1, mode="async")
    state["errors"].append({"agent": "verifier", "error": "revision limit exceeded", "defects": defects})
    runtime.trace.write("case_failed", case_id, "coordinator", errors=state["errors"], mode="async")
    return state
