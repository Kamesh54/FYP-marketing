"""Embedding helpers using sentence-transformers.
Provides lightweight wrappers for text and image embeddings.
"""
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def load_text_model(model_name: str = "all-MiniLM-L6-v2"):
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
        return model
    except Exception as e:
        logger.exception(f"Failed to load text embedding model {model_name}: {e}")
        raise


def load_image_model(model_name: str = "clip-ViT-B-32"):
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
        return model
    except Exception as e:
        logger.exception(f"Failed to load image embedding model {model_name}: {e}")
        raise


def embed_texts(model, texts: List[str], batch_size: int = 32):
    """Return numpy array of embeddings for a list of texts."""
    try:
        emb = model.encode(texts, batch_size=batch_size, convert_to_numpy=True, show_progress_bar=False)
        return emb
    except Exception:
        logger.exception("Text embedding failed")
        raise


def embed_image(model, image_path: str):
    """Embed a single image file using a SentenceTransformer image-capable model."""
    try:
        from PIL import Image
        img = Image.open(image_path).convert('RGB')
        emb = model.encode([img], convert_to_numpy=True, show_progress_bar=False)
        return emb[0]
    except Exception:
        logger.exception(f"Image embedding failed for {image_path}")
        raise
