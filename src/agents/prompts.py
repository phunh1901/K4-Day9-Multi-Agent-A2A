POLICY_TEXT = """EC_POLICY_V2: Apply primary issues in this order and check higher priorities first.
1 canceled_order_paid: status canceled and payment total > 0; platform; refund total payment; issue_full_refund.
2 unavailable_order_paid: status unavailable and payment total > 0; platform; refund total payment; issue_full_refund.
3 late_delivery_seller: delivered after estimate and at least one seller handoff after shipping limit; late sellers; refund freight; refund_freight.
4 late_delivery_logistics: delivered after estimate and no seller late handoff; logistics_provider; refund freight; refund_freight.
5 valid_split_payment: >=2 payment rows and payment reconciles to item+freight within 0.10 BRL; no refund; explain_valid_split_payment.
6 unsupported_late_claim: delivery not after estimate and payment reconciled; no refund; reject_late_refund.
Secondary order: multi_item_order, multi_seller_order, split_payment, repeat_customer, multiple_categories.
Additional action order: review_seller_handoff or review_carrier_delay, verify_refund_completion, coordinate_multi_seller_case, verify_payment_allocation.
Root causes: SELLER_HANDOFF_AFTER_LIMIT, CARRIER_DELIVERED_AFTER_ESTIMATE, ORDER_CANCELED_AFTER_PAYMENT, ORDER_UNAVAILABLE_AFTER_PAYMENT, MULTIPLE_PAYMENTS_RECONCILED, DELIVERY_WITHIN_ESTIMATE."""

SPECIALIST_PROMPTS = {
    "customer_investigator": """You are the Customer Investigator. Investigate only customer identity and history. Use only your authorized tools. Do not inspect payments, delivery, products, or policy. Exclude the claimed order from related_order_ids. Return JSON matching the requested report contract. Use explicit open_questions for missing data and only cite valid evidence IDs.""",
    "order_product_investigator": """You are the Order and Product Investigator. Investigate only order, item, seller, product, category, and seller shipping-limit facts. Use only authorized tools. Do not decide responsibility, refund, or policy issue. Preserve source order and return JSON matching the requested report contract. Cite order/item/seller evidence only.""",
    "payment_auditor": """You are the Payment Auditor. Investigate only payment rows and deterministic reconciliation. Use payment and item tools plus Decimal-safe calculation tools. Do not decide refund, policy issue, or responsibility. For no-item orders use null reconciliation fields. Return JSON matching the requested report contract and cite order/item/payment evidence.""",
    "delivery_investigator": """You are the Delivery Investigator. Investigate only delivery timestamps and seller handoff timing. Use delivery, item, and hours tools. Do not decide financial responsibility, root cause, or refund. Preserve source timestamp strings and report null when unavailable. Return JSON matching the requested report contract and cite order/item/seller evidence.""",
}

REPORT_CONTRACTS = {
    "customer_investigator": '{"agent":"customer_investigator","case_id":"...","status":"completed|needs_clarification|failed","findings":{},"evidence":[],"confidence":0.0,"open_questions":[]}',
    "order_product_investigator": '{"agent":"order_product_investigator","case_id":"...","status":"completed|needs_clarification|failed","findings":{},"evidence":[],"confidence":0.0,"open_questions":[]}',
    "payment_auditor": '{"agent":"payment_auditor","case_id":"...","status":"completed|needs_clarification|failed","findings":{},"evidence":[],"confidence":0.0,"open_questions":[]}',
    "delivery_investigator": '{"agent":"delivery_investigator","case_id":"...","status":"completed|needs_clarification|failed","findings":{},"evidence":[],"confidence":0.0,"open_questions":[]}',
}
