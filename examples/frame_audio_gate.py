from dataclasses import dataclass
from typing import Optional


@dataclass
class AdaptiveRmsGate:
    minimum_rms: float
    alpha: float = 0.9
    multiplier: float = 2.5
    bias: float = 0.001
    noise_floor: Optional[float] = None

    def threshold(self) -> float:
        if self.noise_floor is None:
            return self.minimum_rms
        return max(self.minimum_rms, self.noise_floor * self.multiplier + self.bias)

    def observe(self, rms: float, voiced: bool) -> None:
        candidate = rms if not voiced else min(rms, self.threshold())
        if self.noise_floor is None:
            self.noise_floor = candidate
            return
        self.noise_floor = self.alpha * self.noise_floor + (1.0 - self.alpha) * candidate

    def should_transcribe(self, rms: float) -> bool:
        return rms >= self.threshold()
