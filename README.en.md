# RFB Battle Music

[Русский](README.md) · **English**

A **Deep Rock Galactic** mod that replaces the mission music with custom tracks: swarms, long fights,
extraction, Dreadnoughts and the Core Stone rift, the Machine Event, the loading and statistics screens and
the cave ambient.

- **Audio only.** The pak contains nothing but SoundWave assets with vanilla names; cues and blueprints are
  untouched.
- **Client-side.** Only players who have the mod hear the music.
- **Every track starts at its drop**, and the long-fight loops wrap back to the drop.

A follow-up to [RFB Jukebox](https://github.com/realfamousbae/drg-rfb-jukebox-music): same pipeline,
different part of the game.

## How it works

Mission music is played by Sound Cues in `Content/Audio/Music/**`: one cue per song, with a Wave Player and
a single SoundWave inside. The mod replaces those SoundWaves with its own under the same paths and names; the
cues stay vanilla and keep deciding what plays when. Categories, cues and durations in detail (Russian):
[docs/mission-music.md](docs/mission-music.md).

| Category | Slots | Vanilla length | Loop | When it plays |
|---|---|---|---|---|
| `swarm` | 10 | 2:12 – 3:46 | 5 of 10 | announced swarm |
| `pressure` | 7 | 2:10 – 3:32 | all | long fights |
| `extraction` | 6 | 2:01 – 5:17 | all | run to the drop pod |
| `boss` | 4 | 2:15 – 4:30 | all | Dreadnoughts, Core Stone rift |
| `machine` | 1 | 1:27 | yes | Machine Event |
| `endscreen` | 1 | 2:19 | no | mission statistics screen |
| `deepdive` | 1 | 0:52 | yes | between Deep Dive stages |
| `ambient` | 14 | 4:32 – 9:05 | all | cave background; `St_Deep_Master_1` is also the loading screen |

What is known and what isn't yet:

- Mission waves carry no SoundClass or attenuation: those live on the cue. The `*_Master_*` waves are
  streamed, the seven `pressure` loops are not (their audio sits in `.uexp`). The import reproduces these
  flags.
- Almost every mission cue **loops its wave** until the game stops the cue: ambient, boss, extraction,
  Machine Event, Deep Dive and half of the swarm cues. Only the statistics screen and five swarm cues play
  once. So looping slots get a seamless loop from the drop to the `end` point in `cuts.csv`.
- **Not verified in game yet**: whether the game cuts mission music at the vanilla duration, as it does for
  the jukebox, and whether the loops wrap without a gap. To check: «ЧСВ» in the `St_Tick_Master_1` swarm
  (135 s vs 226 s vanilla), Refinery pumping or the Ommoran in Escort. If it is cut, build with `-FitSlots`.
- `data/mission_slots.csv` was scanned from the live 1.40 game pak (2026-10-25). Compared to the U38P10
  template, only the Core Stone rift slot was added.

## Layout

```
data/
  playlist.tsv         tracklist: artists, title, duration, YouTube link, clip trim
  cuts.csv             where each track starts (hook/drop) and where the fragment ends
  mission_slots.csv    every mission-music wave: category, cue, vanilla duration and flags
  mapping.csv          which track goes into which slot (example: mapping.example.csv)
docs/
  mission-music.md     how the mission music system works
  tracklist.md         track-to-slot layout with reasons
tools/
  scan_slots.py        waves and cues from the game pak (repak unpack) or the template's Audio.zip
  fetch_tracks.py      downloads playlist.tsv tracks into tracks/ (WAV 24-bit / 48 kHz)
  find_cuts.py         suggests start/end for cuts.csv from the loudness curve and tempo
  prepare_tracks.py    loudness, cuts, loops, per-slot layout -> build/import/
  ue_import.py         imports the WAVs into the UE project as SoundWaves with vanilla flags
  collect_cooked.py    takes only the slot assets from the cook
  build.ps1            everything in order: prepare -> import -> cook -> pak -> zip
modio/
  description.md       mod.io page texts and settings
  logo.png             mod.io cover image
tracks/                audio, not stored in git
CHANGELOG.md           version history
```

## Building

Requires Windows, **UE 4.27.2**, [Audio-Modding-Template](https://github.com/DRG-Modding/Audio-Modding-Template)
(with `PythonScriptPlugin` and `EditorScriptingUtilities` enabled in `FSD.uproject` and `Audio/SoundControl`
in Directories to never cook), [repak](https://github.com/trumank/repak), Python 3.8+ (standard library only),
ffmpeg and yt-dlp. The repo path must not contain spaces.

```
python tools/fetch_tracks.py
powershell -ExecutionPolicy Bypass -File tools\build.ps1 -Project <template>\FSD.uproject -Repak <repak.exe>
```

Output: `dist\RFB_BattleMusic_P.pak` and `dist\RFB_BattleMusic.zip` for mod.io. Close the Unreal Editor
before building. The script finds UE 4.27 through the Epic Games Launcher, or pass `-UERoot`. Resume from a
later step with `-SkipPrepare`, `-SkipImport`, `-SkipCook`.

Options:

- `-Categories swarm,pressure,extraction,boss`: which categories to replace; the rest keep the vanilla
  music. Default: every mission category, including `ambient`.
- `-FitSlots`: render every slot at exactly its vanilla length (if the game cuts music there).
- `-Volume 1.5`: volume multiplier on every wave, if the music is quieter than vanilla in game.
- `-TargetLufs -11`: loudness target. Vanilla exports can be measured with
  `python tools/prepare_tracks.py measure <files>`.

For local testing, install the `.pak` with [mint](https://github.com/trumank/mint). Remove that test copy
before playing with the mod.io version, or the music ends up in two paks.

New version: an entry in `CHANGELOG.md`, the zip uploaded to the same mod on mod.io (Files → Upload file) and
a GitHub release `vX.Y.Z` with `RFB_BattleMusic-X.Y.Z.zip` and its SHA-256.

### Tracks

- `fetch_tracks.py` downloads the best audio from the link in `playlist.tsv`. Row N becomes
  `tracks/NN Artists - Title.wav`. The `trim` column (`START-END`, seconds) cuts a music video down to the
  song.
- `fetch_tracks.py` does not download a row with the same link and trim twice: one song can sit in several
  slots with different fragments, so the file is copied.
- `cuts.csv`: `start` is where the track begins (hook or drop), `end` is where the fragment stops (empty =
  to the end). For looping slots `end` is the loop point on a bar line, and the seconds before the drop are
  joined onto the tail so a repeat lands back on the drop without a seam. `python tools/find_cuts.py`
  suggests values from the bass curve and tempo (`--profile N` prints a track's curve); fine-tune by ear.
- `mapping.csv`: a track per slot, by wave name or playlist row number. Slots without a row are filled
  round-robin with the remaining tracks.

## After a DRG patch

```
repak unpack -i FSD/Content/Audio/Music -o <dir> "<DRG>\FSD\Content\Paks\FSD-WindowsNoEditor.pak"
python tools/scan_slots.py <dir>\FSD\Content\Audio\Music
git diff data/mission_slots.csv
```

If the waves and durations didn't change, there's no need to rebuild.

---

All music belongs to its respective artists and labels. The mod is hidden and meant for friends.
