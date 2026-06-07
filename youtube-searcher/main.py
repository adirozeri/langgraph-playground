from agent.graph import *

def demo_invocation():
    graph = build_graph()
    init_questing = "What did Linus Torvalds eat for breakfast in 2003?"
    initial_state = {"question": init_questing}
    
    result = graph.invoke(initial_state)
    print(result["final_answer"])


demo_invocation()


