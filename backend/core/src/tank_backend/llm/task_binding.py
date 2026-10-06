"""Bind task metadata to an LLM without intercepting its SDK/HTTP client."""
from __future__ import annotations

from uuid import uuid4

from ..agents.subagent import SubAgentContext
from .llm import LLM
from .model_call import TaskModelCalls


def bind_llm(llm: LLM, context: SubAgentContext, task_id: str) -> LLM:
    if llm.manages_task_usage:
        if llm._task_context is not context:
            raise ValueError("LLM belongs to another task runtime")
        return llm
    context.check("network")
    bound = LLM(api_key=llm.api_key, model=llm.model, base_url=llm.base_url,
                temperature=llm.temperature, max_tokens=llm.max_tokens,
                stream_options=llm.stream_options, extra_body=llm.extra_body,
                extra_headers=llm.extra_headers, client=llm.client.with_options(max_retries=0))
    bound._task_context = context
    bound._task_calls = TaskModelCalls(task_id, context)
    bound.disable_retries()
    context.runtime.own("llm-" + uuid4().hex, bound.aclose)
    return bound
