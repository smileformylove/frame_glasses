import argparse
import asyncio
from pathlib import Path

import numpy as np

from frame_audio_probe import preflight as probe_preflight
from frame_audio_profile import DEFAULT_PROFILE_PATH, save_profile
from frame_audio_utils import compute_rms, pcm_bytes_to_float32, preprocess_for_whisper
from frame_mic_test import record_from_frame
from meeting_hud import FasterWhisperTranscriber


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record from the Frame microphone and recommend transcription settings")
    parser.add_argument("--name", help="Optional BLE device name such as 'Frame EF'", default=None)
    parser.add_argument("--duration", type=float, default=6.0, help="Seconds to record from the Frame microphone")
    parser.add_argument("--output", default="./captures/frame_audio_calibrate.wav", help="Path to save the WAV recording")
    parser.add_argument("--sample-rate", type=int, default=8000, help="PCM sample rate used by the Frame audio module")
    parser.add_argument("--bits-per-sample", type=int, default=16, help="PCM bit depth used by the Frame audio module")
    parser.add_argument("--window-seconds", type=float, default=0.25, help="Window size for RMS analysis")
    parser.add_argument("--transcribe-preview", action="store_true", help="Run a short transcription preview on the cleaned audio")
    parser.add_argument("--model", default="base", help="faster-whisper model name")
    parser.add_argument("--language", default=None, help="Optional spoken language code such as en or zh")
    parser.add_argument("--device", default="auto", help="Whisper device, usually auto or cpu on macOS")
    parser.add_argument("--compute-type", default="int8", help="Whisper compute type")
    parser.add_argument("--beam-size", type=int, default=1, help="Whisper beam size")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without talking to Frame")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE_PATH), help="Path to the saved audio profile store")
    parser.add_argument("--save-profile", action="store_true", help="Save the suggested settings into the audio profile store")
    return parser


def percentile(values: np.ndarray, q: float) -> float:
    if values.size == 0:
        return 0.0
    return float(np.percentile(values, q))


def suggest_min_rms(rms_values: np.ndarray) -> float:
    if rms_values.size == 0:
        return 0.01
    floor = percentile(rms_values, 20)
    peak = percentile(rms_values, 90)
    suggestion = max(0.003, min(0.08, floor + (peak - floor) * 0.20))
    return float(round(suggestion, 4))


def analyze_windows(samples: np.ndarray, sample_rate: int, window_seconds: float) -> np.ndarray:
    window = max(1, int(sample_rate * window_seconds))
    values = []
    for start in range(0, len(samples), window):
        chunk = samples[start:start + window]
        if chunk.size == 0:
            continue
        values.append(compute_rms(chunk))
    return np.array(values, dtype=np.float32)


async def async_main() -> None:
    args = build_parser().parse_args()
    if args.dry_run:
        print(f"Would calibrate Frame microphone for {args.duration:.1f}s on {args.name or 'Frame'}")
        return

    if args.transcribe_preview:
        probe_preflight(argparse.Namespace(transcribe=True))

    output_path = await record_from_frame(args)
    wav_bytes = output_path.read_bytes()
    pcm_bytes = wav_bytes[44:]
    samples = pcm_bytes_to_float32(pcm_bytes)
    rms_values = analyze_windows(samples, args.sample_rate, args.window_seconds)

    print(f"[frame-audio-calibrate] wav={output_path}")
    print(f"[frame-audio-calibrate] duration={len(pcm_bytes) / (args.sample_rate * (args.bits_per_sample // 8)):.2f}s")
    print(f"[frame-audio-calibrate] rms_min={float(rms_values.min()) if rms_values.size else 0.0:.4f}")
    print(f"[frame-audio-calibrate] rms_p20={percentile(rms_values, 20):.4f}")
    print(f"[frame-audio-calibrate] rms_p50={percentile(rms_values, 50):.4f}")
    print(f"[frame-audio-calibrate] rms_p90={percentile(rms_values, 90):.4f}")
    suggested_min_rms = suggest_min_rms(rms_values)
    suggested_trim_leading = 0.25
    print(f"[frame-audio-calibrate] suggested_min_rms={suggested_min_rms:.4f}")
    print(f"[frame-audio-calibrate] suggested_trim_leading={suggested_trim_leading}")

    if args.save_profile and args.name:
        save_profile(Path(args.profile).expanduser(), args.name, {
            'min_rms': suggested_min_rms,
            'trim_leading': suggested_trim_leading,
            'sample_rate': args.sample_rate,
            'language': args.language,
            'adaptive_rms': True,
            'adaptive_alpha': 0.9,
            'adaptive_multiplier': 2.5,
            'adaptive_bias': 0.001,
        })
        print(f"[frame-audio-calibrate] saved_profile={Path(args.profile).expanduser()} name={args.name}")

    if args.transcribe_preview:
        cleaned = preprocess_for_whisper(samples, args.sample_rate, trim_leading_seconds=0.25)
        transcriber = FasterWhisperTranscriber(
            model_name=args.model,
            language=args.language,
            device=args.device,
            compute_type=args.compute_type,
            beam_size=args.beam_size,
            task="transcribe",
        )
        text = await asyncio.to_thread(transcriber.transcribe, cleaned)
        print(f"[frame-audio-calibrate] preview_transcript={text or '<empty>'}")


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nFrame audio calibration stopped.")


if __name__ == "__main__":
    main()
