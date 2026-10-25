#!/usr/bin/env python3
"""Level the loudness of your tracks and lay them out under the vanilla mission-music wave names.

    python tools/prepare_tracks.py measure path/to/vanilla_export.ogg ...   # LUFS / true peak of any files
    python tools/prepare_tracks.py build [--categories swarm,pressure,...] [--fit-slots] [--order shuffle]
                                         [--rotate swarm,ambient]

build reads tracks/, data/mission_slots.csv, data/mapping.csv (slot -> track) and data/cuts.csv (drop
of each track) and writes build/import/<Audio/Music/...>/<WaveName>.wav plus build/import/manifest.csv
for ue_import.py. Slots of categories not listed in --categories are left alone (vanilla music).

Per slot (data/mission_slots.csv, column cue_loops):
  looping cue  the game plays the wave round and round until it stops the cue (ambient, boss, extraction,
               machine event, Deep Dive screen, the pressure loops and half of the swarm cues), so a seamless
               loop is rendered: the fragment from the drop to `end` (cuts.csv), with the music right before
               the drop crossfaded onto the tail so the loop restarts on the drop.
  one-shot cue the track plays from its drop to `end` and fades out; with --fit-slots it is rendered at
               exactly the vanilla length (if the game cuts mission music there, like the jukebox - test
               in game first).

--rotate CATEGORIES: the game picks one cue per category for the whole mission, so a cue with one wave means
one track per mission. For the listed categories every vanilla cue is replaced by a copy of a master cue
(Random over all waves of the category, under a Looping node where the vanilla cue loops; docs/rotation.md),
written to build/import/cues.csv for ue_cues.py and collect_cooked.py. Waves of these categories are
rendered from the drop to the natural end of the song (no loop tail), since the next play of the cue picks
another track. All cues of a category get one VolumeMultiplier and one Priority, the medians of the vanilla
ones, so a mission does not sound different depending on which cue the game picked.
Requires ffmpeg and ffprobe on PATH.
"""
import argparse
import hashlib
import json
import random
import re
import shutil
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

from common import (BUILD, BUILD_CUES_CSV, CUE_DEFAULT_PRIORITY, CUE_DEFAULT_VOLUME, CUES_CSV, CUTS_CSV,
                    DEFAULT_CATEGORIES, IMPORT_DIR, MANIFEST_CSV, MAPPING_CSV, MASTERS_DIR, REPO, WAVE_PROPS, die,
                    load_slots, master_name, read_csv, write_csv)

TRACKS_DIR = REPO / "tracks"
NORMALIZED_DIR = BUILD / "normalized"
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".ogg", ".opus", ".m4a", ".aac", ".aif", ".aiff", ".wma"}
MANIFEST_FIELDS = ["asset_path", "wav", "track", "category", "duration_sec", "output_lufs"] + WAVE_PROPS
BUILD_CUE_FIELDS = ["cue_path", "category", "loops", "master", "sound_class", "submix", "priority", "volume",
                    "waves"]

TRIM_FILTER = ("silenceremove=start_periods=1:start_threshold=-60dB:start_silence=0.05,"
               "areverse,"
               "silenceremove=start_periods=1:start_threshold=-60dB:start_silence=0.3,"
               "areverse")

FADE_IN = 0.3
FADE_OUT = 2.5
LOOP_XFADE = 1.5
LOOP_PREROLL = 4.0   # seconds before the drop that lead back into it at the loop point
MAX_TAIL_GAP = 10.0  # up to this many seconds short of the slot: end naturally + silence instead of looping


def run_ffmpeg(args):
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        die(f"ffmpeg failed ({' '.join(args[:3])} ...):\n{proc.stderr[-2000:]}")
    return proc.stderr


def last_json(text):
    blocks = [b for b in re.findall(r"\{[^{}]*\}", text) if '"input_i"' in b]
    if not blocks:
        die("could not parse loudnorm output from ffmpeg")
    return json.loads(blocks[-1])


