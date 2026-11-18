"""Original, local acoustic sketches. No recordings, network or model.

Neither continuous bed changes when a car is added. The same moving car is shifted on
the 12-second timeline. Preserve rendered bytes for portable editions: floating
point math across platforms need not be bit-identical.
"""

import io
import math
import random
import sys
import wave
from array import array

SAMPLE_RATE = 24_000
DURATION = 12
_FRAMES = SAMPLE_RATE * DURATION
_TAU = math.tau


def _rain(lanes):
    """Filtered, partly shared rain wash plus individual, non-melodic roof taps."""
    r = random.Random(0x725201)
    noise = r.random
    # Smooth, aperiodic changes in rain density; never gate the continuous bed.
    swell = [r.uniform(0.78, 1.08) for _ in range(18)]
    stride = 18_000
    common = left = right = cslow = lslow = rslow = 0.0
    for i in range(_FRAMES):
        common += 0.58 * (2 * noise() - 1 - common)
        left += 0.60 * (2 * noise() - 1 - left)
        right += 0.60 * (2 * noise() - 1 - right)
        cslow += 0.082 * (common - cslow)
        lslow += 0.075 * (left - lslow)
        rslow += 0.075 * (right - rslow)
        k, rem = divmod(i, stride)
        f = rem / stride
        smooth = f * f * (3 - 2 * f)
        gain = swell[k] + (swell[k + 1] - swell[k]) * smooth
        wash = 0.124 * (common - cslow)
        j = 2 * i
        lanes[j] = gain * (wash + 0.113 * (left - lslow))
        lanes[j + 1] = gain * (wash + 0.113 * (right - rslow))
    when = -0.06
    while when < DURATION:
        when += r.uniform(0.046, 0.21)
        pan = r.uniform(-0.72, 0.72)
        gl, gr = math.sqrt((1 - pan) / 2), math.sqrt((1 + pan) / 2)
        dur, freq, amp = r.uniform(0.02, 0.062), r.uniform(620, 1810), r.uniform(0.021, 0.10)
        start = round(when * SAMPLE_RATE)
        count = int(dur * SAMPLE_RATE)
        # A tiny percussive impact, not a sustained bell: short filtered
        # splatter and a few damped oscillations of the sounding surface.
        memory = phase = 0.0
        for n in range(count):
            idx = start + n
            if not 0 <= idx < _FRAMES:
                continue
            x = n / count
            env = min(1, n / 28) * math.exp(-6.6 * x) * (1 - x)
            memory += 0.73 * (2 * noise() - 1 - memory)
            phase += _TAU * freq * (1.13 - 0.45 * x) / SAMPLE_RATE
            tap = amp * env * (0.64 * memory + 0.36 * math.sin(phase))
            lanes[2 * idx] += tap * gl
            lanes[2 * idx + 1] += tap * gr


