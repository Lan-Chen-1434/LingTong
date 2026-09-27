"""合成启动屏音效（无外部音频依赖，纯标准库生成 WAV）。

生成 assets/sfx/rain.wav：数字雨配套的高级感滴答循环——稀疏柔和的
电子脉冲，音高取自和声频率集，波形归一化，1.5s 无缝循环。

重新生成： python tools/make_sfx.py
"""
import math
import os
import random
import struct
import wave

SR = 22050
OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "sfx")

AMP = 0.26  # 整体音量（ winsound 无 per-play 音量控制，直接在波形里压低）


def write_wav(name: str, samples):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(
            struct.pack("<h", max(-32767, min(32767, int(s * 32767)))) for s in samples))
    print(f"{name}: {len(samples) / SR:.2f}s -> {os.path.normpath(path)}")


def data_ticks(dur=1.5, amp=0.5):
    """数字雨配套音效（高级感）：稀疏柔和的电子脉冲，音高取自和声频率集，
    叠加极淡的滤波噪声底，无缝循环。"""
    rng = random.Random(11)
    n = int(SR * dur)
    out = [0.0] * n
    # 和声感音高集（近似五声音阶的高八度区域），随机选取避免杂乱
    scale = [1567.98, 1760.00, 2093.00, 2349.32, 2637.02, 3135.96]
    # 稀疏滴答：每秒约 9 声，强弱错落
    ext = dur + 0.08
    t = rng.uniform(0, 0.08)
    while t < ext:
        f = rng.choice(scale) * rng.choice((0.5, 1.0))   # 偶尔低八度增加层次
        dec = rng.uniform(0.012, 0.025)
        a = amp * rng.uniform(0.2, 0.65) ** 1.5          # 偏向轻柔
        pos = t % dur
        s = int(pos * SR)
        ln = int(dec * SR * 3) + 1
        for i in range(ln):
            idx = (s + i) % n
            tt = i / SR
            # 双频叠加 + 快衰减，声音圆润不刺耳
            v = (math.sin(2 * math.pi * f * tt)
                 + 0.4 * math.sin(2 * math.pi * f * 2.01 * tt))
            out[idx] += a * v * 0.7 * math.exp(-tt / dec)
        t += rng.expovariate(9.0)
    # 首尾 5ms 淡入淡出，消除循环接缝
    fade = int(0.005 * SR)
    for i in range(fade):
        k = i / fade
        out[i] *= k
        out[n - 1 - i] *= k
    # 归一化到固定峰值，避免音量过低被系统放大后底噪显形
    peak = max(abs(s) for s in out) or 1.0
    return [s / peak for s in out]


if __name__ == "__main__":
    # 数字雨循环滴答声：归一化后峰值 0.5，清晰但不刺耳
    write_wav("rain.wav", [s * 0.5 for s in data_ticks()])