def probe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def measure(files):
    for f in files:
        stats = last_json(run_ffmpeg(["-i", str(f), "-af", "loudnorm=print_format=json", "-f", "null", "-"]))
        print(f"{stats['input_i']:>7} LUFS  {stats['input_tp']:>6} dBTP  "
              f"LRA {stats['input_lra']:>5}  {probe_duration(f):7.1f}s  {f}")


def normalize(src, dst, target_lufs, true_peak, sample_rate, trim):
    """Two-pass EBU R128 loudnorm, linear gain only (no compression): if the target would push the true
    peak over the ceiling, the track is raised only as far as its peak allows."""
    pre = TRIM_FILTER + "," if trim else ""
    first = last_json(run_ffmpeg(["-i", str(src), "-af",
                                  f"{pre}loudnorm=I={target_lufs}:TP={true_peak}:LRA=20:print_format=json",
                                  "-f", "null", "-"]))
    max_linear = float(first["input_i"]) + true_peak - float(first["input_tp"]) - 0.1
    target = f"I={min(target_lufs, round(max_linear, 1))}:TP={true_peak}:LRA=20"
    measured = (f"measured_I={first['input_i']}:measured_TP={first['input_tp']}:"
                f"measured_LRA={first['input_lra']}:measured_thresh={first['input_thresh']}:"
                f"offset={first['target_offset']}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp.wav")
    second = last_json(run_ffmpeg([
        "-y", "-i", str(src), "-vn", "-map_metadata", "-1",
        "-af", f"{pre}loudnorm={target}:{measured}:linear=true:print_format=json",
        "-ar", str(sample_rate), "-ac", "2", "-c:a", "pcm_s16le", str(tmp)]))
    tmp.replace(dst)
    return second


def cache_key(src, args):
    st = src.stat()
    raw = f"{src.name}|{st.st_size}|{st.st_mtime_ns}|{args.target_lufs}|{args.true_peak}|" \
          f"{args.sample_rate}|{args.trim_silence}|linear-only"
    return hashlib.sha1(raw.encode()).hexdigest()


def normalized_track(src, args):
    dst = NORMALIZED_DIR / f"{src.stem}_{src.suffix.lstrip('.').lower()}.wav"
    meta = dst.with_suffix(".json")
    key = cache_key(src, args)
    if dst.exists() and meta.exists():
        cached = json.loads(meta.read_text())
        if cached.get("key") == key:
            return dst, cached
    print(f"  normalizing {src.name} ...")
    report = normalize(src, dst, args.target_lufs, args.true_peak, args.sample_rate, args.trim_silence)
    info = {"key": key, "output_lufs": report["output_i"], "output_tp": report["output_tp"],
            "mode": report.get("normalization_type", ""), "duration_sec": round(probe_duration(dst), 2)}
    meta.write_text(json.dumps(info, indent=2))
    return dst, info


def track_index(tracks):
    """file name and NN prefix (playlist row) -> track"""
    by_key = {t.name: t for t in tracks}
    for t in tracks:
        num = t.name.split(" ", 1)[0]
        if num.isdigit():
            by_key[str(int(num))] = t
            by_key[num] = t
    return by_key


def load_cuts(tracks):
    """data/cuts.csv: track,start[,end[,note]] -> {track: (start, end)}.
    start = second where the hook/drop begins; end = where a pressure loop should wrap (bar-aligned, before
    the outro), empty = whole track."""
    if not CUTS_CSV.exists():
        return {}
    by_key = track_index(tracks)
    cuts = {}
    for row in read_csv(CUTS_CSV):
        key, start, end = ((row.get(k) or "").strip() for k in ("track", "start", "end"))
        if not key or not start:
            continue
        track = by_key.get(key) or by_key.get(key.lstrip("0"))
        if track is None:
            die(f"cuts.csv: track '{key}' not found in tracks/")
        cuts[track] = (float(start), float(end) if end else None)
    return cuts


VANILLA = "vanilla"


