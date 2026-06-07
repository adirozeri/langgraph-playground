"""
LangGraph complete reference.
Every major concept is shown in one file.
Run section by section; some sections need API keys.

Install:
    pip install langgraph langchain-core langchain-google-genai langchain
"""


"""
============================================================
SECTION 1 — ALL IMPORTS YOU WILL EVER NEED
============================================================
"""

from typing import Annotated, Literal, Optional, Any
from typing_extensions import TypedDict

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages        /* reducer: appends instead of replacing */
from langgraph.checkpoint.memory import MemorySaver     /* in-process memory checkpointer */
from langgraph.prebuilt import ToolNode                 /* executes tool_calls from last AI message */
from langgraph.types import Send                        /* used for dynamic parallel fan-out */
from langchain.agents import create_agent               /* full ReAct agent in one call */


"""
============================================================
SECTION 2 — STATE DEFINITION
One state class per graph.
messages uses add_messages so nodes append instead of replace.
Add any extra fields your app needs alongside messages.
============================================================
"""

class AppState(TypedDict):
    """
    The single state type used throughout this reference.
    messages  — full conversation history, accumulated via add_messages.
    category  — example extra field, replaced normally on update.
    error_count — example numeric field, replaced normally on update.
    result    — example optional payload field.
    """
    messages:    Annotated[list[BaseMessage], add_messages]
    category:    str
    error_count: int
    result:      Optional[dict[str, Any]]


"""
============================================================
SECTION 3 — NODE FUNCTIONS
A node is any callable: (state: AppState) -> dict
Return only the keys you want to change.
For messages, return a list — add_messages will append it.
============================================================
"""

def classify_node(state: AppState) -> dict:
    """
    Reads the last human message and writes category.
    Does not touch messages.
    """
    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    text = last_human.content.lower() if last_human else ""
    category = "billing" if "bill" in text else "technical"
    return {"category": category}


def respond_node(state: AppState) -> dict:
    """
    Appends an AI reply based on category.
    Returns a list for messages so add_messages appends it.
    """
    reply = AIMessage(content=f"Routed to {state['category']} support.")
    return {"messages": [reply]}


def llm_node(state: AppState) -> dict:
    """
    Node that calls a real LLM.
    Create the LLM once at module level, not inside the node.

        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")

    Then invoke with the full message history:
        reply = llm.invoke(state["messages"])
        return {"messages": [reply]}

    reply is already an AIMessage — the LLM produces it automatically.
    """
    raise NotImplementedError("Wire in your LLM here.")


"""
============================================================
SECTION 4 — ROUTER (used with conditional edges)
Reads state and returns a string matching a node name or END.
Annotate return type with Literal for clarity and type checks.
============================================================
"""

def route_by_category(state: AppState) -> Literal["billing_node", "tech_node"]:
    if state["category"] == "billing":
        return "billing_node"
    return "tech_node"


def route_by_tool_calls(state: AppState) -> Literal["tools", "__end__"]:
    """
    Standard ReAct routing.
    If the last AI message contains tool_calls go to tools node,
    otherwise end the graph.
    """
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


"""
============================================================
SECTION 5 — BUILDING THE GRAPH
============================================================
"""

def build_linear_graph():
    """
    Linear pipeline:  START -> classify -> respond -> END
    """
    builder = StateGraph(AppState)

    builder.add_node("classify", classify_node)
    builder.add_node("respond",  respond_node)

    builder.add_edge(START, "classify")
    builder.add_edge("classify", "respond")
    builder.add_edge("respond", END)

    return builder.compile()


def build_branching_graph():
    """
    Branching:  START -> classify -> (billing_node | tech_node) -> END
    """
    def billing_node(state: AppState) -> dict:
        return {"messages": [AIMessage(content="Billing dept reply.")]}

    def tech_node(state: AppState) -> dict:
        return {"messages": [AIMessage(content="Tech dept reply.")]}

    builder = StateGraph(AppState)
    builder.add_node("classify",     classify_node)
    builder.add_node("billing_node", billing_node)
    builder.add_node("tech_node",    tech_node)

    builder.add_edge(START, "classify")

    builder.add_conditional_edges(
        "classify",          /* source node */
        route_by_category,   /* router function */
        {                    /* path_map: return value -> node name */
            "billing_node": "billing_node",
            "tech_node":    "tech_node",
        }
    )

    builder.add_edge("billing_node", END)
    builder.add_edge("tech_node",    END)

    return builder.compile()


