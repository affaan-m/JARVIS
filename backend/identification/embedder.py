# RESEARCH: Checked insightface/ArcFace (24k stars), facenet-pytorch (4.5k stars)
# DECISION: Stub implementation for now — ArcFace requires onnxruntime + model download
# ALT: Will swap in insightface ArcFace when GPU/model is available
from __future__ import annotations

import hashlib

from loguru import logger

from identification.models import DetectedFace


class ArcFaceEmbedder:
    """Stub ArcFace embedder that generates deterministic pseudo-embeddings.

    Produces 512-dimensional vectors derived from the face bounding box,
    so the same crop always gets the same embedding. This lets downstream
    code (search, dedup) run against a realistic vector shape while we
    integrate the real onnxruntime model.
    """

    EMBEDDING_DIM = 512

    def __init__(self) -> None:
        self._configured = True

    @property
    def configured(self) -> bool:
        return self._configured

    def embed(self, face: DetectedFace, image_data: bytes) -> list[float]:
        """Generate a pseudo-embedding for a detected face.

        Args:
            face: The detected face with bounding box.
            image_data: Raw image bytes (used for deterministic hashing).

        Returns:
            512-dimensional float vector.
        """
        # Create a deterministic seed from bbox + a hash of the crop region
        bbox = face.bbox
        seed_str = f"{bbox.x:.4f}:{bbox.y:.4f}:{bbox.width:.4f}:{bbox.height:.4f}"
        digest = hashlib.sha256(seed_str.encode() + image_data[:1024]).digest()

        # Expand the 32-byte digest into 512 floats in [-1, 1]
        embedding: list[float] = []
        for i in range(self.EMBEDDING_DIM):
            byte_val = digest[i % len(digest)]
            # XOR with position for variation beyond 32 dims
            mixed = byte_val ^ (i & 0xFF)
            embedding.append((mixed / 127.5) - 1.0)

        logger.debug(
            "Generated stub embedding (dim={}) for face at ({:.2f}, {:.2f})",
            self.EMBEDDING_DIM,
            face.bbox.x,
            face.bbox.y,
        )
        return embedding
