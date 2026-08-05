POLICY_TEXT = """EC_POLICY_V2 is authoritative. Check primary issues in this exact order:
1 canceled_order_paid: order_status=canceled and payment_total>0; platform; refund payment_total; issue_full_refund.
2 unavailable_order_paid: order_status=unavailable and payment_total>0; platform; refund payment_total; issue_full_refund.
3 late_delivery_seller: delivery_variance_hours>0 and any late_handoff=true; responsible parties are exactly late sellers; refund freight_total; refund_freight.
4 late_delivery_logistics: delivery_variance_hours>0 and no late_handoff=true; responsible party logistics_provider; refund freight_total; refund_freight.
5 valid_split_payment: payment_row_count>=2 and reconciled=true; no refund; explain_valid_split_payment.
6 unsupported_late_claim: delivery_variance_hours<=0 and reconciled=true; no refund; reject_late_refund.
Secondary order: multi_item_order, multi_seller_order, split_payment, repeat_customer, multiple_categories.
Additional action order: review_seller_handoff or review_carrier_delay, verify_refund_completion, coordinate_multi_seller_case, verify_payment_allocation.
Root causes: SELLER_HANDOFF_AFTER_LIMIT, CARRIER_DELIVERED_AFTER_ESTIMATE, ORDER_CANCELED_AFTER_PAYMENT, ORDER_UNAVAILABLE_AFTER_PAYMENT, MULTIPLE_PAYMENTS_RECONCILED, DELIVERY_WITHIN_ESTIMATE."""

COMMON = """You must use authorized tools before answering. Follow this protocol: (1) inspect source records, (2) compute only assigned derived values with tools, (3) check every required field and evidence ID, (4) emit JSON. Never answer from memory or the customer message alone. Return JSON only. Evidence is a list of strings, never objects or copied tool records. Valid evidence formats are order:<id>, item:<order_id>:<order_item_id>, payment:<order_id>:<payment_sequential>, seller:<seller_id>, policy:<root_cause_code>. Preserve source order, report missing facts as null/open_questions, and do not infer facts outside your domain. When multiple authorized tool calls are independent, issue them in the same tool-call turn to reduce latency; do not repeat a successful call."""

SPECIALIST_PROMPTS = {
    "customer_investigator": COMMON + """ You are Customer Investigator. Only investigate customer identity/history. Call get_order_customer, get_customer, then get_orders_by_unique_customer. Return findings exactly with customer_id, customer_unique_id, related_order_ids, repeat_customer. Exclude the claimed order and cap related IDs at five. Never discuss payments, delivery, products, refunds, or policy.""",
    "order_product_investigator": COMMON + """ You are Order/Product Investigator. Only investigate order/items/products/sellers/categories. In tool-call round 1, call get_order and get_order_items together. After their results, issue every independent get_product call and every independent get_seller call together in one batch; never repeat a successful call and never call products or sellers one at a time across many rounds. Then emit the report. Return findings exactly with order_id, order_status, item_count, seller_count, category_count, item_ids, seller_ids, product_ids, category_names, multi_item_order, multi_seller_order, multiple_categories, seller_shipping_limits. Do not decide responsibility, lateness, refund, or issue.""",
    "payment_auditor": COMMON + """ You are Payment Auditor. Only investigate payment rows and reconciliation. Call get_order_payments and get_order_items, then use Decimal-safe calculation tools. Calculation tools return scalar numbers/booleans. Return findings exactly with payment_row_count, item_total_brl, freight_total_brl, expected_total_brl, payment_total_brl, difference_brl, reconciled, split_payment, payment_types, payment_ids. For no item rows, item_total_brl/freight_total_brl/expected_total_brl/difference_brl/reconciled are null; payment_total_brl still uses payment rows. Do not decide refund or policy.""",
    "delivery_investigator": COMMON + """ You are Delivery Investigator. Only investigate delivery and seller handoff times. In the first tool-call turn, call get_order_delivery_timestamps and get_order_items together. Call hours_between only when both timestamps are non-null; never call it with null arguments and never repeat a successful null calculation. For each seller with usable timestamps, calculate handoff variance once. Then emit the report. Return findings exactly with delivered_at, estimated_delivery_at, carrier_handoff_at, delivery_variance_hours, seller_handoff_analysis, late_handoff_seller_ids. Preserve timestamp strings and use null for unavailable values. Do not assign blame, root cause, refund, or issue.""",
}

