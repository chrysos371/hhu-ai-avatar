"""音频工具：加载与分帧。"""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Union

import numpy as np


def load_wav(path: Union[str, Path]) -> tuple[np.ndarray, int]:
    """读取 16-bit PCM wav，返回 (float32 样本 [-1,1], 采样率)。

    仅用标准库，多声道取平均转单声道。
    """
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        data = wf.readframes(wf.getnframes())
    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        samples = samples.reshape(-1, ch).mean(axis=1)
    return samples.astype(np.float32), sr


def load_audio(path: Union[str, Path]) -> tuple[np.ndarray, int]:
    """加载任意音频（wav/mp3 等）。优先 librosa，回退到标准库 wav。"""
    try:
        import librosa  # type: ignore

        y, sr = librosa.load(str(path), sr=None, mono=True)
        return y.astype(np.float32), int(sr)
    except ImportError:
        return load_wav(path)


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
