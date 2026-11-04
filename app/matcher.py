import re
import json
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, Set
from app.image_utils import compare_images

STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "up", "about", "into", "over", "after", "is", "was", "are", "were",
    "has", "have", "had", "it", "its", "this", "that", "there", "some", "my", "your",
    "near", "inside", "outside", "around", "beside", "behind", "small", "big", "large"
}

SYNONYM_GROUPS = [
    {"earbuds", "earbud", "buds", "bud", "earphone", "earphones", "airpods", "headset", "headphones", "wireless"},
    {"mobile", "phone", "smartphone", "cellphone", "iphone", "android"},
    {"wallet", "purse", "pouch", "billfold", "cardholder"},
    {"bottle", "flask", "tumbler", "sipper", "waterbottle", "thermos"},
    {"bag", "backpack", "sack", "rucksack", "handbag"},
    {"spectacles", "glasses", "specs", "eyewear", "sunglasses", "shades"},
    {"calculator", "calc", "scientific-calculator"},
    {"watch", "smartwatch", "wristwatch", "timepiece"},
    {"id", "idcard", "identity", "identity-card", "badge"},
    {"notebook", "register", "copy", "book", "journal", "diary"}
]

COLOR_FAMILIES = {
    "black": {"black", "dark", "charcoal", "jet"},
    "blue": {"blue", "navy", "cyan", "sky", "indigo", "azure", "cobalt"},
    "red": {"red", "crimson", "maroon", "burgundy", "scarlet"},
    "brown": {"brown", "tan", "beige", "khaki", "camel", "chocolate"},
    "green": {"green", "olive", "emerald", "mint", "teal", "forest"},
    "white": {"white", "off-white", "cream", "ivory"},
    "gray": {"gray", "grey", "silver", "slate"},
    "yellow": {"yellow", "gold", "golden", "amber"},
    "purple": {"purple", "violet", "lavender", "magenta"},
    "orange": {"orange", "peach", "coral"}
}

def clean_and_tokenize(text: Optional[str]) -> Set[str]:
    """Cleans text, removes punctuation/stopwords, and applies basic stemming."""
    if not text:
        return set()
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    tokens = set()
    for word in cleaned.split():
        if word in STOP_WORDS or len(word) < 2:
            continue
        # Simple stemming: strip plurals
        if word.endswith("ies") and len(word) > 4:
            stemmed = word[:-3] + "y"
        elif word.endswith("es") and len(word) > 3:
            stemmed = word[:-2]
        elif word.endswith("s") and not word.endswith("ss") and len(word) > 2:
            stemmed = word[:-1]
        else:
            stemmed = word
        tokens.add(stemmed)
    return tokens

def expand_synonyms(tokens: Set[str]) -> Set[str]:
    """Expands token set with domain synonyms."""
    expanded = set(tokens)
    for group in SYNONYM_GROUPS:
        stemmed_group = set()
        for g in group:
            if g.endswith("s") and not g.endswith("ss"):
                stemmed_group.add(g[:-1])
            stemmed_group.add(g)
        if tokens & stemmed_group:
            expanded |= stemmed_group
    return expanded

