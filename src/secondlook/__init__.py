"""Second Look — receipt-capture inspection on OpenCV 5.

Public surface of the pipeline core: ``inspect`` (the eight OpenCV 5 measurements),
``decide`` (the deterministic rule cascade in ``policy.toml``), the structured records they
exchange (``schema.py``), and the agent loop that wraps them as tools behind a single
``invoke`` chokepoint (``agent_loop.py``).
"""

from secondlook.agent_loop import AgentLoop, Capture, invoke, process_capture
from secondlook.perception import inspect, inspect_file
from secondlook.policy import Policy, decide, load_policy
from secondlook.schema import Measurements, RuleFiring, TraceEntry, Verdict

__all__ = [
    "AgentLoop",
    "Capture",
    "Measurements",
    "Policy",
    "RuleFiring",
    "TraceEntry",
    "Verdict",
    "decide",
    "inspect",
    "inspect_file",
    "invoke",
    "load_policy",
    "process_capture",
]
