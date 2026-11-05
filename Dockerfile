FROM python:3.10-slim

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency specifications and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download and extract NLTK corpora to eliminate runtime zipfile decompression locks
RUN python -c "import nltk, zipfile, os; nltk.download('wordnet', quiet=True); nltk.download('omw-1.4', quiet=True); nltk.download('averaged_perceptron_tagger_eng', quiet=True); nltk.download('averaged_perceptron_tagger', quiet=True); nltk.download('punkt', quiet=True); nltk.download('punkt_tab', quiet=True); [zipfile.ZipFile(os.path.join(p, 'corpora', z)).extractall(os.path.join(p, 'corpora')) for p in nltk.data.path if os.path.exists(os.path.join(p, 'corpora')) for z in ['wordnet.zip', 'omw-1.4.zip'] if os.path.exists(os.path.join(p, 'corpora', z))]" 

# Pre-download both tiny.en and base.en faster-whisper models into the image for zero-wait startup
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('tiny.en', device='cpu', compute_type='int8'); WhisperModel('base.en', device='cpu', compute_type='int8')"

# Copy application code
COPY . .

# Ensure work directory exists
RUN mkdir -p /app/work/captionlearn-projects

# Default port for Google Cloud Run is 8080
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
