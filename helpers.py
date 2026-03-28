"""Business-logic helpers: query extraction and HydraDB context retrieval."""

import os

from hydra_db import HydraDB

from utils import call_gmi

HYDRA_API_KEY = os.environ["HYDRADB_API_KEY"]
TENANT_ID     = "hubbase"

hydra = HydraDB(token=HYDRA_API_KEY)


def extract_queries(message: str) -> list[str]:
    """Ask the LLM to produce two BM25-friendly search queries from a natural-language message."""
    prompt = (
        "Given this prospect inquiry, produce exactly 2 short keyword search queries "
        "to retrieve relevant info from a HubSpot agency website.\n"
        "Line 1: keywords for the specific service/topic.\n"
        "Line 2: keywords for pricing or cost.\n"
        "Return only the 2 lines, nothing else.\n\n"
        f"Inquiry: {message}"
    )
    try:
        raw   = call_gmi("", prompt).strip()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        return lines[:2] if len(lines) >= 2 else [message, "integration pricing"]
    except Exception:
        return [message, "integration pricing"]


def recall_context(queries: list[str], top_k: int) -> tuple[str, list[str]]:
    """Run parallel BM25 recalls for each query and merge unique chunks."""
    seen, chunks = set(), []
    per_q = max(top_k // len(queries), 3)
    for q in queries:
        result = hydra.recall.recall_preferences(
            query=q, tenant_id=TENANT_ID, max_results=per_q, alpha=0.0,
        )
        for c in result.chunks:
            if c.source_id not in seen:
                seen.add(c.source_id)
                chunks.append(c)
    context = "\n\n---\n\n".join(f"[Source: {c.source_id}]\n{c.chunk_content}" for c in chunks)
    return context, list(seen)