def calculate_text_similarity(title_a: str, desc_a: str, title_b: str, desc_b: str, cat_a: str = "", cat_b: str = "") -> float:
    """Calculates semantic text similarity using token overlap, synonym expansion, and title weighting."""
    tokens_title_a = expand_synonyms(clean_and_tokenize(title_a))
    tokens_title_b = expand_synonyms(clean_and_tokenize(title_b))
    
    tokens_full_a = expand_synonyms(clean_and_tokenize(f"{cat_a} {title_a} {desc_a}"))
    tokens_full_b = expand_synonyms(clean_and_tokenize(f"{cat_b} {title_b} {desc_b}"))
    
    if not tokens_full_a or not tokens_full_b:
        return 0.0
        
    # Title Jaccard (core object identity)
    title_intersection = len(tokens_title_a & tokens_title_b)
    title_min_len = min(len(tokens_title_a), len(tokens_title_b)) if tokens_title_a and tokens_title_b else 1
    # Containment / overlap ratio
    title_overlap = (title_intersection / title_min_len) if title_min_len > 0 else 0.0
    
    # Full document Jaccard
    doc_intersection = len(tokens_full_a & tokens_full_b)
    doc_union = len(tokens_full_a | tokens_full_b)
    doc_jaccard = (doc_intersection / doc_union) if doc_union > 0 else 0.0
    
    # Doc containment ratio (how much of the shorter description is contained in the longer)
    doc_min_len = min(len(tokens_full_a), len(tokens_full_b))
    doc_containment = (doc_intersection / doc_min_len) if doc_min_len > 0 else 0.0
    
    # Category match bonus
    cat_match = 0.15 if cat_a and cat_b and cat_a.lower() == cat_b.lower() else 0.0
    
    # Composite score
    score = (0.45 * title_overlap) + (0.30 * doc_containment) + (0.15 * doc_jaccard) + cat_match
    return round(min(100.0, max(0.0, score * 100.0)), 1)

def calculate_location_similarity(loc_a: Optional[str], loc_b: Optional[str]) -> float:
    """Calculates location similarity based on campus points and token overlap."""
    if not loc_a or not loc_b:
        return 40.0
        
    toks_a = clean_and_tokenize(loc_a)
    toks_b = clean_and_tokenize(loc_b)
    
    if not toks_a or not toks_b:
        return 50.0
        
    if toks_a == toks_b:
        return 100.0
        
    # Remove location modifier words
    loc_modifiers = {"floor", "room", "section", "desk", "hall", "near", "outside", "inside", "bench", "stairs", "entrance"}
    core_a = {t for t in toks_a if t not in loc_modifiers}
    core_b = {t for t in toks_b if t not in loc_modifiers}
    
    if not core_a: core_a = toks_a
    if not core_b: core_b = toks_b
    
    core_overlap = core_a & core_b
    if core_overlap:
        # Both refer to the same main campus location (e.g. 'library' or 'canteen')
        return 95.0
        
    return 15.0

def calculate_date_similarity(date_lost_str: str, date_found_str: str) -> float:
    """
    Calculates date proximity score.
    Found items should be found on or after the lost date.
    """
    if not date_lost_str or not date_found_str:
        return 60.0
        
    def parse_dt(d_str: str) -> Optional[datetime]:
        formats = [
            "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
            "%d-%b-%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"
        ]
        cleaned = d_str.split("Z")[0].split("+")[0].strip()
        for fmt in formats:
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(cleaned)
        except Exception:
            return None

    dt_lost = parse_dt(date_lost_str)
    dt_found = parse_dt(date_found_str)
    
    if not dt_lost or not dt_found:
        return 70.0
        
    days_diff = (dt_found.date() - dt_lost.date()).days
    
    if days_diff >= 0:
        if days_diff == 0:
            return 100.0
        elif days_diff == 1:
            return 98.0
        elif days_diff <= 3:
            return 92.0
        elif days_diff <= 7:
            return 82.0
        elif days_diff <= 14:
            return 65.0
        elif days_diff <= 30:
            return 45.0
        else:
            return 25.0
    else:
        abs_diff = abs(days_diff)
        if abs_diff == 1:
            return 75.0
        elif abs_diff == 2:
            return 50.0
        else:
            return 15.0

