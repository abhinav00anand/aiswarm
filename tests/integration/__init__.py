"""
Integration tests for AISwarm.

Test files:
  test_full_pipeline.py    — Full Boss→Manager→Coder→Critics→Merge pipeline
  test_host_routing.py     — Host-1 routing decisions across FAST/PRODUCTION/HYBRID
  test_sandbox_isolation.py — Execution sandbox path isolation and command allowlisting

Required environment variables (at least one):
  NOVITA_API_KEY / NOVITA_TOKEN
  OPENAI_API_KEY
  ANTHROPIC_API_KEY
  GEMINI_API_KEY / GOOGLE_API_KEY
  DEEPSEEK_API_KEY

Run:
  pytest tests/integration/ -v -m integration
"""
