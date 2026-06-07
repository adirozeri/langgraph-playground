from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode                 
from dotenv import load_dotenv
import os
from googleapiclient.discovery import build
from agent.state import *
from typing import TypedDict, List
from agent.state import VideoCandidate
load_dotenv()
key = os.environ.get("YOUTUBE_API_KEY")
youtube = build("youtube", "v3", developerKey=key)

# @tool
def tool_youtube_searcher(qry: str) -> List[VideoCandidate] :
    """Calls YouTube Data API v3 with a query string, 
    returns list of video metadata (id, title, description, channel, views, duration)"""
    
    response = youtube.search().list(
        part="snippet",
        # q="how does a transformer neural network work",
        q=qry,
        type="video",
        maxResults=5,
        order="relevance",
        videoCaption="closedCaption"
    ).execute()

    items = response["items"]
    if not items:
        return []

    ids = []
    for item in items:
        ids.append(item['id']['videoId'])

    details_response = youtube.videos().list(
        part="snippet,statistics,contentDetails",
        id=ids
    ).execute()
        
    items_destails = details_response["items"]
    
    items_list : List[VideoCandidate] = []

    for item, video in zip(items,items_destails):
        video_id    = item["id"]["videoId"]
        title       = item["snippet"]["title"]
        description = item["snippet"]["description"]
        channel     = item["snippet"]["channelTitle"]

        view_count = video["statistics"]["viewCount"]
        duration   = video["contentDetails"]["duration"]

        items_list.append(
            {
                "video_id" : video_id,
                "title" : title,
                "description" : description,
                "channel_name" : channel
            }
        )

    return items_list

# @tool
# def tool_fetch_transcript():
#     """Given a video id, returns the transcript as plain text"""
#     pass

# @tool
# def tool_fetch_video_details():
#     """Given a list of video ids, returns enriched metadata in one batched API call"""
#     pass
