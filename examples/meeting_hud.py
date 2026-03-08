import argparse
import asyncio
import os
import warnings
import tempfile
import wave
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Sequence, Union

from frame_utils import FrameDisplay, FrameUnicodeDisplay, compact_text, sleep_briefly


DEFAULT_DEMO_LINES = (
    "meeting hud ready",
    "朋友你好，会议现在开始",
    "行动项：本周完成 Frame 原型",
)
SubtitleDisplay = Union[FrameDisplay, FrameUnicodeDisplay]
UNICODE_LANGUAGE_HINTS = ("zh", "chinese", "ja", "japanese", "ko", "korean")


class FasterWhisperTranscriber:
    def __init__(
        self,
        model_name: str,
        language: Optional[str],
        device: str,
        compute_type: str,
        beam_size: int,
        task: str = "transcribe",
    ) -> None:
        from faster_whisper import WhisperModel

        self.language = language
        self.beam_size = beam_size
        self.task = task
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)

    def transcribe(self, audio_chunk) -> str:
        import numpy as np

        audio = audio_chunk
        if isinstance(audio_chunk, np.ndarray):
            audio = np.nan_to_num(audio_chunk.astype(np.float32, copy=False), nan=0.0, posinf=0.0, neginf=0.0)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            segments, _ = self.model.transcribe(
                audio,
                language=self.language,
                task=self.task,
                beam_size=self.beam_size,
                vad_filter=True,
                condition_on_previous_text=False,
            )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return " ".join(text.split())


class OpenAITextTranslator:
    def __init__(self, target_language: str, model: str) -> None:
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI translation mode")

        self.target_language = target_language
        self.model = model
        self.client = OpenAI(api_key=api_key)

    def translate(self, text: str, source_language: Optional[str]) -> str:
        source_label = source_language or "auto-detected"
        response = self.client.responses.create(
            model=self.model,
            instructions=(
                "You translate meeting subtitles. Return only the translated text, no notes, no quotes, no labels. "
                "Keep it concise and natural for heads-up-display subtitles."
            ),
            input=(
                f"Source language: {source_label}\n"
                f"Target language: {self.target_language}\n"
                f"Text: {text}"
            ),
            temperature=0,
            max_output_tokens=120,
        )
        translated = getattr(response, "output_text", "")
        if translated:
            return " ".join(translated.split())
        raise RuntimeError("OpenAI translation returned no text")


class PyannoteSpeakerDiarizer:
    def __init__(
        self,
        model_name: str,
        token_env: str,
        min_speaker_seconds: float,
    ) -> None:
        from pyannote.audio import Pipeline

        token = os.environ.get(token_env) or os.environ.get("HF_TOKEN")
        if not token:
            raise RuntimeError(f"{token_env} is required for pyannote speaker diarization")

        try:
            self.pipeline = Pipeline.from_pretrained(model_name, token=token)
        except TypeError:
            self.pipeline = Pipeline.from_pretrained(model_name, use_auth_token=token)

        self.min_speaker_seconds = min_speaker_seconds
        self.speaker_labels: Dict[str, str] = {}

    def label_audio(self, audio_chunk, samplerate: int) -> Optional[str]:
        wav_path = self._write_temp_wav(audio_chunk, samplerate)
        try:
            result = self.pipeline(wav_path)
        finally:
            Path(wav_path).unlink(missing_ok=True)

        diarization = getattr(result, "speaker_diarization", result)
        durations = self._speaker_durations(diarization)
        if not durations:
            return None

        dominant_speaker = max(durations, key=durations.get)
        if durations[dominant_speaker] < self.min_speaker_seconds:
            return None
        return self._label_for(dominant_speaker)

    def _write_temp_wav(self, audio_chunk, samplerate: int) -> str:
        import numpy as np

        clipped = np.clip(audio_chunk, -1.0, 1.0)
        pcm = (clipped * 32767).astype("int16")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            with wave.open(handle, "wb") as wav_handle:
                wav_handle.setnchannels(1)
                wav_handle.setsampwidth(2)
                wav_handle.setframerate(samplerate)
                wav_handle.writeframes(pcm.tobytes())
            return handle.name

    def _speaker_durations(self, diarization) -> Dict[str, float]:
        durations: Dict[str, float] = {}

        if hasattr(diarization, "itertracks"):
            iterable = ((turn, speaker) for turn, _, speaker in diarization.itertracks(yield_label=True))
        else:
            iterable = diarization

        for turn, speaker in iterable:
            start = getattr(turn, "start", 0.0)
            end = getattr(turn, "end", 0.0)
            durations[str(speaker)] = durations.get(str(speaker), 0.0) + max(0.0, end - start)

        return durations

    def _label_for(self, raw_speaker: str) -> str:
        if raw_speaker not in self.speaker_labels:
            self.speaker_labels[raw_speaker] = numeric_speaker_label(len(self.speaker_labels))
        return self.speaker_labels[raw_speaker]


