import logging
import os
from typing import Literal, TypedDict

from dotenv import load_dotenv
from langfuse import Langfuse, get_client, observe
from langgraph.graph import END, StateGraph

from ai import get_provider
from bot.functions import TOOLS, dispatch
from bot.message import Message
from db.client import get_chat_context, save_turn, summarize_if_needed

load_dotenv()

logger = logging.getLogger(__name__)

_langfuse = Langfuse(
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY"),
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
    host=os.environ.get("LANGFUSE_HOST", "https://us.cloud.langfuse.com"),
)

MAX_TOOL_ITERATIONS = 5

_SYSTEM_PROMPT = """\
You are VehicleBot, a smart assistant for managing family vehicle documents in Kerala, India.

The database tracks these expiry dates per vehicle:
- Insurance           (insurance_valid_until)
- Pollution / PUCC    (pucc_valid_until)
- Fitness / RC        (fitness_valid_until)
- MV Tax              (mv_tax_valid_until)
- Permit              (permit_valid_until) — commercial vehicles only

Family owners: Thomas J Varghese, Varghese Joseph, Joseph C Varghese.
Always show dates with days remaining, e.g. "2027-02-18 (in 260 days)".

UPDATE RULES (strict):
1. Call query_vehicles to fetch the current value first.
2. Show the user: "I'll update [vehicle] [document] from [old] → [new]. Confirm?"
3. Wait for explicit confirmation (yes / confirm / ok / proceed).
4. Only then call update_vehicle_expiry.
Never skip the confirmation step.\
"""


class GraphState(TypedDict):
    user_id: str
    chat_id: str
    platform: str
    user_message: str
    messages: list[dict]
    tool_iteration: int
    final_reply: str
    pending_tool_calls: list[dict]


@observe()
def load_memory(state: GraphState) -> GraphState:
    context = get_chat_context(state["user_id"])
    system = _SYSTEM_PROMPT
    if context["summary"]:
        system += f"\n\nConversation summary:\n{context['summary']}"
    history = [{"role": m["role"], "content": m["content"]} for m in context["messages"]]
    messages = (
        [{"role": "system", "content": system}]
        + history
        + [{"role": "user", "content": state["user_message"]}]
    )
    return {**state, "messages": messages}


@observe(as_type="generation")
def agent(state: GraphState) -> GraphState:
    provider = get_provider()
    has_tool_results = any(
        m.get("role") == "user" and m.get("content", "").startswith("Tool results:")
        for m in state["messages"]
    )
    tools = [] if has_tool_results else TOOLS
    result = provider.chat_with_tools(state["messages"], tools)

    usage = result.get("usage", {})
    if usage:
        get_client().update_current_generation(
            usage_details={
                "input": usage.get("input_tokens", 0),
                "output": usage.get("output_tokens", 0),
            }
        )

    if "tool_calls" in result:
        return {**state, "pending_tool_calls": result["tool_calls"], "final_reply": ""}
    return {
        **state,
        "final_reply": result.get("text", "I'm not sure how to help with that."),
        "pending_tool_calls": [],
    }


@observe()
def execute_tools(state: GraphState) -> GraphState:
    if state["tool_iteration"] >= MAX_TOOL_ITERATIONS:
        return {
            **state,
            "final_reply": "Too many tool calls — please try again.",
            "pending_tool_calls": [],
        }
    results = []
    for tc in state["pending_tool_calls"]:
        try:
            get_client().update_current_span(name=f"tool:{tc['name']}", input=tc.get("arguments"))
            r = dispatch(tc["name"], tc.get("arguments") or {}, state["user_id"])
            get_client().update_current_span(output=r)
        except Exception as exc:
            r = f"Error in {tc['name']}: {exc}"
        results.append(r)
    new_messages = state["messages"] + [
        {"role": "user", "content": f"Tool results: {'; '.join(results)}"}
    ]
    return {
        **state,
        "messages": new_messages,
        "tool_iteration": state["tool_iteration"] + 1,
        "pending_tool_calls": [],
    }


@observe()
def save_memory(state: GraphState) -> GraphState:
    try:
        save_turn(state["user_id"], state["user_message"], state["final_reply"])
        summarize_if_needed(state["user_id"], get_provider())
    except Exception as exc:
        logger.warning("Memory save failed: %s", exc)
    return state


def _route_agent(state: GraphState) -> Literal["execute_tools", "save_memory"]:
    return "execute_tools" if state.get("pending_tool_calls") else "save_memory"


def _route_tools(state: GraphState) -> Literal["agent", "save_memory"]:
    return "save_memory" if state.get("final_reply") else "agent"


def _build_graph():
    g = StateGraph(GraphState)
    g.add_node("load_memory", load_memory)
    g.add_node("agent", agent)
    g.add_node("execute_tools", execute_tools)
    g.add_node("save_memory", save_memory)
    g.set_entry_point("load_memory")
    g.add_edge("load_memory", "agent")
    g.add_conditional_edges("agent", _route_agent)
    g.add_conditional_edges("execute_tools", _route_tools)
    g.add_edge("save_memory", END)
    return g.compile()


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


@observe()
def run_graph(msg: Message) -> str:
    state: GraphState = {
        "user_id": msg.user_id,
        "chat_id": msg.chat_id,
        "platform": msg.platform,
        "user_message": msg.text,
        "messages": [],
        "tool_iteration": 0,
        "final_reply": "",
        "pending_tool_calls": [],
    }
    try:
        return _get_graph().invoke(state)["final_reply"]
    finally:
        try:
            _langfuse.flush()
        except Exception as exc:
            logger.debug("Langfuse flush failed: %s", exc)
