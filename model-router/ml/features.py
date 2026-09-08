"""Turn examples into a feature matrix: semantics + the structural signals.

Two blocks, concatenated:

* **semantic** -- a static embedding of the prompt. Static means the token
  vectors are precomputed and inference is a lookup and a mean, so it costs
  microseconds on a CPU with no torch at runtime. That matters because this
  runs in front of every API call.
* **structural** -- the same signals ccrouter already extracts (loop phase,
  failures, thrash, blast radius). The embedding cannot see that the last two
  tool calls failed; the structural block can.

Keeping them separate lets `train.py` fit each block alone and report whether
semantics actually earned its place.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema import Example

DEFAULT_ENCODER = "minishlab/potion-base-8M"

# The feature order lives in the runtime package so training and serving cannot
# drift apart: if you add a signal, add it in one place.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ccrouter.semantic import STRUCTURAL_KEYS, structural_vector  # noqa: E402,F401

__all__ = ["DEFAULT_ENCODER", "STRUCTURAL_KEYS", "Featurizer", "stack", "structural_vector"]


@dataclass
class Featurizer:
    encoder_name: str = DEFAULT_ENCODER
    cache_dir: str = ".cache/embeddings"
    _model: Any = None

    def load(self) -> Any:
        if self._model is None:
            from model2vec import StaticModel      # imported lazily: training-only dep

            self._model = StaticModel.from_pretrained(self.encoder_name)
        return self._model

    @property
    def dim(self) -> int:
        return int(self.load().dim)

    def embed(self, texts: Sequence[str], use_cache: bool = True) -> np.ndarray:
        """Embed, memoising on disk -- retraining should not re-encode."""
        if not use_cache:
            return np.asarray(self.load().encode(list(texts)), dtype=np.float32)

        key = hashlib.sha256(
            (self.encoder_name + "\x00" + "\x00".join(texts)).encode("utf-8", "replace")
        ).hexdigest()[:24]
        path = Path(self.cache_dir) / f"{key}.npy"
        if path.is_file():
            return np.load(path)

        vectors = np.asarray(self.load().encode(list(texts)), dtype=np.float32)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, vectors)
        return vectors

    def transform(
        self, examples: Sequence[Example], use_cache: bool = True
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return (semantic, structural) blocks so callers can ablate either."""
        semantic = self.embed([e.prompt for e in examples], use_cache=use_cache)
        structural = np.asarray(
            [structural_vector(e.signals, e.prompt) for e in examples], dtype=np.float32
        )
        return semantic, structural


def stack(semantic: np.ndarray, structural: np.ndarray, block: str = "both") -> np.ndarray:
    if block == "semantic":
        return semantic
    if block == "structural":
        return structural
    return np.hstack([semantic, structural])
