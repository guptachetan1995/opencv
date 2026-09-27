"""The local HTTP serving layer for Second Look — not the Lambda handler.

`server.py` wraps `secondlook.agent_loop` (`invoke`, `process_capture`) behind a
standard-library `http.server`; `smoke.py` is the runnable smoke command; `static/` holds
the approval page. See `server.py`'s module docstring for the route list.
"""
