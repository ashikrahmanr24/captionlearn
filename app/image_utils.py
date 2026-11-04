import io
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from PIL import Image
import numpy as np

COLOR_MAP = {
    "black": (25, 25, 25),
    "white": (240, 240, 240),
    "gray": (128, 128, 128),
    "silver": (192, 192, 192),
    "red": (220, 38, 38),
    "blue": (37, 99, 235),
    "navy": (15, 23, 42),
    "green": (22, 163, 74),
    "yellow": (234, 179, 8),
    "brown": (120, 53, 15),
    "gold": (217, 119, 6),
    "pink": (236, 72, 153),
    "purple": (147, 51, 234),
    "orange": (249, 115, 22),
}

def compute_dhash(img: Image.Image, hash_size: int = 8) -> str:
    """Computes difference hash (dHash) of an image."""
    try:
        resized = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)
        arr = np.array(resized)
        
        diff = []
        for row in range(hash_size):
            for col in range(hash_size):
                diff.append("1" if arr[row, col] > arr[row, col + 1] else "0")
        return "".join(diff)
    except Exception:
        return ""

def compute_color_histogram(img: Image.Image, bins: int = 8) -> list[float]:
    """Computes normalized RGB color histogram."""
    try:
        rgb_img = img.convert("RGB").resize((64, 64), Image.Resampling.BILINEAR)
        arr = np.array(rgb_img)
        
        hist_r, _ = np.histogram(arr[:, :, 0], bins=bins, range=(0, 256))
        hist_g, _ = np.histogram(arr[:, :, 1], bins=bins, range=(0, 256))
        hist_b, _ = np.histogram(arr[:, :, 2], bins=bins, range=(0, 256))
        
        hist = np.concatenate([hist_r, hist_g, hist_b]).astype(float)
        norm = np.linalg.norm(hist)
        if norm > 0:
            hist = hist / norm
        return hist.tolist()
    except Exception:
        return []

def detect_dominant_color(img: Image.Image) -> str:
    """Detects closest named color based on average RGB."""
    try:
        rgb_img = img.convert("RGB").resize((32, 32))
        arr = np.array(rgb_img)
        avg_r = float(np.mean(arr[:, :, 0]))
        avg_g = float(np.mean(arr[:, :, 1]))
        avg_b = float(np.mean(arr[:, :, 2]))
        
        min_dist = float("inf")
        best_color = "unknown"
        for name, (cr, cg, cb) in COLOR_MAP.items():
            dist = (avg_r - cr) ** 2 + (avg_g - cg) ** 2 + (avg_b - cb) ** 2
            if dist < min_dist:
                min_dist = dist
                best_color = name
        return best_color
    except Exception:
        return "unknown"

def extract_image_features(image_path: Path | str) -> Dict[str, Any]:
    """Reads image file and extracts perceptual dHash, color histogram, and dominant color."""
    try:
        with Image.open(image_path) as img:
            dhash = compute_dhash(img)
            hist = compute_color_histogram(img)
            dominant = detect_dominant_color(img)
            w, h = img.size
            return {
                "dhash": dhash,
                "color_hist": hist,
                "dominant_color": dominant,
                "dimensions": f"{w}x{h}",
                "valid": True
            }
    except Exception as e:
        return {
            "dhash": "",
            "color_hist": [],
            "dominant_color": "unknown",
            "dimensions": "0x0",
            "valid": False,
            "error": str(e)
        }

def compare_images(features_a: Dict[str, Any], features_b: Dict[str, Any]) -> float:
    """
    Computes visual similarity between two extracted image features (0.0 - 100.0).
    Uses a combination of dHash Hamming distance and color histogram cosine similarity.
    """
    if not features_a or not features_b:
        return 0.0
    if not features_a.get("valid") or not features_b.get("valid"):
        return 0.0
        
    hash_a = features_a.get("dhash", "")
    hash_b = features_b.get("dhash", "")
    
    hash_score = 0.0
    if hash_a and hash_b and len(hash_a) == len(hash_b) and len(hash_a) > 0:
        hamming_dist = sum(c1 != c2 for c1, c2 in zip(hash_a, hash_b))
        hash_score = max(0.0, 1.0 - (hamming_dist / 32.0)) * 100.0
        
    hist_a = features_a.get("color_hist", [])
    hist_b = features_b.get("color_hist", [])
    
    hist_score = 0.0
    if hist_a and hist_b and len(hist_a) == len(hist_b):
        a = np.array(hist_a)
        b = np.array(hist_b)
        dot = float(np.dot(a, b))
        hist_score = max(0.0, min(1.0, dot)) * 100.0
        
    if hash_a and hist_a:
        overall_img_score = (0.55 * hash_score) + (0.45 * hist_score)
    elif hash_a:
        overall_img_score = hash_score
    else:
        overall_img_score = hist_score
        
    return round(min(100.0, max(0.0, overall_img_score)), 1)
