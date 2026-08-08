from __future__ import annotations

import re

from app.models.schemas import Chunk

# Prefer chunks that look like applications / conclusions / definitions
CUE_RE = re.compile(
    r"\b("
    r"abstract|introduction|conclusion|application|applications|advantage|advantages|"
    r"benefit|benefits|nanotechnolog|quantum confinement|quantum dots?|nanowires?|"
    r"tunnel|semiconductor|superconductor|density functional|metamaterial|"
    r"sensor|entangle|summary|objective|significance|results?|discussion"
    r")\b",
    re.I,
)


def select_chunks_for_extraction(chunks: list[Chunk], budget: int = 8) -> list[Chunk]:
    """
    Budgeted sampler for Gemini extraction.
    Embeds stay on all chunks; only these are sent to the LLM extractor.
    """
    if not chunks:
        return []
    if len(chunks) <= budget:
        return list(chunks)

    selected: list[Chunk] = []
    selected_ids: set[str] = set()

    def add(c: Chunk) -> None:
        if c.chunk_id in selected_ids:
            return
        if len(selected) >= budget:
            return
        selected.append(c)
        selected_ids.add(c.chunk_id)

    # Always keep early intro/abstract chunks
    for c in chunks[:2]:
        add(c)

    # Score remaining by cue density + slight preference for mid/late sections
    scored: list[tuple[float, Chunk]] = []
    n = len(chunks)
    for idx, c in enumerate(chunks):
        if c.chunk_id in selected_ids:
            continue
        text = c.text or ""
        cues = len(CUE_RE.findall(text))
        # Short "heading-like" lines boost
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        headingish = sum(1 for ln in lines[:4] if len(ln) < 80 and not ln.endswith("."))
        position = idx / max(1, n - 1)
        # Mild boost for middle-to-late (applications/results often live there)
        pos_boost = 0.5 if 0.3 <= position <= 0.85 else 0.0
        score = cues * 2.0 + headingish * 0.5 + pos_boost
        scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    for score, c in scored:
        if score <= 0 and len(selected) >= max(3, budget // 2):
            break
        add(c)
        if len(selected) >= budget:
            break

    # Fill remaining slots with evenly spaced leftovers for coverage
    if len(selected) < budget:
        step = max(1, len(chunks) // budget)
        for c in chunks[::step]:
            add(c)
            if len(selected) >= budget:
                break

    # Preserve original document order for extraction coherence
    order = {c.chunk_id: i for i, c in enumerate(chunks)}
    selected.sort(key=lambda c: order.get(c.chunk_id, 0))
    return selected