def parse_audio_device(value: Optional[str]) -> Optional[Union[int, str]]:
    if value is None:
        return None
    stripped = value.strip()
    if stripped.isdigit():
        return int(stripped)
    return stripped


def compute_rms(audio_chunk) -> float:
    import numpy as np

    data = audio_chunk
    if getattr(data, "ndim", 1) > 1:
        data = data.mean(axis=1)
    squares = np.square(data.astype("float32"))
    if len(squares) == 0:
        return 0.0
    return float(np.sqrt(squares.mean()))


def normalize_audio(audio_chunk):
    if getattr(audio_chunk, "ndim", 1) > 1:
        return audio_chunk.mean(axis=1)
    return audio_chunk


def capture_audio_chunk(duration: float, samplerate: int, device: Optional[Union[int, str]]):
    import sounddevice as sd

    frames = int(duration * samplerate)
    return sd.rec(frames, samplerate=samplerate, channels=1, dtype="float32", device=device, blocking=True)


def list_audio_devices() -> None:
    import sounddevice as sd

    devices = sd.query_devices()
    for index, device in enumerate(devices):
        in_channels = device.get("max_input_channels", 0)
        out_channels = device.get("max_output_channels", 0)
        print(f"[{index}] in={in_channels} out={out_channels} {device['name']}")


def choose_demo_lines(raw_lines: Optional[str]) -> Sequence[str]:
    if not raw_lines:
        return DEFAULT_DEMO_LINES
    parts = [part.strip() for part in raw_lines.split("|")]
    lines = [part for part in parts if part]
    return lines or DEFAULT_DEMO_LINES


def choose_demo_translations(raw_lines: Optional[str]) -> Optional[Sequence[str]]:
    if not raw_lines:
        return None
    parts = [part.strip() for part in raw_lines.split("|")]
    lines = [part for part in parts if part]
    return lines or None


def choose_demo_speakers(raw_lines: Optional[str]) -> Optional[Sequence[str]]:
    if not raw_lines:
        return None
    parts = [part.strip() for part in raw_lines.split("|")]
    lines = [part for part in parts if part]
    return lines or None


def append_log(log_file: Optional[Path], line: str) -> None:
    if log_file is None:
        return
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {line}\n")


def language_prefers_unicode(language: Optional[str]) -> bool:
    if not language:
        return False
    lowered = language.lower()
    return any(hint in lowered for hint in UNICODE_LANGUAGE_HINTS)


def should_use_unicode(
    render_mode: str,
    language: Optional[str],
    target_language: Optional[str],
    font_family: Optional[str],
    sample_lines: Sequence[str],
) -> bool:
    if render_mode == "unicode":
        return True
    if render_mode == "plain":
        return False
    if font_family:
        return True
    if language_prefers_unicode(language) or language_prefers_unicode(target_language):
        return True
    return any(any(ord(char) > 127 for char in line) for line in sample_lines)


def build_display(args, sample_lines: Sequence[str]) -> SubtitleDisplay:
    if should_use_unicode(args.render_mode, args.language, args.translate_to, args.font_family, sample_lines):
        return FrameUnicodeDisplay(
            name=args.name,
            dry_run=args.dry_run,
            font_family=args.font_family,
            font_size=args.font_size,
            display_width=args.display_width,
            max_rows=args.max_rows,
        )
    return FrameDisplay(name=args.name, dry_run=args.dry_run)


