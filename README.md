# ☁️ Cloud-Based Lost & Found Matcher Using Image and Text Similarity

> An intelligent campus lost-and-found cloud platform featuring automated weighted multi-factor matching (TF-IDF text similarity, campus location intelligence, temporal decay window, brand/color normalization, and perceptual image hashing) deployed with **Supabase Cloud Database & Storage**.

---

## 🌟 Overview & Problem Statement

In universities, airports, and public facilities, conventional lost-and-found systems are passive CRUD bulletin boards where users have to manually scroll through hundreds of posts.

The **Cloud-Based Lost & Found Matcher** automates this by acting as an autonomous matching engine:
1. A student reports a **lost item** (e.g. *Black Samsung earbud case*, lost in College Library on 18-Aug-2026).
2. Another student or security guard reports a **found item** (e.g. *Black wireless-earbud case*, found outside library entrance).
3. The **Cloud Matching Engine** evaluates the reports across 5 distinct factors and calculates an overall correlation score (e.g., **91% Potential Match**).
4. Both parties receive automated match notifications and can initiate ownership verification and claims.

---

## 🏗️ System Architecture

```
                ┌───────────────────────────────┐
                │   Student / Admin Frontend    │
                │  (Responsive Glassmorphic UI) │
                └───────────────┬───────────────┘
                                │ REST API / Form Uploads
                                ▼
                ┌───────────────────────────────┐
                │       FastAPI Cloud App       │
                │     (Uvicorn ASGI Engine)     │
                └───────┬───────┬───────┬───────┘
                        │       │       │
       ┌────────────────┘       │       └────────────────┐
       ▼                        ▼                        ▼
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│  TF-IDF NLP  │         │   Perceptual │         │   Temporal   │
│ Text Vector  │         │  Image dHash │         │   Location   │
│ & Synonyms   │         │ & Color Hist │         │  Decay Model │
└──────┬───────┘         └──────┬───────┘         └──────┬───────┘
       └────────────────────────┼────────────────────────┘
                                ▼
                ┌───────────────────────────────┐
                │  Weighted Similarity Matrix   │
                │  (Score: 0.0% - 100.0%)       │
                └───────────────┬───────────────┘
                                │
        ┌───────────────────────┴───────────────────────┐
        ▼                                               ▼
┌──────────────────────────────┐        ┌──────────────────────────────┐
│   Supabase Cloud Database    │        │    Supabase Cloud Storage    │
│    (PostgreSQL 15 Engine)    │        │       (S3-compatible)        │
│   • users / profiles         │        │    • bucket: item-photos     │
│   • items (lost & found)     │        │    • public CDN URLs         │
│   • matches & audit logs     │        │                              │
│   • notifications & claims   │        │                              │
└──────────────────────────────┘        └──────────────────────────────┘
```

---

## 🧠 Matching Engine & Mathematical Scoring

When comparing a **Lost Report** $L$ and a **Found Report** $F$:

$$\text{Overall Match Score} = (W_t \cdot S_{\text{text}}) + (W_l \cdot S_{\text{location}}) + (W_d \cdot S_{\text{date}}) + (W_b \cdot S_{\text{brand/color}}) + (W_i \cdot S_{\text{image}})$$

### Factor Breakdown:

| Factor | Weight (With Photo) | Weight (No Photo) | Algorithm Applied |
| :--- | :---: | :---: | :--- |
| **Item Description & Title** | **30%** | **35%** | TF-IDF n-gram vectorization + Cosine Similarity + Token-level Jaccard overlap + Campus synonym clustering. |
| **Location Proximity** | **20%** | **25%** | Campus zone semantic mapping (e.g. *Library Reading Room* vs *Outside Library* match root zone *Library*). |
| **Date & Time Proximity** | **15%** | **20%** | Temporal decay window (Found on or after lost date: 0-1 days = 100%, 2-3 days = 92%, 4-7 days = 82%, 8-14 days = 65%). |
| **Brand & Color** | **15%** | **20%** | Exact brand string containment + Color Family dictionary mapping (e.g. *Navy* $\rightarrow$ *Blue*). |
| **Visual Image Match** | **20%** | *Dynamic N/A* | 64-bit difference hashing (dHash Hamming distance) + RGB Color distribution histogram cosine similarity. |

