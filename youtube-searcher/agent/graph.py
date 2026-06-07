from typing import Literal
from langgraph.graph import StateGraph, START, END
from agent.state import GraphState
from agent.nodes import *

def router(state: GraphState) -> Literal["good_rank", "try_next", "give_up"]:
    if not state["ranked_videos"]:
        return "give_up"
    if state["ranked_videos"][0]["score"] >= SCORE_THRESHOLD:
        return "good_rank"
    if state["current_query_index"] < len(state["search_queries"]) - 1:
        return "try_next"
    return "give_up"

def build_graph():
    builder = StateGraph(GraphState)

    builder.add_node("query_formulator", query_formulator)
    builder.add_node("youtube_searcher", youtube_searcher)
    # builder.add_node("transcript_fetcher", transcript_fetcher)
    builder.add_node("relevance_ranker", relevance_ranker)
    builder.add_node("result_formatter", result_formatter)
    builder.add_node("failure_formatter", failure_formatter)

    # builder.add_node("quality_gate", quality_gate)

    builder.add_edge(START, "query_formulator")
    builder.add_edge("query_formulator", "youtube_searcher")
    builder.add_edge("youtube_searcher", "relevance_ranker")
    builder.add_conditional_edges("relevance_ranker",router,
                                  {
                                      "good_rank" : "result_formatter",
                                      "try_next" : "youtube_searcher",
                                      "give_up" : "failure_formatter"
                                  } )
    builder.add_edge("result_formatter", END)
    builder.add_edge("failure_formatter", END)


    return builder.compile()
    

