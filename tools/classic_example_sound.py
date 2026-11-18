"""Two reviewed paragraph accents for the public classic examples.

Rebuild the original finite PCM using the source-distributed procedural renderer.
The public recipe is an exact source span and sound identity, never a private
editable project, audition history, generated transcript, field recording or TTS.
"""

from dataclasses import dataclass

from chibi_source import digest


@dataclass(frozen=True)
class ClassicSound:
    id: str
    start: int
    end: int
    paragraph_sha256: str
    quote: str
    quote_start: int
    palette: str
    sha256: str

    @property
    def project_wav(self):
        return "soundscape/" + self.id + ".wav"

    @property
    def reader_wav(self):
        return "media/" + self.id + ".wav"

    @property
    def cue(self):
        return {
            "id": self.id,
            "duration": 12.0,
            "label": "段落声景",
            "description": {"wind": "风声", "rain": "细雨"}[self.palette],
        }

    @property
    def media(self):
        return {
            "id": self.id,
            "duration": 12.0,
            "origin": "paragraph_soundscape",
            "sha256": self.sha256,
            "type": "audio",
            "url": "./" + self.reader_wav,
        }

    def accepted_record(self, source, original):
        # Resolve and independently validate the exact paragraph and evidence
        # offsets using the same parser/validator as ordinary project import.
        from storygal.reader import paragraphs
        from storygal.soundscape import GENERATOR, binding, inspect_wav, validate_record
        from storygal.soundscape_audio import render_soundscape

        blocks = {b["byte_start"]: b for b in paragraphs(source)}
        rain, wind = self.palette == "rain", self.palette == "wind"
        wav, duration = inspect_wav(render_soundscape(rain, None, wind=wind))
        if digest(wav) != self.sha256 or source != original:
            raise ValueError(
                "Canonical sound or original text changed; do not substitute a new take."
            )
        row = {
            "id": self.id,
            "source_sha256": digest(source),
            "original_sha256": digest(original),
            "byte_start": self.start,
            "byte_end": self.end,
            "paragraph_sha256": self.paragraph_sha256,
            "evidence": self.quote,
            "evidence_start": self.quote_start,
            "generator": GENERATOR,
            "rain": rain,
            "car_at": None,
            **({"wind": True} if wind else {}),
            "duration": duration,
            "status": "accepted",
            "sha256": self.sha256,
        }
        row["binding_sha256"] = binding(row)
        validate_record(row, blocks, digest(source), digest(original), duration)
        return row, wav


SOUNDS = {
    "chibi": ClassicSound(
        "f9519a2b-af85-446a-b1b4-ae8a4537a104",
        5183,
        6014,
        "a5c57905213930a77fc0707e01d136ba424d8495a7a1c1a0a1f2828d1c363d4e",
        "忽聽風聲響，旗旛轉動",
        5378,
        "wind",
        "0423fa1337a7f0a0359954dcbe9ba5a0c803f5458213a1ba82da4d5960bd2f75",
    ),
    "last-light": ClassicSound(
        "f2f784ef-0b15-4e3b-83c1-71ced678417c",
        22,
        526,
        "8f38ad5be9f1937aa51fb329ed0e44b82fc2a4ad56faba03dd3a691abe2cb795",
        "傍晚的雨斜着落进站台",
        67,
        "rain",
        "b56c5adaa50ad8f365bee1451a8d987d2bc58b62c7351781d9d48b0bbc5eca27",
    ),
}
