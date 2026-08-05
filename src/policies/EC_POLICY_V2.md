# EC_POLICY_V2

Apply primary issues in exactly this priority order. The adjudicator must check every higher-priority condition before selecting a lower one.

1. `canceled_order_paid`: order status is `canceled` and total payment is greater than zero. Responsible party `platform`; refund total payment; action `issue_full_refund`.
2. `unavailable_order_paid`: order status is `unavailable` and total payment is greater than zero. Responsible party `platform`; refund total payment; action `issue_full_refund`.
3. `late_delivery_seller`: delivery is after estimated delivery and at least one seller handed off after its shipping limit. Responsible party is each late seller; refund total freight; action `refund_freight`.
4. `late_delivery_logistics`: delivery is after estimated delivery and no seller handed off late. Responsible party `logistics_provider`; refund total freight; action `refund_freight`.
5. `valid_split_payment`: at least two payment rows and payment total reconciles with item total plus freight within 0.10 BRL. No refund; action `explain_valid_split_payment`.
6. `unsupported_late_claim`: delivery is not after estimated delivery and payment is reconciled. No refund; action `reject_late_refund`.

Secondary issues, in order: `multi_item_order`, `multi_seller_order`, `split_payment`, `repeat_customer`, `multiple_categories`.

Additional actions follow the primary action in this order: `review_seller_handoff` or `review_carrier_delay`, `verify_refund_completion`, `coordinate_multi_seller_case`, `verify_payment_allocation`. Do not add `verify_payment_allocation` for `valid_split_payment`.

Root causes: seller late handoff `SELLER_HANDOFF_AFTER_LIMIT`; carrier late delivery `CARRIER_DELIVERED_AFTER_ESTIMATE`; canceled paid `ORDER_CANCELED_AFTER_PAYMENT`; unavailable paid `ORDER_UNAVAILABLE_AFTER_PAYMENT`; valid split `MULTIPLE_PAYMENTS_RECONCILED`; on-time reconciled `DELIVERY_WITHIN_ESTIMATE`.