def build_translator(provider: str, target_language: Optional[str]):
    if not target_language:
        return None

    chosen = provider
    if chosen == "auto":
        if target_language.lower() in ("en", "english"):
            return None
        chosen = "openai"

    if chosen == "whisper":
        if target_language.lower() not in ("en", "english"):
            raise ValueError("Whisper translation mode currently only supports English output")
        return None

    if chosen == "openai":
        return OpenAITextTranslator(target_language=target_language, model="gpt-4.1-mini")

    raise ValueError(f"Unsupported translation provider: {provider}")


def build_speaker_diarizer(mode: str, model_name: str, token_env: str, min_speaker_seconds: float):
    if mode == "none":
        return None
    if mode == "pyannote":
        return PyannoteSpeakerDiarizer(
            model_name=model_name,
            token_env=token_env,
            min_speaker_seconds=min_speaker_seconds,
        )
    raise ValueError(f"Unsupported speaker mode: {mode}")


def build_display_text(
    prefix: str,
    original: str,
    translated: Optional[str],
    bilingual: bool,
    speaker_label: Optional[str] = None,
) -> str:
    speaker_prefix = f"{speaker_label}: " if speaker_label else ""
    base = f"{prefix} {speaker_prefix}{original}".strip()
    if translated:
        if bilingual:
            return f"{base}\n{translated}".strip()
        return f"{prefix} {speaker_prefix}{translated}".strip()
    return base


def fit_for_display(display: SubtitleDisplay, text: str, limit: int) -> str:
    if isinstance(display, FrameUnicodeDisplay):
        return text
    return compact_text(text, limit)


def numeric_speaker_label(index: int) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if index < len(alphabet):
        return alphabet[index]
    return f"S{index + 1}"


async def maybe_translate(text: str, translator, source_language: Optional[str]) -> Optional[str]:
    if translator is None:
        return None
    return await asyncio.to_thread(translator.translate, text, source_language)


async def maybe_label_speaker(audio_chunk, samplerate: int, diarizer) -> Optional[str]:
    if diarizer is None:
        return None
    return await asyncio.to_thread(diarizer.label_audio, audio_chunk, samplerate)


async def run_demo(
    display: SubtitleDisplay,
    lines: Sequence[str],
    demo_translations: Optional[Sequence[str]],
    demo_speakers: Optional[Sequence[str]],
    prefix: str,
    x: int,
    y: int,
    limit: int,
    delay: float,
    log_file: Optional[Path],
    translator,
    source_language: Optional[str],
    bilingual: bool,
) -> None:
    await display.connect()
    try:
        for index, line in enumerate(lines):
            translated = None
            speaker_label = None

            if demo_speakers and index < len(demo_speakers):
                speaker_label = demo_speakers[index]

            if demo_translations and index < len(demo_translations):
                translated = demo_translations[index]
            elif translator is not None:
                translated = await maybe_translate(line, translator, source_language)

            display_text = build_display_text(prefix, line, translated, bilingual, speaker_label=speaker_label)
            rendered = fit_for_display(display, display_text, limit)
            print(f"[demo] {line}")
            if speaker_label:
                print(f"[speaker] {speaker_label}")
            if translated:
                print(f"[translation] {translated}")
            append_log(log_file, display_text)
            await display.show_text(rendered, x=x, y=y)
            await asyncio.sleep(delay)
    finally:
        await display.disconnect()


