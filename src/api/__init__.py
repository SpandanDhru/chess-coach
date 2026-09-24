"""FastAPI sidecar for the desktop UI.

Wraps the existing Python coach (Coach / Knowledge / Database / analyzers) in a
local HTTP API that the Electron + React renderer talks to. No chess or LLM logic
is reimplemented here — this package only adapts the existing modules to HTTP.
"""
