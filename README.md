# CaptionLearn

CaptionLearn is a private local video-learning studio. A signed-in user uploads an English video clip, generates continuous timed subtitles, pauses to explore multiple keyword meanings or idioms on dedicated study cards, reviews content-safety flags, and exports either standard burned subtitles or a complete learning MP4 with a synchronized explanation sidebar.

## Features

- **Continuous Subtitles Everywhere**: Subtitle generation transcribes continuously through the full clip; dialogue is never interrupted or cut short when inappropriate words or emotional shouting are encountered.
- **Multiple Keyword Selection**: Automatically extracts key vocabulary from each subtitle line and provides interactive chips (`[Holly] [Guy] [Man] [Mike]`) to instantly switch definitions in the Pause & Learn card.
- **Clean Subtitle Video Overlay**: In-video captions are rendered in high-contrast Netflix style without distracting keyword highlights or underlines.
- **Complete MP4 Video Export (with Subtitle Explanation)**: One-click export burning both the synchronized bottom subtitles and the dedicated right-hand Pause & Learn explanation sidebar into a universal MP4 file.
- **Universal Format & Resolution Support**: Handles standard video formats (`.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`, `.m4v`, etc.) across any resolution (360p, 720p, 1080p, 4K) with proportional ASS scaling and resilient audio extraction.
- Fast, Balanced, and Best quality choices using local Whisper models.
- Meaning/Idiom starters in `glossary/en.json` and dictionary lookups with local WordNet. Content-review flags in `safety/en.json`.
- Private studio access: public visitors can browse the landing page; only signed-in registered users can access the studio, upload clips, generate captions, or download exports.


## Run on Windows

Open **Anaconda Prompt**:

```bat
conda activate voicefit-ai
cd "C:\Users\Admin\Documents\nlp_project\2026-09-19\project-auth"
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Keep the terminal open. FFmpeg must be available in PATH (the project also tries its detected path). The first use of an ASR model needs a download; cached models can run offline.

Copy `.env.example` to `.env` only if you want SMTP or OAuth. Do not commit `.env`.

## Accuracy and hardware

No speech recogniser is perfect. `fast` (base) is intended for quick CPU previews. `balanced` (small) is the normal choice but can take several minutes on a CPU. `best` (medium) needs considerably more memory and is slow on a CPU; use an NVIDIA GPU for practical longer clips. Tamil-English code-mixed speech, noise, music and unclear recordings need manual caption review.

## Evaluate ASR

Use a short, manually checked reference transcript:

```bat
python evaluate_asr.py --media sample.mp4 --reference reference.txt --language ta
```

The script prints Word Error Rate (WER), Character Error Rate (CER), and elapsed time for each installed quality model. Report measurements from your own clips rather than promising a fixed accuracy.

## Project files

- `main.py` – FastAPI routes, upload, captions, exports and ASR workflow.
- `captionlearn_addons.py` – CaptionLearn authentication, language configuration and migrations.
- `static/` – offline-first plain HTML, CSS and JavaScript interface.
- `glossary/` and `safety/` – editable language data.
- `evaluate_asr.py` – ASR evaluation helper.


## Set up email codes with Gmail

1. Turn on Google 2-Step Verification.
2. Create a Gmail **App Password** (do not use your normal Gmail password).
3. Copy `.env.example` to `.env` and set `APP_ENV=production`, `SMTP_USER`, `SMTP_PASSWORD`, and optionally `SMTP_FROM_NAME`.
4. Run `python tools/send_test_email.py your-address@example.com`, then check Inbox and Spam.

If SMTP is not configured and `APP_ENV=development`, CaptionLearn prints a code only to the server console and marks the response as development mode. Production mode returns HTTP 503 instead.

## Tamil meaning data

CaptionLearn looks for a saved correction, then curated glossary, then the optional local bilingual lexicon, then WordNet/IndoWordNet, before a machine-translation fallback. Build your own reviewed lexicon from a licence-compatible Wiktionary extract with `python tools/build_lexicon.py your-terms.tsv`. Keep the source attribution with the extract. Extend `tests/gold_meanings.csv` to at least 50 human-reviewed examples before reporting translation quality.