def load_mapping(slots, tracks):
    """data/mapping.csv: slot,track - slot is a wave name or /Game/ path, track a file in tracks/ or its NN.
    An empty track (or the word "vanilla") keeps that slot's vanilla music: it is not rendered or packed."""
    if not MAPPING_CSV.exists():
        return {}
    by_slot = {}
    for s in slots:
        by_slot[s["name"]] = s["asset_path"]
        by_slot[s["asset_path"]] = s["asset_path"]
    other = {k for s in load_slots() for k in (s["name"], s["asset_path"])} - set(by_slot)
    by_key = track_index(tracks)
    mapping = {}
    for row in read_csv(MAPPING_CSV):
        slot, track = (row.get("slot") or "").strip(), (row.get("track") or "").strip()
        if not slot or slot in other:  # a slot of a category not in --categories
            continue
        if slot not in by_slot:
            die(f"mapping.csv: unknown slot '{slot}' (not in data/mission_slots.csv)")
        if not track or track.lower() == VANILLA:
            mapping[by_slot[slot]] = VANILLA
            continue
        t = by_key.get(track) or by_key.get(track.lstrip("0"))
        if t is None:
            die(f"mapping.csv: track '{track}' not found in tracks/")
        mapping[by_slot[slot]] = t
    return mapping


def render(src, dst, graph, sample_rate):
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-y", "-i", str(src), "-filter_complex", graph, "-map", "[out]",
                "-ar", str(sample_rate), "-ac", "2", "-c:a", "pcm_s16le", str(dst)])


