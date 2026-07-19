"""DistilBERT category classifier — the supervised half of hybrid classification
(TRD §5 stage 6; Phase 5 decision: DistilBERT fine-tuned on seed data).

Artifacts come from scripts/train_classifier.py. If the trained model directory
is missing, `predict` returns None and the pipeline degrades to LLM-only.
"""

import logging
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger("agentdesk")


@lru_cache(maxsize=1)
def _load():
    path = Path(get_settings().classifier_dir)
    if not (path / "config.json").is_file():
        logger.warning("DistilBERT classifier not found at %s — LLM-only classification", path)
        return None
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(path)
    model = AutoModelForSequenceClassification.from_pretrained(path)
    model.eval()
    return tokenizer, model


def predict(text: str) -> tuple[str, float] | None:
    """Return (category_name, probability 0–1), or None when no model is trained.

    Blocking (CPU inference) — the pipeline calls this via asyncio.to_thread.
    """
    loaded = _load()
    if loaded is None:
        return None
    import torch

    tokenizer, model = loaded
    inputs = tokenizer(text, truncation=True, max_length=256, return_tensors="pt")
    with torch.no_grad():
        probs = model(**inputs).logits[0].softmax(dim=-1)
    idx = int(probs.argmax())
    return model.config.id2label[idx], float(probs[idx])
