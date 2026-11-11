"""口型同步：自研元音驱动（复现 wLipSync 思路，Python 实现）。

思路（对齐 AIRI 的 wLipSync）：
1. 音频分帧，用 LPC 提取前两个共振峰 F1/F2
2. 共振峰在元音四边形中定位元音（A/E/I/O/U）
3. 元音 → 张嘴幅度（A 最大，U 最小），叠加音量包络加权
4. 静音检测 → 闭嘴；移动平均平滑；可选装饰性周期闭口（默认关闭）

与 AIRI 的差异：本方案基于声学共振峰，可解释、无模型依赖，
并可扩展中文元音与声调。
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from ..utils.audio import frame_signal

# 元音 → 张嘴幅度（0-1）
_VOWEL_MOUTH = {"a": 1.0, "o": 0.6, "e": 0.5, "i": 0.3, "u": 0.35}


def _finite_number(value):
    return (isinstance(value, (int, float, np.integer, np.floating))
            and not isinstance(value, (bool, np.bool_)) and np.isfinite(value))


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


@lru_cache(maxsize=8)
def _formant_basis(n_fft: int, coefficient_count: int):
    """Bounded immutable geometry; retain the legacy accumulation order."""
    w = np.linspace(0.0, np.pi, n_fft)
    w.setflags(write=False)
    basis = []
    for k in range(coefficient_count):
        values = np.exp(-1j * k * w)
        values.setflags(write=False)
        basis.append(values)
    return w, tuple(basis)


def _formants(
    a: np.ndarray, sr: int, n_fft: int = 512, min_f: float = 200.0, max_f: float = 4000.0
) -> np.ndarray:
    """从 LPC 系数求共振峰频率（Hz）。共振峰 = |A(e^jw)| 的局部极小。"""
    w, basis = _formant_basis(n_fft, len(a))
    A = np.zeros(n_fft, dtype=np.complex128)
    for ak, values in zip(a, basis):
        A += ak * values
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


def _conservative_formants(a: np.ndarray, sr: int) -> np.ndarray:
    """Experimental missing-peak fallback; never replace a complete legacy pair."""
    legacy = _formants(a, sr)
    if len(legacy) != 1:
        return legacy
    try:
        poles = np.roots(a)
    except np.linalg.LinAlgError:
        return legacy
    radii = np.abs(poles)
    poles = poles[(poles.imag > 1e-6) & (radii > 0) & (radii < 1)]
    frequencies = np.angle(poles) * sr / (2 * np.pi)
    bandwidths = -sr * np.log(np.abs(poles)) / np.pi
    roots = np.sort(frequencies[(frequencies > 200) & (frequencies < 4000)
                                & (bandwidths > 0) & (bandwidths <= 400)])
    if len(roots) < 2 or abs(legacy[0] - roots[0]) > 50:
        return legacy
    # Refinement must not cross existing F1 decision regions. Probe each F2
    # region through the classifier itself rather than duplicating thresholds.
    if any(_classify_vowel(legacy[0], probe) != _classify_vowel(roots[0], probe)
           for probe in (500., 1500., 2500.)):
        return legacy
    return roots


class LipSyncEngine:
    """自研元音驱动口型同步引擎。"""

    def __init__(
        self,
        frame_ms: float = 25.0,
        hop_ms: float = 10.0,
        silence_ratio: float = 0.05,
        smooth: int = 3,
        close_every: float | None = None,  # 显式装饰选项，不代表检测到发音停顿
        silence_rms: float = 0.001,
        formant_mode: str = 'legacy',
    ):
        if not isinstance(formant_mode, str) or formant_mode not in {'legacy', 'conservative'}:
            raise ValueError('formant_mode must be legacy or experimental conservative')
        for label, value in [('frame_ms', frame_ms), ('hop_ms', hop_ms)]:
            if not _finite_number(value) or value <= 0:
                raise ValueError(f'{label} must be finite and positive')
        if (not isinstance(smooth, (int, np.integer)) or isinstance(smooth, (bool, np.bool_))
                or smooth < 1):
            raise ValueError('smooth must be a positive integer')
        for label, value in [('silence_ratio', silence_ratio), ('silence_rms', silence_rms)]:
            if not _finite_number(value) or not 0 <= value <= 1:
                raise ValueError(f'{label} must be finite and within 0..1')
        if close_every is not None and (not _finite_number(close_every) or close_every <= 0):
            raise ValueError('close_every must be None or finite and positive')
        self.frame_ms = frame_ms
        self.hop_ms = hop_ms
        self.silence_ratio = silence_ratio
        self.smooth = smooth
        self.close_every = close_every
        self.silence_rms = silence_rms
        self.formant_mode = formant_mode

    def analyze(self, samples: np.ndarray, sr: int, *, cancel=None) -> list[LipSyncFrame]:
        """分析归一化单声道有限PCM（[-1,1]），返回逐帧口型参数。"""
        if cancel:
            cancel.checkpoint()
        if (not isinstance(sr, (int, np.integer)) or isinstance(sr, (bool, np.bool_))
                or not 0 < sr <= 384000):
            raise ValueError('sample rate must be an integer within 1..384000')
        frame_samples = sr * (float(self.frame_ms) / 1000)
        hop_samples = sr * (float(self.hop_ms) / 1000)
        if (not np.isfinite(frame_samples) or not np.isfinite(hop_samples)
                or max(frame_samples, hop_samples) >= np.iinfo(np.intp).max):
            raise ValueError('frame and hop sizes exceed representable sample dimensions')
        if int(frame_samples) < 2 or int(hop_samples) < 1:
            raise ValueError('frame and hop must span at least two and one samples')
        samples = np.asarray(samples)
        if (samples.ndim != 1 or samples.dtype.kind not in 'iuf'
                or not np.isfinite(samples).all() or np.any(samples < -1) or np.any(samples > 1)):
            raise ValueError('samples must be finite normalized mono PCM within -1..1')
        samples = samples.astype(np.float32, copy=False)
        if len(samples) == 0:
            return []

        frames = frame_signal(samples, self.frame_ms, self.hop_ms, sr)
        n = len(frames)
        if n == 0:
            return []

        times = np.arange(n) * self.hop_ms / 1000.0
        # 能量（RMS）与静音判定
        energy = np.sqrt(np.mean(frames**2, axis=1))
        peak = energy.max() if energy.size else 0.0
        if not np.isfinite(peak) or peak <= 1e-8:
            return [LipSyncFrame(float(t), 0.0, "", 0.0) for t in times]
        energy_norm = energy / peak
        silence = energy < max(peak * self.silence_ratio, self.silence_rms)

        order = min(2 + sr // 1000, 24)
        mouth = np.zeros(n, dtype=np.float64)
        vowels: list[str] = [""] * n

        for i in range(n):
            if cancel:
                cancel.checkpoint()
            if silence[i]:
                mouth[i] = 0.0
                continue
            a = _lpc(frames[i], order)
            fs = _conservative_formants(a, sr) if self.formant_mode == 'conservative' else _formants(a, sr)
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

        # Optional cosmetic motion; no acoustic evidence of a pause is implied.
        if self.close_every is not None and self.close_every < n * self.hop_ms / 1000:
            hop = int(sr * self.hop_ms / 1000)
            close_every_frames = max(1, int(self.close_every * sr / hop))
            for i in range(close_every_frames, n, close_every_frames):
                if mouth[i] > 0.3:
                    mouth[i] = 0.05

        mouth = np.clip(mouth, 0.0, 1.0)
        mouth[silence] = 0.0
        return [
            LipSyncFrame(
                time=float(times[i]),
                mouth_open=float(mouth[i]),
                vowel=vowels[i],
                energy=float(energy_norm[i]),
            )
            for i in range(n)
        ]
