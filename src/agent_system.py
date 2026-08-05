"""
agent_system.py — Đinh Quốc Việt (nhánh `viet`)
Hệ Multi-Agent A2A giải quyết khiếu nại thương mại điện tử.

Thiết kế:
  - 6 sub-agent chuyên trách, mỗi agent chỉ được cấp đúng phần dữ liệu cần cho
    domain của mình (least-privilege): agent nào không cần bảng nào thì không
    đọc bảng đó.
  - Coordinator không tự tính toán nghiệp vụ. Nó phát REQUEST, nhận RESPONSE,
    ráp kết quả và đưa qua Verifier.
  - Verifier là vòng phản hồi thật: nếu output vi phạm schema/giới hạn, nó trả
    REPAIR_REQUIRED kèm danh sách lỗi, Coordinator chạy bước chuẩn hóa rồi gửi
    lại. Chỉ khi verify sạch lỗi, case mới được ghi ra file.
  - Toàn bộ REQUEST/RESPONSE được ghi vào trace.jsonl kèm msg_id / parent_msg_id
    nên có thể dựng lại cây handoff của từng case.

Model: khai báo cứng trong source (MODEL_NAME), không đặt trong .env.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from dotenv import load_dotenv

from src import policy_engine
from src.data_engine import OlistRepository, get_repository
from src.logger import Stopwatch, TraceLogger
from src.verifier import verify_output

load_dotenv()

# ---------------------------------------------------------------------------
# Cấu hình model — phải <= 10B parameters theo yêu cầu đề bài
# ---------------------------------------------------------------------------
MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
MODEL_PARAMETER_SIZE = "7.6B"
MODEL_TEMPERATURE = 0.0
MODEL_MAX_TOKENS = 256

# Chỉ endpoint và khóa nằm trong .env; tên model luôn nằm trong source.
LLM_API_KEY = (
    os.getenv("LLM_API_KEY")
    or os.getenv("TOGETHER_API_KEY")
    or os.getenv("OPENAI_API_KEY")
    or ""
)
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.together.xyz/v1"

try:  # openai SDK là optional: thiếu nó hệ thống vẫn chạy ở chế độ deterministic
    import openai
except ImportError:  # pragma: no cover
    openai = None


class LLMAdvisor:
    """
    Cầu nối tới model <= 10B (`Qwen/Qwen2.5-7B-Instruct`).

    Vai trò: *advisory only*. Model được dùng để diễn giải/đối chiếu lại kết luận
    của rule-engine bằng ngôn ngữ tự nhiên và ghi vào trace; nó không được phép
    sửa con số, ID hay quyết định trong output. Lý do: mọi trường trong schema đều
    phải kiểm chứng được từ CSV, nên nguồn sự thật duy nhất là dữ liệu, còn LLM chỉ
    đóng vai reviewer. Khi không cấu hình khóa API, hệ thống chạy hoàn toàn
    deterministic và trace ghi rõ `llm_available: false`.
    """

    def __init__(self) -> None:
        self.model_name = MODEL_NAME
        self.client = None
        self.calls = 0
        if openai and LLM_API_KEY:
            try:
                self.client = openai.OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
            except Exception as exc:  # pragma: no cover
                print(f"[!] Không khởi tạo được LLM client: {exc}")

    @property
    def available(self) -> bool:
        return self.client is not None

    def review(self, agent_role: str, system_prompt: str, user_prompt: str) -> dict:
        """Trả về {'llm_available', 'model', 'note'} — luôn an toàn, không raise."""
        if not self.available:
            return {"llm_available": False, "model": self.model_name, "note": "deterministic-only"}
        try:
            self.calls += 1
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": f"Bạn là {agent_role}. {system_prompt}"},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=MODEL_TEMPERATURE,
                max_tokens=MODEL_MAX_TOKENS,
            )
            return {
                "llm_available": True,
                "model": self.model_name,
                "note": (completion.choices[0].message.content or "").strip()[:500],
            }
        except Exception as exc:
            return {"llm_available": True, "model": self.model_name, "note": f"llm_error: {exc}"}


# ---------------------------------------------------------------------------
# Sub-agent
# ---------------------------------------------------------------------------

class SubAgent:
    """Agent nhận REQUEST từ Coordinator và trả RESPONSE có ghi vết."""

    name = "SubAgent"
    role = ""
    data_access: tuple[str, ...] = ()

    def __init__(self, logger: TraceLogger, repo: OlistRepository, advisor: LLMAdvisor):
        self.logger = logger
        self.repo = repo
        self.advisor = advisor

    def handle(self, case_id: str, request: dict) -> tuple[dict, str, dict]:
        """Trả về (payload đầy đủ, message tóm tắt, payload_summary cho trace)."""
        raise NotImplementedError


class CustomerAgent(SubAgent):
    name = "CustomerAgent"
    role = "Xác định danh tính khách hàng và lịch sử mua hàng"
    data_access = ("customers", "orders")

    def handle(self, case_id: str, request: dict):
        order = request["order"]
        customer = self.repo.get_customer(order.get("customer_id"))
        customer_unique_id = customer.get("customer_unique_id") if customer else None

        all_orders = self.repo.get_customer_order_ids(customer_unique_id)
        related = [oid for oid in all_orders if oid != order.get("order_id")]

        payload = {
            "customer_unique_id": customer_unique_id,
            "related_order_ids": policy_engine.limit(related, "related_order_ids"),
            "related_order_count": len(related),
        }
        message = (
            f"customer_unique_id={customer_unique_id}; {len(related)} order khác của cùng khách "
            f"(giữ tối đa {len(payload['related_order_ids'])} theo giới hạn schema)"
        )
        return payload, message, payload


class OrderProductAgent(SubAgent):
    name = "OrderProductAgent"
    role = "Đối chiếu item, seller, sản phẩm và category của order"
    data_access = ("order_items", "products", "sellers")

    def handle(self, case_id: str, request: dict):
        order_id = request["order_id"]
        items = self.repo.get_order_items(order_id)

        item_ids = [f"{order_id}:{i.get('order_item_id')}" for i in items]
        seller_ids = policy_engine.dedupe([i.get("seller_id") for i in items])
        product_ids = policy_engine.dedupe([i.get("product_id") for i in items])
        category_names = policy_engine.dedupe(
            [self.repo.get_category_name(pid) for pid in product_ids]
        )

        payload = {
            "items": items,
            "item_ids": policy_engine.limit(item_ids, "item_ids"),
            "seller_ids": policy_engine.limit(seller_ids, "seller_ids"),
            "product_ids": policy_engine.limit(product_ids, "product_ids"),
            "category_names": policy_engine.limit(category_names, "category_names"),
            "item_count": len(items),
            "seller_count": len(seller_ids),
            "category_count": len(category_names),
        }
        message = (
            f"{len(items)} item row, {len(seller_ids)} seller, {len(product_ids)} product, "
            f"{len(category_names)} category"
        )
        summary = {k: v for k, v in payload.items() if k != "items"}
        return payload, message, summary


class PaymentAgent(SubAgent):
    name = "PaymentAgent"
    role = "Tổng hợp payment row và đối soát với item + freight"
    data_access = ("order_payments",)

    def handle(self, case_id: str, request: dict):
        order_id = request["order_id"]
        items = request["items"]
        payments = self.repo.get_order_payments(order_id)
        reconciliation = self.repo.compute_payment_reconciliation(items, payments)

        payload = {
            "payments": payments,
            "payment_ids": policy_engine.limit(
                [f"{order_id}:{p.get('payment_sequential')}" for p in payments], "payment_ids"
            ),
            "reconciliation": reconciliation,
            "payment_count": len(payments),
        }
        message = (
            f"{len(payments)} payment row, payment_total={reconciliation['payment_total_brl']} BRL, "
            f"expected={reconciliation['expected_total_brl']}, "
            f"difference={reconciliation['difference_brl']}, reconciled={reconciliation['reconciled']}"
        )
        return payload, message, {"payment_ids": payload["payment_ids"], **reconciliation}


class DeliveryAgent(SubAgent):
    name = "DeliveryAgent"
    role = "Tính delivery variance và seller handoff variance"
    data_access = ("orders", "order_items")

    def handle(self, case_id: str, request: dict):
        analysis = policy_engine.build_delivery_analysis(
            request["order"], request["items"], self.repo
        )
        payload = {"delivery_analysis": analysis, "is_late": policy_engine.is_late_delivery(analysis)}
        message = (
            f"delivery_variance={analysis['delivery_variance_hours']}h, "
            f"late_delivery={payload['is_late']}, "
            f"late_sellers={analysis['late_handoff_seller_ids'] or 'không có'}"
        )
        summary = {
            "delivery_variance_hours": analysis["delivery_variance_hours"],
            "carrier_handoff_at": analysis["carrier_handoff_at"],
            "late_handoff_seller_ids": analysis["late_handoff_seller_ids"],
            "is_late": payload["is_late"],
        }
        return payload, message, summary


class PolicyAgent(SubAgent):
    name = "PolicyAgent"
    role = "Áp dụng EC_POLICY_V2 lên bằng chứng do các agent khác bàn giao"
    data_access = ()  # chỉ làm việc trên bằng chứng đã được handoff

    def handle(self, case_id: str, request: dict):
        order = request["order"]
        order_id = order["order_id"]
        items = request["items"]
        payments = request["payments"]
        reconciliation = request["reconciliation"]
        delivery = request["delivery_analysis"]

        primary_issue, rationale = policy_engine.determine_primary_issue(
            order, payments, reconciliation, delivery
        )
        secondary_issues = policy_engine.determine_secondary_issues(
            items, payments, request["related_order_ids"], request["category_names"]
        )
        root_cause_code = policy_engine.get_root_cause_code(primary_issue)
        responsible_parties = policy_engine.build_responsible_parties(
            primary_issue, delivery["late_handoff_seller_ids"]
        )
        financial_resolution = policy_engine.compute_financial_resolution(primary_issue, reconciliation)
        refund = financial_resolution["recommended_refund_brl"]
        actions = policy_engine.build_resolution_actions(primary_issue, secondary_issues, payments)
        evidence_ids = policy_engine.build_evidence_ids(
            order_id,
            items,
            payments,
            [p["party_id"] for p in responsible_parties if p["party_type"] == "seller"],
            root_cause_code,
        )
        confidence = policy_engine.compute_confidence(
            primary_issue, reconciliation, delivery, items, payments
        )

        payload = {
            "primary_issue": primary_issue,
            "secondary_issues": secondary_issues,
            "case_status": "action_required" if refund > 0 else "no_action",
            "confidence": confidence,
            "ranked_causes": policy_engine.build_ranked_causes(primary_issue),
            "responsible_parties": responsible_parties,
            "financial_resolution": financial_resolution,
            "resolution_actions": actions,
            "evidence_ids": evidence_ids,
            "rationale": rationale,
        }

        # Bước review bằng model <= 10B: chỉ diễn giải, không sửa số liệu.
        review = self.advisor.review(
            agent_role="Policy reviewer của hệ dispute resolution",
            system_prompt=(
                "Bạn chỉ được xác nhận hoặc nêu nghi vấn về kết luận, tuyệt đối không "
                "bịa thêm sự kiện và không thay đổi con số. Trả lời tối đa 2 câu tiếng Việt."
            ),
            user_prompt=json.dumps(
                {
                    "order_status": order.get("order_status"),
                    "delivery_variance_hours": delivery["delivery_variance_hours"],
                    "late_handoff_seller_ids": delivery["late_handoff_seller_ids"],
                    "payment_total_brl": reconciliation["payment_total_brl"],
                    "expected_total_brl": reconciliation["expected_total_brl"],
                    "primary_issue": primary_issue,
                    "recommended_refund_brl": refund,
                },
                ensure_ascii=False,
            ),
        )
        payload["llm_review"] = review

        message = (
            f"primary={primary_issue} ({rationale}); secondary={secondary_issues or 'không có'}; "
            f"refund={refund} BRL; actions={actions}"
        )
        summary = {
            "primary_issue": primary_issue,
            "secondary_issues": secondary_issues,
            "root_cause_code": root_cause_code,
            "responsible_parties": responsible_parties,
            "recommended_refund_brl": refund,
            "resolution_actions": actions,
            "confidence": confidence,
            "rationale": rationale,
            "llm_review": review,
        }
        return payload, message, summary


class VerifierAgent(SubAgent):
    name = "VerifierAgent"
    role = "Kiểm tra schema, giới hạn mảng, grounding ID và nhất quán nghiệp vụ"
    data_access = ("orders", "order_items", "order_payments", "sellers")

    def handle(self, case_id: str, request: dict):
        errors = verify_output(request["output"], self.repo)
        payload = {"valid": not errors, "errors": errors}
        message = "output hợp lệ" if not errors else f"phát hiện {len(errors)} lỗi: {errors[:3]}"
        return payload, message, payload


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------

class CoordinatorAgent:
    """Điều phối: giao việc, nhận bàn giao, ráp output, gọi kiểm chứng và sửa lỗi."""

    name = "CoordinatorAgent"
    MAX_REPAIR_ROUNDS = 2

    def __init__(self, logger: TraceLogger, repo: Optional[OlistRepository] = None):
        self.logger = logger
        self.repo = repo or get_repository()
        self.advisor = LLMAdvisor()
        self.agents: dict[str, SubAgent] = {
            agent.name: agent
            for agent in (
                CustomerAgent(logger, self.repo, self.advisor),
                OrderProductAgent(logger, self.repo, self.advisor),
                PaymentAgent(logger, self.repo, self.advisor),
                DeliveryAgent(logger, self.repo, self.advisor),
                PolicyAgent(logger, self.repo, self.advisor),
                VerifierAgent(logger, self.repo, self.advisor),
            )
        }
        self.stats: dict[str, int] = {"repairs": 0, "cases": 0}

    # -- giao thức A2A -----------------------------------------------------
    def dispatch(self, case_id: str, agent_name: str, action: str, request: dict,
                 request_note: str) -> dict:
        """Gửi REQUEST tới sub-agent, nhận RESPONSE, ghi cả hai chiều vào trace."""
        agent = self.agents[agent_name]
        req_id = self.logger.request(
            case_id, self.name, agent.name, action, request_note,
            payload={"data_access": list(agent.data_access), "role": agent.role},
        )
        try:
            with Stopwatch() as sw:
                payload, message, summary = agent.handle(case_id, request)
        except Exception as exc:
            self.logger.error(
                case_id, agent.name, self.name, f"{action}_FAILED", str(exc), parent=req_id
            )
            raise

        self.logger.response(
            case_id, agent.name, self.name, f"{action}_DONE", message,
            payload=summary, evidence_ids=payload.get("evidence_ids"),
            parent=req_id, latency_ms=sw.elapsed_ms,
        )
        return payload

    # -- xử lý một case ----------------------------------------------------
    def process_case(self, case_input: dict) -> dict:
        case_id = case_input.get("case_id", "UNKNOWN")
        claimed_order_id = case_input.get("customer_request", {}).get("claimed_order_id")
        policy_version = case_input.get("policy_version", policy_engine.POLICY_VERSION)

        intake_id = self.logger.event(
            case_id, "CustomerRequest", self.name, "CASE_RECEIVED",
            f"Nhận khiếu nại {case_id} cho order {claimed_order_id} theo {policy_version}",
            payload={
                "claimed_order_id": claimed_order_id,
                "policy_version": policy_version,
                "investigation_scope": case_input.get("investigation_scope", {}),
            },
        )

        order = self.repo.get_order(claimed_order_id)
        if not order:
            self.logger.error(
                case_id, self.name, "CustomerRequest", "ORDER_NOT_FOUND",
                f"Không tìm thấy order {claimed_order_id} trong orders CSV", parent=intake_id,
            )
            raise ValueError(f"Order {claimed_order_id} không tồn tại trong dữ liệu Olist")

        # 1) Customer identity & history
        customer_ctx = self.dispatch(
            case_id, "CustomerAgent", "RESOLVE_CUSTOMER_HISTORY",
            {"order": order},
            f"Xác định customer_unique_id và các order khác của khách trên order {claimed_order_id}",
        )

        # 2) Order / item / seller / product
        order_ctx = self.dispatch(
            case_id, "OrderProductAgent", "INSPECT_ORDER_ITEMS",
            {"order_id": claimed_order_id},
            "Liệt kê item, seller, product và category của order",
        )
        items = order_ctx["items"]

        # 3) Payment reconciliation (cần item để tính expected total)
        payment_ctx = self.dispatch(
            case_id, "PaymentAgent", "RECONCILE_PAYMENTS",
            {"order_id": claimed_order_id, "items": items},
            "Đối soát tổng payment với tổng item + freight (ngưỡng 0.10 BRL)",
        )
        payments = payment_ctx["payments"]
        reconciliation = payment_ctx["reconciliation"]

        # 4) Delivery / handoff variance
        delivery_ctx = self.dispatch(
            case_id, "DeliveryAgent", "ANALYZE_DELIVERY",
            {"order": order, "items": items},
            "Tính delivery variance và handoff variance từng seller",
        )
        delivery = delivery_ctx["delivery_analysis"]

        # 5) Policy decision trên toàn bộ bằng chứng đã handoff
        policy_ctx = self.dispatch(
            case_id, "PolicyAgent", "APPLY_EC_POLICY_V2",
            {
                "order": order,
                "items": items,
                "payments": payments,
                "reconciliation": reconciliation,
                "delivery_analysis": delivery,
                "related_order_ids": customer_ctx["related_order_ids"],
                "category_names": order_ctx["category_names"],
            },
            f"Áp dụng {policy_version} để chốt primary issue, trách nhiệm, refund và actions",
        )

        output = self.assemble(case_id, claimed_order_id, customer_ctx, order_ctx,
                               payment_ctx, delivery, policy_ctx)

        # 6) Vòng kiểm chứng + sửa lỗi
        output = self.verify_with_repair(case_id, output)

        self.logger.event(
            case_id, self.name, "CustomerRequest", "CASE_COMPLETED",
            f"Hoàn tất {case_id}: {policy_ctx['primary_issue']}, "
            f"refund {policy_ctx['financial_resolution']['recommended_refund_brl']} BRL",
            payload={
                "case_status": output["case_assessment"]["case_status"],
                "primary_issue": output["case_assessment"]["primary_issue"],
                "recommended_refund_brl": output["financial_resolution"]["recommended_refund_brl"],
                "evidence_count": len(output["evidence_ids"]),
            },
            parent=intake_id,
        )
        self.stats["cases"] += 1
        return output

    # -- ráp output --------------------------------------------------------
    def assemble(self, case_id, order_id, customer_ctx, order_ctx, payment_ctx,
                 delivery, policy_ctx) -> dict:
        return {
            "case_id": case_id,
            "case_assessment": {
                "primary_issue": policy_ctx["primary_issue"],
                "secondary_issues": policy_ctx["secondary_issues"],
                "case_status": policy_ctx["case_status"],
                "confidence": policy_ctx["confidence"],
            },
            "affected_entities": {
                "order_ids": policy_engine.limit([order_id], "order_ids"),
                "item_ids": order_ctx["item_ids"],
                "seller_ids": order_ctx["seller_ids"],
                "payment_ids": payment_ctx["payment_ids"],
            },
            "customer_context": {
                "customer_unique_id": customer_ctx["customer_unique_id"],
                "related_order_ids": customer_ctx["related_order_ids"],
            },
            "product_context": {
                "product_ids": order_ctx["product_ids"],
                "category_names": order_ctx["category_names"],
            },
            "delivery_analysis": delivery,
            "payment_reconciliation": payment_ctx["reconciliation"],
            "root_cause_analysis": {
                "ranked_causes": policy_ctx["ranked_causes"],
                "responsible_parties": policy_ctx["responsible_parties"],
            },
            "evidence_ids": policy_ctx["evidence_ids"],
            "financial_resolution": policy_ctx["financial_resolution"],
            "resolution_actions": policy_ctx["resolution_actions"],
        }

    # -- kiểm chứng + sửa --------------------------------------------------
    def verify_with_repair(self, case_id: str, output: dict) -> dict:
        for attempt in range(1, self.MAX_REPAIR_ROUNDS + 1):
            result = self.dispatch(
                case_id, "VerifierAgent", "VERIFY_OUTPUT", {"output": output},
                f"Kiểm chứng output lần {attempt} trước khi ghi file",
            )
            if result["valid"]:
                return output

            self.stats["repairs"] += 1
            repair_id = self.logger.request(
                case_id, "VerifierAgent", self.name, "REPAIR_REQUIRED",
                f"Output chưa đạt, yêu cầu Coordinator chuẩn hóa: {result['errors'][:5]}",
                payload={"error_count": len(result["errors"])},
            )
            output = self.normalize(output)
            self.logger.response(
                case_id, self.name, "VerifierAgent", "REPAIR_APPLIED",
                "Đã chuẩn hóa giới hạn mảng, khử trùng lặp và làm tròn số tiền",
                payload={"attempt": attempt}, parent=repair_id,
            )

        final = self.dispatch(
            case_id, "VerifierAgent", "VERIFY_OUTPUT", {"output": output},
            "Kiểm chứng lần cuối sau khi chuẩn hóa",
        )
        if not final["valid"]:
            raise ValueError(f"{case_id} không vượt qua verifier: {final['errors']}")
        return output

    @staticmethod
    def normalize(output: dict) -> dict:
        """Chuẩn hóa cơ học: cắt mảng về đúng giới hạn, khử trùng lặp, làm tròn tiền."""
        entities = output["affected_entities"]
        for field in ("order_ids", "item_ids", "seller_ids", "payment_ids"):
            entities[field] = policy_engine.limit(policy_engine.dedupe(entities.get(field, [])), field)

        customer_ctx = output["customer_context"]
        customer_ctx["related_order_ids"] = policy_engine.limit(
            policy_engine.dedupe(customer_ctx.get("related_order_ids", [])), "related_order_ids"
        )
        product_ctx = output["product_context"]
        product_ctx["product_ids"] = policy_engine.limit(
            policy_engine.dedupe(product_ctx.get("product_ids", [])), "product_ids"
        )
        product_ctx["category_names"] = policy_engine.limit(
            policy_engine.dedupe(product_ctx.get("category_names", [])), "category_names"
        )

        output["evidence_ids"] = policy_engine.limit(
            policy_engine.dedupe(output.get("evidence_ids", [])), "evidence_ids"
        )
        output["resolution_actions"] = policy_engine.limit(
            policy_engine.dedupe(output.get("resolution_actions", [])), "resolution_actions"
        )

        reconciliation = output["payment_reconciliation"]
        for field in ("item_total_brl", "freight_total_brl", "expected_total_brl",
                      "payment_total_brl", "difference_brl"):
            value = reconciliation.get(field)
            if isinstance(value, (int, float)):
                reconciliation[field] = round(float(value), 2)

        refund = output["financial_resolution"].get("recommended_refund_brl")
        if isinstance(refund, (int, float)):
            output["financial_resolution"]["recommended_refund_brl"] = round(float(refund), 2)
            output["case_assessment"]["case_status"] = (
                "action_required" if refund > 0 else "no_action"
            )
        return output