### Confidence Thresholds:
- **$\ge 80\%$**: 🟢 **High Confidence Match** $\rightarrow$ Triggers immediate alert notification to both parties.
- **$65\% - 79\%$**: 🟡 **Moderate Match** $\rightarrow$ Displayed in Match Explorer for review.
- **$50\% - 64\%$**: 🔵 **Low Similarity Candidate** $\rightarrow$ Available for administrator inspection.

---

## ☁️ Genuine Cloud Computing Features

This project demonstrates genuine cloud infrastructure:
1. **Cloud Relational Database (PostgreSQL)**: Fully hosted on **Supabase**, with schema tables, foreign key constraints, indexes, and Row Level Security (RLS).
2. **Cloud Object Storage**: S3-compatible cloud bucket (`item-photos`) storing uploaded lost and found photographs with CDN delivery.
3. **Dual Cloud-Native Hybrid Mode**: If Supabase credentials are not provided initially, the application falls back seamlessly to local SQLite and provides a **1-Click Sync Local Data to Supabase** button in the Admin dashboard!
4. **Cloud Container Deployment**: Includes production `Dockerfile`, `docker-compose.yml`, `render.yaml`, and `Procfile`.

---

## 🚀 Quick Start (Local Setup)

### 1. Prerequisites
- Python 3.10+ (Tested on Python 3.14)
- Web browser (Chrome, Firefox, Edge, Safari)

### 2. Install Dependencies
```bash
python -m pip install -r requirements.txt
```

### 3. Run Application Server
```bash
python run.py
```

Open your browser to:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

### 4. Demo Evaluation Accounts
The system automatically pre-seeds realistic student reports (Samsung earbuds, Wildcraft wallet, Milton bottle, Casio watch). You can sign in instantly using the **Quick Demo Login** button in the top navigation:
- **Student Account**: `rahul.sharma@campus.edu` / `Student@123`
- **Admin Account**: `admin@campus.edu` / `Admin@123`

---

## ☁️ Deploying to Supabase Cloud

### Step 1: Create a Free Supabase Project
1. Go to [supabase.com](https://supabase.com) and create a free project.
2. In the Supabase Dashboard, go to **SQL Editor**.
3. Copy the contents of [`supabase_schema.sql`](file:///supabase_schema.sql) and click **Run**.
4. In Supabase Dashboard, go to **Project Settings $\rightarrow$ API**. Copy:
   - **Project URL**
   - **anon / public key** or **service_role key**

### Step 2: Configure Environment Variables
Add your credentials to `.env`:
```env
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your-supabase-key
SUPABASE_BUCKET=item-photos
```

### Step 3: 1-Click Sync
Start your application and navigate to the **Admin Panel** $\rightarrow$ click **1-Click Sync Local Data to Supabase**. All sample reports, photos, and match scores will instantly push to your Supabase Cloud Database!

---

## 🌐 Deploying to Cloud Hosts (Render / Railway / Fly.io)

### Deploy to Render
1. Push this repository to GitHub.
2. In [Render Dashboard](https://dashboard.render.com), click **New + $\rightarrow$ Blueprint** and link your repository (Render automatically reads `render.yaml`).
3. Set your `SUPABASE_URL` and `SUPABASE_KEY` environment variables.
4. Click **Deploy**!

---

## 🧪 Interactive Live Simulator for Viva & Review

Visit the **Live Simulator 🧪** tab in the top navigation bar:
- Select one of the preset demonstration pairs (*Earbuds*, *Wallet*, *Water Bottle*).
- Click **Compute Multi-Factor Match Score**.
- Observe the real-time breakdown of TF-IDF Cosine Similarity, Location Proximity, Date Temporal Proximity, and Brand/Color composite scores!
