# Музыка миссий в Deep Rock Galactic: разбор

Черновик для нового мода (рабочее имя RFB Battle Music). Источники: шаблон
[Audio-Modding-Template](https://github.com/DRG-Modding/Audio-Modding-Template)
(ветка `all-assets`, релиз U38P10, март 2024), раздел «Kraeus' Music Breakdown» из
[гайда по аудиомодам на mod.io](https://mod.io/g/drg/r/drg-mods-a-comprehensive-guide-to-audio-modding),
[страница Soundtrack на вики](https://deeprockgalactic.wiki.gg/wiki/Soundtrack) и описания
существующих музыкальных модов. Длительности сняты из cooked-ассетов шаблона
(`Duration` в SoundWave) тем же способом, что и в `scan_slots.py` старого мода.

## Чем это отличается от джукбокса

У джукбокса `BP_JukeBox` играет SoundWave напрямую. У музыки миссий между игрой и
звуком стоит **Sound Cue**: один кью на одну песню, внутри Wave Player → Output с
SoundClass. Игра выбирает кью, кью играет свою волну. Отсюда два способа замены:

| Способ | Что делаем | Плюсы | Минусы |
|---|---|---|---|
| **Замена волн** (как в джукбоксе) | Кладём свои SoundWave с ванильными именами в `AudioFiles/` | Пайплайн старого мода почти без изменений, мод чисто звуковой, auto-verified | Ровно один трек на слот, зацикливание и длительность решает ванильный кью |
| **Замена кью** | Пересобираем `*_Cue` с Random/Looping-нодами и своими волнами в `_RFB/` | Сколько угодно треков на событие, случайный выбор, свои петли | Нужна ветка `all-assets`, исключать из cook `AudioFiles/` и `SoundControl/`, скриптовать граф кью в UE; у каждого клиента свой случайный трек |

Открытый вопрос, который решает всё остальное: **обрезает ли игра музыку миссий по
ванильной длительности**, как джукбокс (тот брал её из `AssetRegistry.bin`). Для кью
это не доказано ни в одну сторону. Есть косвенный намёк: в комментариях к модам
пишут, что заменённая боевая музыка «не зацикливается и возвращается к спокойной
посреди боя». Запасной вариант тот же, что в
джукбоксе: рендерить каждый слот ровно в ванильную длину (`--fit-slots`).

## Кто зацикливает волну

В таблице имён каждого кью флаг `bLooping` сериализуется только когда он включён у Wave Player.
По этому признаку (шаблон U38P10) **почти все кью миссий играют волну по кругу, пока игра не
остановит сам кью**: все 14 эмбиентных, все 3 босса, все 6 эвакуации, machine event, экран между
этапами Deep Dive, экран загрузки, 7 петель `pressure` и 5 из 10 кью роя (`St_DOTSA_Cue`,
`St_MorkiteIsADancer_Cue`, `St_MountainBlaster_Cue`, `St_NotTheBees_Cue`, `St_SpaceFire_Cue`).
Один раз играют только `St_EndMission_Completed_Cue` (экран статистики) и пять кью роя
(`St_Tick_Cue`, `St_Boss_wave_Cue`, `St_HoldMyBeard_Cue`, `St_Hole_Cue`, `St_Wave_Cue`).

Для мода это значит: трек в зацикленном слоте должен бесшовно замыкаться (фрагмент от дропа до
точки `end` на границе такта, без затухания), иначе каждый круг будет проваливаться в тишину.
Колонка `cue_loops` в `data/mission_slots.csv`; режим рендера выбирается по ней.

## Категории и слоты

SoundClass задан в кью, у волн его нет. Все `*_Master_*` волны стриминговые
(`bStreaming`), флага `bLooping` ни у одной нет: петля делается нодой в кью.
Семь волн из `AudioFilesLooping/` не стриминговые, аудио лежит в `.uexp` (как
`TRJMusic` в джукбоксе). Это надо повторить при импорте. Машиночитаемая версия
этих таблиц: `data/mission_slots.csv`, её делает `tools/scan_slots.py`.

### Level: фоновая музыка в пещере (15 слотов, SoundClass `Music_Background`)

Играет в любой миссии как эмбиент, с паузами тишины между треками. Самые длинные
слоты в игре. Ванильные треки спокойные и атмосферные.

| Кью | Волна | Трек OST | Длина |
|---|---|---|---|
| `St_Alien_Cue` | `St_Alien_Master_1` | Fathomless Tomb | 9:04 |
| `St_Crawl_Cue` | `St_Crawl_Master_1` | Coward's Crossing | 8:09 |
| `St_ST_Cue` | `St_ST_Master_1` | The Only Way Out Is Through | 7:48 |
| `St_JourneyOfTheProspector_Cue` | `A_Quiet_Tomb_ST_Master_1` | Journey Of The Prospector | 6:45 |
| `St_AxeRunner_Cue` | `ST_AxeRunner_Master_3` | Let's Go Deeper | 6:42 |
| `St_Carp_Cue` | `St_Carp_Master_1` | Into The Abyss | 6:24 |
| `St_Slow_Cue` | `St_Slow_Master_1` | I am Lost | 5:56 |
| `St_Horror_Cue` | `St_Horror_Master_1` | A Matter of Skill and Ammunition | 5:51 |
| `St_Pod_Cue` | `St_Pod_Master_1` | Principle of Darkness | 5:49 |
| `St_Deep_Cue` | `St_Deep_Master_1` | The Descent | 5:36 |
| `St_ValleyOfDeath_Cue` | `ST_ValleyOfDeath_Master_3` | Deceived by Light | 5:15 |
| `St_LOTD_Cue` | `ST_LOTD_Master_3` | Echoes From The Past | 4:57 |
| `St_Cold_Cue` | `ST_Cold_Master_3` | Absolute Zero | 4:50 |
| `St_Clutch_Cue` | `St_Clutch_Master_1` | Karl's End | 4:32 |

Отдельно в той же папке: `LoadingScreenMusic_Cue` (загрузка миссии) играет **ту же**
волну `St_Deep_Master_1`, что и `St_Deep_Cue`. Заменив волну, меняем и загрузку, и
эмбиент. `St_Goodbye_SpaceRig_Cue` (`St_Goodbye_Master_1`, Ode to the Fallen, 5:09,
SoundClass `Music_MemorialHall`) звучит только в Мемориальном зале Space Rig, к
миссиям не относится.

### Wave, одиночные: объявленный рой (10 слотов, SoundClass `Music_Action`)

Включается, когда Mission Control объявляет рой («They're coming!»). Играет один раз
и затихает. Это и есть «боевая музыка» в обычном понимании.

| Кью | Волна | Трек OST | Длина |
|---|---|---|---|
| `St_Tick_Cue` | `St_Tick_Master_1` | Petrified Fury | 3:45 |
| `St_Boss_wave_Cue` | `St_Boss_Master_1` | They're Here! | 3:14 |
| `St_NotTheBees_Cue` | `ST_NotTheBees_Master_3` | A Distant Terror | 2:48 |
| `St_MountainBlaster_Cue` | `ST_MountainBlaster_Master_3` | In the Belly of the Beast | 2:43 |
| `St_Hole_Cue` | `St_Hole_Master_1` | The Shadows are Moving | 2:33 |
| `St_MorkiteIsADancer_Cue` | `ST_MorkiteIsADancer_Master_3` | Axes Out | 2:28 |
| `St_SpaceFire_Cue` | `ST_SpaceFire_Master_3` | RUN! | 2:27 |
| `St_HoldMyBeard_Cue` | `St_HoldMyBeard_Master_1` | Hold My Beard | 2:15 |
| `St_Wave_Cue` | `St_Wave_Master_1` | Attack of the Glyphids | 2:13 |
| `St_DOTSA_Cue` | `ST_DOTSA_Master_3` | Dance of the Dreadnought | 2:12 |

«Dance of the Dreadnought» вопреки названию играет на рой, а не на дредноута.

### Wave, зацикленные: затяжные бои (7 слотов, SoundClass `Music_Action`)

Петля на событиях, где рой не прекращается: откачка на On-Site Refining, Ommoran
Heartstone в Escort, а по данным мода Custom Soundtrack также Power Stations
(Industrial Sabotage), Caretaker, Lithophage Meteorite, Rival bomb, Data Deposit.
Волны не стриминговые, аудио встроено в `.uexp`.

| Кью | Волна | Трек OST | Длина петли |
|---|---|---|---|
| `PetrifiedFury_Looping_Cue` | `PetrifiedFury_Looping_1` | Petrified Fury | 3:31 |
| `Theyre_Here_Looping_Cue` | `Theyre_Here_Looping_1` | They're Here! | 2:58 |
| `A_Distant_Terror_Looping_Cue` | `A_Distant_Terror_Looping_01` | A Distant Terror | 2:32 |
| `MorkiteIsADancer_Looping_1_Cue` | `MorkiteIsADancer_Looping_1` | Axes Out | 2:22 |
| `SpaceFire_Looping_1_Cue` | `SpaceFire_Looping_1` | RUN! | 2:17 |
| `MountainBlaster_Looping_1_Cue` | `MountainBlaster_Looping_1` | In the Belly of the Beast | 2:12 |
| `Dance_Of_The_Dreadnaught_Looping_Cue` | `Dance_Of_The_Dreadnaught_Looping_01` | Dance of the Dreadnought | 2:09 |

Для петли трек должен бесшовно замыкаться: срез по тактам, без затухания в конце.

### EndWave: эвакуация (6 слотов, SoundClass `Music_Endwave`)

Бег к дроп-поду в Mining, Egg Hunt, Escort, Elimination; Refining после 100 %;
Salvage на обеих обороне точек (вторая песня идёт до отлёта пода); ожидание пода.

| Кью | Волна | Трек OST | Длина |
|---|---|---|---|
| `St_SW_Edited_A_01_Cue` | `St_SW_Master_1` | March of the Brave | 5:17 |
| `St_OperasFascination_Cue` | `ST_OperasFascination_Master_3` | Follow Molly | 4:34 |
| `St_SabotageOfMolly_Cue` | `ST_SabotageOfMolly_Master_3` | I Welcome The Darkness | 3:57 |
| `St_RobotGetAway_EditedA_01_Cue` | `St_RobotGetaway_Master_1` | Robot Getaway | 2:56 |
| `St_Marching_Edited_A_2_Cue` | `St_Marching_Master_1` | Leave No Dwarf Behind | 2:36 |
| `St_WhereTheyReallyDare_Cue` | `ST_WhereTheyReallyDare_Master_3` | The Last Ascent | 2:01 |

В той же папке лежат `St_Action_Master_1` (2:18, Beneath the Crust) и его копия
`St_Action_Edited_B_3`. Первую играет `St_EndMission_Completed_Cue` (SoundClass
`Music_Menu_Endscreen`) на экране статистики после миссии; копия ни одним кью не
используется.

### Boss: дредноуты (3 слота, SoundClass `Music_Boss`)

Только Elimination и любой активный дредноут.

| Кью | Волна | Трек OST | Длина |
|---|---|---|---|
| `St_InsterstellarNightmares_Cue` | `ST_InterstellarNightmares_Master_3` | Interstellar Nightmares | 4:30 |
| `St_Boss_Music_Cue` | `St_Nova_Master_1` | Horrors of Hoxxes | 3:52 |
| `St_Stalker_Cue` | `St_Stalker_Master_1` | Fighting the Shadows | 2:58 |

Core Stone (сезон 5), по скану пака 1.40 от 25.10.2026: кью `Boss/RC_Rift_Looping_1_Cue`
(SoundClass `Music_Boss`, сабмикс `MusicSubmix`, петля) играет волну `RC_Rift_Master3_Looping`
(2:15, не стриминговая, аудио в `.uexp`). Рядом лежат ещё шесть волн `RC_Rift_*` и
`RC_DRGS5_Rift_Final_V4_Looping_*`, но их не играет ни один кью: это черновики, в `common.py` они
помечены как `unused`. В шаблоне U38P10 Core Stone ещё нет.

### Остальное (по одному слоту)

| Где | Кью | Волна | Трек | Длина |
|---|---|---|---|---|
| Machine Event | `ST_GameEventA_Cue` | `ST_GameEvent_Master_1` | The Core Infuser | 1:27 |
| Загрузка миссии | `LoadingScreenMusic_Cue` | `St_Deep_Master_1` (общая с эмбиентом) | The Descent | 5:36 |
| Экран статистики | `St_EndMission_Completed_Cue` | `St_Action_Master_1` | Beneath the Crust | 2:18 |
| Между этапами Deep Dive | `St_DeepDives_InbetweenScreen_Cue` | `ST_Where_They_Really_DareDLoop_1` | The Last Ascent (отрывок) | 0:52 |
| Найден ящик или потерянный груз | `DiscoverMusic_1` | | джингл | 0:12 |

Space Rig (`SpaceRigMusic/`): `Ambience_Music_Cue` → `St_Ambience_Master_1`
(The Deep Dive, 2:30), праздничные и Anniversary-наборы, пивная дискотека, аркада.
Джукбокс уже закрыт старым модом.

## Бюджет слотов при замене волн

| Категория | Слотов | Ванильная длина |
|---|---|---|
| Level (эмбиент) | 14 (+ общая волна загрузки) | 4:32 – 9:04 |
| Wave одиночные (рой) | 10 | 2:12 – 3:45 |
| Wave петли (затяжной бой) | 7 | 2:09 – 3:31 |
| EndWave (эвакуация) | 6 | 2:01 – 5:17 |
| Boss (дредноут + Core Stone) | 4 | 2:15 – 4:30 |
| Machine Event | 1 | 1:27 |
| Экран статистики | 1 | 2:18 |
| Deep Dive, между этапами | 1 | 0:52 |
| **Итого** | **44** | |

Треки из плейлиста джукбокса в основном 2:00 – 3:00: они естественно ложатся на
рой, петли, эвакуацию и босса (26 слотов). Эмбиент-слоты на 5 – 9 минут под них не
подходят: либо повтор с дропа, как в джукбоксе, либо оставить ваниль, либо собирать
кью с несколькими треками подряд.

## Как игра выбирает трек

По C++-заголовкам игры ([FSD-Template](https://github.com/DRG-Modding/FSD-Template), `Source/FSD/Public/`) и
библиотекам из `Audio.zip` шаблона (U38P10):

- `UMusicLibrary` (data asset) — массив `MusicCues` и категория. `UMusicManager::PlayLibrary(library,
  musicIndex)` играет кью библиотеки **по номеру**, вызывает его только хост. `AMusicReplicator` раздаёт
  играющий кью всем клиентам, поэтому в ванили у всей команды звучит одно и то же.
- `AProceduralSetup::StartMusicAndAmbient(int32 Music)` получает один номер при генерации уровня.
- Библиотеки в `SoundControl/`: `ML_LevelMusic` (14 кью фона пещеры), `ML_LevelTutorial` (`St_Carp_Cue`,
  `St_Horror_Cue`), `ML_EndWave` (6 кью эвакуации), `ML_BossMusic` (7 петель **затяжного боя** из
  `Music_Wave/CueLooping`, не дредноуты). Для 10 кью роя библиотеки нет, их выбирает блюпринт.

В игре это слышно так: за миссию рой и фон пещеры играют по одному и тому же кью, то есть по одному треку
(проверено на 1.0.0). Чтобы треки менялись внутри миссии, в кью должно быть несколько волн. В игре уже
есть такие кью: `SpaceRigMusic/Ambience_Music_Christmas_Cue` устроен как Looping → Random → Modulator →
Wave Players. Как это сделано в моде: [rotation.md](rotation.md).

Свойства кью, которые копия должна сохранить (`data/mission_cues.csv`, пишет `scan_slots.py`): SoundClass,
сабмикс `SubMixes/MusicSubmix` (у петель затяжного боя его нет), `Priority` (рой и эвакуация 50, фон 100,
у `St_SpaceFire` и его петли 1.1, у петель затяжного боя по умолчанию) и `VolumeMultiplier` от 0,45 до 1,4.
Если громкость в ассете не записана, это значение `USoundCue` по умолчанию 0,75, а не 1,0.

## Что ещё не известно и как узнать

1. **Обрезка по ванильной длительности.** Тест в игре: заменить одну волну роя
   треком заметно длиннее и короче ванили и послушать, где он кончается.
2. **Актуальный список кью для 1.40.** Снят с живого пака 25.10.2026: к списку шаблона
   добавился один слот Core Stone (см. Boss), остальные волны и длительности не изменились.
3. **Что игра делает с фоном пещеры во время роя:** глушит и продолжает, перезапускает кью или ставит
   его на паузу. Выбор кью разобран выше (один номер на миссию); привязки к биому в коде не видно.
4. **Совместимость.** Пользователи пишут, что некоторые моды боевой музыки глушат
   другие звуковые моды во время игры музыки. Скорее всего это следствие
   упаковки `SoundControl/` в пак; наш пайплайн её не трогает.

## Альтернатива без сборки пака

Мод [Custom Soundtrack](https://mod.io/g/drg/m/custom-soundtrack) (Verified, 1.40)
играет mp3/m4a/wav из папки `FSD/Mods/CustomSoundtrack/Music/<вид>/`, следуя
музыкальным состояниям игры: Ambient, Swarm, Pressure (по событиям), Machine,
Dreadnought, CoreRift, Extraction, Loading, RigAmbient, Memorial, Jukebox. Шаффл,
кроссфейды, громкость по треку, песни на биом. Это готовый плеер, а не свой мод:
подходит, если цель просто слышать свою музыку. Свой пак нужен, если хочется
раздать друзьям одной подпиской на mod.io и не зависеть от чужого мода.
