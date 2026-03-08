"""CLI to populate Chroma vector store from `previews/` and `generated_images/`.

Run with `--dry-run` to list actions without computing embeddings.
"""
import os
import sys
import argparse
import logging
from pathlib import Path
from bs4 import BeautifulSoup

# Ensure repo root is on sys.path so imports work when running from scripts/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)


def extract_text_from_html(path: Path) -> str:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            html = f.read()
        soup = BeautifulSoup(html, 'lxml')
        return soup.get_text(separator=' ', strip=True)
    except Exception:
        logger.exception(f"Failed to extract text from {path}")
        return ""


def main(dry_run: bool = True, text_model_name: str = "all-MiniLM-L6-v2", img_model_name: str = "clip-ViT-B-32", limit: int = 0):
    # Local imports to avoid heavy deps when dry-running
    from memory import _chroma_text_collection, _chroma_vis_collection, write_campaign_entity

    previews_dir = Path('previews')
    images_dir = Path('generated_images')

    text_files = sorted(previews_dir.glob('*.html')) if previews_dir.exists() else []
    image_files = sorted(images_dir.glob('*')) if images_dir.exists() else []

    if limit and limit > 0:
        text_files = text_files[:limit]
        image_files = image_files[:limit]

    if dry_run:
        print(f"Dry run: found {len(text_files)} previews and {len(image_files)} images")
        for p in text_files:
            print(f"[preview] {p}")
        for im in image_files:
            print(f"[image] {im}")
        return

    # Load embedding models
    from tools.embedding import load_text_model, load_image_model, embed_texts, embed_image

    text_model = load_text_model(text_model_name)
    try:
        img_model = load_image_model(img_model_name)
    except Exception:
        img_model = None

    # Process previews
    for p in text_files:
        text = extract_text_from_html(p)
        if not text:
            continue
        emb = embed_texts(text_model, [text])[0]
        campaign_id = f"preview_{p.stem}"
        # add to chroma if available
        if _chroma_text_collection is not None:
            try:
                _chroma_text_collection.add(ids=[campaign_id], embeddings=[emb.tolist()], metadatas=[{"source": "preview", "path": str(p)}])
            except Exception:
                logger.exception("Failed to add preview embedding to Chroma")

        # write a memory record
        write_campaign_entity({
            "campaign_id": campaign_id,
            "text_vector": emb.tolist(),
            "text_model": text_model_name,
            "context_metadata": {"source_path": str(p)},
            "source": "populate_chroma"
        })

    # Process images
    for im in image_files:
        try:
            if img_model is None:
                logger.warning("No image model available; skipping image embeddings")
                break
            emb = embed_image(img_model, str(im))
            campaign_id = f"image_{im.stem}"
            if _chroma_vis_collection is not None:
                try:
                    _chroma_vis_collection.add(ids=[campaign_id], embeddings=[emb.tolist()], metadatas=[{"source": "generated_image", "path": str(im)}])
                except Exception:
                    logger.exception("Failed to add image embedding to Chroma")

            write_campaign_entity({
                "campaign_id": campaign_id,
                "visual_vector": emb.tolist(),
                "visual_model": img_model_name,
                "context_metadata": {"source_path": str(im)},
                "source": "populate_chroma"
            })
        except Exception:
            logger.exception(f"Failed to process image {im}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='List files to process without computing embeddings')
    parser.add_argument('--text-model', default='all-MiniLM-L6-v2')
    parser.add_argument('--img-model', default='clip-ViT-B-32')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of files processed (0 = no limit)')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    main(dry_run=args.dry_run, text_model_name=args.text_model, img_model_name=args.img_model, limit=args.limit)
