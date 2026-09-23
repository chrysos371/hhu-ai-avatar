"""口型同步：自研元音驱动（复现 wLipSync 思路，Python 实现）。

思路（对齐 AIRI 的 wLipSync）：
1. 音频分帧，用 LPC 提取前两个共振峰 F1/F2
2. 共振峰在元音四边形中定位元音（A/E/I/O/U）
3. 元音 → 张嘴幅度（A 最大，U 最小），叠加音量包络加权
4. 静音检测 → 闭嘴；长句强制自然停顿闭嘴；移动平均平滑

与 AIRI 的差异：本方案基于声学共振峰，可解释、无模型依赖，
并可扩展中文元音与声调。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..utils.audio import frame_signal

# 元音 → 张嘴幅度（0-1）
_VOWEL_MOUTH = {"a": 1.0, "o": 0.6, "e": 0.5, "i": 0.3, "u": 0.35}


@dataclass
class LipSyncFrame:
    """单帧口型参数。"""

    time: float       # 帧起始时间（秒）
    mouth_open: float  # 张嘴幅度 0~1
    vowel: str         # 当前元音（静音为 ""）
    energy: float      # 归一化能量 0~1


def _lpc(signal: np.ndarray, order: int) -> np.ndarray:
    """用 Levinson-Durbin 递归求 LPC 系数，返回预测误差滤波器系数（含 a[0]=1）。"""
    n = len(signal)
    # 自相关
    r = np.zeros(order + 1)
    for k in range(order + 1):
        r[k] = float(np.dot(signal[: n - k], signal[k:])) if k < n else 0.0
    r = r / (r[0] + 1e-10)

    a = np.zeros(order + 1)
    a[0] = 1.0
    e = r[0]
    for i in range(1, order + 1):
        acc = r[i]
        for j in range(1, i):
            acc += a[j] * r[i - j]
        k = -acc / e
        if abs(k) >= 1.0:  # 数值保护
            k = 0.0
        new_a = a.copy()
        for j in range(1, i):
            new_a[j] = a[j] + k * a[i - j]
        new_a[i] = k
        a = new_a
        e *= 1.0 - k * k
        if e < 1e-12:
            e = 1e-12
    return a


def _formants(
    a: np.ndarray, sr: int, n_fft: int = 512, min_f: float = 200.0, max_f: float = 4000.0
) -> np.ndarray:
    """从 LPC 系数求共振峰频率（Hz）。共振峰 = |A(e^jw)| 的局部极小。"""
    w = np.linspace(0.0, np.pi, n_fft)
    A = np.zeros(n_fft, dtype=np.complex128)
    for k, ak in enumerate(a):
        A += ak * np.exp(-1j * k * w)
    amp = np.abs(A)
    local_min = (amp[1:-1] < amp[:-2]) & (amp[1:-1] <= amp[2:])
    idx = np.where(local_min)[0] + 1
    freqs = w[idx] / (2.0 * np.pi) * sr
    freqs = freqs[(freqs > min_f) & (freqs < max_f)]
    return np.sort(freqs)


def _classify_vowel(f1: float | None, f2: float | None) -> str | None:
    """根据 F1/F2 判定元音（简化的元音四边形规则）。"""
    if f1 is None or f2 is None:
        return None
    if f1 > 600:            # 低舌位 → a
        return "a"
    if f2 > 2000:           # 高 F2 → i 或 e
        return "i" if f1 < 400 else "e"
    if f2 < 1000:           # 低 F2 → u 或 o
        return "u" if f1 < 450 else "o"
    return "e"


class LipSyncEngine:
    """自研元音驱动口型同步引擎。"""

    def __init__(
        self,
        frame_ms: float = 25.0,
        hop_ms: float = 10.0,
        silence_ratio: float = 0.05,
        smooth: int = 3,
        close_every: float = 0.3,  # 长句每间隔多少秒强制自然闭嘴
    ):
        self.frame_ms = frame_ms
        self.hop_ms = hop_ms
        self.silence_ratio = silence_ratio
        self.smooth = smooth
        self.close_every = close_every

    def analyze(self, samples: np.ndarray, sr: int) -> list[LipSyncFrame]:
        """分析音频，返回逐帧口型参数序列。"""
        if len(samples) == 0:
            return []

        frames = frame_signal(samples, self.frame_ms, self.hop_ms, sr)
        n = len(frames)
        if n == 0:
            return []

        times = np.arange(n) * self.hop_ms / 1000.0
        # 能量（RMS）与静音判定
        energy = np.sqrt(np.mean(frames**2, axis=1) + 1e-12)
        peak = energy.max() if energy.size else 0.0
        energy_norm = energy / (peak + 1e-12)
        silence = energy < peak * self.silence_ratio

        order = min(2 + sr // 1000, 24)
        mouth = np.zeros(n, dtype=np.float64)
        vowels: list[str] = [""] * n

        for i in range(n):
            if silence[i]:
                mouth[i] = 0.0
                continue
            a = _lpc(frames[i], order)
            fs = _formants(a, sr)
            f1 = float(fs[0]) if len(fs) > 0 else None
            f2 = float(fs[1]) if len(fs) > 1 else None
            v = _classify_vowel(f1, f2)
            if v is None:
                mouth[i] = 0.2 * float(energy_norm[i])
                continue
            vowels[i] = v
            # 张嘴幅度 = 元音基础幅度 × (音量加权)
            mouth[i] = _VOWEL_MOUTH[v] * (0.4 + 0.6 * float(energy_norm[i]))

        # 移动平均平滑
        if self.smooth > 1 and n > self.smooth:
            kernel = np.ones(self.smooth) / self.smooth
            mouth = np.convolve(mouth, kernel, mode="same")

        # 长句强制自然闭嘴：每 close_every 秒，若正在张嘴则插入短暂闭合
        hop = int(sr * self.hop_ms / 1000)
        close_every_frames = max(1, int(self.close_every * sr / hop))
        for i in range(close_every_frames, n, close_every_frames):
            if mouth[i] > 0.3:
                mouth[i] = 0.05

        mouth = np.clip(mouth, 0.0, 1.0)
        return [
            LipSyncFrame(
                time=float(times[i]),
                mouth_open=float(mouth[i]),
                vowel=vowels[i],
                energy=float(energy_norm[i]),
            )
            for i in range(n)
        ]
