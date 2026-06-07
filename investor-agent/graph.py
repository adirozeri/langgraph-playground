from langgraph.graph import StateGraph, END
from state import AgentState
from nodes import research_node, portfolio_node, analysis_node, decision_node, memory_node


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("research", research_node)
    builder.add_node("portfolio", portfolio_node)
    builder.add_node("analysis", analysis_node)
    builder.add_node("decision", decision_node)
    builder.add_node("memory", memory_node)

    builder.set_entry_point("research")
    builder.add_edge("research", "portfolio")
    builder.add_edge("portfolio", "analysis")
    builder.add_edge("analysis", "decision")
    builder.add_edge("decision", "memory")
    builder.add_edge("memory", END)

    return builder.compile()


graph = build_graph()


if __name__ == "__main__":
    # Quick sanity check — visualize the graph structure
    print(graph.get_graph().draw_ascii())
