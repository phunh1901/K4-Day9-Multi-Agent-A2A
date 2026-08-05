from __future__ import annotations

import json
import asyncio
from typing import Any, Callable

from openai import AsyncOpenAI, OpenAI

from provider import MODEL_NAME, get_async_client, get_client
from src.models import AgentMessage
from src.tools.registry import ToolRegistry
from src.tracing import TraceWriter


class AgentRuntime:
    """Model runtime with bounded tool-call and structured-output retries."""

    def __init__(self, tools: ToolRegistry, trace: TraceWriter, model: str = MODEL_NAME, client: OpenAI | None = None, async_client: AsyncOpenAI | None = None, max_tool_rounds: int = 8, max_model_concurrency: int = 4):
        self.tools = tools
        self.trace = trace
        self.model = model
        self.client = client
        self.async_client = async_client
        self.max_tool_rounds = max_tool_rounds
        self.request_semaphore = asyncio.Semaphore(max(1, max_model_concurrency))

    def _client(self) -> OpenAI:
        if self.client is None:
            self.client = get_client()
        return self.client

    async def _async_client(self) -> AsyncOpenAI:
        if self.async_client is None:
            self.async_client = get_async_client()
        return self.async_client

    def handoff(self, case_id: str, sender: str, recipient: str, message_type: str, objective: str, payload: dict[str, Any], evidence_ids: list[str] | None = None, parent_message_id: str | None = None) -> AgentMessage:
        message = AgentMessage(case_id=case_id, sender=sender, recipient=recipient, message_type=message_type, objective=objective, payload=payload, evidence_ids=evidence_ids or [], parent_message_id=parent_message_id)
        self.trace.write("agent_handoff", case_id, sender, message_id=message.message_id, recipient=recipient, message_type=message_type, objective=objective, payload_summary={"keys": list(payload)})
        return message

    def run_json(self, *, case_id: str, agent: str, system: str, user: str, allowed_tools: list[str], validator: Callable[[dict[str, Any]], Any] | None = None, response_schema: dict[str, Any] | None = None, max_rounds: int | None = None) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        tool_schemas = self.tools.schemas_for(allowed_tools)
        for round_no in range(max_rounds or self.max_tool_rounds):
            self.trace.write("model_request", case_id, agent, model=self.model, tool_names=allowed_tools, round=round_no + 1)
            response_format = {"type": "json_schema", "json_schema": {"name": f"{agent}_response", "strict": True, "schema": response_schema}} if response_schema else {"type": "json_object"}
            response = self._client().chat.completions.create(model=self.model, messages=messages, tools=tool_schemas or None, tool_choice="auto" if tool_schemas else None, response_format=response_format, temperature=0)
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
                    summary = {"record_count": result.get("record_count"), "keys": list(result)} if isinstance(result, dict) else {"value_type": type(result).__name__}
                    self.trace.write("tool_called", case_id, agent, model=self.model, tool=name, input=arguments, status="success" if status == "success" else "error", output_summary=summary)
                    self.trace.write("tool_result", case_id, agent, model=self.model, tool=name, status="success" if status == "success" else "error", output_summary=summary)
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

    async def run_json_async(self, *, case_id: str, agent: str, system: str, user: str, allowed_tools: list[str], validator: Callable[[dict[str, Any]], Any] | None = None, response_schema: dict[str, Any] | None = None, max_rounds: int | None = None) -> dict[str, Any]:
        """Async counterpart to run_json; tool functions remain local and bounded."""
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        tool_schemas = self.tools.schemas_for(allowed_tools)
        client = await self._async_client()
        for round_no in range(max_rounds or self.max_tool_rounds):
            self.trace.write("model_request", case_id, agent, model=self.model, tool_names=allowed_tools, round=round_no + 1, mode="async")
            response_format = {"type": "json_schema", "json_schema": {"name": f"{agent}_response", "strict": True, "schema": response_schema}} if response_schema else {"type": "json_object"}
            request_kwargs = {"model": self.model, "messages": messages, "tools": tool_schemas or None, "tool_choice": "auto" if tool_schemas else None, "response_format": response_format, "temperature": 0}
            for retry_no in range(4):
                try:
                    async with self.request_semaphore:
                        response = await client.chat.completions.create(**request_kwargs)
                    break
                except Exception as exc:
                    status_code = getattr(exc, "status_code", None)
                    is_connection_error = "connection error" in str(exc).lower()
                    if (status_code not in {429, 500, 502, 503, 504} and not is_connection_error) or retry_no == 3:
                        raise
                    delay = min(8.0, 0.5 * (2 ** retry_no))
                    self.trace.write("provider_retry", case_id, agent, status_code=status_code, error_type=type(exc).__name__, retry=retry_no + 1, delay_seconds=delay, mode="async")
                    await asyncio.sleep(delay)
            choice = response.choices[0]
            message = choice.message
            self.trace.write("model_response", case_id, agent, model=self.model, round=round_no + 1, finish_reason=choice.finish_reason, tool_call_count=len(message.tool_calls or []), mode="async")
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
                    summary = {"record_count": result.get("record_count"), "keys": list(result)} if isinstance(result, dict) else {"value_type": type(result).__name__}
                    self.trace.write("tool_called", case_id, agent, model=self.model, tool=name, input=arguments, status="success" if status == "success" else "error", output_summary=summary, mode="async")
                    self.trace.write("tool_result", case_id, agent, model=self.model, tool=name, status="success" if status == "success" else "error", output_summary=summary, mode="async")
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False, default=str)})
                continue
            try:
                payload = json.loads(message.content or "{}")
            except json.JSONDecodeError as exc:
                messages.append({"role": "user", "content": f"Return only valid JSON. JSON error: {exc}"})
                continue
            if validator:
                try:
                    validator(payload)
                except Exception as exc:
                    messages.append({"role": "user", "content": f"Correct the structured JSON output. Validation error: {exc}"})
                    continue
            return payload
        raise RuntimeError(f"{agent} exceeded bounded async model/tool rounds")
