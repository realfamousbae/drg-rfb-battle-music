"""Shared helpers for the RFB Battle Music tooling (plain Python 3.8+, no dependencies)."""
import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
BUILD = REPO / "build"

SLOTS_CSV = DATA / "mission_slots.csv"
MAPPING_CSV = DATA / "mapping.csv"
CUTS_CSV = DATA / "cuts.csv"
IMPORT_DIR = BUILD / "import"
MANIFEST_CSV = IMPORT_DIR / "manifest.csv"

# Properties copied from the vanilla SoundWave so the replacement behaves the same in game.
# Mission music waves carry no SoundClass/attenuation themselves (the Sound Cue does), but the
# columns stay so a scan of a newer game build can still record them.
WAVE_PROPS = ["sound_class", "attenuation", "volume", "compression_quality", "looping", "streaming"]
SLOT_FIELDS = ["asset_path", "name", "category", "cue", "cue_loops", "duration_sec", "shared_with"] + WAVE_PROPS

# Where each vanilla wave is played. The folder of the wave decides the category; a few waves are
# special-cased because the game reuses them (see docs/mission-music.md).
#   ambient     Music_Level: cave background music during every mission
#   swarm       Music_Wave single cues: a Mission Control announced swarm, plays once
#   pressure    Music_Wave looping cues: sustained fights (Refinery pumping, Ommoran, Caretaker, ...)
#   extraction  Music_EndWave: run to the drop pod / wait for it
#   boss        Boss: Dreadnoughts (Elimination), Core Stone rift
#   machine     Music_SpecialEvents: Machine Event
#   endscreen   mission statistics screen
#   deepdive    screen between Deep Dive stages
#   loading     mission loading screen (shares its wave with an ambient slot)
#   memorial    Space Rig Memorial Hall (lives in Music_Level but is not mission music)
#   spacerig    Space Rig ambience, holiday sets, arcade, promotion fanfares
#   jingle      short stingers (treasure found, player down) - never replaced
CATEGORY_BY_FOLDER = {
    "Music_Level/AudioFiles": "ambient",
    "Music_Wave/AudioFilesSingle": "swarm",
    "Music_Wave/AudioFilesLooping": "pressure",
    "Music_EndWave/AudioFiles": "extraction",
    "Boss/AudioFiles": "boss",
    "Boss": "boss",
    "Music_SpecialEvents/AudioFiles": "machine",
    "Music_Menu": "deepdive",
    "SpaceRigMusic": "spacerig",
}
CATEGORY_BY_NAME = {
    "St_Action_Master_1": "endscreen",
    "St_Action_Edited_B_3": "unused",
    "DeepDives_InbetweenScreen_Music": "unused",
    "St_Goodbye_Master_1": "memorial",
    "DiscoverMusic_1": "jingle",
}
# wave -> other cue that also plays it
SHARED_WITH = {"St_Deep_Master_1": "LoadingScreenMusic_Cue (loading)"}

# Categories a default build replaces. The rest keep the vanilla music unless asked for.
DEFAULT_CATEGORIES = ["swarm", "pressure", "extraction", "boss", "machine", "endscreen", "deepdive", "ambient"]
MISSION_CATEGORIES = ["ambient", "swarm", "pressure", "extraction", "boss", "machine", "endscreen", "deepdive"]


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if not (next(iter(r.values())) or "").startswith("#")]


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def category_of(asset_path, name):
    """Category for a wave under /Game/Audio/Music/<folder>/<name>."""
    if name in CATEGORY_BY_NAME:
        return CATEGORY_BY_NAME[name]
    rel = asset_path[len("/Game/Audio/Music/"):] if asset_path.startswith("/Game/Audio/Music/") else ""
    folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
    while folder:
        if folder in CATEGORY_BY_FOLDER:
            return CATEGORY_BY_FOLDER[folder]
        folder = folder.rsplit("/", 1)[0] if "/" in folder else ""
    return "other"


def load_slots(categories=None):
    if not SLOTS_CSV.exists():
        die(f"{SLOTS_CSV.relative_to(REPO)} not found - run tools/scan_slots.py first")
    slots = read_csv(SLOTS_CSV)
    if not slots:
        die(f"{SLOTS_CSV.relative_to(REPO)} is empty")
    names = [s["asset_path"] for s in slots]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        die(f"duplicate slots in {SLOTS_CSV.name}: {', '.join(sorted(dupes))}")
    for s in slots:
        if not s["asset_path"].startswith("/Game/"):
            die(f"slot asset_path must start with /Game/: {s['asset_path']}")
    if categories is not None:
        unknown = set(categories) - set(MISSION_CATEGORIES) - {"memorial", "spacerig"}
        if unknown:
            die(f"unknown categories: {', '.join(sorted(unknown))} (known: {', '.join(MISSION_CATEGORIES)})")
        slots = [s for s in slots if s["category"] in categories]
    return slots