def _wind(lanes):
    """Air in foliage, not a whistle or a tapped surface.

    One broad moving bed, with two overlapping airs in the crown. A swell changes
    both audibility and bandwidth; there is no oscillator, repetition or impulse.
    """
    noise = random.Random(0xA17F03).random
    # Asymmetric, non-equally spaced gusts. Each arrives and releases on a
    # smooth curve; the second has a weaker shoulder, not another sharp onset.
    fronts = ((0.10, 2.95, 5.35, 0.78), (4.85, 7.25, 10.80, 1.0), (8.85, 9.9, 11.88, 0.36))
    common = common2 = drift = l_mid = r_mid = l_low = r_low = 0.0
    l_air = r_air = l_air_low = r_air_low = 0.0
    for i in range(_FRAMES):
        t = i / SAMPLE_RATE
        g = 0.0
        for start, peak, end, strength in fronts:
            if start < t < end:
                x = (t - start) / (peak - start) if t < peak else (end - t) / (end - peak)
                g += strength * x * x * (3 - 2 * x)
        # Near branches catch air from slightly different directions. Shared
        # pressure is central and leaves a substantial signal in a mono fold.
        n0, nl, nr = 2 * noise() - 1, 2 * noise() - 1, 2 * noise() - 1
        k = 0.085 + 0.064 * g
        common += k * (n0 - common)
        common2 += (k + 0.042) * (common - common2)
        drift += 0.023 * (common2 - drift)
        k = 0.13 + 0.13 * g
        l_mid += k * (nl - l_mid)
        r_mid += k * (nr - r_mid)
        l_low += 0.08 * (l_mid - l_low)
        r_low += 0.08 * (r_mid - r_low)
        airy = 0.31 + 0.18 * g
        l_air += airy * (nl - l_air)
        r_air += airy * (nr - r_air)
        l_air_low += 0.26 * (l_air - l_air_low)
        r_air_low += 0.26 * (r_air - r_air_low)
        # No brittle, discrete 'drops': a soft, narrow rustle opens over the
        # lower wind, especially at the top of a gust.
        shared = (0.19 + 0.48 * g) * (common2 - drift)
        branch = 0.069 + 0.102 * g
        tips = 0.014 + 0.035 * g
        j = i * 2
        lanes[j] = shared + branch * (l_mid - l_low) + tips * (l_air - l_air_low)
        lanes[j + 1] = shared + branch * (r_mid - r_low) + tips * (r_air - r_air_low)


def _car(lanes, at):
    """A single pass: wet tire noise, a little rolling/engine body, no horn.

    Simulate along a fixed trajectory in event time, *then* place it on the
    passage clock. This keeps the car identical when the author moves the cue.
    """
    noise = random.Random(0xCA2102).random
    half = 4 * SAMPLE_RATE
    phase = low = mid = air = body = 0.0
    for n in range(2 * half + 1):
        t = (n - half) / SAMPLE_RATE
        # Lane clearance 8 m, constant speed 14.5 m/s. Projection gives a
        # coherent left→right pan AND the direction of the pitch change.
        dx = t * 14.5
        dist = math.hypot(dx, 8)
        sight = dx / dist
        near = 8 / dist
        # Softer spectral cutoff after the vehicle turns away from the listener.
        rad = 343 / (343 + 14.5 * sight)
        hz = 71.5 + 1.2 * math.sin(t * 1.43) + 0.55 * math.sin(t * 3.9)
        phase += (_TAU / SAMPLE_RATE) * rad * hz
        seed = 2 * noise() - 1
        air += (0.23 + 0.29 * near - 0.06 * sight) * (seed - air)
        mid += (0.10 + 0.038 * near) * (air - mid)
        low += 0.024 * (mid - low)
        body += 0.04 * (seed - body)
        spray = (air - mid) * (0.83 + 0.22 * near) + 0.48 * (mid - low)
        motor = (
            0.088 * math.sin(phase + 0.14 * math.sin(phase * 0.5))
            + 0.031 * math.sin(phase * 2.0 + 0.45)
            + 0.017 * math.sin(phase * 3.0 + 1.12)
        )
        # Shallow wet-road grooves at the near pass, heard as texture, not a beat.
        seam = 1 + 0.17 * math.exp(-(((t - 0.23) / 0.18) ** 2))
        edge = min(1, (4.0 - abs(t)) / 0.9)
        edge = edge * edge * (3 - 2 * edge)
        sound = edge * near**1.50 * (0.56 * spray * seam + motor + 0.23 * body)
        idx = (at * SAMPLE_RATE) + n - half
        if 0 <= idx < _FRAMES:
            pan = 0.74 * sight
            lanes[2 * idx] += sound * math.sqrt((1 - pan) / 2)
            lanes[2 * idx + 1] += sound * math.sqrt((1 + pan) / 2)