"""
============================================================
SECTION 6 — CHECKPOINTING (memory / persistence)
Checkpointers let the graph remember state across calls
by associating it with a thread_id.
============================================================
"""

def build_graph_with_memory():
    """
    MemorySaver is an in-process store — good for dev/testing.
    For production use PostgresSaver or SqliteSaver.
    """
    builder = StateGraph(AppState)
    builder.add_node("classify", classify_node)
    builder.add_node("respond",  respond_node)

    builder.add_edge(START, "classify")
    builder.add_edge("classify", "respond")
    builder.add_edge("respond", END)

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


"""
============================================================
SECTION 7 — INVOKING THE GRAPH
============================================================
"""

def demo_invocation():
    graph = build_linear_graph()

    initial_state = {
        "messages":    [HumanMessage(content="I have a billing question")],
        "category":    "",
        "error_count": 0,
        "result":      None,
    }

    """
    .invoke() — runs the full graph, returns final state.
    """
    result = graph.invoke(initial_state)
    print(result["messages"])

    """
    .stream() — yields snapshots after each node.
    stream_mode options:
        "values"   — full state after each step (default)
        "updates"  — only the dict returned by each node
        "messages" — token-by-token for LLM nodes
    """
    for chunk in graph.stream(initial_state, stream_mode="updates"):
        print(chunk)

    """
    With a checkpointer you MUST pass config with thread_id.
    The same thread_id resumes the same conversation.
    """
    graph_mem = build_graph_with_memory()
    config = {"configurable": {"thread_id": "user-42"}}

    graph_mem.invoke(
        {"messages": [HumanMessage(content="hello")], "category": "", "error_count": 0, "result": None},
        config,
    )
    graph_mem.invoke(
        {"messages": [HumanMessage(content="follow up")]},  /* only send new message; rest is in checkpoint */
        config,
    )

    """
    .get_state(config)          — read current checkpoint without running
    .update_state(config, patch) — manually patch state (useful for HITL)
    """
    snapshot = graph_mem.get_state(config)
    print(snapshot.values)

    graph_mem.update_state(config, {"category": "billing"})


"""
============================================================
SECTION 8 — INTERRUPT / HUMAN-IN-THE-LOOP
============================================================
"""

def build_hitl_graph():
    """
    interrupt_before=["node"] pauses the graph before that node.
    Resume by calling .invoke(None, config).
    """
    def human_review_node(state: AppState) -> dict:
        last = state["messages"][-1]
        approved = AIMessage(content="Human approved: " + last.content)
        return {"messages": [approved]}

    builder = StateGraph(AppState)
    builder.add_node("classify",     classify_node)
    builder.add_node("human_review", human_review_node)
    builder.add_node("respond",      respond_node)

    builder.add_edge(START, "classify")
    builder.add_edge("classify", "human_review")
    builder.add_edge("human_review", "respond")
    builder.add_edge("respond", END)

    checkpointer = MemorySaver()
    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review"],
    )


def demo_hitl():
    graph = build_hitl_graph()
    config = {"configurable": {"thread_id": "hitl-1"}}

    graph.invoke(
        {"messages": [HumanMessage(content="billing issue")], "category": "", "error_count": 0, "result": None},
        config,
    )

    snapshot = graph.get_state(config)
    print("Paused at:", snapshot.next)           /* ('human_review',) */

    graph.update_state(config, {
        "messages": [AIMessage(content="manually edited reply")]
    })

    final = graph.invoke(None, config)           /* resume from checkpoint */
    print(final["messages"])


"""
============================================================
SECTION 9 — TOOLS AND TOOL NODES
============================================================
"""

@tool
def search(query: str) -> str:
    """Search the web for a query."""
    return f"Results for: {query}"


@tool
def calculator(expression: str) -> str:
    """Evaluate a math expression."""
    return str(eval(expression))                 /* noqa: S307 */


tools = [search, calculator]

"""
ToolNode executes all tool_calls found in the last AI message
and writes ToolMessage results back into messages.
The state must have a messages field with add_messages for this to work.
"""
tool_node = ToolNode(tools)


def build_tool_graph():
    """
    ReAct loop:
        START -> llm -> (tools -> llm -> ...) | END

    Wire in your LLM at module level:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
        llm_with_tools = llm.bind_tools(tools)

    Then the llm node becomes:
        def llm_node(state: AppState) -> dict:
            reply = llm_with_tools.invoke(state["messages"])
            return {"messages": [reply]}
    """
    builder = StateGraph(AppState)
    builder.add_node("llm",   llm_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "llm")
    builder.add_conditional_edges("llm", route_by_tool_calls, {"tools": "tools", END: END})
    builder.add_edge("tools", "llm")             /* loop back after tool execution */

    return builder.compile()


