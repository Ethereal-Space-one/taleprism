"""Waveform-level tests. Not a substitute for audition on speakers/headphones."""

import io
import sys
import wave
from array import array
from math import sqrt

import pytest

from storygal.soundscape_audio import DURATION, SAMPLE_RATE, render_soundscape


def samples(blob):
    with wave.open(io.BytesIO(blob)) as w:
        assert w.getparams()[:4] == (2, 2, SAMPLE_RATE, SAMPLE_RATE * DURATION)
        assert w.getcomptype() == "NONE"
        data = array("h")
        data.frombytes(w.readframes(w.getnframes()))
        if sys.byteorder != "little":
            data.byteswap()
        return data


def rms(data):
    return sqrt(sum(x * x for x in data) / len(data))


def pair(pcm, start, stop):
    a = pcm[int(start * SAMPLE_RATE) * 2 : int(stop * SAMPLE_RATE) * 2]
    return rms(a[::2]), rms(a[1::2])


@pytest.fixture(scope="module")
def palette():
    return {k: render_soundscape(*k) for k in [(True, None), (False, 6), (True, 6)]}


@pytest.mark.parametrize(
    "rain,car",
    [(False, None), (1, 6), (None, 6), (True, 2.0), (True, True), (False, 1), (False, 11)],
)
def test_invalid_layers(rain, car):
    with pytest.raises(ValueError):
        render_soundscape(rain, car)


def test_fixed_length_headroom_edges_and_repeatability(palette):
    for raw in palette.values():
        a = samples(raw)
        assert raw[36:40] == b"data" and len(raw) == 44 + 4 * SAMPLE_RATE * DURATION
        assert a[:2] == a[-2:] == array("h", (0, 0))
        assert 3000 < max(abs(x) for x in a) < 29_000
    assert render_soundscape(True, 6) == palette[True, 6]


def test_pass_approaches_crosses_and_leaves_without_canceling_in_mono(palette):
    car = samples(palette[False, 6])
    left_in, right_in = pair(car, 4, 5)
    left_out, right_out = pair(car, 7, 8)
    assert left_in > 2 * right_in and right_out > 2 * left_out
    center = pair(car, 5.7, 6.3)
    assert 0.9 < center[0] / center[1] < 1.1
    assert min(center) > 3 * max(left_in, right_out)
    assert not any(car[: 2 * SAMPLE_RATE * 2]) and not any(car[-2 * SAMPLE_RATE * 2 :])
    mono_energy = sum(((l + r) / 2) ** 2 for l, r in zip(car[::2], car[1::2]))
    stereo_energy = sum(x * x for x in car) / 2
    assert mono_energy > 0.85 * stereo_energy


def test_bed_stays_put_and_offsets_shift_the_same_car(palette):
    mix, rain, car = [samples(palette[k]) for k in [(True, 6), (True, None), (False, 6)]]
    period = SAMPLE_RATE * 2
    assert mix[: 2 * period] == rain[: 2 * period]
    assert mix[-2 * period :] == rain[-2 * period :]
    assert max(abs(m - r - c) for m, r, c in zip(mix, rain, car)) <= 2
    assert 1.7 < (sum(pair(mix, 5.8, 6.2)) / sum(pair(rain, 5.8, 6.2))) < 4.5
    for at in [2, 10]:
        shifted = samples(render_soundscape(False, at))
        assert shifted[(at - 1) * period : (at + 1) * period] == car[5 * period : 7 * period]


@pytest.mark.parametrize("rain,wind", [(True, True), (False, 1), (True, None)])
def test_alternative_beds_are_strict(rain, wind):
    with pytest.raises(ValueError):
        render_soundscape(rain, None, wind=wind)


def test_wind_gusts_and_coloration_are_not_rain_impacts(palette):
    blob = render_soundscape(False, None, wind=True)
    assert blob == render_soundscape(False, None, wind=True)
    wind, rain = samples(blob), samples(palette[True, None])
    assert wind[:2] == wind[-2:] == array("h", [0, 0])
    assert max(abs(v) for v in wind[:480]) <= 6 and max(abs(v) for v in wind[-480:]) <= 2
    assert 5_500 < max(abs(v) for v in wind) < 20_000
    # A soft arrival, clearly separated breaths and the second longer front;
    # no flat hiss, silent bed, large DC shift, or disappearance in mono.
    seconds = [sum(pair(wind, i, i + 1)) / 2 for i in range(12)]
    assert min(seconds) > 300 and max(seconds) < 3700
    assert seconds[2] > seconds[4] * 1.7 and seconds[7] > seconds[5] * 2.1
    assert abs(sum(wind) / len(wind)) < 2
    mono = rms([(l + r) / 2 for l, r in zip(wind[::2], wind[1::2])])
    assert 0.85 < mono / rms(wind) < 0.99

    # Relative first-difference energy is much lower than the rain bed.
    def roughness(a):
        left = a[::2]
        return rms([x - y for x, y in zip(left[1:], left)]) / rms(left)

    assert roughness(wind) < 0.55 * roughness(rain)
    mix, car = samples(render_soundscape(False, 6, wind=True)), samples(palette[False, 6])
    assert max(abs(m - w - c) for m, w, c in zip(mix, wind, car)) <= 2


def test_pencil_contacts_lifts_and_then_leaves_the_page_silent():
    from statistics import correlation

    blob = render_soundscape(False, None, pencil=True)
    assert blob == render_soundscape(False, None, pencil=True)
    a = samples(blob)
    # Audible contact, longer return, short softer finish. Air gaps are
    # digitally silent (both channels), including the last nine whole seconds.
    for start, end in [(0, 0.50), (1.01, 1.16), (1.87, 2.64), (3.0, DURATION)]:
        assert not any(a[2 * round(start * SAMPLE_RATE) : 2 * round(end * SAMPLE_RATE)])
    loudness = [
        sum(pair(a, start, end)) / 2 for start, end in ((0.57, 0.93), (1.23, 1.78), (2.70, 2.86))
    ]
    assert 400 < loudness[2] < loudness[0] < loudness[1] < 4000
    assert 3000 < max(abs(x) for x in a) < 20_000
    # A dry friction signal, without an audible pitched carrier. Large
    # autocorrelation at a nonzero period is a red flag for a periodic beep.
    t = a[2 * round(1.23 * SAMPLE_RATE) : 2 * round(1.73 * SAMPLE_RATE) : 2]
    assert max(abs(correlation(t[i:], t[:-i])) for i in range(4, 257)) < 0.20


@pytest.mark.parametrize(
    "rain,wind,car,pencil",
    [
        (True, False, None, True),
        (False, True, None, True),
        (False, False, 6, True),
        (False, False, None, 1),
    ],
)
def test_pencil_is_strictly_solo(rain, wind, car, pencil):
    with pytest.raises(ValueError):
        render_soundscape(rain, car, wind=wind, pencil=pencil)
