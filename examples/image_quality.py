from dataclasses import dataclass
from io import BytesIO
from typing import Optional

import numpy as np
from PIL import Image


@dataclass
class ImageQualityReport:
    width: int
    height: int
    brightness_mean: float
    brightness_std: float
    laplacian_energy: float
    likely_blurry: bool
    likely_dark: bool
    likely_overexposed: bool

    def summary(self, locale: str = 'en') -> str:
        if locale == 'zh':
            flags = []
            if self.likely_blurry:
                flags.append('模糊')
            if self.likely_dark:
                flags.append('过暗')
            if self.likely_overexposed:
                flags.append('过曝')
            if not flags:
                flags.append('正常')
            return f"图像质量：{'、'.join(flags)}，亮度 {self.brightness_mean:.1f}，清晰度 {self.laplacian_energy:.1f}"

        flags = []
        if self.likely_blurry:
            flags.append('blurry')
        if self.likely_dark:
            flags.append('dark')
        if self.likely_overexposed:
            flags.append('overexposed')
        if not flags:
            flags.append('ok')
        return f"quality {'/'.join(flags)}, brightness {self.brightness_mean:.1f}, sharpness {self.laplacian_energy:.1f}"


def _laplacian_energy(gray: np.ndarray) -> float:
    center = gray[1:-1, 1:-1]
    lap = (
        gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:]
        - 4.0 * center
    )
    return float(np.mean(np.abs(lap))) if lap.size else 0.0


def analyze_image_bytes(image_bytes: bytes) -> ImageQualityReport:
    with Image.open(BytesIO(image_bytes)) as image:
        image.load()
        gray = np.asarray(image.convert('L'), dtype=np.float32)
        brightness_mean = float(gray.mean()) if gray.size else 0.0
        brightness_std = float(gray.std()) if gray.size else 0.0
        sharpness = _laplacian_energy(gray)
        return ImageQualityReport(
            width=image.width,
            height=image.height,
            brightness_mean=brightness_mean,
            brightness_std=brightness_std,
            laplacian_energy=sharpness,
            likely_blurry=sharpness < 4.0,
            likely_dark=brightness_mean < 35.0,
            likely_overexposed=brightness_mean > 220.0,
        )


def should_retry_capture(report: ImageQualityReport) -> bool:
    return report.likely_blurry or report.likely_dark or report.likely_overexposed