async def run_live(
    display: SubtitleDisplay,
    prefix: str,
    x: int,
    y: int,
    limit: int,
    duration: float,
    samplerate: int,
    device: Optional[Union[int, str]],
    min_rms: float,
    transcriber: FasterWhisperTranscriber,
    log_file: Optional[Path],
    translator,
    source_language: Optional[str],
    bilingual: bool,
    speaker_diarizer,
) -> None:
    last_sent = ""

    await display.connect()
    await display.show_text(fit_for_display(display, f"{prefix} listening...", limit), x=x, y=y)

    try:
        while True:
            audio_chunk = await asyncio.to_thread(capture_audio_chunk, duration, samplerate, device)
            rms = compute_rms(audio_chunk)
            print(f"[audio] rms={rms:.4f}")
            if rms < min_rms:
                continue

            normalized = normalize_audio(audio_chunk)
            speaker_label = await maybe_label_speaker(normalized, samplerate, speaker_diarizer)
            text = await asyncio.to_thread(transcriber.transcribe, normalized)
            if not text:
                continue

            translated = await maybe_translate(text, translator, source_language)
            display_text = build_display_text(prefix, text, translated, bilingual, speaker_label=speaker_label)
            if display_text == last_sent:
                continue

            print(f"[subtitle] {text}")
            if speaker_label:
                print(f"[speaker] {speaker_label}")
            if translated:
                print(f"[translation] {translated}")
            append_log(log_file, display_text)
            rendered = fit_for_display(display, display_text, limit)
            await display.show_text(rendered, x=x, y=y)
            last_sent = display_text
            await sleep_briefly()
    finally:
        await display.disconnect()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture microphone audio and mirror subtitles to Brilliant Labs Frame")
    parser.add_argument("--name", help="Optional BLE device name", default=None)
    parser.add_argument("--prefix", help="Optional display prefix", default="MEET")
    parser.add_argument("--x", type=int, default=1, help="Display x coordinate")
    parser.add_argument("--y", type=int, default=1, help="Display y coordinate")
    parser.add_argument("--limit", type=int, default=80, help="Maximum displayed characters per line")
    parser.add_argument("--dry-run", action="store_true", help="Print locally instead of connecting to Frame")
    parser.add_argument("--demo", action="store_true", help="Run a built-in subtitle demo instead of using the microphone")
    parser.add_argument("--demo-lines", help="Custom demo lines separated by |", default=None)
    parser.add_argument("--demo-translations", help="Optional demo translations separated by |", default=None)
    parser.add_argument("--demo-speakers", help="Optional demo speaker labels separated by |", default=None)
    parser.add_argument("--demo-delay", type=float, default=1.5, help="Delay between demo subtitle lines")
    parser.add_argument("--list-devices", action="store_true", help="List audio input devices and exit")
    parser.add_argument("--audio-device", help="Audio device index or name", default=None)
    parser.add_argument("--duration", type=float, default=4.0, help="Seconds captured per transcription chunk")
    parser.add_argument("--samplerate", type=int, default=16000, help="Audio sample rate")
    parser.add_argument("--min-rms", type=float, default=0.015, help="Silence threshold for microphone chunks")
    parser.add_argument("--model", default="base", help="faster-whisper model name, for example tiny, base, small")
    parser.add_argument("--language", default=None, help="Optional source language code such as en or zh")
    parser.add_argument("--device", default="auto", help="Whisper device, usually auto or cpu on macOS")
    parser.add_argument("--compute-type", default="int8", help="Whisper compute type, int8 is a good default on Mac mini")
    parser.add_argument("--beam-size", type=int, default=1, help="Whisper beam size")
    parser.add_argument("--log-file", help="Optional subtitle log file path", default=None)
    parser.add_argument(
        "--render-mode",
        choices=("auto", "plain", "unicode"),
        default="auto",
        help="Subtitle rendering mode. unicode uses the official text_sprite_block path for Chinese and other Unicode text",
    )
    parser.add_argument("--font-family", default=None, help="Optional font path for unicode rendering")
    parser.add_argument("--font-size", type=int, default=28, help="Unicode subtitle font size in pixels")
    parser.add_argument("--display-width", type=int, default=600, help="Unicode subtitle layout width")
    parser.add_argument("--max-rows", type=int, default=2, help="Maximum unicode subtitle rows displayed at once")
    parser.add_argument("--translate-to", default=None, help="Optional target language such as English or Chinese")
    parser.add_argument(
        "--translation-provider",
        choices=("auto", "whisper", "openai"),
        default="auto",
        help="Translation backend. whisper supports translation to English only; openai supports arbitrary target languages",
    )
    parser.add_argument("--bilingual", action="store_true", help="Show original and translated text together when translation is enabled")
    parser.add_argument(
        "--speaker-mode",
        choices=("none", "pyannote"),
        default="none",
        help="Optional speaker diarization backend. pyannote adds labels like A: and B: based on who spoke in the current chunk",
    )
    parser.add_argument(
        "--speaker-model",
        default="pyannote/speaker-diarization-community-1",
        help="Speaker diarization model name for pyannote",
    )
    parser.add_argument(
        "--speaker-token-env",
        default="HUGGINGFACE_TOKEN",
        help="Environment variable that stores the Hugging Face token for pyannote speaker diarization",
    )
    parser.add_argument(
        "--speaker-min-seconds",
        type=float,
        default=0.8,
        help="Minimum seconds a dominant speaker must occupy in the chunk before a label is shown",
    )
    return parser


