from typing import Optional

import numpy as np


def pcm_bytes_to_float32(pcm_bytes: bytes) -> np.ndarray:
    samples = np.frombuffer(pcm_bytes, dtype='<i2').astype(np.float32)
    return samples / 32768.0


def compute_rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples))))


def linear_resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or samples.size == 0:
        return samples.astype(np.float32, copy=False)
    x_old = np.arange(samples.size, dtype=np.float32)
    x_new = np.linspace(0, samples.size - 1, int(samples.size * target_rate / source_rate), dtype=np.float32)
    return np.interp(x_new, x_old, samples).astype(np.float32)


def preprocess_for_whisper(
    samples: np.ndarray,
    sample_rate: int,
    trim_leading_seconds: float = 0.25,
    target_sample_rate: int = 16000,
    remove_dc: bool = True,
    clip_peak: float = 0.95,
) -> np.ndarray:
    audio = samples.astype(np.float32, copy=False)

    trim_samples = int(trim_leading_seconds * sample_rate)
    if trim_samples > 0 and audio.size > trim_samples:
        audio = audio[trim_samples:]

    if remove_dc and audio.size:
        audio = audio - np.mean(audio)

    if clip_peak is not None:
        audio = np.clip(audio, -clip_peak, clip_peak)

    audio = linear_resample(audio, sample_rate, target_sample_rate)
    return audio.astype(np.float32, copy=False)
