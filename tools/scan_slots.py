#!/usr/bin/env python3
"""Build data/mission_slots.csv: every vanilla music SoundWave of the mission music system, with the
cue that plays it, its category and the properties we must reproduce.

Input is the game's Content/Audio/Music folder as cooked .uasset/.uexp files, either unpacked straight
from the game pak (preferred - it is the live game version):

    repak unpack -i FSD/Content/Audio/Music -o <dir> "<DRG>\\FSD\\Content\\Paks\\FSD-WindowsNoEditor.pak"
    python tools/scan_slots.py <dir>/FSD/Content/Audio/Music

or the Music folder from Audio.zip of DRG-Modding/Audio-Modding-Template (all-assets release; the
properties are the same, but the release may lag behind the game). FModel .json exports work too.

The raw scan reads Duration, Volume, bLooping, bStreaming of each wave and finds which cue references
it (by name table). SoundClass lives on the cue, not on the wave, so it is recorded per wave for
information only.

It also writes data/mission_cues.csv: one row per cue with its path, SoundClass, submix, Priority and
VolumeMultiplier - what a replacement cue (prepare_tracks.py --rotate, ue_cues.py) has to keep.
"""
import argparse
import json
import re
import struct
from pathlib import Path

from common import (CATEGORY_BY_CUE, CUE_FIELDS, CUES_CSV, REPO, SHARED_WITH, SLOTS_CSV, SLOT_FIELDS, category_of,
                    die, write_csv)

MIN_DURATION = 30.0


def game_path(file):
    """.../Content/Audio/Music/Boss/Foo.uasset -> /Game/Audio/Music/Boss/Foo"""
    parts = list(file.with_suffix("").parts)
    if "Content" in parts:
        idx = len(parts) - 1 - parts[::-1].index("Content")
        return "/Game/" + "/".join(parts[idx + 1:])
    if "Music" in parts:  # a bare Music folder extracted from Audio.zip
        idx = len(parts) - 1 - parts[::-1].index("Music")
        return "/Game/Audio/Music/" + "/".join(parts[idx + 1:])
    return None


def uasset_names(data):
    """Name map of a cooked UE4 (4.27, unversioned custom versions) package summary."""
    if struct.unpack_from("<I", data, 0)[0] != 0x9E2A83C1:
        raise struct.error("not a UE4 package")
    o = 4
    legacy = struct.unpack_from("<i", data, o)[0]
    o += 4 if legacy == -4 else 8
    o += 8  # FileVersionUE4, FileVersionLicenseeUE4
    o += 4 + struct.unpack_from("<i", data, o)[0] * 20  # custom versions
    o += 4  # TotalHeaderSize
    n = struct.unpack_from("<i", data, o)[0]
    o += 4 + (n if n >= 0 else -2 * n)  # FolderName
    o += 4  # PackageFlags
    count, offset = struct.unpack_from("<ii", data, o)
    names, o = [], offset
    for _ in range(count):
        n = struct.unpack_from("<i", data, o)[0]
        o += 4
        if n < 0:
            names.append(data[o:o - 2 * n - 2].decode("utf-16-le"))
            o += -2 * n
        else:
            names.append(data[o:o + n - 1].decode("latin-1"))
            o += n
        o += 4  # hash
    return names


def export_data(file):
    """Serialized exports: the .uexp of a cooked package, the .uasset itself for an editor package."""
    uexp = file.with_suffix(".uexp")
    return uexp.read_bytes() if uexp.exists() else file.read_bytes()


def find_tag(names, data, prop, typ, size):
    if prop not in names or typ not in names:
        return -1, b""
    pat = struct.pack("<iiiiii", names.index(prop), 0, names.index(typ), 0, size, 0)
    return data.find(pat), pat


def float_tag(names, data, prop):
    """First FloatProperty tag named prop, or None when it is not serialized (= class default)."""
    i, pat = find_tag(names, data, prop, "FloatProperty", 4)
    return struct.unpack_from("<f", data, i + len(pat) + 1)[0] if i >= 0 else None  # +1: HasPropertyGuid


