"""Replace the vanilla mission-music Sound Cues listed in build/import/cues.csv (prepare_tracks.py --rotate)
with copies of master cues that play every wave of a category in random order.

Runs inside Unreal Editor 4.27 like ue_import.py, after it:
  - Editor: File > Execute Python Script... > tools/ue_cues.py
  - Commandlet (editor closed):
      UE4Editor-Cmd.exe <path>/FSD.uproject -run=pythonscript -script=<repo>/tools/ue_cues.py

UE 4.27 Python cannot wire Sound Cue nodes, so the masters are made by hand once (docs/rotation.md):
  RFB_<category>_once   Random -> one Wave Player per wave -> Output
  RFB_<category>_loop   Looping -> Random -> one Wave Player per wave -> Output
in /Game/_RFB/Masters (or anywhere in the project under that name). The script checks each master, points its
Wave Players at the category's waves if they play other ones, turns on Randomize Without Replacement and
turns off Wave Player looping. Then for every cue path it deletes the vanilla cue (the all-assets template
has them), duplicates the master there and sets SoundClass, submix, Priority and VolumeMultiplier from
cues.csv, plus bExcludeFromRandomNodeBranchCulling so the engine never prunes the Random node to one branch.
RFB_DRY_RUN=1 only checks the masters and prints what would change.
"""
import csv
import os

import unreal

INDEFINITELY_LOOPING = 10000.0  # Duration of a cue that loops until stopped

try:
    REPO = os.environ.get("RFB_REPO") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    REPO = os.environ.get("RFB_REPO", "")
CUES = os.path.join(REPO, "build", "import", "cues.csv")
DONE = os.path.join(REPO, "build", "import", "cues.done")  # collect_cooked.py refuses to pack cues without it
DRY_RUN = os.environ.get("RFB_DRY_RUN", "").strip() not in ("", "0")
ASSETS = unreal.EditorAssetLibrary


def log(msg):
    unreal.log("[rfb-battle-music] " + msg)


def warn(msg):
    unreal.log_warning("[rfb-battle-music] " + msg)


def set_prop(obj, name, value):
    try:
        obj.set_editor_property(name, value)
        return True
    except Exception as e:  # property names differ slightly between engine versions
        warn("{}: could not set {}: {}".format(obj.get_name(), name, e))
        return False


def asset_path(obj):
    """/Game/Dir/Name for an asset, a soft pointer value or an object path string."""
    if obj is None:
        return None
    text = obj.get_path_name() if isinstance(obj, unreal.Object) else (
        obj.export_text() if hasattr(obj, "export_text") else str(obj))
    text = text.strip().strip("'\"")
    return text.split(".", 1)[0] if text.startswith("/") else None


def load(path):
    return ASSETS.load_asset(path) if path and ASSETS.does_asset_exist(path) else None


def find_master(path):
    """The master at its path, else a SoundCue of that name anywhere in the project."""
    master = load(path)
    if master:
        return master
    name = path.rsplit("/", 1)[1]
    for data in unreal.AssetRegistryHelpers.get_asset_registry().get_assets_by_class("SoundCue"):
        if str(data.asset_name) == name:
            return data.get_asset()
    return None


def nodes_of(cue):
    """Sound nodes of a cue by class name. Nodes are subobjects of the cue; looked up by class name because
    not every USoundNode subclass is exposed to Python."""
    nodes = {}
    for obj in unreal.ObjectIterator(getattr(unreal, "SoundNode", unreal.Object)):
        if obj.get_outer() == cue and obj.get_class().get_name().startswith("SoundNode"):
            nodes.setdefault(obj.get_class().get_name(), []).append(obj)
    return nodes


def wave_of(player):
    for name in ("sound_wave_asset_ptr", "sound_wave"):
        try:
            return asset_path(player.get_editor_property(name))
        except Exception:
            continue
    return None


def set_wave(player, wave):
    for name in ("sound_wave_asset_ptr", "sound_wave"):
        try:
            player.set_editor_property(name, wave)
            return True
        except Exception:
            continue
    warn("{}: could not set its Sound Wave".format(player.get_name()))
    return False


