# Бренд-кит студии (`brand/brand.yaml`)

Стиль ролика без программирования (ROADMAP A2): палитра, шрифты, фон, камера, субтитры и ассеты бренда лежат
данными в `studios/<id>/brand/`. Код — `studio/brand.py` (чтение и проверка), `studio/style.py` (`Style` из кита).
Образец — кит Notes From The Mind (`studios/notes-from-the-mind/brand/brand.yaml`, пресет `lab` в виде данных),
второй пример — тестовый `tests/fixtures/brands/sunrise/brand.yaml`.

## Как включается
```yaml
# studios/<id>/studio.yaml — кит для всех проектов студии
defaults:
  style:
    brand: brand           # папка с brand.yaml от корня студии (или абсолютный путь)
```
Проект может отключить кит (`style: {brand: null, palette: neon}`) или взять другой (`brand: brand-alt`).
С китом `style.palette` проекта не действует — палитру задаёт кит (`base` + `palette`); `style.mood` и
`style.overrides` работают поверх цветов кита, как раньше поверх `lab`.

`project.load` разворачивает кит в `cfg["style"]["kit"]`: пути к файлам — от корня репозитория, поэтому ключ кэша
рендера не зависит от машины, а правка `brand.yaml` пересобирает сцены (рендер их перерисует сам). Ошибки кита —
сразу при загрузке проекта, списком (`❌ fonts.head: укажите license …`).

## Формат
```yaml
name: Sunrise Coffee
base: lab                  # встроенная палитра-основа (style.PALETTES: neon | calm | lab): ключи, которых нет ниже
palette:                   # роль → #RRGGBB
  bg: "#2A1220"            # фон: bg, bg_top, bg_bot
  bg_bot: "#4A1C1C"        # ключ палитры движка напрямую — главнее роли (здесь: низ градиента)
  surface: "#3A1A2A"       # карточки и панели: bg2, panel
  text: "#FFF4E6"
  dim: "#C9A48F"
  accent: "#FF8A3D"        # accent, cyan
  accent2: "#FFD166"       # accent2, magenta, violet
  good: "#7BD389"          # «хорошо»: true, lime
  warn: "#FFD166"          # half, amber
  bad: "#FF5964"           # «плохо»: myth, red
  neutral: "#C9A48F"       # noev
  ink: "#3A1A2A"
fonts:                     # роли head | num | mono; файл ищется в brand/, brand/fonts/, затем общие assets/fonts/
  head: {file: Unbounded-VF.ttf, license: OFL-1.1}   # license обязательна: права на шрифт
  num: {file: Manrope-VF.ttf, license: OFL-1.1}
logo: {light: logo-light.png, dark: logo-dark.png}    # light — для тёмного фона, dark — для светлого
background: gradient       # lab | gradient | solid | {type: image, file: photo.jpg, dim: 0.45}
camera: false              # дрейф камеры у шаблонов с camera = True (lab_*)
subs: tiktok               # karaoke | plate | tiktok
shape: {radius: 28, line: 3}   # дизайн-пиксели 1920×1080
intro: sting.mp4           # логотип-«стинг» в начале / outro — в конце
cta: {text: Order now, url: example.com}
music: theme.wav           # музыка по умолчанию: music.file проекта, если своего нет
voice: {tone: warm, upbeat}
```
Всё, кроме `name`, необязательно; без `palette` — цвета `base`, без `fonts` — системное семейство `style.font`.

**Что рисуется уже сейчас:** палитра, шрифты по ролям, фон (`lab` — сетка и подсветки STYLE; `gradient` — градиент
`bg_top → bg_bot` с пятнами; `solid` — сплошной `bg`; `image` — фото «cover», затемнённое к `bg` на долю `dim`),
камера, субтитры (`karaoke` — слова загораются; `plate` — плашка; `tiktok` — крупно, ×1,6, без плашки, с обводкой,
звучащее слово — `accent`, выше интерфейса площадки), музыка по умолчанию.
**Хранится для следующих задач** (проверяется, что файлы есть; шаблоны читают из `self.style.brand` / `self.style.shape`):
`logo`, `intro`/`outro` (шаблон `logo_sting` — ROADMAP C2), `cta` (`cta_end` — C4), `shape` (токены шаблонов `lab_*`
остаются своими — STYLE), `voice.tone` (подсказка для текста и голоса; голоса студии — A3).

## Обложка (ROADMAP B5)
`brand/cover.yaml` рядом с `brand.yaml` — шаблон обложки для `python -m studio package` (не входит в кит и ключ
рендера). Ключи (все необязательны, умолчание — `studio/package.py: COVER`; размеры — доли меньшей стороны обложки):
```yaml
text: {font: head, weight: extrabold, size: 0.16, color: text, upper: true, max_words: 3}  # заголовок cover.text
verdict: {size: 0.17, pos: bottom}   # плашка вердикта: bottom — над заголовком, top — у верхнего поля
shade: 0.6                           # затемнение снизу (градиент цвета bg), 0 — без него
```
Кадр, текст и вердикт ролика — `package.cover` в `project.yaml`; `max_words` — ⚠️, если текст длиннее.

## Свой стиль по референсу
Для новой студии весь путь ведёт мастер `/new-studio` (ROADMAP A4): `python -m studio new-studio` кладёт заготовку
кита (`studios/_template/brand/brand.yaml`) и проект демо `projects/<id>-style/`; дальше — шаги ниже.
Пользователь даёт описание и скриншоты (сайт, упаковка, чужой ролик-ориентир).
1. Снять с референса: фон (тёмный/светлый, сплошной/градиент/фото), 1–2 акцента, цвет текста и приглушённого текста,
   форму (радиусы, толщина линий), характер шрифта (геометрический, гротеск, моно для цифр), субтитры.
   HEX — пипеткой по скриншоту (`PIL.Image.getpixel`), а не на глаз.
2. Заполнить `studios/<id>/brand/brand.yaml`; шрифты — только с известной лицензией (OFL из `assets/fonts/` или файлы
   клиента в `brand/fonts/` с его лицензией). Цвета «хорошо/плохо» не должны совпадать с акцентами.
3. `python -m studio stills <проект>` на коротком сценарии (или `python -m studio demo <проект>` — 10–15 с) и
   **посмотреть лист**: контраст текста, читаемость субтитров, акцент не спорит с «плохо».
4. Показать пользователю лист/демо и ждать подтверждения; правки — в `brand.yaml`, снова `stills`. Стиль фиксируется
   на весь ролик до старта (не меняется по главам).
