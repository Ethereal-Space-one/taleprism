"""Pixel and lifecycle regression against the real React inline plate.

Requires frontend dependencies, Python Playwright, and Chromium. Uses two original
geometric calibration cards, one with rain and one with a sloped shore mask.
The harness represents the already-tested reading conductor's arm/disarm signal;
it neither mocks the browser renderer nor pretends to test passage timing.
"""

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HARNESS = """
import React from 'react'
import {createRoot} from 'react-dom/client'
import {ReaderPlate} from './src/reader/ReaderPlate'
import {resolveReadingMotion} from './src/reader/motion/recipes'
import './src/reader.css'
const data=JSON.parse(document.querySelector('#fixture').textContent)
const plate=data.config.illustrations[0], asset=data.media[plate.image_asset_id]
const root=createRoot(document.getElementById('root')),seen=new Set()
const recipe=resolveReadingMotion(data,plate)
window.present=(armed,show=true) => root.render(show ? <ReaderPlate
  plate={plate} asset={asset} sourceByte={plate.after_byte-1}
  motionSeen={seen} motionRecipe={recipe} motionArmed={armed}
  onLoad={()=>{}} onError={()=>{}} onRetry={()=>{}} onOpen={()=>window.opened++}
 /> : null)
window.opened=0
window.present(false)
"""
# Independent byte inspection of actual Canvas output: all changed pixels must
# be on the authored side, and the frame digest must change without replacing
# the underlying image. Clipping/interpolation can cover a 1px border of a mask.
PIXELS = """c => {
  const {width:w,height:h}=c, a=c.getContext('2d').getImageData(0,0,w,h).data;
  const m=JSON.parse(document.querySelector('#fixture').textContent).config.illustrations[0].motion;
  const mask=document.createElement('canvas');mask.width=w;mask.height=h;
  const mx=mask.getContext('2d');
  mx.fillStyle=mx.strokeStyle='white';mx.lineWidth=2;mx.lineJoin='round';
  for(const poly of (m.water||m.areas)){
    mx.beginPath();poly.forEach(([x,y],i)=>i?mx.lineTo(x*w,y*h):mx.moveTo(x*w,y*h));
    mx.closePath();mx.fill();mx.stroke();
  }
  const allowed=mx.getImageData(0,0,w,h).data;
  let changed=0, protectedPixels=0, outsideMask=0, hash=0;
  for(let i=3;i<a.length;i+=4) if(a[i]){
    changed++;let x=((i-3)/4)%w; if(x/w<.50) protectedPixels++;
    if(!allowed[i])outsideMask++;
    hash=(Math.imul(hash,16777619)^(i+a[i]))>>>0;
  }
  return {changed,protectedPixels,outsideMask,hash}
}"""


def make_pages(scratch):
    source = (ROOT / "examples/reading-lab/rain-grid/source.txt").read_bytes()
    plan = json.loads(
        (ROOT / "examples/reading-lab/rain-grid/edition.json").read_bytes()
    )
    image = (ROOT / "examples/reading-lab/rain-grid/plate.png").read_bytes()
    (scratch / "rain.png").write_bytes(image)
    sha = hashlib.sha256(image).hexdigest()
    source_sha = hashlib.sha256(source).hexdigest()
    parts = source.strip().split(b"\n\n")
    pos = source.index(parts[1]) + len(parts[1])
    motion = {
        "version": 1,
        "effect": "rain-wet-ground",
        "reviewed": True,
        "playback_only": True,
        "after_byte": pos,
        "width": 640,
        "height": 384,
        "source_sha256": source_sha,
        "image_sha256": sha,
        "areas": plan["areas"],
        "ground": plan["ground"],
        "drops": 25,
        "rings": 7,
    }
    data = {
        "preview": False,
        "project": {"canonical_sha256": source_sha},
        "blocks": [
            {
                "byte_start": source.index(text),
                "byte_end": source.index(text) + len(text),
                "text": text.decode(),
            }
            for text in parts
        ],
        "config": {
            "illustrations": [
                {
                    "id": "rain-grid",
                    "image_asset_id": "grid",
                    "after_byte": pos,
                    "title": "Rain grid",
                    "motion": motion,
                }
            ]
        },
        "media": {
            "grid": {
                "id": "grid",
                "type": "image",
                "url": "rain.png",
                "width": 640,
                "height": 384,
                "sha256": sha,
            }
        },
    }
    wave = json.loads(json.dumps(data))
    p = wave["config"]["illustrations"][0]
    p.update(id="synthetic-bank", title="QA shore fixture")
    a = wave["media"][p["image_asset_id"]]
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="500" height="300"><rect width="500" height="300" fill="#4d6770"/><path d="M250 255 L465 150 L500 170 V300 H250Z" fill="#a48b77"/></svg>'
    (scratch / "shore.svg").write_bytes(svg)
    sha = hashlib.sha256(svg).hexdigest()
    a.update(url="shore.svg", width=500, height=300, sha256=sha)
    p["motion"] = {
        "version": 1,
        "effect": "wave-impact-backwash",
        "reviewed": True,
        "after_byte": p["after_byte"],
        "width": 500,
        "height": 300,
        "source_sha256": wave["project"]["canonical_sha256"],
        "image_sha256": sha,
        "playback_only": True,
        "water": [[[0.51, 0.2], [0.93, 0.2], [0.93, 0.51], [0.51, 0.85]]],
        "bank": [[0.51, 0.85], [0.93, 0.51]],
        "hits": [{"x": 0.70, "phase": 0, "length": 7.1, "gain": 1.0}],
    }
    for name, fixture in [("rain", data), ("wave", wave)]:
        (scratch / (name + ".html")).write_text(
            '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            '<link rel="stylesheet" href="plate.css"><style>body{margin:0;min-height:300vh}'
            '#root{max-width:600px}.reader-plate{margin:0}</style><div id="root"></div>'
            '<script id="fixture" type="application/json">'
            + json.dumps(fixture, ensure_ascii=True).replace("<", "\\u003c")
            + '</script><script src="plate.js"></script>',
            encoding="utf-8",
        )