def render_once(src, dst, total, cut, end, slot_dur, fit, sample_rate):
    """A track that plays once: from its drop (cut) to `end` (cuts.csv; default: the whole track), fading
    out at the end.

    fit=True renders exactly slot_dur seconds (the game may stop the music at the vanilla duration):
    a track shorter than the slot keeps playing by repeating from the drop (crossfaded) instead of silence.
    Returns (rendered length, note)."""
    start = cut
    if end is not None:
        total = min(total, end)
    remaining = total - start
    fade_in = f",afade=t=in:d={FADE_IN}" if start > 0 else ""
    if not fit:
        graph = (f"[0:a]atrim=start={start}:duration={remaining:.3f},asetpts=PTS-STARTPTS{fade_in},"
                 f"afade=t=out:st={max(0.0, remaining - FADE_OUT):.3f}:d={FADE_OUT}[out]")
        render(src, dst, graph, sample_rate)
        return remaining, f"{start:.0f}s"
    if 0 < slot_dur - remaining <= MAX_TAIL_GAP:
        graph = (f"[0:a]atrim=start={start}:duration={remaining:.3f},asetpts=PTS-STARTPTS{fade_in},apad=whole_dur={slot_dur},"
                 f"atrim=duration={slot_dur}[out]")
        render(src, dst, graph, sample_rate)
        return slot_dur, f"{start:.0f}s+pad"
    if remaining >= slot_dur:
        graph, note = f"[0:a]atrim=start={start}:duration={remaining:.3f},asetpts=PTS-STARTPTS[x]", f"{start:.0f}s"
    else:
        loop_len = total - cut - LOOP_XFADE
        n = 1 + max(1, int((slot_dur - remaining) // max(loop_len, 1.0)) + 1)
        parts = [f"[0:a]asplit={n}" + "".join(f"[s{i}]" for i in range(n))]
        parts.append(f"[s0]atrim=start={start}:duration={remaining:.3f},asetpts=PTS-STARTPTS[c0]")
        for i in range(1, n):
            parts.append(f"[s{i}]atrim=start={cut}:duration={remaining:.3f},asetpts=PTS-STARTPTS[r{i}]")
            parts.append(f"[c{i - 1}][r{i}]acrossfade=d={LOOP_XFADE}[c{i}]")
        parts.append(f"[c{n - 1}]anull[x]")
        graph, note = ";".join(parts), f"{start:.0f}s+repeat"
    graph += (f";[x]atrim=duration={slot_dur},asetpts=PTS-STARTPTS{fade_in},"
              f"afade=t=out:st={max(0.0, slot_dur - FADE_OUT):.3f}:d={FADE_OUT}[out]")
    render(src, dst, graph, sample_rate)
    return slot_dur, note


def render_loop(src, dst, total, cut, end, slot_dur, fit, sample_rate):
    """A wave the game loops (pressure slots): no fades, and the end leads back into the drop.

    Body = the track from its drop to `end` (cuts.csv; default: the whole track minus trailing silence).
    The LOOP_PREROLL seconds right before the drop are crossfaded onto the tail, so when the game restarts
    the wave it lands on the drop as if the music never stopped. With fit=True the result is no longer
    than the vanilla slot."""
    body_end = end if end is not None else total
    preroll = min(LOOP_PREROLL, cut)
    body_len = body_end - cut
    if fit:  # the crossfade with the preroll shortens the result by LOOP_XFADE
        body_len = min(body_len, slot_dur - preroll + LOOP_XFADE if preroll >= 1.0 else slot_dur)
    body = f"atrim=start={cut}:duration={body_len:.3f},asetpts=PTS-STARTPTS"
    if end is None:
        body += ",areverse,silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.2,areverse"
    if preroll >= 1.0:
        graph = (f"[0:a]asplit=2[a][b];[a]{body}[body];"
                 f"[b]atrim=start={cut - preroll}:duration={preroll},asetpts=PTS-STARTPTS[pre];"
                 f"[body][pre]acrossfade=d={min(LOOP_XFADE, preroll / 2):.3f}[out]")
        note = f"{cut:.0f}s loop"
    else:
        # nothing before the drop to lead back in: tiny fades keep the loop point from clicking
        graph = (f"[0:a]{body},afade=t=in:d=0.05,areverse,afade=t=in:d=0.3,areverse[out]")
        note = f"{cut:.0f}s loop (no preroll)"
    if end is not None:
        note += f" to {end:.0f}s"
    render(src, dst, graph, sample_rate)
    return probe_duration(dst), note


def render_rotation(src, dst, cut, sample_rate):
    """A wave of a rotation cue (--rotate): when it ends the cue picks another track, so it plays from the
    drop to the natural end of the song. `end` from cuts.csv is a loop point and is not used. Trailing
    silence is cut so the next track follows right away; a short fade covers clips that stop abruptly."""
    fade_in = f",afade=t=in:d={FADE_IN}" if cut > 0 else ""
    graph = (f"[0:a]atrim=start={cut},asetpts=PTS-STARTPTS{fade_in},"
             "areverse,silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.2,"
             f"afade=t=in:d={FADE_OUT},areverse[out]")
    render(src, dst, graph, sample_rate)
    return probe_duration(dst), f"{cut:.0f}s to end, rotation"


def rotation_cues(rotate, slots):
    """build/import/cues.csv rows: every vanilla cue of a rotated category (data/mission_cues.csv), to be
    replaced by a copy of its master cue that plays all waves of the category."""
    if not CUES_CSV.exists():
        die(f"{CUES_CSV.relative_to(REPO)} not found - run tools/scan_slots.py first")
    cues = read_csv(CUES_CSV)
    rows = []
    for cat in rotate:
        cat_slots = [s for s in slots if s["category"] == cat]
        cat_cues = [c for c in cues if c["category"] == cat]
        if not cat_cues:
            die(f"--rotate {cat}: no cues of this category in {CUES_CSV.name}")
        played = {w for c in cat_cues for w in c["waves"].split()}
        missing = [s["name"] for s in cat_slots if s["name"] not in played]
        if missing:
            die(f"--rotate {cat}: no cue in {CUES_CSV.name} plays {', '.join(missing)} - rescan with scan_slots.py")
        volume = statistics.median(float(c["volume"] or CUE_DEFAULT_VOLUME) for c in cat_cues)
        priority = statistics.median(float(c["priority"] or CUE_DEFAULT_PRIORITY) for c in cat_cues)
        waves = " ".join(s["asset_path"] for s in cat_slots)
        for c in cat_cues:
            rows.append({"cue_path": c["cue_path"], "category": cat, "loops": c["loops"],
                         "master": f"{MASTERS_DIR}/{master_name(cat, c['loops'] == 'true')}",
                         "sound_class": c["sound_class"], "submix": c["submix"],
                         "priority": f"{priority:g}", "volume": f"{volume:g}",
                         "waves": waves})
    return rows


def build(args):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        die("ffmpeg/ffprobe not found on PATH")
    categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    rotate = [c.strip() for c in args.rotate.split(",") if c.strip()]
    if set(rotate) - set(categories):
        die(f"--rotate {', '.join(sorted(set(rotate) - set(categories)))} not in --categories {args.categories}")
    slots = load_slots(categories)
    if not slots:
        die(f"no slots in categories {args.categories}")
    tracks = sorted((p for p in TRACKS_DIR.iterdir() if p.suffix.lower() in AUDIO_EXTS),
                    key=lambda p: p.name.lower()) if TRACKS_DIR.is_dir() else []
    if not tracks:
        die(f"no audio files in {TRACKS_DIR.relative_to(REPO)}/ ({', '.join(sorted(AUDIO_EXTS))})")
    if args.order == "shuffle":
        random.Random(args.seed).shuffle(tracks)
    mapping = load_mapping(slots, tracks)
    cuts = load_cuts(tracks)

    # explicit mapping first; free slots take the unmapped tracks round-robin, category by category
    assignment = dict(mapping)
    spare = [t for t in tracks if t not in mapping.values()] or tracks
    i = 0
    for cat in categories:
        for s in slots:
            if s["category"] == cat and s["asset_path"] not in assignment:
                assignment[s["asset_path"]] = spare[i % len(spare)]
                i += 1
    if i and spare is not tracks:
        print(f"{i} slots had no mapping.csv entry and were filled round-robin from {len(spare)} unmapped tracks")
    unused = [t.name for t in tracks if t not in assignment.values()]
    if unused:
        print(f"not used in any slot: {', '.join(unused)}")
    kept = [s["name"] for s in slots if assignment[s["asset_path"]] == VANILLA]
    if kept:
        print(f"kept vanilla (mapping.csv): {', '.join(kept)}")
        kept_rotated = [s["name"] for s in slots if s["category"] in rotate and assignment[s["asset_path"]] == VANILLA]
        if kept_rotated:
            die(f"--rotate needs every slot of the category replaced; vanilla in mapping.csv: {', '.join(kept_rotated)}")
    slots = [s for s in slots if assignment[s["asset_path"]] != VANILLA]

    print(f"normalizing to {args.target_lufs} LUFS / {args.true_peak} dBTP, {args.sample_rate} Hz")
    infos = {t: normalized_track(t, args) for t in sorted(set(assignment.values()) - {VANILLA})}

    if IMPORT_DIR.exists():
        shutil.rmtree(IMPORT_DIR)
    rows, notes, no_loop_end = [], {}, []
    for s in slots:
        track = assignment[s["asset_path"]]
        norm, info = infos[track]
        wav = IMPORT_DIR / (s["asset_path"][len("/Game/"):] + ".wav")
        slot_dur = float(s["duration_sec"] or 0) or info["duration_sec"]
        cut, end = cuts.get(track, (0.0, None))
        if cut >= info["duration_sec"] - 5:
            die(f"cuts.csv: start {cut:g}s is past the end of {track.name} ({info['duration_sec']:.0f}s)")
        if end is not None and end <= cut + 10:
            die(f"cuts.csv: end {end:g}s must be well after start {cut:g}s for {track.name}")
        if s["category"] in rotate:
            duration, note = render_rotation(norm, wav, cut, args.sample_rate)
        elif s.get("cue_loops") == "true" or (not s.get("cue_loops") and s["category"] == "pressure"):
            if end is None:
                no_loop_end.append(track.name)
            duration, note = render_loop(norm, wav, info["duration_sec"], cut, end, slot_dur, args.fit_slots,
                                         args.sample_rate)
        else:
            duration, note = render_once(norm, wav, info["duration_sec"], cut, end, slot_dur, args.fit_slots,
                                         args.sample_rate)
            if end is not None:
                note += f" to {end:.0f}s"
        notes[s["asset_path"]] = note
        rows.append({**{k: s.get(k, "") for k in WAVE_PROPS},
                     "asset_path": s["asset_path"], "wav": wav.relative_to(REPO).as_posix(),
                     "track": track.name, "category": s["category"], "duration_sec": round(duration, 2),
                     "output_lufs": info["output_lufs"]})
    write_csv(MANIFEST_CSV, MANIFEST_FIELDS, rows)
    cue_rows = rotation_cues(rotate, slots) if rotate else []
    if cue_rows:
        write_csv(BUILD_CUES_CSV, BUILD_CUE_FIELDS, cue_rows)

    print()
    print(f"{'category':<11}{'slot':<38}{'vanilla':>8}{'ours':>7}  {'fragment':<24}{'track'}")
    for r, s in zip(rows, slots):
        print(f"{r['category']:<11}{s['name'][:36]:<38}{float(s['duration_sec'] or 0):>7.0f}s"
              f"{r['duration_sec']:>6.0f}s  {notes[r['asset_path']]:<24}{r['track']}")
    print()
    for track, (_, info) in infos.items():
        quieter = args.target_lufs - float(info["output_lufs"])
        if info["mode"] not in ("", "linear"):
            flag = "  (loudnorm fell back to dynamic mode and compressed it)"
        elif quieter > 0.3:
            flag = f"  ({quieter:.1f} dB below target: peaks leave no more headroom)"
        else:
            flag = ""
        print(f"{info['output_lufs']:>7} LUFS {info['output_tp']:>6} dBTP {info['duration_sec']:7.1f}s  "
              f"{track.name}{flag}")
    if no_loop_end:
        print(f"\nwarning: looping slots without an 'end' in cuts.csv wrap after the song's outro "
              f"(trailing silence trimmed): {', '.join(sorted(set(no_loop_end)))}")
    if cue_rows:
        print()
        for cat in rotate:
            mine = [c for c in cue_rows if c["category"] == cat]
            loops = sum(1 for c in mine if c["loops"] == "true")
            masters = sorted({c["master"].rsplit("/", 1)[1] for c in mine})
            print(f"rotation {cat}: {len(mine)} cues ({loops} looping), {len(mine[0]['waves'].split())} waves each, "
                  f"volume x{mine[0]['volume']}, masters {', '.join(masters)}")
        if args.fit_slots:
            print("note: --fit-slots does not apply to rotation waves (they play to the end of the song)")
        print(f"cues to replace: {BUILD_CUES_CSV.relative_to(REPO)} (ue_cues.py)")
    print(f"\n{len(rows)} slots -> {IMPORT_DIR.relative_to(REPO)}/, manifest: {MANIFEST_CSV.relative_to(REPO)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure", help="print loudness of audio files (e.g. vanilla exports)")
    m.add_argument("files", nargs="+", type=Path)
    b = sub.add_parser("build", help="normalise tracks and lay them out per mission-music slot")
    b.add_argument("--categories", default=",".join(DEFAULT_CATEGORIES),
                   help="slot categories to replace, comma-separated (default: %(default)s)")
    b.add_argument("--target-lufs", type=float, default=-11.0,
                   help="integrated loudness target (default -11, like the jukebox mod; measure vanilla exports to check)")
    b.add_argument("--true-peak", type=float, default=-1.0, help="true-peak ceiling in dBTP (default -1)")
    b.add_argument("--sample-rate", type=int, default=48000)
    b.add_argument("--trim-silence", action="store_true", help="cut leading/trailing silence")
    b.add_argument("--order", choices=["name", "shuffle"], default="name",
                   help="order of unmapped tracks for round-robin filling (default: by file name)")
    b.add_argument("--seed", type=int, default=1, help="seed for --order shuffle")
    b.add_argument("--rotate", default="",
                   help="categories whose cues play all their tracks in random order, e.g. swarm,ambient "
                        "(default: none, one track per cue as in the vanilla game)")
    b.add_argument("--fit-slots", action="store_true",
                   help="render every slot at exactly its vanilla duration (use if the game cuts mission music there)")
    args = ap.parse_args()
    if args.cmd == "measure":
        measure(args.files)
    else:
        build(args)


if __name__ == "__main__":
    main()
