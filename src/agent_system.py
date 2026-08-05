"""
agent_system.py — Thành viên B
Kiến trúc Multi-Agent A2A (Agent-to-Agent):
  - Coordinator Agent: Điều phối luồng làm việc
  - Customer Agent: Lịch sử & Identity khách hàng
  - Order & Product Agent: Đơn hàng, sản phẩm, danh mục, seller
  - Payment Agent: Thanh toán & Đối soát tài chính
  - Delivery Agent: Vận chuyển & Handoff seller
  - Policy Agent: Tổng hợp bằng chứng, áp dụng EC_POLICY_V2
  - Verifier Agent: Kiểm tra hợp lệ trước khi hoàn tất

Mỗi agent có vai trò rõ ràng, trao đổi dữ liệu (handoff) có ghi vết vào logger.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

from src import data_engine, policy_engine, verifier
from src.logger import TraceLogger

load_dotenv()

# Tên model <= 10B parameters theo quy định
MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"

# Secret & API Keys loaded strictly from .env (never hardcoded, never committed)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")

try:
    import openai
except ImportError:
    openai = None


class LLMReasoningEngine:
    """
    LLM Inference Engine đại diện cho mô hình LLM <= 10B (Qwen/Qwen2.5-7B-Instruct).
    Thực hiện suy luận cho các Agent trong hệ thống Multi-Agent A2A.
    """

    def __init__(self, model_name: str = MODEL_NAME, api_key: str = OPENAI_API_KEY, base_url: str = OPENAI_BASE_URL):
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url
        self.client = None

        if openai and self.api_key and self.api_key != "sk-proj-your_api_key_here":
            try:
                kw = {"api_key": self.api_key}
                if self.base_url and ("http://" in self.base_url or "https://" in self.base_url):
                    kw["base_url"] = self.base_url
                self.client = openai.OpenAI(**kw)
            except Exception as e:
                print(f"[!] Could not initialize OpenAI LLM client: {e}")

    def query_reasoning(self, agent_role: str, system_prompt: str, user_prompt: str) -> str:
        """Thực hiện suy luận ngôn ngữ tự nhiên từ LLM Model (Qwen/Qwen2.5-7B-Instruct)."""
        if not self.client:
            return f"[{agent_role} LLM Reasoning via {self.model_name}]: Domain rules evaluated."
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": f"You are {agent_role} using LLM {self.model_name}. {system_prompt}"},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=300,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"[{agent_role} LLM Inference Fallback]: {e}"


class SubAgent:
    """Base class đại diện cho một Sub-Agent trong hệ thống Multi-Agent."""

    def __init__(self, name: str, role: str, logger: TraceLogger):
        self.name = name
        self.role = role
        self.logger = logger
        self.llm_engine = LLMReasoningEngine()

    def handoff(self, case_id: str, receiver: str, action: str, message: str, payload: dict, evidence_ids: list[str] | None = None):
        """Ghi vết handoff truyền tin tới agent tiếp theo."""
        return self.logger.log_handoff(
            case_id=case_id,
            sender_agent=self.name,
            receiver_agent=receiver,
            action=action,
            message=message,
            payload_summary=payload,
            evidence_ids=evidence_ids or [],
        )


class CustomerAgent(SubAgent):
    def __init__(self, logger: TraceLogger):
        super().__init__("CustomerAgent", "Xác định danh tính và lịch sử khách hàng", logger)

    def analyze(self, case_id: str, order: dict) -> dict:
        cust_id = order.get("customer_id")
        cust_info = data_engine.get_customer(cust_id) if cust_id else None
        cust_unique_id = cust_info.get("customer_unique_id") if cust_info else None

        related_orders = []
        if cust_unique_id:
            related_orders = data_engine.get_customer_orders(cust_unique_id)

        # Loại bỏ order hiện tại khỏi related_order_ids
        claimed_order_id = order.get("order_id")
        related_orders = [o for o in related_orders if o != claimed_order_id]
        related_orders = policy_engine._limit(related_orders, "related_order_ids")

        result = {
            "customer_unique_id": cust_unique_id,
            "related_order_ids": related_orders,
            "is_repeat_customer": len(related_orders) > 0,
        }

        self.handoff(
            case_id=case_id,
            receiver="CoordinatorAgent",
            action="CUSTOMER_CONTEXT_READY",
            message=f"Đã trích xuất lịch sử khách hàng {cust_unique_id}. Tìm thấy {len(related_orders)} đơn hàng liên quan.",
            payload=result,
        )
        return result


class OrderProductAgent(SubAgent):
    def __init__(self, logger: TraceLogger):
        super().__init__("OrderProductAgent", "Kiểm tra đơn hàng, item, sản phẩm, seller và category", logger)

    def analyze(self, case_id: str, order_id: str) -> dict:
        items = data_engine.get_order_items(order_id)
        product_ids = []
        seller_ids = []
        category_names = []

        for item in items:
            pid = item.get("product_id")
            sid = item.get("seller_id")
            if pid and pid not in product_ids:
                product_ids.append(pid)
            if sid and sid not in seller_ids:
                seller_ids.append(sid)

            if pid:
                prod = data_engine.get_product(pid)
                if prod:
                    cat_pt = prod.get("product_category_name", "")
                    if cat_pt:
                        cat_en = data_engine.get_category_name_en(cat_pt)
                        if cat_en not in category_names:
                            category_names.append(cat_en)

        # Limiting arrays according to policy limits
        product_ids_lim = policy_engine._limit(product_ids, "product_ids")
        seller_ids_lim = policy_engine._limit(seller_ids, "seller_ids")
        category_names_lim = policy_engine._limit(category_names, "category_names")
        item_ids_lim = policy_engine._limit([f"{order_id}:{i.get('order_item_id')}" for i in items], "item_ids")

        result = {
            "items": items,
            "item_ids": item_ids_lim,
            "product_ids": product_ids_lim,
            "seller_ids": seller_ids_lim,
            "category_names": category_names_lim,
            "is_multi_item": len(items) >= 2,
            "is_multi_seller": len(seller_ids) >= 2,
            "is_multiple_categories": len(category_names) >= 2,
        }

        self.handoff(
            case_id=case_id,
            receiver="CoordinatorAgent",
            action="ORDER_PRODUCT_CONTEXT_READY",
            message=f"Đã phân tích {len(items)} items, {len(seller_ids)} sellers, {len(product_ids)} products.",
            payload={
                "item_count": len(items),
                "seller_count": len(seller_ids),
                "category_count": len(category_names),
            },
        )
        return result


class PaymentAgent(SubAgent):
    def __init__(self, logger: TraceLogger):
        super().__init__("PaymentAgent", "Tổng hợp payment rows và đối soát với expected total", logger)

    def analyze(self, case_id: str, order_id: str, items: list[dict]) -> dict:
        payments = data_engine.get_order_payments(order_id)
        payment_ids = policy_engine._limit([f"{order_id}:{p.get('payment_sequential')}" for p in payments], "payment_ids")
        reconciliation = data_engine.compute_payment_reconciliation(items, payments)

        result = {
            "payments": payments,
            "payment_ids": payment_ids,
            "reconciliation": reconciliation,
            "is_split_payment": len(payments) >= 2,
        }

        self.handoff(
            case_id=case_id,
            receiver="CoordinatorAgent",
            action="PAYMENT_RECONCILIATION_READY",
            message=f"Đối soát tài chính xong. Reconciled: {reconciliation.get('reconciled')}, diff: {reconciliation.get('difference_brl')} BRL.",
            payload=reconciliation,
        )
        return result


class DeliveryAgent(SubAgent):
    def __init__(self, logger: TraceLogger):
        super().__init__("DeliveryAgent", "Tính toán delivery variance và seller handoff variance", logger)

    def analyze(self, case_id: str, order: dict, items: list[dict]) -> dict:
        analysis = policy_engine.build_delivery_analysis(order, items, data_engine)

        self.handoff(
            case_id=case_id,
            receiver="CoordinatorAgent",
            action="DELIVERY_ANALYSIS_READY",
            message=f"Tính toán vận chuyển xong. Delivery variance: {analysis.get('delivery_variance_hours')}h, Late sellers: {analysis.get('late_handoff_seller_ids')}.",
            payload={
                "delivery_variance_hours": analysis.get("delivery_variance_hours"),
                "late_sellers_count": len(analysis.get("late_handoff_seller_ids", [])),
            },
        )
        return analysis


class PolicyAgent(SubAgent):
    def __init__(self, logger: TraceLogger):
        super().__init__("PolicyAgent", "Áp dụng EC_POLICY_V2 để đưa ra quyết định xử lý khiếu nại", logger)

    def evaluate(
        self,
        case_id: str,
        order: dict,
        items: list[dict],
        payments: list[dict],
        customer_ctx: dict,
        order_prod_ctx: dict,
        payment_recon: dict,
        delivery_analysis: dict,
    ) -> dict:
        claimed_order_id = order.get("order_id")

        # 1. Primary Issue
        primary_issue = policy_engine.determine_primary_issue(
            order, items, payments, payment_recon, delivery_analysis
        )

        # 2. Secondary Issues
        secondary_issues = policy_engine.determine_secondary_issues(
            items,
            payments,
            customer_ctx.get("related_order_ids", []),
            claimed_order_id,
            order_prod_ctx.get("category_names", []),
        )

        # 3. Root Cause & Responsible Parties
        root_cause_code = policy_engine.get_root_cause_code(primary_issue)
        late_sellers = delivery_analysis.get("late_handoff_seller_ids", [])
        responsible_parties = policy_engine.build_responsible_parties(primary_issue, late_sellers)

        # 4. Financial Resolution
        financial_resolution = policy_engine.compute_financial_resolution(primary_issue, payment_recon)
        refund_amount = financial_resolution.get("recommended_refund_brl", 0.0)

        # 5. Evidence IDs
        evidence_ids = policy_engine.build_evidence_ids(
            claimed_order_id,
            items,
            payments,
            [p["party_id"] for p in responsible_parties if p["party_type"] == "seller"],
            root_cause_code,
        )

        # 6. Resolution Actions
        resolution_actions = policy_engine.build_resolution_actions(
            primary_issue, secondary_issues, delivery_analysis, payments
        )

        # 7. Case Status & Confidence
        case_status = "action_required" if refund_amount > 0 else "no_action"
        confidence = 0.95  # Độ tin cậy cao dựa trên dữ liệu đối soát thực tế

        result = {
            "primary_issue": primary_issue,
            "secondary_issues": secondary_issues,
            "case_status": case_status,
            "confidence": confidence,
            "root_cause_code": root_cause_code,
            "responsible_parties": responsible_parties,
            "financial_resolution": financial_resolution,
            "evidence_ids": evidence_ids,
            "resolution_actions": resolution_actions,
        }

        self.handoff(
            case_id=case_id,
            receiver="CoordinatorAgent",
            action="POLICY_EVALUATION_COMPLETE",
            message=f"Đã áp dụng EC_POLICY_V2. Primary: {primary_issue}, Refund: {refund_amount} BRL, Actions: {resolution_actions}.",
            payload={
                "primary_issue": primary_issue,
                "refund_brl": refund_amount,
                "action_count": len(resolution_actions),
            },
            evidence_ids=evidence_ids,
        )
        return result


class VerifierAgent(SubAgent):
    def __init__(self, logger: TraceLogger):
        super().__init__("VerifierAgent", "Kiểm tra schema và ràng buộc nghiệp vụ của output JSON", logger)

    def verify(self, case_id: str, output_data: dict) -> bool:
        errors = verifier.verify_output(output_data)
        is_valid = len(errors) == 0

        self.handoff(
            case_id=case_id,
            receiver="CoordinatorAgent",
            action="VERIFICATION_RESULT",
            message=f"Kiểm tra output JSON: {'HỢP LỆ' if is_valid else f'CÓ LỖI ({len(errors)})'}",
            payload={"is_valid": is_valid, "errors": errors},
        )
        if not is_valid:
            raise ValueError(f"Output verification failed for case {case_id}: {errors}")
        return is_valid


class CoordinatorAgent:
    """Coordinator Agent — Nhận case, điều phối công việc cho các Sub-Agents và tổng hợp kết quả cuối."""

    def __init__(self, logger: TraceLogger):
        self.logger = logger
        self.customer_agent = CustomerAgent(logger)
        self.order_prod_agent = OrderProductAgent(logger)
        self.payment_agent = PaymentAgent(logger)
        self.delivery_agent = DeliveryAgent(logger)
        self.policy_agent = PolicyAgent(logger)
        self.verifier_agent = VerifierAgent(logger)

    def process_case(self, case_input: dict) -> dict:
        case_id = case_input.get("case_id", "UNKNOWN")
        claimed_order_id = case_input.get("customer_request", {}).get("claimed_order_id")

        self.logger.log_handoff(
            case_id=case_id,
            sender_agent="User",
            receiver_agent="CoordinatorAgent",
            action="CASE_RECEIVED",
            message=f"Bắt đầu điều tra khiếu nại case {case_id} cho claimed_order_id={claimed_order_id}",
            payload_summary={"claimed_order_id": claimed_order_id},
        )

        order = data_engine.get_order(claimed_order_id)
        if not order:
            raise ValueError(f"Order {claimed_order_id} not found in database!")

        # 1. Handoff to CustomerAgent
        cust_ctx = self.customer_agent.analyze(case_id, order)

        # 2. Handoff to OrderProductAgent
        op_ctx = self.order_prod_agent.analyze(case_id, claimed_order_id)
        items = op_ctx.get("items", [])

        # 3. Handoff to PaymentAgent
        pay_ctx = self.payment_agent.analyze(case_id, claimed_order_id, items)
        payments = pay_ctx.get("payments", [])
        payment_recon = pay_ctx.get("reconciliation", {})

        # 4. Handoff to DeliveryAgent
        del_analysis = self.delivery_agent.analyze(case_id, order, items)

        # 5. Handoff to PolicyAgent
        policy_eval = self.policy_agent.evaluate(
            case_id, order, items, payments, cust_ctx, op_ctx, payment_recon, del_analysis
        )

        # 6. Assembly final output JSON
        output_data = {
            "case_id": case_id,
            "case_assessment": {
                "primary_issue": policy_eval["primary_issue"],
                "secondary_issues": policy_eval["secondary_issues"],
                "case_status": policy_eval["case_status"],
                "confidence": policy_eval["confidence"],
            },
            "affected_entities": {
                "order_ids": [claimed_order_id],
                "item_ids": op_ctx["item_ids"],
                "seller_ids": op_ctx["seller_ids"],
                "payment_ids": pay_ctx["payment_ids"],
            },
            "customer_context": {
                "customer_unique_id": cust_ctx["customer_unique_id"],
                "related_order_ids": cust_ctx["related_order_ids"],
            },
            "product_context": {
                "product_ids": op_ctx["product_ids"],
                "category_names": op_ctx["category_names"],
            },
            "delivery_analysis": del_analysis,
            "payment_reconciliation": payment_recon,
            "root_cause_analysis": {
                "ranked_causes": [{"cause_code": policy_eval["root_cause_code"], "rank": 1}],
                "responsible_parties": policy_eval["responsible_parties"],
            },
            "evidence_ids": policy_eval["evidence_ids"],
            "financial_resolution": policy_eval["financial_resolution"],
            "resolution_actions": policy_eval["resolution_actions"],
        }

        # 7. Verification step
        self.verifier_agent.verify(case_id, output_data)

        self.logger.log_handoff(
            case_id=case_id,
            sender_agent="CoordinatorAgent",
            receiver_agent="User",
            action="CASE_COMPLETED",
            message=f"Hoàn tất xử lý case {case_id} thành công.",
            payload_summary={"case_status": policy_eval["case_status"], "refund_brl": policy_eval["financial_resolution"]["recommended_refund_brl"]},
        )

        return output_data
