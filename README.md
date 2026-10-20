# CaptionLearn 🎬📖
**English Video Subtitle & Vocabulary Learning Studio**

CaptionLearn is an AI-powered video learning platform that transforms spoken English dialogue into synchronized subtitles, provides interactive multi-keyword vocabulary and idiom explanations whenever you pause, flags sensitive language, and exports complete MP4 study videos with a dedicated learning sidebar.

---

## 🌟 Key Features

* **⚡ Continuous Subtitle Generation**: Powered by Faster-Whisper AI. Subtitles transcribe seamlessly from second `0.00` through to the end of the video without stopping or dropping dialogue during loud noise or shouting.
* **🎯 Interactive Keyword Selection**: Automatically extracts key vocabulary from every line of dialogue, allowing viewers to switch definitions using interactive keyword chips.
* **💬 Netflix-Style Captions**: Clean, high-contrast bottom subtitles formatted for readability without distracting highlights.
* **⏸️ Pause & Learn Cards**: Automatically surfaces 4-line WordNet dictionary definitions, parts of speech, and recognized English idioms whenever the video is paused.
* **🛡️ Content-Safety Annotations**: Automatically detects sensitive language and applies safety flags without interrupting video playback or subtitle generation.
* **📦 Complete MP4 Video Export**: One-click export that burns both the bottom synchronized subtitles and the right-hand Pause & Learn explanation sidebar into a universal MP4 file.
* **🎨 Modern SaaS Interface**: Deep obsidian-emerald and electric neon-mint dark theme with responsive controls across desktop, tablet, and mobile.
* **🔒 Private Studio Workspace**: Built-in user authentication and project isolation ensuring each user's videos and transcripts remain completely private.

---

## 🛠️ Tech Stack

* **Backend**: FastAPI, Uvicorn, Python 3.10+
* **AI & Speech Recognition**: Faster-Whisper (CTranslate2), OpenAI Whisper
* **Video & Audio Processing**: FFmpeg, Libass
* **NLP & Dictionaries**: NLTK WordNet
* **Frontend**: HTML5, Modern CSS3 (Glassmorphic Dark Theme), Vanilla JavaScript (ES6+)
* **Database**: SQLite3

---

## 🚀 Quick Start (Local Setup)

### 1. Prerequisites
* Python 3.10 or higher
* [FFmpeg](https://ffmpeg.org/download.html) installed and added to your system `PATH`

### 2. Clone the Repository
```bash
git clone https://github.com/<YOUR-USERNAME>/captionlearn.git
cd captionlearn
```

### 3. Create a Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Run the Server
```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser and navigate to: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🐳 Docker & Cloud Deployment

A production-ready `Dockerfile` is included in the root directory.

### Build and Run with Docker
```bash
docker build -t captionlearn .
docker run -p 8080:8080 captionlearn
```
Visit `http://localhost:8080` in your browser.

### Deploying to Cloud (Render / Google Cloud Run)
* **Render.com**: Connect your GitHub repository, choose **Docker** runtime, and select the **Free** instance type.
* **Google Cloud Run**:
  ```bash
  gcloud run deploy captionlearn \
    --source . \
    --region us-central1 \
    --platform managed \
    --allow-unauthenticated \
    --memory 4Gi \
    --cpu 2 \
    --timeout 600
  ```

---

## 📂 Project Structure

```text
├── main.py                     # FastAPI application & ASR processing routes
├── captionlearn_addons.py      # Authentication, verification, and API routing
├── Dockerfile                  # Container build file (Python, FFmpeg, Whisper)
├── .dockerignore               # Build exclusion rules
├── requirements.txt            # Python dependencies
├── static/                     # Frontend assets
│   ├── index.html              # Main single-page application markup
│   ├── styles.css              # Dark emerald & neon mint stylesheet
│   ├── app.js                  # Frontend logic & video synchronization
│   └── images/                 # SVGs and vector iconography
├── glossary/                   # English idioms and phrase starter data
├── safety/                     # Sensitive and inappropriate word filters
└── work/                       # Local project workspaces and SQLite database
```

---

## 📝 License
This project is open-source and available under the [MIT License](LICENSE).
