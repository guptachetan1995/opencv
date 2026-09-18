"""Second Look — receipt-capture inspection on OpenCV 5.

Public surface of the pipeline core: ``inspect`` (the eight measurements, SPEC § 4),
``decide`` (the deterministic cascade, SPEC § 8), the structured records they exchange
(SPEC § 6), and the agent loop that wraps them as tools behind a single ``invoke``
chokepoint (SPEC § 3, § 5, § 7).
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
