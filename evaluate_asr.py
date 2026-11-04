"""Measure CaptionLearn ASR quality against a manually checked transcript."""
import argparse
import time
from pathlib import Path

from jiwer import cer, wer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--media", required=True, help="Audio or video file")
    parser.add_argument("--reference", required=True, help="UTF-8 text transcript")
    parser.add_argument("--language", choices=("en", "ta"), default="en")
    parser.add_argument("--qualities", nargs="+", default=["fast", "balanced", "best"])
    args = parser.parse_args()

    import whisper
    reference = Path(args.reference).read_text(encoding="utf-8").strip()
    model_names = {"fast": "base", "balanced": "small", "best": "medium"}
    for quality in args.qualities:
        model_name = model_names[quality]
        started = time.perf_counter()
        model = whisper.load_model(model_name)
        result = model.transcribe(
            args.media, language=args.language, fp16=False, word_timestamps=True,
            beam_size=5, best_of=5, temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
            condition_on_previous_text=False, compression_ratio_threshold=2.4,
            logprob_threshold=-1.0, no_speech_threshold=0.6,
        )
        transcript = result.get("text", "").strip()
        elapsed = time.perf_counter() - started
        print(f"{quality:8} model={model_name:6} WER={wer(reference, transcript):.3f} CER={cer(reference, transcript):.3f} time={elapsed:.1f}s")
        print(f"  transcript: {transcript}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
