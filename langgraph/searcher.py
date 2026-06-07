from typing import Annotated, Literal, Optional, Any, List
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
from langgraph.graph.message import add_messages        
from langgraph.checkpoint.memory import MemorySaver     
from langgraph.prebuilt import ToolNode                 
from langgraph.types import Send                        
from langchain.agents import create_agent               
from tavily import TavilyClient

tavily_client = TavilyClient(api_key="tvly-YOUR_API_KEY")
response = tavily_client.search("Who is Leo Messi?")

print(response)

class AppState(TypedDict):
    messages : Annotated[List[BaseMessage], add_messages]

def serach_node(state: AppState):
    