def run():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chromium")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryDirectory(prefix="taleprism-inline-") as tmp,
        sync_playwright() as pw,
    ):
        scratch = Path(tmp)
        subprocess.run(
            [
                str(ROOT / "frontend/node_modules/.bin/esbuild"),
                "--loader=tsx",
                "--jsx=automatic",
                "--bundle",
                '--define:process.env.NODE_ENV="production"',
                "--outfile=" + str(scratch / "plate.js"),
            ],
            input=HARNESS,
            text=True,
            check=True,
            cwd=ROOT / "frontend",
        )
        make_pages(scratch)
        browser = pw.chromium.launch(executable_path=args.chromium)
        for name, width in [("rain", 950), ("wave", 390)]:
            page = browser.new_page(viewport={"width": width, "height": 760})
            errors = []
            page.on("pageerror", lambda e, captured=errors: captured.append(str(e)))
            page.goto((scratch / (name + ".html")).as_uri())
            fig = page.locator("figure")
            img = fig.locator("img")
            expect(img).to_be_visible()
            assert not fig.locator("canvas").count()
            # Deliberate inline letterbox: the overlay must match the contained
            # original image, not the button/caption, despite an unusual frame.
            page.add_style_tag(content=".reader-plate .reader-plate-art{height:440px}")
            page.evaluate("present(true)")
            canvas = fig.locator("canvas")
            expect(canvas).to_be_visible()
            frame = None
            for _ in range(24):
                frame = canvas.evaluate(PIXELS)
                if frame["changed"] > 30:
                    break
                page.wait_for_timeout(90)
            assert (
                frame
                and frame["changed"] > 30
                and not frame["protectedPixels"]
                and not frame["outsideMask"]
            ), frame
            initial = frame["hash"]
            for _ in range(10):
                page.wait_for_timeout(90)
                second = canvas.evaluate(PIXELS)
                if second["changed"] > 30 and second["hash"] != initial:
                    break
            assert (
                second["changed"] > 30
                and second["hash"] != initial
                and not second["protectedPixels"]
                and not second["outsideMask"]
            )
            bounds = fig.evaluate("""f=>{
              const i=f.querySelector('img'), c=f.querySelector('canvas').getBoundingClientRect();
              const r=i.getBoundingClientRect(),s=Math.min(r.width/i.naturalWidth,r.height/i.naturalHeight);
              const w=i.naturalWidth*s,h=i.naturalHeight*s;
              return [c.width-w,c.height-h,c.left-r.left-(r.width-w)/2,c.top-r.top-(r.height-h)/2];
            }""")
            assert max(map(abs, bounds)) <= 1, bounds
            assert (
                page.evaluate("window.opened") == 0
                and not page.locator("dialog[open]").count()
            )
            if args.output:
                fig.screenshot(path=args.output / (name + "-inline.png"))
            print(
                f"{name}: changed pixels {frame['changed']} → {second['changed']}; protected left half 0; outside authored mask 0; containment error <1px",
                flush=True,
            )
            if name == "rain":
                expect(canvas).to_be_hidden(timeout=9300)
                assert canvas.evaluate(PIXELS)["changed"] == 0
            else:
                page.evaluate("scrollTo(0,innerHeight*2)")
                expect(canvas).to_be_hidden()
                page.evaluate("scrollTo(0,0)")
                page.wait_for_timeout(350)
                expect(canvas).to_be_hidden()
            page.evaluate("present(false,false)")
            expect(fig).to_have_count(0)
            page.evaluate("present(true,true)")
            expect(img).to_be_visible()
            page.wait_for_timeout(350)
            expect(canvas).to_be_hidden()
            # Manual expansion remains available even after the automatic run.
            fig.locator(".reader-plate-art").click()
            assert page.evaluate("window.opened") == 1
            page.reload()
            page.emulate_media(reduced_motion="reduce")
            expect(img).to_be_visible()
            page.evaluate("present(true)")
            page.wait_for_timeout(350)
            expect(canvas).to_be_hidden()
            assert canvas.evaluate(PIXELS)["changed"] == 0
            assert not errors, errors
            page.close()
        browser.close()


if __name__ == "__main__":
    run()
