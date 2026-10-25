# Проверка мода на Windows

Что нужно на машине: UE 4.27.2, Audio-Modding-Template (как для джукбокса), repak, Python 3.8+, ffmpeg,
yt-dlp, mint для установки пака. Путь к репозиторию без пробелов.

## 1. Слоты с живого пака

```
repak unpack -i FSD/Content/Audio/Music -o C:\tmp\drg-music "<DRG>\FSD\Content\Paks\FSD-WindowsNoEditor.pak"
python tools\scan_slots.py C:\tmp\drg-music\FSD\Content\Audio\Music
git diff data\mission_slots.csv
```

Список снят с пака 1.40 25.10.2026, Core Stone (`RC_Rift_Master3_Looping`) уже в `mapping.csv`. Если после
патча появятся новые волны, они станут слотами без строки в `mapping.csv` и заполнятся по кругу. Решить, что
в них ставить, или вписать `vanilla`.

## 2. Треки и сборка

```
python tools\fetch_tracks.py
powershell -ExecutionPolicy Bypass -File tools\build.ps1 -Project <template>\FSD.uproject -Repak <repak.exe>
```

На выходе `dist\RFB_BattleMusic_P.pak`. Для первого теста можно собрать только бой:
`-Categories swarm,pressure,boss`.

## 3. Тесты в игре

Поставить пак через mint, зайти в миссию (удобно Elimination или On-Site Refining: там и рой, и петли, и босс).

1. **Обрезка по длине.** Слот `St_Tick_Master_1` (ЧСВ, у нас 135 с против ванильных 226 с) и
   `St_HoldMyBeard_Master_1` (гетто район, 138 с против 136 с). Если рой дольше трека, слышно ли,
   что трек кончился и наступила тишина, или игра сама затухает по событию? Если игра режет ровно по
   ванильной длине, пересобрать с `-FitSlots`.
2. **Швы петель.** Откачка на Refining или Ommoran в Escort: петли `pressure` должны возвращаться на
   дроп без провала. Эмбиент в пещере: не проваливается ли музыка в тишину на стыке.
3. **Громкость.** Сравнить с ванилью на слух, при необходимости `-Volume 1.5` или другой `-TargetLufs`.
   «Девочка снюс» заведомо тише на 4 дБ.
4. **Экраны.** Загрузка миссии (Грустный реп), статистика (А МОЖЕТ ДА), Deep Dive между этапами (Фотки).
5. **Другие звуковые моды** не должны глохнуть во время музыки: признак того, что в пак попал
   `SoundControl`.

Итоги записать в CHANGELOG или сюда, точки в `data/cuts.csv` править по слуху и пересобирать.
