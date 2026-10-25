# Публикация за один проход

Порядок для v1.0.0 и для обновлений. Части «Claude» делаются по команде в чате, части «ты» руками.

Что уже готово к проходу:
- `dist\RFB_BattleMusic.zip` и `dist\RFB_BattleMusic-1.0.0.zip` (один и тот же файл), SHA-256 в `dist\sha`;
- тексты и настройки страницы: [description.md](description.md);
- описание релиза для GitHub: `dist\release_notes.md`, история версий: [CHANGELOG.md](../CHANGELOG.md);
- ТЗ обложки: [cover-brief.md](cover-brief.md). Сама обложка `modio/logo.png` пока за тобой.

## 1. Git и GitHub (Claude)
1. Влить ветку в `main`, запушить.
2. Тег `v1.0.0`, GitHub-релиз «RFB Battle Music 1.0.0»: текст из `dist\release_notes.md`, файл
   `RFB_BattleMusic-1.0.0.zip`. Репозиторий публичный, так что этот zip сможет скачать любой. Джукбокс
   выложен так же; если не нужно, релиз без файла.

## 2. Убрать тестовую копию из mint (ты)
Иначе в игре окажутся две копии музыки.
- Открой mint (`X:\DRGModding\tools\mint\drg_mod_integration.exe`), отключи или удали локальный
  `RFB_BattleMusic_P.pak` и нажми Install. Если других модов в mint нет, можно Uninstall.
- Проверь `...\Deep Rock Galactic\FSD\Content\Paks`: если `mods_P.pak` остался, в нём не должно быть
  нашего пака (после Uninstall файла нет совсем).

## 3. Создать мод на mod.io (ты)
1. https://drg.mod.io → войти → **Add mod**.
2. Поля по [description.md](description.md): Logo (`modio/logo.png`), Name `RFB Battle Music`,
   Summary и Description из блоков файла, Tags только `Audio`, Visibility **Hidden**.
3. Сохранить.

## 4. Загрузить файл (ты)
1. **Files → Upload file**, файл `dist\RFB_BattleMusic.zip` (~139 МБ).
2. Version `1.0.0`, Changelog `First release`. Game Version `1.40`, Required `Optional`, если форма спросит.
3. Дождаться окончания загрузки и проверки.

## 5. Доступ друзьям (ты)
Скрытый мод видят только участники команды: **Team** → пригласить друзей по нику на mod.io. Тем, кто уже
в команде джукбокса, нужно отдельное приглашение: команда у каждого мода своя.

## 6. Проверить в игре (ты)
1. **Subscribe** на странице мода, запустить DRG → **Modding**, включить мод.
2. Статус **Verified**, загрузился обычный сейв, а не Sandbox. Если не Verified, на основном сейве не играть,
   написать мне.
3. Миссия: фон пещеры, загрузка, статистика в конце. Если попадутся рой, затяжной бой или Core Stone,
   отметить для [windows-test.md](../docs/windows-test.md): обрывается ли трек, нет ли провала на стыке петли.
4. С другом: зайти в лобби друг к другу в обе стороны. Джукбокс и этот мод меняют разные волны и работают
   вместе.

## Обновление
Правка треков → `tools\build.ps1` → Claude копирует zip в `RFB_BattleMusic-<версия>.zip`, считает SHA,
пишет запись в `CHANGELOG.md` и GitHub-релиз. На mod.io: **Files → Upload file**, новая версия
(`1.1.0`, ...), подписчики получат её сами.