REPORT_CONTRACTS = {
    "customer_investigator": '{"agent":"customer_investigator","case_id":"EC_001","status":"completed","findings":{"customer_id":"<id>","customer_unique_id":"<id>","related_order_ids":[],"repeat_customer":false},"evidence":["order:<order_id>"],"confidence":0.0,"open_questions":[]}',
    "order_product_investigator": '{"agent":"order_product_investigator","case_id":"EC_001","status":"completed","findings":{"order_id":"<id>","order_status":"delivered","item_count":0,"seller_count":0,"category_count":0,"item_ids":[],"seller_ids":[],"product_ids":[],"category_names":[],"multi_item_order":false,"multi_seller_order":false,"multiple_categories":false,"seller_shipping_limits":[]},"evidence":["order:<order_id>"],"confidence":0.0,"open_questions":[]}',
    "payment_auditor": '{"agent":"payment_auditor","case_id":"EC_001","status":"completed","findings":{"payment_row_count":0,"item_total_brl":0.0,"freight_total_brl":0.0,"expected_total_brl":0.0,"payment_total_brl":0.0,"difference_brl":0.0,"reconciled":false,"split_payment":false,"payment_types":[],"payment_ids":[]},"evidence":["order:<order_id>"],"confidence":0.0,"open_questions":[]}',
    "delivery_investigator": '{"agent":"delivery_investigator","case_id":"EC_001","status":"completed","findings":{"delivered_at":null,"estimated_delivery_at":null,"carrier_handoff_at":null,"delivery_variance_hours":null,"seller_handoff_analysis":[],"late_handoff_seller_ids":[]},"evidence":["order:<order_id>"],"confidence":0.0,"open_questions":[]}',
}

POLICY_OUTPUT_RULES = """Return JSON only, with exactly these wrapper fields: agent, case_id, decision, final_output, root_cause_analysis, justification, evidence_ids, confidence, open_questions. `decision` must contain primary_issue, secondary_issues, case_status, confidence. `final_output` must contain exactly the repository sections: case_id, case_assessment, affected_entities, customer_context, product_context, delivery_analysis, payment_reconciliation, root_cause_analysis, evidence_ids, financial_resolution, resolution_actions. Use only evidence IDs present in reports. Keep limits, ordering, null handling, and two-decimal money/hour rules."""

VERIFIER_OUTPUT_RULES = """Return JSON only, with exactly agent, case_id, status, defects, checks. Use lookup_evidence_id for every evidence ID and validate_array_limits. Recalculate money/time where applicable. Report VERIFIED only when schema, evidence, policy priority, arithmetic, null handling, ordering, and limits all pass. Never repair silently."""


def _obj(properties: dict[str, dict]) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _arr(item: dict) -> dict:
    return {"type": "array", "items": item}


def _nullable(item: dict) -> dict:
    return {"anyOf": [item, {"type": "null"}]}


_string = {"type": "string"}
_number = {"type": "number"}
_string_list = _arr(_string)
_number_or_null = _nullable(_number)
_string_or_null = _nullable(_string)
_cause = _obj({"cause_code": _string, "rank": {"type": "integer"}})
_party = _obj({"party_type": _string, "party_id": _string_or_null})
_handoff = _obj({"seller_id": _string, "shipping_limit_at": _string_or_null, "handoff_variance_hours": _number_or_null, "late_handoff": {"type": "boolean"}})
_justification = _obj({"conclusion": _string, "supporting_report": _string, "supporting_path": _string, "evidence_ids": _string_list})
_assessment = _obj({"primary_issue": _string, "secondary_issues": _string_list, "case_status": {"type": "string", "enum": ["action_required", "no_action"]}, "confidence": _number})
_root_cause = _obj({"ranked_causes": _arr(_cause), "responsible_parties": _arr(_party)})
_final_output = _obj({
    "case_id": _string,
    "case_assessment": _assessment,
    "affected_entities": _obj({"order_ids": _string_list, "item_ids": _string_list, "seller_ids": _string_list, "payment_ids": _string_list}),
    "customer_context": _obj({"customer_unique_id": _string_or_null, "related_order_ids": _string_list}),
    "product_context": _obj({"product_ids": _string_list, "category_names": _string_list}),
    "delivery_analysis": _obj({"delivered_at": _string_or_null, "estimated_delivery_at": _string_or_null, "carrier_handoff_at": _string_or_null, "delivery_variance_hours": _number_or_null, "seller_handoff_analysis": _arr(_handoff), "late_handoff_seller_ids": _string_list}),
    "payment_reconciliation": _obj({"currency": _string, "item_total_brl": _number_or_null, "freight_total_brl": _number_or_null, "expected_total_brl": _number_or_null, "payment_total_brl": _number_or_null, "difference_brl": _number_or_null, "reconciled": _nullable({"type": "boolean"}), "payment_types": _string_list}),
    "root_cause_analysis": _root_cause,
    "evidence_ids": _string_list,
    "financial_resolution": _obj({"currency": _string, "recommended_refund_brl": _number}),
    "resolution_actions": _string_list,
})

POLICY_RESPONSE_SCHEMA = _obj({
    "agent": {"type": "string", "enum": ["policy_adjudicator"]},
    "case_id": _string,
    "decision": _obj({"primary_issue": _string, "secondary_issues": _string_list, "case_status": {"type": "string", "enum": ["action_required", "no_action"]}, "confidence": _number}),
    "final_output": _final_output,
    "root_cause_analysis": _root_cause,
    "justification": _arr(_justification),
    "evidence_ids": _string_list,
    "confidence": _number,
    "open_questions": _string_list,
})
