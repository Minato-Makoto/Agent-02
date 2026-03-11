"""
ModelProxy — thin proxy to the llama-server router model list.

All model data comes from ``GET /v1/models`` on the llama-server.
No caching, no registry file — llama-server is the single source of truth.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Minimal model descriptor returned by the router."""

    id: str
    object: str = "model"
    owned_by: str = ""
    meta: Dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.meta is None:
            self.meta = {}

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "object": self.object, "owned_by": self.owned_by}


class ModelProxy:
    """Proxy that fetches the model list from the llama-server router endpoint."""

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    def list_models(self) -> List[ModelInfo]:
        """Fetch models from ``/v1/models``."""
        try:
            resp = requests.get(f"{self._base_url}/v1/models", timeout=5)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.exception("Failed to fetch model list from llama-server.")
            return []

        models: List[ModelInfo] = []
        for item in data.get("data", []):
            models.append(
                ModelInfo(
                    id=str(item.get("id", "")),
                    object=str(item.get("object", "model")),
                    owned_by=str(item.get("owned_by", "")),
                    meta=item.get("meta", {}),
                )
            )
        return models

    def get_model_ids(self) -> List[str]:
        """Return just the model ID strings."""
        return [m.id for m in self.list_models()]

    def find_model(self, model_id: str) -> Optional[ModelInfo]:
        """Look up a specific model by ID."""
        for m in self.list_models():
            if m.id == model_id:
                return m
        return None
