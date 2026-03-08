import argparse
import asyncio
from pathlib import Path

from frame_audio_utils import compute_rms, pcm_bytes_to_float32, preprocess_for_whisper
from frame_mic_test import record_from_frame
from meeting_hud import FasterWhisperTranscriber


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe the Frame microphone path and report recording quality")
    parser.add_argument("--name", help="Optional BLE device name such as 'Frame EF'", default=None)
    parser.add_argument("--duration", type=float, default=4.0, help="Seconds to record from the Frame microphone")
    parser.add_argument("--output", default="./captures/frame_audio_probe.wav", help="Path to save the WAV recording")
    parser.add_argument("--sample-rate", type=int, default=8000, help="PCM sample rate used by the Frame audio module")
    parser.add_argument("--bits-per-sample", type=int, default=16, help="PCM bit depth used by the Frame audio module")
    parser.add_argument("--transcribe", action="store_true", help="Run faster-whisper on the recorded audio")
    parser.add_argument("--model", default="base", help="faster-whisper model name")
    parser.add_argument("--language", default=None, help="Optional spoken language code such as en or zh")
    parser.add_argument("--device", default="auto", help="Whisper device, usually auto or cpu on macOS")
    parser.add_argument("--compute-type", default="int8", help="Whisper compute type")
    parser.add_argument("--beam-size", type=int, default=1, help="Whisper beam size")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without talking to Frame")
    parser.add_argument("--trim-leading", type=float, default=0.25, help="Seconds trimmed from the start before Whisper preprocessing")
    return parser


def preflight(args) -> None:
    if args.transcribe:
        try:
            import faster_whisper  # noqa: F401
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Missing dependency: faster-whisper. Install it with: pip install -r requirements-meeting.txt"
            ) from exc


async def async_main() -> None:
    args = build_parser().parse_args()
    if args.dry_run:
        print(f"Would record {args.duration:.1f}s from {args.name or 'Frame'} to {Path(args.output).expanduser()}")
        if args.transcribe:
            print(f"Would also transcribe with model={args.model}")
        return

    preflight(args)
    output_path = await record_from_frame(args)
    wav_bytes = output_path.read_bytes()
    pcm_bytes = wav_bytes[44:]
    samples = pcm_bytes_to_float32(pcm_bytes)
    rms = compute_rms(samples)
    duration_seconds = len(pcm_bytes) / (args.sample_rate * (args.bits_per_sample // 8))

    print(f"[frame-audio-probe] wav={output_path}")
    print(f"[frame-audio-probe] bytes={len(pcm_bytes)} duration={duration_seconds:.2f}s rms={rms:.4f}")

    if args.transcribe:
        transcriber = FasterWhisperTranscriber(
            model_name=args.model,
            language=args.language,
            device=args.device,
            compute_type=args.compute_type,
            beam_size=args.beam_size,
            task="transcribe",
        )
        whisper_audio = preprocess_for_whisper(samples, args.sample_rate, trim_leading_seconds=args.trim_leading)
        text = await asyncio.to_thread(transcriber.transcribe, whisper_audio)
        print(f"[frame-audio-probe] transcript={text or '<empty>'}")


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nFrame audio probe stopped.")


if __name__ == "__main__":
    main()