def _pencil(lanes):
    """Three dry contact gestures and a lifted point, never a loop or a written word.

    Aperiodic little catches roughen a band of friction as a moving point loads
    and lifts. The paper adds a duller part of the same excitation, not a pitched
    resonator. No room tone: the unmarked part of the timeline is literal zero.
    """
    r = random.Random(0x7061706572)
    # onset, length, pressure, travel across a small patch of paper
    for at, length, weight, x0, x1 in (
        (0.53, 0.46, 0.78, -0.21, 0.08),
        (1.17, 0.69, 1.00, 0.11, -0.13),
        (2.66, 0.25, 0.53, -0.10, 0.03),
    ):
        start, count = round(at * SAMPLE_RATE), round(length * SAMPLE_RATE)
        point = paper = low = grain = 0.0
        next_catch = 0
        for n in range(count):
            x = n / (count - 1)
            # Small, smooth edge ramps and an uneven pressure shoulder. Never
            # seed the noise from manuscript text or assign letter-like units.
            ramp = min(1.0, n / 460, (count - 1 - n) / 850)
            pressure = weight * ramp * ramp * (3 - 2 * ramp) * (1 - 0.33 * x)
            if n >= next_catch:
                grain += r.uniform(0.19, 0.81)
                next_catch = n + r.randint(45, 320)
            grain *= 0.982
            noise = r.uniform(-1, 1)
            point += (0.53 + 0.17 * pressure) * (noise - point)
            paper += 0.25 * (point - paper)
            low += 0.052 * (paper - low)
            drag = (0.19 + 0.19 * grain) * (point - paper) + 0.095 * (paper - low)
            pan = x0 + (x1 - x0) * x
            j = 2 * (start + n)
            lanes[j] = pressure * drag * math.sqrt((1 - pan) / 2)
            lanes[j + 1] = pressure * drag * math.sqrt((1 + pan) / 2)


def validate_palette(rain, car_at, wind=False, pencil=False):
    """One constraint for the API, portable recipes, and renderer."""
    if any(type(v) is not bool for v in (rain, wind, pencil)):
        raise ValueError("声层选项须为开或关。")
    if car_at is not None and (type(car_at) is not int or not 2 <= car_at <= 10):
        raise ValueError("车辆经过时刻须为第 2–10 秒的整数。")
    if rain and wind:
        raise ValueError("细雨和风声只能选择一种底声。")
    if pencil and (rain or wind or car_at is not None):
        raise ValueError("纸上铅笔声单独使用；落笔后的留白不混入雨、风或车辆。")
    if not (rain or wind or pencil) and car_at is None:
        raise ValueError("声景至少需要一种声音。")


def render_soundscape(
    rain: bool, car_at: int | None, wind: bool = False, pencil: bool = False
) -> bytes:
    """Return a canonical RIFF/WAVE file: 12 s, 24 kHz, stereo, signed PCM16."""
    validate_palette(rain, car_at, wind, pencil)
    lanes = array("f", [0.0]) * (_FRAMES * 2)
    if rain:
        _rain(lanes)
    elif wind:
        _wind(lanes)
    elif pencil:
        _pencil(lanes)
    if car_at is not None:
        _car(lanes, car_at)
    # Fixed mix gain, no normalization: rain stays at the same level whether
    # or not there is a vehicle. Smooth common fades; both edge frames are zero.
    for i in range(SAMPLE_RATE // 4):
        f = 0.5 - 0.5 * math.cos(math.pi * i / (SAMPLE_RATE // 4))
        lanes[2 * i] *= f
        lanes[2 * i + 1] *= f
    for i in range(SAMPLE_RATE // 2):
        f = 0.5 - 0.5 * math.cos(math.pi * i / (SAMPLE_RATE // 2))
        j = 2 * (_FRAMES - 1 - i)
        lanes[j] *= f
        lanes[j + 1] *= f
    pcm = array("h", (round(max(-1, min(1, v)) * 32767) for v in lanes))
    if sys.byteorder != "little":
        pcm.byteswap()
    dest = io.BytesIO()
    with wave.open(dest, "wb") as wav:
        wav.setparams((2, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
        wav.writeframes(pcm.tobytes())
    return dest.getvalue()