def wave_from_uasset(file):
    """Tagged SoundWave properties from a raw .uasset/.uexp pair. Properties equal to the class default
    are not serialized, so a missing bool means false."""
    names = uasset_names(file.read_bytes())
    if "SoundWave" not in names:
        return None
    uexp = export_data(file)

    def float_prop(prop):
        return float_tag(names, uexp, prop)

    def int_prop(prop):
        i, pat = find_tag(names, uexp, prop, "IntProperty", 4)
        return struct.unpack_from("<i", uexp, i + len(pat) + 1)[0] if i >= 0 else None

    def bool_prop(prop):
        i, pat = find_tag(names, uexp, prop, "BoolProperty", 0)
        return "true" if i >= 0 and uexp[i + len(pat)] else "false"

    duration, volume, quality = float_prop("Duration"), float_prop("Volume"), int_prop("CompressionQuality")
    return {
        "duration_sec": f"{duration:.2f}" if duration is not None else "",
        "sound_class": "", "attenuation": "",
        "volume": f"{volume:g}" if volume is not None else "",
        "compression_quality": "" if quality is None else str(quality),
        "looping": bool_prop("bLooping"),
        "streaming": bool_prop("bStreaming"),
    }


def ref_to_game_path(ref):
    if not ref:
        return ""
    p = ref.get("ObjectPath") or ref.get("AssetPathName") or "" if isinstance(ref, dict) else str(ref)
    m = re.search(r"'([^']+)'", p)
    if m:
        p = m.group(1)
    p = re.sub(r"\.\d+$", "", p)
    if p.startswith("FSD/Content/"):
        p = "/Game/" + p[len("FSD/Content/"):]
    head, _, tail = p.rpartition("/")
    if "." in tail:
        p = head + "/" + tail.split(".", 1)[0]
    return p if p.startswith("/Game/") else ""


def wave_from_json(file):
    data = json.loads(file.read_text(encoding="utf-8-sig"))
    exports = data if isinstance(data, list) else [data]
    wave = next((e for e in exports if isinstance(e, dict) and e.get("Type") == "SoundWave"), None)
    if wave is None:
        return None
    props = wave.get("Properties") or {}
    duration = props.get("Duration", wave.get("Duration"))
    return {
        "duration_sec": f"{float(duration):.2f}" if duration is not None else "",
        "sound_class": ref_to_game_path(props.get("SoundClassObject")),
        "attenuation": ref_to_game_path(props.get("AttenuationSettings")),
        "volume": props.get("Volume", ""),
        "compression_quality": props.get("CompressionQuality", ""),
        "looping": str(props.get("bLooping", "")).lower(),
        "streaming": str(props.get("bStreaming", "")).lower(),
    }