"""
create_agent builds the same loop automatically.
Use it when you do not need to customise individual nodes.

    agent = create_agent(llm_with_tools, tools)
    agent.invoke({"messages": [HumanMessage(content="what is 2+2")]})
"""


"""
============================================================
SECTION 10 — PARALLEL EXECUTION WITH Send
Send lets one node fan-out to N parallel instances of another node.
============================================================
"""

class BatchState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    items:    list[str]
    results:  Annotated[list[str], lambda a, b: a + b]


def fan_out_node(state: BatchState) -> list[Send]:
    """
    Return a list of Send objects, one per parallel branch.
    Each Send names the target node and passes it a partial state slice.
    """
    return [Send("process_item", {"item": item}) for item in state["items"]]


def process_item_node(state: dict) -> dict:
    return {"results": [state["item"].upper()]}


def build_parallel_graph():
    builder = StateGraph(BatchState)
    builder.add_node("fan_out",      fan_out_node)
    builder.add_node("process_item", process_item_node)

    builder.add_edge(START, "fan_out")
    builder.add_conditional_edges("fan_out", lambda s: s, ["process_item"])
    builder.add_edge("process_item", END)

    return builder.compile()


"""
============================================================
SECTION 11 — SUBGRAPHS
A compiled graph can be added as a node inside another graph.
The subgraph state and parent state must share the fields
that need to be passed between them.
============================================================
"""

def build_parent_graph():
    sub = build_linear_graph()

    parent_builder = StateGraph(AppState)
    parent_builder.add_node("pre",      lambda s: s)
    parent_builder.add_node("subgraph", sub)
    parent_builder.add_node("post",     lambda s: s)

    parent_builder.add_edge(START, "pre")
    parent_builder.add_edge("pre", "subgraph")
    parent_builder.add_edge("subgraph", "post")
    parent_builder.add_edge("post", END)

    return parent_builder.compile()


"""
============================================================
SECTION 12 — VISUALISING THE GRAPH
Requires: pip install grandalf   (for ASCII art)
          or pygraphviz          (for PNG)
============================================================
"""

def visualise():
    graph = build_branching_graph()
    print(graph.get_graph().draw_ascii())
    graph.get_graph().draw_mermaid_png(output_file_path="graph.png")


"""
============================================================
SECTION 13 — QUICK REFERENCE TABLE
============================================================

| What you want                    | How                                                         |
|----------------------------------|-------------------------------------------------------------|
| Define state                     | class S(TypedDict): ...                                     |
| Accumulate messages              | messages: Annotated[list[BaseMessage], add_messages]        |
| Accumulate any list              | field: Annotated[list, lambda a, b: a + b]                  |
| Create graph                     | builder = StateGraph(AppState)                              |
| Add node                         | builder.add_node("name", fn)                                |
| Linear edge                      | builder.add_edge("a", "b")                                  |
| Conditional edge                 | builder.add_conditional_edges("a", router, path_map)        |
| Compile                          | graph = builder.compile()                                   |
| Compile with memory              | graph = builder.compile(checkpointer=MemorySaver())         |
| Pause before node                | compile(interrupt_before=["node"])                          |
| Initial invoke                   | graph.invoke({"messages": [HumanMessage(...)], ...}, config)|
| Follow-up invoke (checkpointed)  | graph.invoke({"messages": [HumanMessage(...)]}, config)     |
| Stream updates                   | graph.stream(state, config, stream_mode="updates")          |
| Read checkpoint                  | graph.get_state(config)                                     |
| Edit checkpoint                  | graph.update_state(config, patch)                           |
| Resume after interrupt           | graph.invoke(None, config)                                  |
| Execute tool calls               | ToolNode(tools)                                             |
| Full ReAct loop manually         | llm node + conditional edge + ToolNode + loop back edge     |
| Full ReAct loop automatically    | create_agent(llm_with_tools, tools)                         |
| Parallel fan-out                 | return [Send("node", partial_state), ...]                   |
| Nest a graph                     | builder.add_node("sub", compiled_subgraph)                  |
| Draw ASCII diagram               | graph.get_graph().draw_ascii()                              |

"""