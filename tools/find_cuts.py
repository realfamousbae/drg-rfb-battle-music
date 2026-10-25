#!/usr/bin/env python3
"""Propose data/cuts.csv entries (start = first drop, end = where the outro begins) from the loudness curve.

    python tools/find_cuts.py                 # all tracks in tracks/, rows already in cuts.csv are kept
    python tools/find_cuts.py --only 7 15     # a few tracks
    python tools/find_cuts.py --profile 7     # print the per-second energy curve of a track and exit

A drop is the first second where the bass energy (below 150 Hz) jumps well above the level of the music
before it and stays there for a while. The outro starts after the last loud stretch. Both are guesses to
listen to and correct by hand; the note column says how confident the guess is.
Requires ffmpeg on PATH.
"""
import argparse
import csv
import re
import subprocess
from pathlib import Path

from common import CUTS_CSV, REPO, die, read_csv

TRACKS_DIR = REPO / "tracks"
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".ogg", ".opus", ".m4a", ".aac", ".aif", ".aiff", ".wma"}
STEP = 1.0  # seconds per energy sample


def energy_curve(path, lowpass=None):
    """RMS level in dB of each STEP-second window (optionally of the low band only)."""
    # asetnsamples makes every frame exactly STEP seconds long; astats then reports one RMS value per frame
    filt = ((f"lowpass=f={lowpass}," if lowpass else "") + f"asetnsamples=n={int(48000 * STEP)}:p=0,"
            "astats=metadata=1:reset=1:measure_overall=none:measure_perchannel=RMS_level,"
            "ametadata=print:key=lavfi.astats.1.RMS_level")
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-ar", "48000", "-ac", "1",
                           "-af", filt, "-f", "null", "-"], capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        die(f"ffmpeg failed on {path.name}:\n{proc.stderr[-1500:]}")
    vals = [float(v) if v != "-inf" else -90.0
            for v in re.findall(r"lavfi\.astats\.1\.RMS_level=(-?[\d.]+|-inf)", proc.stderr)]
    return vals