def check_master(path, loops, waves):
    """Problems with a master (empty list = usable); fixes what a script can fix unless DRY_RUN."""
    kind = "Looping -> Random -> Wave Players -> Output" if loops else "Random -> Wave Players -> Output"
    master = find_master(path)
    if master is None:
        return [path + " does not exist (make it by hand: " + kind + ")"], None
    problems = []
    nodes = nodes_of(master)
    randoms = nodes.get("SoundNodeRandom", [])
    loopers = nodes.get("SoundNodeLooping", [])
    players = nodes.get("SoundNodeWavePlayer", [])
    if len(randoms) != 1:
        problems.append("{} Random nodes, needs exactly one".format(len(randoms)))
    else:
        try:  # ChildNodes may not be readable from Python; the wiring is then left to the in-game test
            wired = len([n for n in randoms[0].get_editor_property("child_nodes") if n])
            if wired != len(players):
                problems.append("Random has {} inputs wired, needs all {} Wave Players".format(wired, len(players)))
        except Exception:
            pass
    if loops and not loopers:
        problems.append("no Looping node between Random and Output")
    elif loops and len(randoms) == 1:
        try:
            inputs = [n for n in loopers[0].get_editor_property("child_nodes") if n]
            if len(inputs) != 1 or inputs[0] != randoms[0]:
                problems.append("Random is not wired into the Looping node")
        except Exception:
            pass
    if not loops and loopers:
        problems.append("has a Looping node, this master must play once")
    try:
        duration = master.get_editor_property("duration")
    except Exception as e:
        duration = None
        warn("{}: cannot read duration ({}), wiring not checked".format(master.get_name(), e))
    if duration is not None and duration <= 0:
        problems.append("nothing is wired to Output")
    elif duration is not None and loops and duration < INDEFINITELY_LOOPING:
        problems.append("the Looping node is not wired between Random and Output")
    if len(players) != len(waves):
        problems.append("{} Wave Players, needs {} (one per wave)".format(len(players), len(waves)))
    if problems:
        return ["{} ({}): {}".format(path, kind, p) for p in problems], master

    missing = [w for w in waves if not ASSETS.does_asset_exist(w)]
    if missing:
        return ["wave not in the project (run ue_import.py first): " + w for w in missing], master
    wave_objs = [ASSETS.load_asset(w) for w in waves]
    current = [wave_of(p) for p in players]
    if sorted(c or "" for c in current) != sorted(waves):
        log("{}: Wave Players play {} - pointing them at the {} waves of the category".format(
            master.get_name(), ", ".join(sorted((c or "nothing").rsplit("/", 1)[-1] for c in current)),
            len(waves)))
        if not DRY_RUN:
            for player, wave in zip(sorted(players, key=lambda p: p.get_name()), wave_objs):
                set_wave(player, wave)
    if not DRY_RUN:
        set_prop(randoms[0], "randomize_without_replacement", True)
        for looper in loopers:
            set_prop(looper, "loop_indefinitely", True)
        for player in players:
            set_prop(player, "looping", False)
        ASSETS.save_loaded_asset(master, False)
    return [], master


def apply_cue_props(cue, row):
    sound_class = load(row["sound_class"])
    if row["sound_class"] and sound_class is None:
        warn("SoundClass {} not in the project - copy Audio/SoundControl from the template".format(row["sound_class"]))
    set_prop(cue, "sound_class_object", sound_class)
    submix = load(row["submix"])
    if row["submix"] and submix is None:
        warn("submix {} not in the project - copy Audio/SoundControl from the template".format(row["submix"]))
    set_prop(cue, "sound_submix_object", submix)
    set_prop(cue, "priority", float(row["priority"]))
    set_prop(cue, "volume_multiplier", float(row["volume"]))
    set_prop(cue, "exclude_from_random_node_branch_culling", True)


def main():
    if not os.path.isfile(CUES):
        raise RuntimeError("{} not found - run `python tools/prepare_tracks.py build --rotate ...` first "
                           "(or set RFB_REPO to the repo path)".format(CUES))
    with open(CUES, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    log("{} cues from {}{}".format(len(rows), CUES, " (dry run)" if DRY_RUN else ""))
    unreal.SystemLibrary.collect_garbage()  # nodes deleted in an open editor must not count

    masters, problems = {}, []
    for row in rows:
        if row["master"] in masters:
            continue
        found, master = check_master(row["master"], row["loops"] == "true", row["waves"].split())
        problems += found
        masters[row["master"]] = master
    if problems:
        raise RuntimeError("master cues are not ready (see docs/rotation.md):\n  " + "\n  ".join(problems))

    with unreal.ScopedSlowTask(len(rows), "Replacing mission-music cues") as slow:
        slow.make_dialog(True)
        for row in rows:
            slow.enter_progress_frame(1, row["cue_path"])
            master, path = masters[row["master"]], row["cue_path"]
            vanilla = ASSETS.does_asset_exist(path)
            log("{} {} <- {}".format("replace" if vanilla else "create", path, master.get_name()))
            if DRY_RUN:
                continue
            if vanilla and not ASSETS.delete_asset(path):
                raise RuntimeError("could not delete " + path)
            cue = ASSETS.duplicate_loaded_asset(master, path)
            if cue is None:
                raise RuntimeError("could not duplicate {} to {}".format(master.get_path_name(), path))
            apply_cue_props(cue, row)
            ASSETS.save_loaded_asset(cue, False)
    if not DRY_RUN:
        with open(DONE, "w", encoding="utf-8") as f:
            f.write("\n".join(r["cue_path"] for r in rows) + "\n")
    log("done: {} cues {}".format(len(rows), "checked" if DRY_RUN else "replaced and saved"))


main()
