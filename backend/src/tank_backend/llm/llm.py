from typing import List, Dict, Any, Optional, Union, AsyncGenerator, Tuple
import logging
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionAssistantMessageParam
from ..core.events import UpdateType

logger = logging.getLogger("LLM")

class LLM:
    def __init__(self, api_key: str, model: str = "anthropic/claude-3-5-nano", base_url: str = "https://openrouter.ai/api/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

        # Initialize OpenAI client with custom base URL and headers
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={
                "HTTP-Referer": "http://localhost:3000",
                "X-Title": "Tank Voice Assistant"
            }
        )

    async def chat_stream(
        self,
        messages: List[ChatCompletionMessageParam],
        temperature: float = 0.7,
        max_tokens: int = 10000,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_executor: Any = None
    ) -> AsyncGenerator[Tuple[UpdateType, str, Dict[str, Any]], None]:
        """
        Stream chat completion with automatic tool call handling.
        Yields: (UpdateType, content_delta, metadata)
        """
        working_messages = messages.copy()
        turn = 0
        
        while True:
            turn += 1
            logger.debug(f"LLM Stream iteration {turn} with {len(working_messages)} messages")
            
            api_kwargs = {
                "model": self.model,
                "messages": working_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
                # Explicitly include usage for stream if supported (OpenAI/OpenRouter)
                "stream_options": {"include_usage": True}
            }
            if tools:
                api_kwargs["tools"] = tools

            full_content = ""
            full_reasoning = ""
            tool_calls_data = {} # index -> {id, name, arguments}

            stream = await self.client.chat.completions.create(**api_kwargs)

            try:
                async for chunk in stream:
                    if not chunk.choices:
                        continue

                    delta = chunk.choices[0].delta

                    # 1. Handle Reasoning (Thought) - Provider specific (e.g. DeepSeek)
                    reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
                    if reasoning:
                        full_reasoning += reasoning
                        yield UpdateType.THOUGHT, reasoning, {"turn": turn}

                    # 2. Handle Content (Text)
                    if delta.content:
                        full_content += delta.content
                        yield UpdateType.TEXT, delta.content, {"turn": turn}

                    # 3. Handle Tool Calls Delta
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in tool_calls_data:
                                tool_calls_data[idx] = {"id": None, "name": "", "arguments": ""}

                            if tc_delta.id:
                                tool_calls_data[idx]["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    tool_calls_data[idx]["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    tool_calls_data[idx]["arguments"] += tc_delta.function.arguments

                            # Yield partial tool call info for UI
                            yield UpdateType.TOOL_CALL, "", {
                                "index": idx,
                                "name": tool_calls_data[idx]["name"],
                                "arguments": tool_calls_data[idx]["arguments"],
                                "status": "calling",
                                "turn": turn
                            }
            finally:
                # Explicitly close the internal async generator chain.
                # AsyncStream.close() only closes the HTTP response, not _iterator.
                # shutdown_asyncgens() in _teardown_event_loop handles remaining finalizers.
                await stream._iterator.aclose()
                await stream.response.aclose()

            # ... (Prepare assistant message)
            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": full_content}
            if tool_calls_data:
                # Convert accumulated tool calls to OpenAI format
                formatted_tool_calls = []
                for idx in sorted(tool_calls_data.keys()):
                    formatted_tool_calls.append({
                        "id": tool_calls_data[idx]["id"],
                        "type": "function",
                        "function": {
                            "name": tool_calls_data[idx]["name"],
                            "arguments": tool_calls_data[idx]["arguments"]
                        }
                    })
                assistant_msg["tool_calls"] = formatted_tool_calls
            
            working_messages.append(assistant_msg)

            # If there are tool calls, execute them and continue the loop
            if tool_calls_data and tool_executor:
                for idx in sorted(tool_calls_data.keys()):
                    tc = tool_calls_data[idx]
                    try:
                        # Yield status update
                        yield UpdateType.TOOL_CALL, "", {
                            "index": idx,
                            "name": tc["name"],
                            "arguments": tc["arguments"],
                            "status": "executing",
                            "turn": turn
                        }
                        
                        # Mock the tool call object for executor
                        from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall, Function
                        
                        tool_call_obj = ChatCompletionMessageToolCall(
                            id=tc["id"],
                            type="function",
                            function=Function(name=tc["name"], arguments=tc["arguments"])
                        )
                        
                        result = await tool_executor.execute_openai_tool_call(tool_call_obj)
                        
                        # Summary for UI (truncated)
                        result_str = str(result)
                        summary = (result_str[:200] + "...") if len(result_str) > 200 else result_str
                        
                        yield UpdateType.TOOL_RESULT, summary, {
                            "index": idx,
                            "name": tc["name"],
                            "status": "success",
                            "turn": turn
                        }
                        
                        working_messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "name": tc["name"],
                            "content": result_str
                        })
                    except Exception as e:
                        yield UpdateType.TOOL_RESULT, f"Error: {str(e)}", {
                            "index": idx,
                            "name": tc["name"],
                            "status": "error",
                            "turn": turn
                        }
                        working_messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "name": tc["name"],
                            "content": f"Error: {str(e)}"
                        })
                # Continue loop to get next response after tools
                continue
            else:
                # No tool calls, we are done
                break

    async def chat_completion_async(
        self,
        messages: List[ChatCompletionMessageParam],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_executor=None
    ) -> Dict[str, Any]:
        """
        Chat completion with automatic tool call handling.

        Args:
            messages: List of ChatCompletionMessageParam objects
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            tools: Available tools for the model to use
            tool_executor: Object that can execute tool calls (must have execute_openai_tool_call method)
        """
        try:
            # Create a working copy of messages to avoid modifying the original
            working_messages: List[ChatCompletionMessageParam] = messages.copy()
            total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            iterations = 0

            while True:
                iterations += 1
                logger.debug(f"LLM iteration {iterations} with {len(working_messages)} messages")

                # Prepare kwargs for the API call
                api_kwargs = {
                    "model": self.model,
                    "messages": working_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": stream
                }

                # Add tools if provided
                if tools:
                    api_kwargs["tools"] = tools

                # Make the API call
                response = await self.client.chat.completions.create(**api_kwargs)

                # Accumulate usage statistics
                if response.usage:
                    total_usage["prompt_tokens"] += response.usage.prompt_tokens or 0
                    total_usage["completion_tokens"] += response.usage.completion_tokens or 0
                    total_usage["total_tokens"] += response.usage.total_tokens or 0

                # Get the assistant's message
                choice = response.choices[0]
                assistant_message = choice.message

                # Add the assistant's message to working messages
                assistant_msg: ChatCompletionAssistantMessageParam = {
                    "role": "assistant",
                    "content": assistant_message.content
                }

                # Add tool calls if they exist
                if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
                    assistant_msg["tool_calls"] = assistant_message.tool_calls

                working_messages.append(assistant_msg)

                # Check if there are tool calls
                if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls and tool_executor:
                    logger.info(f"Processing {len(assistant_message.tool_calls)} tool calls")

                    # Execute each tool call and add results as tool messages
                    for tool_call in assistant_message.tool_calls:
                        try:
                            # Execute the tool call
                            tool_result = await tool_executor.execute_openai_tool_call(tool_call)

                            # Convert tool result to string
                            if isinstance(tool_result, dict):
                                if "error" in tool_result:
                                    result_content = f"Error: {tool_result['error']}"
                                elif "message" in tool_result:
                                    result_content = tool_result["message"]
                                else:
                                    result_content = str(tool_result)
                            else:
                                result_content = str(tool_result)

                            # Add tool response as a tool message
                            working_messages.append({
                                "role": "tool",
                                "content": result_content,
                                "tool_call_id": tool_call.id,
                                "name": tool_call.function.name
                            })

                            logger.debug(f"Tool {tool_call.function.name} executed successfully")

                        except Exception as e:
                            logger.error(f"Error executing tool {tool_call.function.name}: {e}")
                            # Add error message as tool response
                            working_messages.append({
                                "role": "tool",
                                "content": f"Error executing {tool_call.function.name}: {str(e)}",
                                "tool_call_id": tool_call.id,
                                "name": tool_call.function.name
                            })
                else:
                    # No more tool calls, return the final response
                    result = {
                        "choices": [{
                            "message": {
                                "role": assistant_message.role,
                                "content": assistant_message.content
                            },
                            "finish_reason": choice.finish_reason
                        }],
                        "usage": total_usage,
                        "model": response.model,
                        "id": response.id,
                        "tool_iterations": iterations
                    }

                    # Add tool calls if present (for debugging/logging purposes)
                    if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
                        result["choices"][0]["message"]["tool_calls"] = assistant_message.tool_calls

                    return result

        except Exception as e:
            logger.error(f"Chat completion error: {e}")
            raise

    async def check_connection(self) -> bool:
        try:
            test_messages = [{"role": "user", "content": "Hello, can you hear me?"}]
            await self.chat_completion_async(test_messages, max_tokens=16)
            return True
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False