def smooth(vals, n=3):
    out = []
    for i in range(len(vals)):
        w = vals[max(0, i - n // 2): i + n // 2 + 1]
        out.append(sum(w) / len(w))
    return out


def find_drop(bass, full):
    """First second where the smoothed bass reaches the track's loud level (within 4 dB of its peak), stays
    there for 8 s and is a clear step up from the seconds before it. Falls back to the first loud second."""
    b = smooth(bass, 3)
    n = len(b)
    if n < 20:
        return 0, "short track"
    peak = sorted(b)[int(n * 0.95)]  # robust peak: 95th percentile
    for i in range(2, n - 8):
        before = sum(b[max(0, i - 6):i]) / min(6, i)
        if b[i] >= peak - 4 and min(b[i:i + 8]) >= peak - 5 and b[i] - before >= 3:
            return i, f"bass +{b[i] - before:.0f} dB"
    if b[0] >= peak - 4:
        return 0, "starts at full energy"
    loud = [i for i in range(n) if b[i] >= peak - 4]
    return (loud[0] if loud else 0), "first loud second (check)"


def find_outro(bass, start):
    """Last second of the last stretch (>= 8 s) that stays near the track's loud level; the outro begins after."""
    b = smooth(bass, 3)
    n = len(b)
    body = b[start:]
    if len(body) < 16:
        return None
    level = sorted(body)[len(body) * 3 // 4]  # upper quartile = "the loud parts"
    loud = [i for i in range(start, n) if b[i] >= level - 3]
    if not loud:
        return None
    # walk back from the end to the last loud second that is part of a run >= 8 s
    end = loud[-1]
    for i in reversed(loud):
        run = [j for j in range(i - 7, i + 1) if j in set(loud)]
        if len(run) >= 8:
            end = i
            break
    return end + 1 if end + 1 < n - 2 else None


def estimate_bpm(path, lo=80, hi=200):
    """Tempo from the autocorrelation of the onset strength (positive RMS increments every 25 ms)."""
    hop = 0.025
    filt = (f"asetnsamples=n={int(48000 * hop)}:p=0,"
            "astats=metadata=1:reset=1:measure_overall=none:measure_perchannel=RMS_level,"
            "ametadata=print:key=lavfi.astats.1.RMS_level")
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-ar", "48000", "-ac", "1",
                           "-af", filt, "-f", "null", "-"], capture_output=True, text=True, errors="replace")
    vals = [float(v) if v != "-inf" else -90.0
            for v in re.findall(r"lavfi\.astats\.1\.RMS_level=(-?[\d.]+|-inf)", proc.stderr)]
    onset = [max(0.0, vals[i] - vals[i - 1]) for i in range(1, len(vals))]
    if len(onset) < 400:
        return None
    mean = sum(onset) / len(onset)
    onset = [o - mean for o in onset]
    best, best_lag = -1.0, None
    for lag in range(int(60 / hi / hop), int(60 / lo / hop) + 1):
        c = sum(onset[i] * onset[i + lag] for i in range(len(onset) - lag)) / (len(onset) - lag)
        if c > best:
            best, best_lag = c, lag
    if best_lag is None:
        return None
    # refine: parabolic interpolation around the best lag
    def ac(l):
        return sum(onset[i] * onset[i + l] for i in range(len(onset) - l)) / (len(onset) - l)
    a, b, c = ac(best_lag - 1), best, ac(best_lag + 1)
    denom = a - 2 * b + c
    frac = 0.5 * (a - c) / denom if denom else 0.0
    return 60.0 / ((best_lag + frac) * hop)


def snap_to_bars(start, end, bpm):
    """Move end back to the last bar line (4 beats) counted from start."""
    bar = 4 * 60.0 / bpm
    bars = int((end - start) / bar + 0.1)  # a point just short of a bar line (tempo rounding) counts as on it
    return round(start + bars * bar, 2) if bars >= 1 else end


def track_number(path):
    num = path.name.split(" ", 1)[0]
    return int(num) if num.isdigit() else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", type=int, nargs="+", metavar="N")
    ap.add_argument("--profile", type=int, metavar="N", help="print the energy curve of track N and exit")
    ap.add_argument("--force", action="store_true", help="replace rows already in cuts.csv")
    args = ap.parse_args()

    tracks = sorted((p for p in TRACKS_DIR.iterdir() if p.suffix.lower() in AUDIO_EXTS), key=lambda p: p.name)
    if args.profile is not None:
        t = next((p for p in tracks if track_number(p) == args.profile), None)
        if not t:
            die(f"track {args.profile} not found")
        bass, full = energy_curve(t, 150), energy_curve(t)
        print(f"{t.name}\n  sec   bass   full")
        for i, (b, f) in enumerate(zip(bass, full)):
            bar = "#" * max(0, int((b + 40) / 1.5))
            print(f"{i:5d} {b:6.1f} {f:6.1f}  {bar}")
        return

    existing = {}
    header = ["track", "start", "end", "note"]
    comments = []
    if CUTS_CSV.exists():
        with open(CUTS_CSV, newline="", encoding="utf-8") as f:
            for line in f:
                if line.startswith("#"):
                    comments.append(line.rstrip("\n"))
        for row in read_csv(CUTS_CSV):
            if (row.get("track") or "").strip():
                existing[row["track"].strip().lstrip("0") or "0"] = row

    rows = dict(existing)
    for t in tracks:
        n = track_number(t)
        if n is None or (args.only and n not in args.only):
            continue
        key = str(n)
        if key in existing and not args.force:
            print(f"[{n:02d}] kept: start={existing[key].get('start')} end={existing[key].get('end')}")
            continue
        bass, full = energy_curve(t, 150), energy_curve(t)
        start, how = find_drop(bass, full)
        end = find_outro(bass, start)
        bpm = estimate_bpm(t)
        if end is not None and bpm:
            end = snap_to_bars(start, end, bpm)
        title = t.stem.split(" - ", 1)[-1]
        tempo = f"{bpm:.1f} bpm" if bpm else "bpm ?"
        rows[key] = {"track": f"{n:02d}", "start": str(start), "end": "" if end is None else f"{end:g}",
                     "note": f"{title} ({how}, {tempo}; auto, check)"}
        print(f"[{n:02d}] start={start:>4}  end={'' if end is None else f'{end:g}':>7}  {tempo:>10}  {how:<24} {t.name}")

    with open(CUTS_CSV, "w", newline="", encoding="utf-8") as f:
        f.write(",".join(header) + "\n")
        for c in comments:
            f.write(c + "\n")
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        for key in sorted(rows, key=int):
            w.writerow({k: rows[key].get(k, "") for k in header})
    print(f"wrote {CUTS_CSV.relative_to(REPO)}")


if __name__ == "__main__":
    main()
