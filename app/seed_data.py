import os
from pathlib import Path
from PIL import Image, ImageDraw
from app.config import settings
from app.database import (
    create_user, get_user_by_email, create_item, list_items
)
from app.auth import hash_password
from app.image_utils import extract_image_features
from app.match_engine import rerun_all_matches

def create_sample_item_image(filename: str, color_rgb: tuple, text_label: str) -> Path:
    """Generates a clean representative item icon/image with Pillow."""
    img_dir = settings.UPLOAD_DIR
    img_dir.mkdir(parents=True, exist_ok=True)
    out_path = img_dir / filename
    
    if not out_path.exists():
        img = Image.new("RGB", (320, 320), color=(245, 247, 250))
        draw = ImageDraw.Draw(img)
        
        # Draw background rounded rectangle card
        draw.rounded_rectangle([(20, 20), (300, 300)], radius=24, fill=color_rgb, outline=(200, 200, 200), width=2)
        
        # Draw inner decorative element
        draw.rounded_rectangle([(50, 50), (270, 270)], radius=16, fill=(255, 255, 255, 128), outline=color_rgb, width=4)
        
        # Save
        img.save(out_path, "JPEG", quality=90)
        
    return out_path

def seed_database_if_empty():
    """Initializes standard demonstration users, items, and matches if database is fresh."""
    existing_items = list_items()
    if len(existing_items) > 0:
        return # Already seeded
        
    print("[Seed] Seeding sample users and campus lost-and-found items...")
    
    # 1. Create Users
    admin_user = get_user_by_email("admin@campus.edu")
    if not admin_user:
        admin_user = create_user(
            name="Campus Administrator",
            email="admin@campus.edu",
            password_hash=hash_password("Admin@123"),
            role="admin",
            phone="+91 98765 43210"
        )
        
    student_rahul = get_user_by_email("rahul.sharma@campus.edu")
    if not student_rahul:
        student_rahul = create_user(
            name="Rahul Sharma",
            email="rahul.sharma@campus.edu",
            password_hash=hash_password("Student@123"),
            role="student",
            student_id="CS-2026-042",
            phone="+91 98111 22334"
        )
        
    student_priya = get_user_by_email("priya.patel@campus.edu")
    if not student_priya:
        student_priya = create_user(
            name="Priya Patel",
            email="priya.patel@campus.edu",
            password_hash=hash_password("Student@123"),
            role="student",
            student_id="EC-2026-108",
            phone="+91 98222 33445"
        )
        
    student_ananya = get_user_by_email("ananya.sen@campus.edu")
    if not student_ananya:
        student_ananya = create_user(
            name="Ananya Sen",
            email="ananya.sen@campus.edu",
            password_hash=hash_password("Student@123"),
            role="student",
            student_id="IT-2026-077",
            phone="+91 98333 44556"
        )
        
    student_vikram = get_user_by_email("vikram.singh@campus.edu")
    if not student_vikram:
        student_vikram = create_user(
            name="Vikram Singh",
            email="vikram.singh@campus.edu",
            password_hash=hash_password("Student@123"),
            role="student",
            student_id="ME-2026-019",
            phone="+91 98444 55667"
        )

    # 2. Generate representative photos
    earbud_lost_img = create_sample_item_image("samsung_earbuds_lost.jpg", (30, 30, 30), "Earbuds")
    earbud_found_img = create_sample_item_image("wireless_earbuds_found.jpg", (35, 35, 35), "Earbuds")
    
    wallet_lost_img = create_sample_item_image("wildcraft_wallet_lost.jpg", (120, 53, 15), "Wallet")
    wallet_found_img = create_sample_item_image("brown_wallet_found.jpg", (115, 50, 12), "Wallet")
    
    bottle_lost_img = create_sample_item_image("milton_bottle_lost.jpg", (37, 99, 235), "Bottle")
    bottle_found_img = create_sample_item_image("milton_bottle_found.jpg", (30, 90, 220), "Bottle")
    
    watch_lost_img = create_sample_item_image("casio_watch_lost.jpg", (45, 45, 45), "Watch")
    watch_found_img = create_sample_item_image("casio_watch_found.jpg", (40, 40, 40), "Watch")
    
    # Extract image features
    feat_eb_lost = extract_image_features(earbud_lost_img)
    feat_eb_found = extract_image_features(earbud_found_img)
    
    feat_wal_lost = extract_image_features(wallet_lost_img)
    feat_wal_found = extract_image_features(wallet_found_img)
    
    feat_bot_lost = extract_image_features(bottle_lost_img)
    feat_bot_found = extract_image_features(bottle_found_img)
    
    feat_wat_lost = extract_image_features(watch_lost_img)
    feat_wat_found = extract_image_features(watch_found_img)

    # 3. Create Pair 1: Samsung Earbuds (From User Request)
    create_item(
        user_id=student_rahul["id"],
        user_name=student_rahul["name"],
        user_email=student_rahul["email"],
        item_type="lost",
        category="electronics",
        title="Black Samsung Earbud Case",
        brand="Samsung",
        color="Black",
        location="College Library 2nd Floor",
        item_date="2026-08-18",
        description="Black matte Samsung Galaxy Buds case with small scratch on the hinge. Lost near library reading section.",
        image_url="/uploads/samsung_earbuds_lost.jpg",
        image_hash=feat_eb_lost.get("dhash", ""),
        image_features=feat_eb_lost
    )
    
    create_item(
        user_id=student_priya["id"],
        user_name=student_priya["name"],
        user_email=student_priya["email"],
        item_type="found",
        category="electronics",
        title="Black Wireless-Earbud Case",
        brand="Samsung",
        color="Black",
        location="Outside College Library",
        item_date="2026-08-18",
        description="Black wireless earbud charging case found on the bench right outside the library entrance stairs.",
        image_url="/uploads/wireless_earbuds_found.jpg",
        image_hash=feat_eb_found.get("dhash", ""),
        image_features=feat_eb_found,
        safekeeping_location="Library Front Reception Desk"
    )

    # 4. Create Pair 2: Wildcraft Wallet (From User Request)
    create_item(
        user_id=student_ananya["id"],
        user_name=student_ananya["name"],
        user_email=student_ananya["email"],
        item_type="lost",
        category="wallets",
        title="Wildcraft Leather Wallet",
        brand="Wildcraft",
        color="Brown",
        location="College Library",
        item_date="2026-08-18",
        description="Brown leather wallet with three cards, metro pass, and college ID card inside.",
        image_url="/uploads/wildcraft_wallet_lost.jpg",
        image_hash=feat_wal_lost.get("dhash", ""),
        image_features=feat_wal_lost
    )
    
    create_item(
        user_id=student_vikram["id"],
        user_name=student_vikram["name"],
        user_email=student_vikram["email"],
        item_type="found",
        category="wallets",
        title="Brown Wallet",
        brand="Wildcraft",
        color="Brown",
        location="Library Reading Section",
        item_date="2026-08-18",
        description="Brown wallet found near reading section desk 14. Handed over to library security with cards intact.",
        image_url="/uploads/brown_wallet_found.jpg",
        image_hash=feat_wal_found.get("dhash", ""),
        image_features=feat_wal_found,
        safekeeping_location="Central Security Office"
    )

    # 5. Create Pair 3: Milton Water Bottle (From User Request)
    create_item(
        user_id=student_rahul["id"],
        user_name=student_rahul["name"],
        user_email=student_rahul["email"],
        item_type="lost",
        category="accessories",
        title="Blue Water Bottle",
        brand="Milton",
        color="Blue",
        location="College Canteen",
        item_date="2026-08-19",
        description="Blue insulated Milton steel water bottle 750ml, has a small anime sticker near the cap.",
        image_url="/uploads/milton_bottle_lost.jpg",
        image_hash=feat_bot_lost.get("dhash", ""),
        image_features=feat_bot_lost
    )
    
    create_item(
        user_id=student_ananya["id"],
        user_name=student_ananya["name"],
        user_email=student_ananya["email"],
        item_type="found",
        category="accessories",
        title="Blue Milton Bottle",
        brand="Milton",
        color="Blue",
        location="Canteen Food Court",
        item_date="2026-08-19",
        description="Blue Milton bottle left on the table near the juice counter in the canteen.",
        image_url="/uploads/milton_bottle_found.jpg",
        image_hash=feat_bot_found.get("dhash", ""),
        image_features=feat_bot_found,
        safekeeping_location="Canteen Cashier Counter"
    )

    # 6. Create Pair 4: Casio Watch (From User Request)
    create_item(
        user_id=student_priya["id"],
        user_name=student_priya["name"],
        user_email=student_priya["email"],
        item_type="lost",
        category="accessories",
        title="Casio Wrist Watch",
        brand="Casio",
        color="Black",
        location="College Auditorium",
        item_date="2026-08-20",
        description="Black Casio digital chronograph wrist watch with resin band, lost during the annual symposium.",
        image_url="/uploads/casio_watch_lost.jpg",
        image_hash=feat_wat_lost.get("dhash", ""),
        image_features=feat_wat_lost
    )
    
    create_item(
        user_id=student_vikram["id"],
        user_name=student_vikram["name"],
        user_email=student_vikram["email"],
        item_type="found",
        category="accessories",
        title="Casio Watch",
        brand="Casio",
        color="Black",
        location="Auditorium Hall B",
        item_date="2026-08-20",
        description="Black Casio watch found under row 4 seats after the morning session.",
        image_url="/uploads/casio_watch_found.jpg",
        image_hash=feat_wat_found.get("dhash", ""),
        image_features=feat_wat_found,
        safekeeping_location="Dean Student Welfare Office"
    )

    # 7. Run initial matching engine calculation
    count = rerun_all_matches()
    print(f"[Seed] Successfully seeded demo data and generated {count} candidate matches!")
