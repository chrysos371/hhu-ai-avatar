"""音频工具：加载与分帧。"""
from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import Union

import numpy as np


class AudioDurationError(ValueError):
    """Audio exceeds the caller's decoding duration budget."""


def _frame_budget(max_seconds, sr):
    if not math.isfinite(max_seconds) or max_seconds <= 0 or sr <= 0:
        raise ValueError('Invalid audio decoding budget')
    return math.floor(max_seconds * sr)


def load_wav(path: Union[str, Path], *, max_seconds: float | None = None) -> tuple[np.ndarray, int]:
    """读取 16-bit PCM wav，返回 (float32 样本 [-1,1], 采样率)。

    仅用标准库，多声道取平均转单声道。
    """
    with wave.open(str(path), "rb") as wf:
        if wf.getsampwidth() != 2 or wf.getcomptype() != "NONE":
            raise ValueError("Only uncompressed 16-bit PCM WAV is supported")
        sr = wf.getframerate()
        ch = wf.getnchannels()
        frames = wf.getnframes()
        if max_seconds is not None and frames > _frame_budget(max_seconds, sr):
            raise AudioDurationError('Audio exceeds duration budget')
        data = wf.readframes(frames)
    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        samples = samples.reshape(-1, ch).mean(axis=1)
    return samples.astype(np.float32), sr


def load_audio(path: Union[str, Path], *, max_seconds: float | None = None) -> tuple[np.ndarray, int]:
    """加载音频；PCM WAV 用标准库，其他格式优先 soundfile 再用 librosa。"""
    with open(path, "rb") as stream:
        header = stream.read(12)
    if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return load_wav(path, max_seconds=max_seconds)
    try:
        import soundfile as sf
        options = {}
        if max_seconds is not None:
            info = sf.info(str(path))
            budget = _frame_budget(max_seconds, info.samplerate)
            if info.frames > budget:
                raise AudioDurationError('Audio exceeds duration budget')
            # Do not trust metadata alone: request at most one frame beyond the cap.
            options['frames'] = budget + 1
        samples, sr = sf.read(str(path), dtype="float32", always_2d=True, **options)
        if max_seconds is not None and len(samples) > _frame_budget(max_seconds, sr):
            raise AudioDurationError('Audio exceeds duration budget')
        return samples.mean(axis=1), int(sr)
    except (ImportError, RuntimeError):
        pass
    try:
        import librosa  # type: ignore

        options = {}
        if max_seconds is not None:
            source_sr = librosa.get_samplerate(str(path))
            _frame_budget(max_seconds, source_sr)
            options['duration'] = max_seconds + 1 / source_sr
        y, sr = librosa.load(str(path), sr=None, mono=True, **options)
        if max_seconds is not None and len(y) > _frame_budget(max_seconds, sr):
            raise AudioDurationError('Audio exceeds duration budget')
        return y.astype(np.float32), int(sr)
    except ImportError:
        return load_wav(path, max_seconds=max_seconds)


def frame_signal(
    samples: np.ndarray,
    frame_ms: float = 25.0,
    hop_ms: float = 10.0,
    sr: int = 24000,
) -> np.ndarray:
    """分帧 + 汉明窗，返回 (num_frames, frame_len) 的 float32 数组。"""
    frame_len = int(sr * frame_ms / 1000)
    hop = int(sr * hop_ms / 1000)
    if len(samples) < frame_len:
        return np.zeros((0, frame_len), dtype=np.float32)
    n_frames = 1 + (len(samples) - frame_len) // hop
    idx = np.arange(frame_len)[None, :] + hop * np.arange(n_frames)[:, None]
    frames = samples[idx].astype(np.float32)
    window = np.hamming(frame_len).astype(np.float32)
    return frames * window


def downsample_for_analysis(samples: np.ndarray, sr: int, target_sr: int = 16000,
                            *, cancel=None) -> tuple[np.ndarray, int]:
    """Zero-phase windowed-sinc low-pass before reducing sample rate.

    Native rate/timeline are preserved when already below the target. Chunked
    convolution bounds cancellation latency; this does not calibrate vowel labels.
    """
    samples = np.asarray(samples, dtype=np.float32)
    if (samples.ndim != 1 or not np.isfinite(samples).all()
            or not 0 < sr <= 384000 or not 8000 <= target_sr <= 192000):
        raise ValueError('Invalid analysis signal or sample rate')
    if cancel:
        cancel.checkpoint()
    if sr <= target_sr:
        return samples, sr
    if len(samples) == 0:
        return samples, target_sr
    ratio = sr / target_sr
    half = int(np.ceil(32 * ratio))
    offsets = np.arange(-half, half + 1)
    cutoff = .45 / ratio  # 10% transition margin below target Nyquist.
    kernel = 2 * cutoff * np.sinc(2 * cutoff * offsets) * np.hamming(len(offsets))
    kernel /= kernel.sum()
    padded = np.pad(samples, (half, half), mode='reflect' if len(samples) > 1 else 'edge')
    filtered = np.empty(len(samples), dtype=np.float32)
    for start in range(0, len(samples), 65536):
        if cancel:
            cancel.checkpoint()
        end = min(len(samples), start + 65536)
        filtered[start:end] = np.convolve(padded[start:end + 2 * half], kernel, mode='valid')
    positions = np.arange(0, len(samples), ratio)
    output = np.interp(positions, np.arange(len(samples)), filtered).astype(np.float32)
    if cancel:
        cancel.checkpoint()
    return output, target_sr