def cue_refs(file):
    """(name table, SoundClass name, loops, cue properties) of a SoundCue package."""
    try:
        names = uasset_names(file.read_bytes())
    except (OSError, struct.error, UnicodeDecodeError):
        return None
    if "SoundCue" not in names:
        return None
    sound_class = next((n for n in names if n.startswith("Music_") and "/" not in n), "")
    # bLooping is only serialized when some node sets it (defaults are skipped), so its presence in the
    # name table means a looping Wave Player: the game plays the wave round and round until it stops the
    # cue. A Looping node (bLoopIndefinitely on by default) shows up as its class name.
    loops = "bLooping" in names or "SoundNodeLooping" in names
    data = export_data(file)
    priority, volume = float_tag(names, data, "Priority"), float_tag(names, data, "VolumeMultiplier")
    props = {
        "sound_class": next((n for n in names if n.startswith("/Game/Audio/SoundControl/SoundClasses/")), ""),
        "submix": next((n for n in names if n.startswith("/Game/Audio/SoundControl/SubMixes/")), ""),
        "priority": f"{priority:g}" if priority is not None else "",
        "volume": f"{volume:g}" if volume is not None else "",
    }
    return names, sound_class, loops, props


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("music", type=Path, help="Content/Audio/Music folder (cooked .uasset/.uexp or FModel .json)")
    ap.add_argument("--min-duration", type=float, default=MIN_DURATION,
                    help=f"skip SoundWaves shorter than this many seconds (default {MIN_DURATION:g})")
    ap.add_argument("--out", type=Path, default=SLOTS_CSV)
    ap.add_argument("--cues-out", type=Path, default=CUES_CSV)
    args = ap.parse_args()
    if not args.music.is_dir():
        die(f"not a directory: {args.music}")

    waves, cues, skipped = {}, [], []
    for file in sorted(args.music.rglob("*")):
        if file.suffix.lower() not in (".json", ".uasset"):
            continue
        if "JukeBox" in file.parts:
            continue  # the jukebox is a separate mod
        path = game_path(file)
        if path is None:
            die(f"{file}: cannot derive the /Game/ path (expected .../Content/Audio/Music/...)")
        try:
            if file.suffix.lower() == ".json":
                info = wave_from_json(file)
            else:
                if path in waves:
                    continue
                refs = cue_refs(file)
                if refs:
                    cues.append((file.stem, path, *refs))
                    continue
                info = wave_from_uasset(file)
        except (OSError, ValueError, struct.error, UnicodeDecodeError) as e:
            print(f"  skip {file.name}: {e}")
            continue
        if info is None:
            continue
        name = file.stem
        dur = info["duration_sec"]
        if dur and float(dur) < args.min_duration:
            skipped.append(f"{path} ({dur}s)")
            continue
        waves[path] = {"asset_path": path, "name": name, "category": category_of(path, name),
                       "cue": "", "cue_loops": "", "shared_with": SHARED_WITH.get(name, ""), **info}
    if not waves:
        die("no SoundWave assets found under " + str(args.music))

    # which cue plays which wave: the cue's name table contains the wave's object name. UE stores an FName
    # "Foo_1" as "Foo" plus a number, so compare without the trailing _N (a leading zero keeps it: Foo_01).
    def fname(n):
        m = re.fullmatch(r"(.*)_([1-9]\d*)", n)
        return m.group(1) if m else n

    cue_rows = []
    for cue_name, cue_path, names, sound_class, loops, props in cues:
        played = []
        for w in waves.values():
            if w["name"] in names or fname(w["name"]) in names:
                w["cue"] = (w["cue"] + " " if w["cue"] else "") + cue_name
                w["cue_loops"] = "true" if loops or w["cue_loops"] == "true" else "false"
                if sound_class and not w["sound_class"]:
                    w["sound_class"] = sound_class
                played.append(w)
        if played:
            category = CATEGORY_BY_CUE.get(cue_name, played[0]["category"])
            cue_rows.append({"cue_path": cue_path, "name": cue_name, "category": category,
                             "loops": "true" if loops else "false", **props,
                             "waves": " ".join(w["name"] for w in played)})

    rows = sorted(waves.values(), key=lambda s: (s["category"], -float(s["duration_sec"] or 0)))
    write_csv(args.out, SLOT_FIELDS, rows)
    write_csv(args.cues_out, CUE_FIELDS, sorted(cue_rows, key=lambda c: (c["category"], c["cue_path"])))

    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    for cat, items in by_cat.items():
        durs = [float(r["duration_sec"]) for r in items if r["duration_sec"]]
        rng = f"{min(durs) // 60:.0f}:{min(durs) % 60:02.0f} - {max(durs) // 60:.0f}:{max(durs) % 60:02.0f}" if durs else ""
        loops = sum(1 for r in items if r["cue_loops"] == "true")
        print(f"{cat:>11}: {len(items):2d} slots  {rng:<13} {loops} looping cues")
    orphans = [r["name"] for r in rows if not r["cue"] and r["category"] not in ("unused", "jingle", "spacerig")]
    if orphans:
        print(f"note: no cue found for {', '.join(orphans)} (unused, or played by a blueprint)")
    if skipped:
        print(f"skipped {len(skipped)} short SoundWaves (< {args.min_duration:g}s)")
    for out in (args.out, args.cues_out):
        try:
            shown = out.resolve().relative_to(REPO)
        except ValueError:
            shown = out
        print(f"wrote {shown}")


if __name__ == "__main__":
    main()
