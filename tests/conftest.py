from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure repo root is importable regardless of how pytest is invoked.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Seed minimal env so Settings() succeeds in unit tests.
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "anon-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("LLAMA_CLOUD_API_KEY", "llx-test")
os.environ.setdefault("APP_ENV", "test")
