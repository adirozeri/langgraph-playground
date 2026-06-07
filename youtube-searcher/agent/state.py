from typing import Annotated, Literal, Optional, Any, List, Dict
from typing_extensions import TypedDict
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph.message import add_messages        



class VideoCandidate(TypedDict):
    video_id: str
    title: str
    description: str
    channel: str
    # view_count: int
    # duration: str

class RankedVideo(TypedDict):
    video: VideoCandidate
    score: float
    # explanation: str

class GraphState(TypedDict):
    question: str
    search_queries: List[str]
    current_query_index: int
    candidate_videos: List[VideoCandidate]
    # transcripts: Dict[str, str]
    ranked_videos: List[RankedVideo]
    final_answer: str