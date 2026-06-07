from langchain_openai import ChatOpenAI
from agent.prompts import *
from agent.tools import *

import json

from agent.state import GraphState
from dotenv import load_dotenv
import os
load_dotenv()

openai_api_key = os.environ.get("OPENAI_API_KEY")

llm = ChatOpenAI(model="gpt-4o")
SCORE_THRESHOLD = 0.95

def query_formulator(state: GraphState):
    """
    Takes the raw question, uses LLM to produce 2-3 optimized YouTube search strings
    """
    prompt = QUERY_FORMULATOR_PROMPT.format(question=state["question"])
    response = llm.invoke(prompt)
    queries = [q.strip() for q in response.content.strip().split("\n")]

    return {"search_queries": queries,"current_query_index": 0}
    
def youtube_searcher(state: GraphState):
    """
    Runs each search query, collects raw video candidates
    """
    cur_query_idx = state["current_query_index"]
    qry = state["search_queries"][state["current_query_index"]]

    return {"candidate_videos": tool_youtube_searcher(qry), "current_query_index" : cur_query_idx + 1}
    
# def transcript_fetcher(state: GraphState):
#     """
#     For top N candidates, pulls transcripts or falls back to description
#     """
#     pass
    
def relevance_ranker(state: GraphState):
    """
    LLM scores each candidate against the original question, produces ranked list
    """
    ranked_videos : List[RankedVideo] = []
    question = state["question"]
    for candidate in state["candidate_videos"]:
        prompt = RELEVANCE_RANKER_PROMPT.format(
            question=question,
            title=candidate["title"],
            description=candidate["description"]
        )
        response = llm.invoke(prompt)
        try:
            data = json.loads(response.content)
            score = data["score"]
        except (json.JSONDecodeError, KeyError):
            score = 0.0

        ranked_videos.append({"video" : candidate, "score": score})
        print("https://www.youtube.com/watch?v={video_id} ".format(video_id=candidate["video_id"]) + response.content)
    
    
    ranked_videos.sort(key=lambda x: x["score"], reverse=True)

    return {"ranked_videos" : ranked_videos}
        

    
def result_formatter(state: GraphState):
    """
    Builds the final human-readable answer from ranked results
    """
    
    prompt = RESULT_FORMATTER_PROMPT.format(
        question=state["question"], 
        ranked_videos=state["ranked_videos"]        
        )
    response = llm.invoke(prompt)
    return {"final_answer" : response.content}
    

def failure_formatter(state: GraphState):
    """
    Builds the final human-readable answer from ranked results
    """
    
    prompt = FAILURE_FORMATTER_PROMPT.format(
        question=state["question"]
        )
    response = llm.invoke(prompt)
    return {"final_answer" : response.content}
