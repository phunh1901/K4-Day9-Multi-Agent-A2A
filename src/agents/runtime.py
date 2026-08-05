from __future__ import annotations

import json
from typing import Any, Callable

from openai import OpenAI

from provider import MODEL_NAME, get_client
from src.models import AgentMessage
from src.tools.registry import ToolRegistry
from src.tracing import TraceWriter


class AgentRuntime:
    """Model runtime with bounded tool-call and structured-output retries."""

    def __init__(self, tools: ToolRegistry, trace: TraceWriter, model: str = MODEL_NAME, client: OpenAI | None = None, max_tool_rounds: int = 8):
        self.tools = tools
        self.trace = trace
        self.model = model
        self.client = client
        self.max_tool_rounds = max_tool_rounds

    def _client(self) -> OpenAI:
        if self.client is None:
            self.client = get_client()
        return self.client

    def handoff(self, case_id: str, sender: str, recipient: str, message_type: str, objective: str, payload: dict[str, Any], evidence_ids: list[str] | None = None, parent_message_id: str | None = None) -> AgentMessage:
        message = AgentMessage(case_id=case_id, sender=sender, recipient=recipient, message_type=message_type, objective=objective, payload=payload, evidence_ids=evidence_ids or [], parent_message_id=parent_message_id)
        self.trace.write("agent_handoff", case_id, sender, message_id=message.message_id, recipient=recipient, message_type=message_type, objective=objective, payload_summary={"keys": list(payload)})
        return message

    def run_json(self, *, case_id: str, agent: str, system: str, user: str, allowed_tools: list[str], validator: Callable[[dict[str, Any]], Any] | None = None) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        tool_schemas = self.tools.schemas_for(allowed_tools)
        for round_no in range(self.max_tool_rounds):
            self.trace.write("model_request", case_id, agent, model=self.model, tool_names=allowed_tools, round=round_no + 1)
            response = self._client().chat.completions.create(model=self.model, messages=messages, tools=tool_schemas or None, tool_choice="auto" if tool_schemas else None, response_format={"type": "json_object"}, temperature=0)
            choice = response.choices[0]
            message = choice.message
            self.trace.write("model_response", case_id, agent, model=self.model, round=round_no + 1, finish_reason=choice.finish_reason, tool_call_count=len(message.tool_calls or []))
            if message.tool_calls:
                messages.append(message.model_dump(exclude_none=True))
                for call in message.tool_calls:
                    name = call.function.name
                    if name not in allowed_tools:
                        raise RuntimeError(f"agent {agent} attempted unauthorized tool {name}")
                    arguments: dict[str, Any] = {}
                    try:
                        arguments = json.loads(call.function.arguments or "{}")
                        result = self.tools.functions[name](**arguments)
                        status = result.get("status") if isinstance(result, dict) else "success"
                    except Exception as exc:
                        result = {"status": "error", "error": str(exc), "tool": name}
                        status = "error"
                    self.trace.write("tool_called", case_id, agent, model=self.model, tool=name, input=arguments if "arguments" in locals() else {}, status="success" if status == "success" else "error", output_summary={"record_count": result.get("record_count")} if isinstance(result, dict) else {})
                    self.trace.write("tool_result", case_id, agent, model=self.model, tool=name, status="success" if status == "success" else "error", output_summary={"record_count": result.get("record_count"), "keys": list(result) if isinstance(result, dict) else []})
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False, default=str)})
                continue
            content = message.content or "{}"
            try:
                payload = json.loads(content)
            except json.JSONDecodeError as exc:
                messages.append({"role": "user", "content": f"Return only valid JSON. JSON error: {exc}"})
                continue
            if validator:
                try:
                    validator(payload)
                except Exception as exc:
                    messages.append({"role": "user", "content": f"Correct the structured output. Validation error: {exc}"})
                    continue
            return payload
        raise RuntimeError(f"{agent} exceeded bounded model/tool rounds")
