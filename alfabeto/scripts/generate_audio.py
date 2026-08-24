#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Alfabeto clip baker. Same engine as Oído: tts-1-hd, speed 0.95, nova + onyx.

Run from the alfabeto folder:
    py -3 scripts/generate_audio.py --dry-run
    py -3 scripts/generate_audio.py
    py -3 scripts/generate_audio.py --verify

Do not edit CLIP count. Do not add voices. Do not bake base64 into HTML.
"""
from __future__ import print_function

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "index.html")
AUDIO_DIR = os.path.join(ROOT, "audio")
MANIFEST = os.path.join(AUDIO_DIR, "manifest.json")
CACHE = os.path.join(ROOT, "audio_cache")
VOICES = {"nova": ("f", "Nova"), "onyx": ("m", "Onyx")}
MODEL, FORMAT, SPEED = "tts-1-hd", "mp3", 0.95
EXPECTED = 40
MIN_BYTES = 800

def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "x"

def read_block(html, block_id):
    m = re.search(r'<script id="%s"[^>]*>(.*?)</script>' % block_id, html, re.S)
    return m.group(1) if m else None

def collect_keys():
    if not os.path.exists(HTML):
        sys.exit("Missing " + HTML)
    html = open(HTML, encoding="utf-8").read()
    raw = read_block(html, "clip-keys")
    if not raw:
        sys.exit("No <script id=\"clip-keys\"> in index.html")
    keys = json.loads(raw)
    if not isinstance(keys, list):
        sys.exit("clip-keys must be a JSON array of strings")
    out = []
    seen = set()
    for k in keys:
        if not isinstance(k, str) or not k.strip():
            sys.exit("Bad clip key: %r" % (k,))
        if k in seen:
            sys.exit("Duplicate clip key: %r" % (k,))
        seen.add(k)
        out.append(k)
    if len(out) != EXPECTED:
        sys.exit("Expected %d clip keys, found %d" % (EXPECTED, len(out)))
    return out

def load_manifest():
    if os.path.exists(MANIFEST):
        return json.load(open(MANIFEST, encoding="utf-8"))
    return {"voices": [], "clips": {}}

def save_manifest(manifest):
    os.makedirs(AUDIO_DIR, exist_ok=True)
    json.dump(manifest, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(MANIFEST, "a", encoding="utf-8").write("\n")

def load_api_key():
    k = os.environ.get("OPENAI_API_KEY", "").strip()
    if k:
        return k
    candidates = [
        os.path.join(ROOT, ".env"),
        os.path.join(os.path.dirname(ROOT), ".env"),
        os.path.join(os.path.expanduser("~"), "Documents", "GitHub", "oido", ".env"),
        os.path.join(os.path.expanduser("~"), "Documents", "GitHub", "oido", "audio_cache", ".env"),
    ]
    for path in candidates:
        if not os.path.isfile(path):
            continue
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("OPENAI_API_KEY="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    return ""

def tts(api_key, voice, text):
    cdir = os.path.join(CACHE, voice)
    os.makedirs(cdir, exist_ok=True)
    cpath = os.path.join(cdir, slug(text) + "." + FORMAT)
    if os.path.exists(cpath) and os.path.getsize(cpath) >= MIN_BYTES:
        return open(cpath, "rb").read()
    body = json.dumps({
        "model": MODEL,
        "voice": voice,
        "input": text,
        "response_format": FORMAT,
        "speed": SPEED,
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=body,
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if len(data) < MIN_BYTES:
                sys.exit("Clip too small for %r / %s (%d bytes)" % (text, voice, len(data)))
            open(cpath, "wb").write(data)
            return data
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="ignore")
            if e.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            sys.exit("OpenAI error %s: %s" % (e.code, msg))
        except Exception as e:
            if attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            sys.exit("Network error: %s" % e)

def verify():
    keys = collect_keys()
    manifest = load_manifest()
    voices = [v.get("id") for v in manifest.get("voices", [])]
    clips = manifest.get("clips", {})
    bad = 0
    print("Manifest: %s" % MANIFEST)
    print("Keys: %d (must be %d)" % (len(keys), EXPECTED))
    for vid in ("nova", "onyx"):
        bag = clips.get(vid, {})
        missing_keys = [k for k in keys if k not in bag]
        missing_files = []
        tiny = []
        for k in keys:
            rel = bag.get(k)
            if not rel:
                continue
            path = os.path.join(ROOT, rel.replace("/", os.sep))
            if not os.path.isfile(path):
                missing_files.append(rel)
            elif os.path.getsize(path) < MIN_BYTES:
                tiny.append(rel)
        print("  %s: %d keys, missing_keys=%d missing_files=%d tiny=%d" % (
            vid, len(bag), len(missing_keys), len(missing_files), len(tiny)))
        if vid not in voices:
            print("    FAIL: voice %s not listed in manifest.voices" % vid)
            bad += 1
        if missing_keys or missing_files or tiny:
            bad += 1
            for k in missing_keys[:8]:
                print("    missing key: %r" % k)
            for p in missing_files[:8]:
                print("    missing file: %s" % p)
            for p in tiny[:8]:
                print("    tiny file: %s" % p)
    if bad:
        sys.exit("VERIFY FAIL")
    print("VERIFY OK  80 mp3s (40 x nova + onyx)")

def dry_run():
    keys = collect_keys()
    print("%d clip keys:" % len(keys))
    for i, k in enumerate(keys, 1):
        print("%2d  %s  ->  %s.mp3" % (i, k, slug(k)))
    print("Would synthesize %d files (x2 voices)." % len(keys))

if "--dry-run" in sys.argv:
    dry_run()
    sys.exit(0)
if "--verify" in sys.argv:
    verify()
    sys.exit(0)

API_KEY = load_api_key()
if not API_KEY:
    sys.exit(
        "No OPENAI_API_KEY. Set the env var, or put OPENAI_API_KEY=... in alfabeto/.env\n"
        "STOP. Do not fake clips. Do not use device TTS files."
    )

keys = collect_keys()
manifest = load_manifest()
manifest["voices"] = [{"id": v, "gender": g, "label": lbl} for v, (g, lbl) in VOICES.items()]
manifest.setdefault("clips", {})
for v in VOICES:
    manifest["clips"].setdefault(v, {})

todo = []
for voice in VOICES:
    bag = manifest["clips"][voice]
    vdir = os.path.join(AUDIO_DIR, voice)
    os.makedirs(vdir, exist_ok=True)
    for key in keys:
        rel = bag.get(key)
        path = os.path.join(ROOT, rel.replace("/", os.sep)) if rel else ""
        if rel and os.path.isfile(path) and os.path.getsize(path) >= MIN_BYTES:
            continue
        todo.append((voice, key))

total = len(todo)
print("%d clip keys x 2 voices. Missing: %d" % (len(keys), total))
if not todo:
    print("Nothing to synthesize")
    verify()
    sys.exit(0)

done = 0
for voice, key in todo:
    mp3 = tts(API_KEY, voice, key)
    fname = slug(key) + "." + FORMAT
    rel = "audio/%s/%s" % (voice, fname)
    dest = os.path.join(ROOT, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    open(dest, "wb").write(mp3)
    manifest["clips"][voice][key] = rel
    done += 1
    print("  %d/%d  %s  %s" % (done, total, voice, key))
    save_manifest(manifest)

print("Updated %s" % MANIFEST)
verify()