async def async_main() -> None:
    args = build_parser().parse_args()

    if args.list_devices:
        list_audio_devices()
        return

    demo_lines = choose_demo_lines(args.demo_lines)
    demo_translations = choose_demo_translations(args.demo_translations)
    demo_speakers = choose_demo_speakers(args.demo_speakers)
    source_language = args.language

    translator = None if (args.demo and demo_translations is not None) else build_translator(args.translation_provider, args.translate_to)
    speaker_diarizer = None if args.demo else build_speaker_diarizer(
        args.speaker_mode,
        args.speaker_model,
        args.speaker_token_env,
        args.speaker_min_seconds,
    )
    whisper_task = "translate" if args.translate_to and args.translation_provider in ("auto", "whisper") and args.translate_to.lower() in ("en", "english") else "transcribe"

    preview_lines = list(demo_lines)
    if demo_translations:
        preview_lines.extend(demo_translations)
    if demo_speakers:
        preview_lines.extend(demo_speakers)
    if args.translate_to:
        preview_lines.append(args.translate_to)
    if args.prefix:
        preview_lines.append(args.prefix)

    display = build_display(args, preview_lines if args.demo or args.translate_to else ())
    log_file = Path(args.log_file).expanduser() if args.log_file else None
    mode_name = "unicode" if isinstance(display, FrameUnicodeDisplay) else "plain"
    print(f"[display] {mode_name}")
    if args.translate_to:
        provider_name = "whisper" if whisper_task == "translate" and translator is None else args.translation_provider
        print(f"[translation] {provider_name} -> {args.translate_to}")
        if args.demo and translator is None and whisper_task == "translate" and not demo_translations:
            print("[translation] demo mode previews layout only; live audio is needed for Whisper translation")
    if args.speaker_mode != "none":
        print(f"[speaker] {args.speaker_mode}")
        if args.demo and not demo_speakers:
            print("[speaker] demo mode previews layout only; use --demo-speakers to fake A/B labels")

    if args.demo:
        await run_demo(
            display=display,
            lines=demo_lines,
            demo_translations=demo_translations,
            demo_speakers=demo_speakers,
            prefix=args.prefix,
            x=args.x,
            y=args.y,
            limit=args.limit,
            delay=args.demo_delay,
            log_file=log_file,
            translator=translator,
            source_language=source_language,
            bilingual=args.bilingual,
        )
        return

    transcriber = FasterWhisperTranscriber(
        model_name=args.model,
        language=args.language,
        device=args.device,
        compute_type=args.compute_type,
        beam_size=args.beam_size,
        task=whisper_task,
    )

    await run_live(
        display=display,
        prefix=args.prefix,
        x=args.x,
        y=args.y,
        limit=args.limit,
        duration=args.duration,
        samplerate=args.samplerate,
        device=parse_audio_device(args.audio_device),
        min_rms=args.min_rms,
        transcriber=transcriber,
        log_file=log_file,
        translator=translator,
        source_language=source_language,
        bilingual=args.bilingual,
        speaker_diarizer=speaker_diarizer,
    )


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nMeeting HUD stopped.")


if __name__ == "__main__":
    main()
