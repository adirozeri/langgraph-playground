QUERY_FORMULATOR_PROMPT = """
You are a YouTube search expert.
Given a user question, generate exactly 3 short keyword-focused YouTube search queries
that would find videos answering it.

User question: {question}

Rules:
- Each query should be 3 to 6 words
- Focus on keywords, not full sentences
- Each query should approach the question from a different angle
- Return one query per line, nothing else, no numbering, no punctuation
"""
#################################################################################################
RELEVANCE_RANKER_PROMPT = """
You are evaluating whether a YouTube video answers a user question.

User question: {question}

Video title: {title}
Video description: {description}

Score this video from 0.0 to 1.0 based on how well it answers the question.
Return a JSON object with exactly two fields:
- score: a float between 0.0 and 1.0

Return nothing else. The response should be a string starting with {{ and ending with }}. nothing else.
"""
# Video transcript: {transcript}
#################################################################################################
RESULT_FORMATTER_PROMPT = """
You are summarizing YouTube search results for a user.

User question: {question}

Top videos found:
{ranked_videos}

Write a short answer to the user explaining which video best answers their question
and why, including the video title and a YouTube link in the format:
https://www.youtube.com/watch?v={{video_id}}
"""
#################################################################################################
FAILURE_FORMATTER_PROMPT = """
You were unable to find a YouTube video that adequately answers the following question:

{question}

Write a short, honest message to the user explaining that no good result was found
and suggest they try rephrasing their question.
"""