def calculate_brand_color_similarity(brand_a: Optional[str], color_a: Optional[str],
                                     brand_b: Optional[str], color_b: Optional[str]) -> float:
    """Calculates Brand and Color composite similarity."""
    toks_ba = clean_and_tokenize(brand_a)
    toks_bb = clean_and_tokenize(brand_b)
    toks_ca = clean_and_tokenize(color_a)
    toks_cb = clean_and_tokenize(color_b)
    
    # Brand matching
    if toks_ba and toks_bb:
        if toks_ba & toks_bb:
            brand_score = 100.0
        else:
            brand_score = 15.0
    elif not toks_ba and not toks_bb:
        brand_score = 80.0
    else:
        brand_score = 75.0
        
    # Color matching
    if toks_ca and toks_cb:
        if toks_ca & toks_cb:
            color_score = 100.0
        else:
            matched_family = False
            for family_members in COLOR_FAMILIES.values():
                if (toks_ca & family_members) and (toks_cb & family_members):
                    color_score = 90.0
                    matched_family = True
                    break
            if not matched_family:
                color_score = 20.0
    elif not toks_ca and not toks_cb:
        color_score = 80.0
    else:
        color_score = 75.0
        
    return round((brand_score * 0.5) + (color_score * 0.5), 1)

def match_items(lost_item: Dict[str, Any], found_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compares a Lost item against a Found item and calculates multi-factor score.
    Returns composite score and detailed breakdown.
    """
    # 1. Text Similarity (Description, Title, Category)
    text_score = calculate_text_similarity(
        lost_item.get("title", ""),
        lost_item.get("description", ""),
        found_item.get("title", ""),
        found_item.get("description", ""),
        lost_item.get("category", ""),
        found_item.get("category", "")
    )
    
    # 2. Location Similarity
    loc_score = calculate_location_similarity(
        lost_item.get("location", ""),
        found_item.get("location", "")
    )
    
    # 3. Date Proximity
    date_score = calculate_date_similarity(
        lost_item.get("item_date", ""),
        found_item.get("item_date", "")
    )
    
    # 4. Brand & Color Similarity
    brand_color_score = calculate_brand_color_similarity(
        lost_item.get("brand", ""),
        lost_item.get("color", ""),
        found_item.get("brand", ""),
        found_item.get("color", "")
    )
    
    # 5. Image Similarity (Optional / Advanced)
    lost_features = lost_item.get("image_features")
    found_features = found_item.get("image_features")
    
    if isinstance(lost_features, str):
        try:
            lost_features = json.loads(lost_features)
        except Exception:
            lost_features = None
    if isinstance(found_features, str):
        try:
            found_features = json.loads(found_features)
        except Exception:
            found_features = None
            
    has_images = bool(lost_features and found_features and lost_features.get("valid") and found_features.get("valid"))
    
    image_score = None
    if has_images:
        image_score = compare_images(lost_features, found_features)
        # Weights with image: Description 30%, Location 20%, Date 15%, Brand/Color 15%, Image 20%
        overall = (
            (text_score * 0.30) +
            (loc_score * 0.20) +
            (date_score * 0.15) +
            (brand_color_score * 0.15) +
            (image_score * 0.20)
        )
    else:
        # Standard weights without image: Description 35%, Location 25%, Date 20%, Brand/Color 20%
        overall = (
            (text_score * 0.35) +
            (loc_score * 0.25) +
            (date_score * 0.20) +
            (brand_color_score * 0.20)
        )
        
    overall_score = round(min(100.0, max(0.0, overall)), 1)
    
    if overall_score >= 80.0:
        confidence = "high"
    elif overall_score >= 65.0:
        confidence = "moderate"
    elif overall_score >= 50.0:
        confidence = "low"
    else:
        confidence = "none"
        
    return {
        "overall_score": overall_score,
        "text_score": text_score,
        "location_score": loc_score,
        "date_score": date_score,
        "brand_color_score": brand_color_score,
        "image_score": image_score,
        "has_images": has_images,
        "confidence": confidence,
        "is_match": overall_score >= 50.0,
        "breakdown": {
            "Item Description": f"{text_score}%",
            "Location Proximity": f"{loc_score}%",
            "Date Similarity": f"{date_score}%",
            "Brand & Color": f"{brand_color_score}%",
            "Image Visual": f"{image_score}%" if image_score is not None else "N/A"
        }
    }
