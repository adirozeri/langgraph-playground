# Architecture contract — enforced at every module boundary:
#   ALL numeric values must originate from a real financial data API
#   and be computed deterministically in Python.
#   The LLM is only ever used to interpret numbers it is explicitly given.
#   The LLM must never generate or invent any figure that appears in output.
