# Формат сценария `script/chNN.yaml`

```yaml
chapter: ch01
title: "Название главы"
scenes:
  - id: s01                 # уникален в главе
    template: phone_lock    # см. python -m studio templates (полное имя phone.lock — то же)
    lines:                  # что говорит диктор; строка = синтез целиком
      - "Зашёл проверить одно уведомление."
      - "Очнулся — прошёл час."
    params: {...}           # параметры шаблона
    min_duration: 0         # жёсткий минимум длительности сцены, с
    want_duration: 0        # мягкое желание: получает запас времени, если он есть (при target_duration)
    hold: 0                 # секунды после речи (например, финальный титр)
    voice: {style: 0.4}     # необязательно: акцент голоса на сцену (только elevenlabs, docs/TTS.md)
    item: 3                 # только kind: listicle — номер пункта топ-N (1…brief.count, по порядку или обратный отсчёт)
```
Ролик без голоса (`kind: music`/`slideshow`, `tts.backend: none`, ROADMAP C1): у сцен нет `lines`, длительность —
`min_duration`, весь текст в кадре — в `params`. Биты сцены пусты, поэтому шаблоны показывают всё с начала сцены.

**Музыка и ритм (ROADMAP C3, `studio/music.py`).** `music.sync: beat` — склейки сцен двигаются к ближайшей доле трека
(`bar` — к сильной доле, первой в такте; `music.meter`, по умолчанию 4). Сцена не становится короче своей речи, запас до
`target_duration` раздают доли, а не паузы. Сценам **без голоса** доли трека отдаются как биты: `first_beat`, `at_beat`,
`at: 2` — элементы появляются в долю (бит 0 — доля на склейке); субтитров из них нет. У озвученных сцен биты — речь, как
прежде. Трек: `music.file` (путь от папки проекта или имя в библиотеке студии `brand/music/`), иначе при `sync` —
ритм-трек кодом (`music.bpm`, 120). Свой трек на главу — `music.by_chapter: {ch02: calm.mp3}`, стык — кроссфейд
`music.crossfade` с (2); вместе с `sync` нельзя (доли ищутся в одном треке). У каждого трека — источник и лицензия:
`brand/music/music.yaml` (`tracks: [{file, title, source, license, by, bpm}]`) или `assets.yaml` проекта. QA «Склейки в
долю трека» ищет доли заново в звуке готового файла: каждая склейка — ±1 кадр от доли (тип `music` — всегда).
Строка `lines` — строка или словарь с акцентом голоса только на неё:
```yaml
    lines:
      - "So is it true?"
      - {text: "This one is false.", voice: {style: 0.4, stability: 0.35}}
```
`voice` строки ложится поверх `voice` сцены, тот — поверх `tts` в `project.yaml`. Ключи: `stability`, `similarity_boost`,
`style`, `use_speaker_boost`, `speed`, `model`. Канал: **не больше 1–2 акцентов на ролик** (крючок, вердикт).

## Биты
`|` внутри строки делит её на биты, не ломая интонацию:
```yaml
lines:
  - "Каждый свайп обещает что-то новое: | смешное видео, | неожиданную историю, | важную новость."
```
Это 4 бита (0..3) одной фразы. Биты нумеруются подряд по всем строкам сцены.
Шаблоны вешают события на биты: `cards` с `first_beat: 1` покажет карточку 0 на бите 1 («смешное видео»).
Субтитры по умолчанию режутся по битам (короткие склеиваются, длинные делятся по словам).

## Разметка текста
- `*слово*` в текстах шаблонов (title/statement/outro…) — акцентный цвет. Пунктуация снаружи звёздочек можно:
  `*time*,`, `*66*.`, `(*word*)` — знаки остаются в слове и красятся вместе с ним.
- В `lines` разметка `*` и `|` удаляется перед синтезом и в субтитрах.
- `lines` и тексты в `params` — на языке проекта (`language`). Умолчания params в шаблонах русские —
  для другого языка задавать тексты явно. Надписи, которые шаблон рисует сам (шапка «Лента»), берутся из
  `ui` профиля языка в `studio/lang.py`. Склонения (`counter_label`): ru `[пост, поста, постов]`, en `[post, posts]`.

## Фото, видео, логотип: ассеты проекта (ROADMAP C2)
Файлы клиента и свои — в `projects/<slug>/assets/`, а их происхождение — в `projects/<slug>/assets.yaml`:
```yaml
assets:
  - {file: assets/lamp-front.jpg, source: фотосессия клиента 2026-10, license: права у клиента, by: Aurora Lighting}
```
Сцена ссылается на файл путём от папки проекта: `params: {file: assets/lamp-front.jpg}` (любая строка в `params` с
расширением фото, видео или звука — ссылка; у нарезки ищется и в папке исходника). `validate`: файла нет — ❌, файла нет
в `assets.yaml` или у записи нет `source`/`license` — ⚠️; `qa` «Ассеты: источник и лицензия» — то же как ❌: чужое без
прав не сдаём. Содержимое файла — в ключе кэша сцены: заменили фото тем же именем — сцена перерисуется.

Шаблоны пакета `media` (параметры — в справочнике ниже):
- `media.image` — фото: `motion: kenburns` (наезд `zoom: [1.04, 1.14]` и панорама `pan`), `parallax` (`layers` — фон
  и вырезанный объект PNG, `depth` 0–1), `reveal` (проявление по маске: `reveal: wipe | circle` с `at`),
  `before_after` (`after` — второе фото, шторка с `at`, ярлыки `labels`), `none`.
- `media.video` — кусок видео: `start` (с какой секунды), `speed`, `zoom` (медленный наезд), `audio: true` — звук в микс.
- `media.screen` — запись экрана (видео или скриншот) в окне: `zoom: [{at, box}]` — плавный зум на область записи
  (доли), `callouts: [{at, text, x, y}]` — выноски со стрелкой, `clicks` — кольцо клика. Для `tutorial`.
- `media.clip` — подкаст/интервью: видео (или звук + `cover`) исходника, звук — в микс вместо голоса, волна, плашка
  `speaker`/`role`, караоке из расшифровки `captions: [{t, text}]` (секунды сцены). Для `clip` (`tts.backend: none`).
- `media.logo_sting` — логотип-«стинг»: `file` или логотип бренд-кита (`light` на тёмном фоне), иначе имя бренда
  текстом; пружина, свечение, блик, `tagline`.
- `media.product_card` — карточка продукта: фото, `name`, `note`, `was` → `price` (зачёркивание `strike_at`, цена с `at`),
  плашка `badge`.

Общие параметры фото и видео: `box: [x0, y0, x1, y1]` — рамка в долях рабочей зоны (нет — весь кадр под обрез, это
подложка: «Контент в безопасной зоне» проверяет только подпись поверх), `shape: rect | round | circle` (радиус — из
бренд-кита), `border`, `enter`/`exit`, подпись `caption` (+ `kicker`) с `caption_at`, `dim` — затемнение низа под
подпись. `at` у media — бит (число), секунды (`'1.5s'`) или слово озвучки; у роликов без голоса битов нет — секунды.
Звук исходника (`audio_clips` шаблона) кладётся в дорожку голоса: музыка под ним приглушается, итог — по LUFS.
Прозрачный экспорт для монтажки — `python -m studio render <проект> --alpha mov|webm`: графика без фона и субтитров,
ProRes 4444 или VP9 с альфой, `build/final/<slug>.alpha.mov`.

## Сгенерированные картинки: `image:` сцены (ROADMAP C5)
Включается на ролик: блок `images:` в `project.yaml` (или `studio.yaml → defaults`), без блока — выключено.
Умолчания и цены — [`IMAGES.md`](IMAGES.md); схема — `studio/config.py`, проверки — `studio/imagegen.py`.
```yaml
images: {enabled: true, style: "flat vector illustration, palette #0B0F1A #4FD1C5 …", budget_usd: 3}
# по умолчанию: backend kie, model nano-banana-2, resolution 2K, layers seedream/5-flash-layer-decomposition, cutout rembg
```
Сцена просит картинку блоком `image:` (словарь или список):
```yaml
image:
  - prompt: "a cozy bedroom at night, a person asleep in bed, a bedside lamp"
    role: scene        # scene — сцена целиком под раскладку на слои | bg — фон | subject — объект под вырезание | state_b
    layers: [room, bed with a person, bedside table with a lamp]   # только scene: что вынести в слои
    variant: 0         # сид: другой вариант той же картинки
  - {prompt: "the same room, morning light", role: state_b}        # правка первой картинки сцены — «до → после»
```
Картинка кэшируется в `assets/images/<ключ>.png`; ключ — промпт + `images.style` + `model` + `resolution` + `variant`
(у `state_b` — ещё ключ первой картинки сцены). `validate`: `image:` при выключенных `images` — ❌ с подсказкой; нет
`prompt`, чужая `role`, `state_b` первой, `variant` не целое ≥ 0 — ❌. `status` показывает фазу «3б Картинки», только
если `images.enabled`. Текст и цифры в кадр — только кодом: модели коверкают буквы. Генерация — `python -m studio
images` (смета, `--yes` для платного, учёт в `assets.yaml` — [`IMAGES.md`](IMAGES.md)).

Сцена с `image:` без `template` — `media.image`; её `params` берутся из готовых PNG (`imagegen.scene_params`, при
`render`/`stills`), явные `params` сцены — поверх (`caption`, `zoom`, `pan`, свой `motion`):
- `scene` с `layers` → `motion: parallax`: база раскладки (`depth` 0,1) и слои по `layers.json` от дальнего к
  ближнему (`depth` 0,45 → 1), у каждого `box` — место прямо из `bounding_box`; без раскладки — Ken Burns по картинке;
- `bg` + `subject` → параллакс: фон и вырезанный объект стикером (`sticker: true`, `box` — `imagegen.SUBJECT_BOX` по
  формату); один `subject` — стикер на фоне ролика;
- `state_b` → `motion: before_after`, первая картинка → правка, шторка на втором бите.
Слои поверх базы появляются по битам (i-й — на бите i), при одном бите — сразу. Нет PNG — `render` останавливается с
подсказкой `python -m studio images`: сеть и генерация в рендере не участвуют, одно и то же на входе — тот же кадр.
У слоя с `box` ход меньше (запас 0,03 + 0,05·depth вместо 0,05 + 0,10·depth): ближний объект не уезжает за край.
Стикер — PNG целиком в `box`, внизу рамки, не крупнее ×1,2 своего размера, тень по альфе; `sticker: true` у сцены с
одним `file` — объект в середине кадра без рамочной тени и обрезки.

## Сцена из HTML: `web.html` (ROADMAP C6, второй движок)
Для «богатых» сцен, которые PIL рисует дорого или никак: размытие и «стекло» (`filter`, `backdrop-filter`),
3D-перспектива, градиент по тексту, SVG, сложная вёрстка текста. Тело сцены рисует страница HTML/CSS в headless
Chromium (playwright, не входит в requirements: `pip install playwright && python -m playwright install chromium`).
Сценарий, голос, тайминг, фон, субтитры, микс, кэш, куски и QA — наши; кадр страницы ложится слоем между фоном и
субтитрами, поэтому склейка `-c copy` и черновик работают как у любой сцены.
```yaml
- id: s02
  template: web.html
  params: {file: assets/rich.html, vars: {title: "Two engines"}}   # страница — ассет проекта, запись в assets.yaml
  lines: ["A browser draws this one, | frame by frame, | on our clock."]
```
Контракт страницы (пример — `tests/fixtures/web/assets/rich.html`):
- вёрстка в «пикселях 1080»: короткая сторона кадра — 1080 CSS px при любом размере (черновик — `zoom` корня);
  размеры кадра — `SCENE.W`, `SCENE.H`, рабочая и безопасная зоны — `SCENE.area`, `SCENE.safe`;
- фон `html, body` — прозрачный (иначе страница закроет фон студии);
- время только виртуальное: все анимации документа стоят на паузе, кадру t выставляется `currentTime = t` — CSS
  `@keyframes` с `animation-delay` (от начала сцены) работают сами; свой ход — `window.seek = (t, S) => {…}`.
  Таймеры, `requestAnimationFrame`, `Date.now()` и переходы `transition`, запущенные сменой класса, — нет;
- биты: `--b0`…`--bN` (начала, `s`), `--e0`… (концы), `SCENE.beats` (с текстом), слова — `SCENE.words`;
- стиль ролика: цвета палитры `--c-<имя>` (`--c-accent`, `--c-text`, …), шрифт `var(--font)` (файлы стиля), данные —
  `SCENE.vars` и `--v-<имя>` из `params.vars`;
- сеть закрыта (только `file:`/`data:`); в ключе кэша — сам `.html`: CSS, JS, картинки — внутри него, иначе `render --force`.
Цена — в 3–6 раз дороже кадра PIL (замеры и когда что брать — `ROADMAP.md`, C6). В фикстурах галереи и golden шаблона
нет (кадр зависит от сборки Chromium), тест — `tests/test_web_html.py`.

## Шаблоны (встроенные)
Шаблоны разложены по пакетам `studio/packs/`: `core` (title, statement, bullets, counter, outro), `phone` (cards,
questions и три `phone_*`), `lab` (канал, ниже), `commerce` (`price_tag` — ценник «было → стало» на верёвочке и чек
из принтера, `number` — Full Number с запятыми; на основе lab, бирку и чек можно подмешать в свой шаблон миксинами
`PriceTag`/`Receipt`, как `lab_anchor` в fake-discounts), `media` (фото, видео, запись экрана, клип, логотип, карточка
продукта — [выше](#фото-видео-логотип-ассеты-проекта-roadmap-c2)), `kit` (ROADMAP C4, для любой палитры и формата:
`chart` — столбики, линия или круг из CSV в `assets/` или `values`; `timeline`, `steps`, `compare`, `map` — заглушка без
контуров стран; `quote`, `testimonial`, `lower_third`, `cta_end`, `chapter_bumper`; триггеры `at` — бит, секунды или
слово озвучки, элементы списков без `at` — по битам `first_beat + i`). Превью всех шаблонов во всех форматах —
`python -m studio gallery` → `output/gallery/index.html`. Полное имя — `<пакет>.<имя>` (`core.title`, `phone.feed`,
`lab.flow`); прежние имена из таблиц — алиасы, в сценарии годятся оба. `python -m studio templates` показывает
у каждого шаблона алиас, форматы кадра (`formats`) и параметры с типом, умолчанием и описанием. `validate`:
неизвестный параметр или значение не того типа (строка вместо числа) — ⚠️; шаблон не свёрстан под `format`
проекта — ⚠️ (сейчас так у `commerce.*` вне 16:9; `lab.*` свёрстан во всех четырёх — ROADMAP B2); опечатка в имени шаблона — ❌ с подсказкой ближайшего.

Полный список шаблонов с битами, форматами и параметрами — [справочник в конце документа](#справочник-шаблонов-из-кода):
он генерируется из метаданных кода, руками не правится.

Данные графика: `data: assets/sales.csv` (первая строка — заголовки; разделитель `,` `;` или таб; `x`/`y` — имена
столбцов, по умолчанию первый и второй) — CSV записывается в `assets.yaml` с источником, как фото; или прямо в сценарии
`values: [{label, value}]`. Субтитры ролика — `subtitles: {style: plate | karaoke | tiktok}` в `project.yaml`
(`tiktok` — крупные, по слову, выше интерфейса площадки; без ключа — из палитры или бренд-кита).

Иконки (рисуются кодом): clock, laugh, book/story, news, question, bell, heart, play/video, check, bolt,
eye, chart, star, phone, hourglass, target, brain, lock.

## Свой шаблон для проекта
Файл `projects/<slug>/templates/my.py`:
```python
from studio.templates import P, Template, template
from studio import anim as A, gfx as G

@template("big_quote", doc="Цитата", params={"text": P("", "текст цитаты")}, beats="с бита 0",
          formats=("vertical", "horizontal"))
class BigQuote(Template):
    def setup(self):
        self.spr = G.text_sprite(self.p.get("text", ""), int(80 * self.u), "black", glow=int(18 * self.u),
                                 maxw=int(self.W * 0.8))
    def draw(self, img, t, T):
        k = A.span(t, self.bt(0, 0.2), self.bt(0, 0.2) + 0.5)
        G.blitc(img, self.spr, self.W / 2, self.H * 0.42, A.eo(k) * self.io(t))
```
Прогресс и кривые — `studio/anim.py` (`from studio import anim as A`): `A.span(t, a, b)` — 0..1 на отрезке [a, b],
`A.ramp(t, start, dur)` — 0..1 за `dur` секунд от `start`. Старые `G.prog` (= `span`) и `M.prog` (= `ramp`) работают:
имя одно, семантика разная — в новом коде не использовать.
Шаблон проекта регистрируется в пространстве `project` (`project.big_quote`), в сценарии — просто `big_quote`.
Имя, совпадающее со встроенным (`title`, `lab_flow`), — ошибка `validate` и рендера: встроенный не перетирается.
`params`: просто значение по умолчанию (тип выводится из него) или `P(умолчание, "описание", type=…)`;
`formats` — форматы кадра, под которые шаблон свёрстан (по умолчанию все четыре: `vertical` 9:16, `horizontal` 16:9,
`square` 1:1, `portrait` 4:5); не свёрстан — сузить список (явный отказ, `validate` даст ⚠️).

**Сетка безопасной зоны (ROADMAP B2).** У шаблона есть `self.safe` и `self.area` — рамки `Box` в пикселях кадра
(`x0, y0, x1, y1, w, h, cx, cy`). `safe` — поля площадки проекта (`platform:`), без неё — площадки формата
(`platforms.LAYOUT`: 9:16 → `tiktok`, 4:5 → `instagram-feed`, 1:1 → `square`, 16:9 → `youtube`), не меньше
`qa.safe_margin`, с запасом 1 % на покачивание; интерфейс площадки (колонка кнопок справа) входит в симметричные боковые
поля. `area` — та же рамка, но выше полосы субтитров (`subs.band_top`): тело шаблона верстать в ней. Поля — в ключе
сцены, смена площадки пересчитывает сцены. Контент за рамкой — ❌ в `stills`/`qa` («Контент в безопасной зоне»).
У проекта с площадкой (ROADMAP B3) полоса субтитров стоит над нижним полем зоны (в Reels — выше нижних 35 %), и `area`
поднимается вместе с ней. Элемент, «висящий» с края кадра, крепить к краю зоны (бирка `commerce` — на гвоздике у
`safe.y0`), а не за кадр: за кадром он тоже контент у края.
Телефон (`phone_ctx(ctx, self.area)`, ROADMAP B2.1) в высоком кадре вписан в `area`: сверху полоса `STRIP` (200 при
z = 1) под счётчик `phone_feed` и ряд-историю `cards` (`phone.strip_cy` — её центр), ниже корпус со свечением; рост —
от рамки (не больше 0,6 высоты кадра), стопка по центру рамки. Рамка общая у всех сцен проекта — телефон на склейках
не прыгает. Карточки и вопросы — вокруг `phone.cy` (`self.fy`). Горизонталь — прежняя геометрия.
Правила: дорогое — в `setup`; `draw` только композиция; всё, что должно продолжаться через склейку,
передавать через `state` (как `feed_offset`, `screen_dim`), а не начинать заново. `draw` рисует только контент поверх
переданного кадра (не заливает его целиком): `safezone` рисует шаблон на прозрачный слой и по непрозрачным пикселям
проверяет поля кадра — сплошная заливка выглядела бы как «контент до края».
Цвета и пресет — из `self.style` (`studio/style.py`): `self.style.pal["accent"]`, `self.style.col("dim", 120)`,
`self.style.background`/`camera`/`subs`, бренд-кит — `self.style.brand` (логотип, CTA…) и `self.style.shape`
(радиус, толщина линий), формат — [`BRAND.md`](BRAND.md). Хелперы gfx (`text_sprite`, `icon`, `panel`, `radial`, `glowify`, `font`, `col`)
принимают `style=`; без него берут стиль ролика (рендер делает его активным). `G.PAL`/`G.STYLE` — только для старых
шаблонов: это снимок, запись в них ничего не меняет.

## Нарезка: сцены-ссылки `from:` (ROADMAP B4)
В проекте-нарезке (`cutdown: {source: <slug>}` в `project.yaml`, команда `cutdown`) сцена может быть ссылкой на
сцену исходника: `- from: s05` (глава с тем же id) или `- from: ch02/s05`. Остальные ключи рядом с `from` — поверх
сцены исходника (`params` сливаются). Без своих `lines` строки идут в синтез с контекстом соседей из исходника —
озвучка берётся из его кэша. Новые сцены (крючок, CTA) пишутся как обычно. Шапка `chrome` и подсветка `glow` главы —
как в исходнике к началу отрезка; переносы через state (`keep`, `from_prev`) из сцен вне нарезки не приходят.

## Шаблоны канала: пресет `lab` (Notes From The Mind)
Включаются `style.palette: lab` в `project.yaml` или бренд-китом студии (`style.brand: brand` в `studio.yaml → defaults`,
кит `studios/notes-from-the-mind/brand/brand.yaml` — тот же `lab` данными, кадры пиксель в пиксель). Правила стиля — `studios/notes-from-the-mind/channel/STYLE.md`, эталон движения —
`studios/notes-from-the-mind/channel/style-demo.html`, тестовый проект — `projects/style-test`, галерея всех шаблонов — `projects/lab-gallery`.
Код: пакет `studio/packs/lab/` (`background` — фон и камера, `elements` — примитивы и фирменные элементы,
`triggers` — `at`, `check` — их проверка, `base` — `LabTemplate`, `hero`/`crowd`/`templates` — шаблоны; полные имена `lab.flow` и т. п.), `studio/motion.py` (тайминги в кадрах @30), `studio/anim.py` (кривые), `studio/sfx.py` (звуки).

Шаблоны `lab.*` (композиции §5 STYLE: Hero + Stack, Flow, Versus, Crowd, Center Diagram, Full Number, карточка главы,
вердикт) и их params — в [справочнике](#справочник-шаблонов-из-кода). У `lab_chapter` в сцене — `min_duration: 3`.

**Общие params у всех `lab_*`:**
- `chrome: {rubric, number, steps: [CLAIM, EVIDENCE, VERDICT], step, clock: "07:00"}` — шапка. Наследуется
  следующими сценами через state: задать один раз в первой сцене, дальше менять только `step`/`clock`.
  На склейке шапка не появляется заново; стрелка часов доезжает до нового времени.
- `source: {label, text, at}` — плашка источника внизу слева (обязательна, когда звучит исследование).
- `verdict: {verdict: TRUE|HALF-TRUE|MYTH|NO EVIDENCE, sub: "… *акцент* …", at}` — штамп поверх любой сцены,
  всё остальное гаснет до 32 %; звук: райзер 0,5 с + удар.
- `neuron: {mood: surprised|nod|facepalm, at, x, y}` — «Нейрон» (не больше 3–4 раз за ролик).
- `keep: [hero]` — элемент не уходит в конце сцены и переезжает в следующую (у неё `hero.from_prev: true`).

**Триггер `at`** (у каждого элемента): `"66"` или `"w:median"` — слово в озвучке (старт за 4 кадра до слова),
`"median of"` — последовательность слов, `"some#2"` — второе вхождение, `3` — номер бита, `"1.5s"` — секунды.
Таймкоды слов: ElevenLabs и edge дают настоящие; piper/rhvoice — оценка по слогам внутри битов.
Ненайденное слово (или номер бита, которого нет) — ❌ в выводе `voice` с подсказкой похожих слов озвучки и в
`validate`, пока `timeline.json` актуален (B8); при рендере — запасное время (стаггер) и ⚠️ в логе. Проверяются ключи
`at` и `*_at` на любой глубине `params` (`hero.strike_at`, `crowd.highlight[0].at`).

**Цветовое настроение** (`studios/notes-from-the-mind/channel/STYLE.md` §14) — на весь ролик, в `project.yaml`:
```yaml
style:
  palette: lab
  mood: ember            # lab (по умолчанию) | night | ember | deep | orchid  — gfx.MOODS
  overrides:             # необязательно, HEX поверх настроения: только glow_cool, glow_warm, accent2
    accent2: "#F78FB3"
```
Меняет только подсветки фона (`glow_cool` сверху-слева, `glow_warm` снизу-справа) и второй акцент `accent2`;
`bg`, бренд-циан `accent`, цвета вердиктов — никогда. Без `mood` фон пиксель в пиксель прежний.
`validate` — ошибка, если `accent2` ближе 48 единиц RGB к цвету вердикта (`true/half/myth/noev`) или к `accent`.

**Подсветка главы** — в `script/chNN.yaml` на верхнем уровне: `glow: night` (имя настроения) или
`glow: {cool: "#5B7CFF", warm: "#9B8CFF"}`. Главы без `glow` — подсветка ролика. Переход на стыке — 1,2 с
в начале первой сцены новой главы, цвет переносится через `state` (`lab_glow`), поэтому склейка бесшовна.
`accent2` по главам не меняется.

**Демо стиля:** `python -m studio demo <проект>` → `projects/<slug>-demo/` (стиль, формат, язык, голос — из проекта;
сценарий — `projects/<slug>/demo/ch01.yaml`, иначе заготовка `projects/_template/demo/ch01.yaml`; свои шаблоны
`templates/*.py` копируются). Делает `validate → voice → render → assemble → qa`, проверяет 10–15 с.
`--no-render` — только создать проект; `--yes` — платный синтез ElevenLabs.

**Раскадровка под `lab`** (чек-лист — STYLE §13): шаблон композиции на каждую сцену и смена шаблона от сцены
к сцене; новый элемент не реже раза в 2,5 с; разрыв ритма (`lab_full_number`, `lab_chapter`, вердикт, «Нейрон»)
каждые 20–30 с; ≤ 7 слов текста в кадре; цвет вердикта — только для вердикта; цифры в кадре = источник = озвучка.
Высокие кадры (9:16, 4:5, 1:1) у `lab_*` свёрстаны отдельно (ROADMAP B2): всё — в `self.area`, масштаб
`z = min(area.w / 760, area.h / 1300)` (в 9:16 TikTok ≈ 1, в 4:5 и 1:1 мельче). Шапка — рубрика слева сверху, шаги
второй строкой под ней, часы справа; колонки и ряды стали стопкой сверху вниз: `hero_stack` — утверждение → цифра →
карточки (без линий), `crowd` — исследование → цифра → толпа → шкала, `versus` — «думают» / VS / «нашли», `flow` —
станции сверху вниз с линией по оси плиток, `diagram` — эллипс ярлыков вытянут вниз, `chapter` — столбик по центру.
Цифра (`hero`) у всех стоит на одном месте (`HeroMixin.hero_xy`) — переезд через склейку работает; `x`/`y` из params и
у «Нейрона» — координаты сетки 16:9, в высоком кадре не используются. Штамп вердикта ужимается до ширины рамки.

## Справочник шаблонов (из кода)
Встроенные пакеты `core`, `phone`, `lab`, `commerce`. Свои шаблоны проекта — `python -m studio templates <проект> --md`.
После правки `@template(...)` (описание, биты, форматы, `params`) — `python -m studio templates --md --write`;
`tests/test_templates_md.py` падает, если блок разошёлся с кодом.

<!-- templates:begin — генерируется `python -m studio templates --md --write`, руками не править -->
| Шаблон | Алиас | Для чего | Форматы |
|---|---|---|---|
| [`core.bullets`](#corebullets) | `bullets` | Заголовок + список пунктов с иконками; пункт i появляется на бите first_beat+i. | vertical, horizontal, square, portrait |
| [`core.counter`](#corecounter) | `counter` | Большое число, которое «набегает» от from до to во время бита, с подписью. | vertical, horizontal, square, portrait |
| [`core.outro`](#coreoutro) | `outro` | Финальный текст с подписью; держится до конца ролика. | vertical, horizontal, square, portrait |
| [`core.statement`](#corestatement) | `statement` | Крупная фраза по центру (\*слово\* — акцент), опционально иконка сверху и подпись. | vertical, horizontal, square, portrait |
| [`core.title`](#coretitle) | `title` | Заставка/глава: маленький надзаголовок + крупный заголовок, неоновая линия. | vertical, horizontal, square, portrait |
| [`phone.cards`](#phonecards) | `cards` | Карточки с иконками сменяют друг друга в ритме речи (вылетают из телефона). | vertical, horizontal, square, portrait |
| [`phone.close`](#phoneclose) | `phone_close` | Приложение сворачивается в иконку на домашнем экране, телефон уходит, появляется финальный текст (держится до конца). | vertical, horizontal, square, portrait |
| [`phone.feed`](#phonefeed) | `phone_feed` | Бесконечная лента в телефоне: свайп на каждый бит + между битами, motion blur, счётчик просмотренных постов над телефоном. | vertical, horizontal, square, portrait |
| [`phone.lock`](#phonelock) | `phone_lock` | Экран блокировки: уведомление прилетает, часы скачком перепрыгивают вперёд. | vertical, horizontal, square, portrait |
| [`phone.questions`](#phonequestions) | `questions` | Лента замедляется и останавливается, экран темнеет (пауза). | vertical, horizontal, square, portrait |
| [`lab.chapter`](#labchapter) | `lab_chapter` | lab · Карточка главы: «световой веер» 6 кадров → «01» в контуре + черта + заголовок капсом + подзаголовок моно + прогресс точками «chapter 1 of 8». | vertical, horizontal, square, portrait |
| [`lab.crowd`](#labcrowd) | `lab_crowd` | lab · Crowd: толпа из N иконок = реальная выборка, подсветка отдельных людей с ярлыками; опц. карточка исследования, шкала-диапазон и цифра слева (может морфить цифру прошлой сцены). | vertical, horizontal, square, portrait |
| [`lab.diagram`](#labdiagram) | `lab_diagram` | lab · Center Diagram: одна схема по центру (узел с иконкой и подписью), ярлыки вокруг, линии от центра; эффект, механизм. | vertical, horizontal, square, portrait |
| [`lab.flow`](#labflow) | `lab_flow` | lab · Flow: 3 станции слева направо, соединены линиями с бегущими точками; процесс, «как это работает». | vertical, horizontal, square, portrait |
| [`lab.full_number`](#labfull_number) | `lab_full_number` | lab · Full Number: одна цифра на весь кадр + подпись; опц. | vertical, horizontal, square, portrait |
| [`lab.hero_stack`](#labhero_stack) | `lab_hero_stack` | lab · Hero + Stack: слева огромная цифра (счётчик, «миф → реальность»), справа стопка 3–4 карточек, линии с бегущими точками от цифры к карточкам; опц. карточка утверждения сверху-слева. | vertical, horizontal, square, portrait |
| [`lab.verdict`](#labverdict) | `lab_verdict` | lab · Вердикт отдельной сценой: штамп TRUE/HALF-TRUE/MYTH/NO EVIDENCE падает пружиной, вспышка цвета вердикта, подпись; перенесённая цифра (keep: [hero]) видна приглушённой. | vertical, horizontal, square, portrait |
| [`lab.versus`](#labversus) | `lab_versus` | lab · Versus: две колонки «Думают / Нашли», посередине разделитель; пункты — карточки по `at`. | vertical, horizontal, square, portrait |
| [`commerce.number`](#commercenumber) | — | lab · Full Number для цен и сумм: числа ≥ 1000 с запятыми ($14,550). | vertical, horizontal, square, portrait |
| [`commerce.price_tag`](#commerceprice_tag) | `price_tag` | Ценник-бирка на верёвочке: падает от гвоздика у верха зоны и качается, старая цена зачёркивается accent-2, новая выпрыгивает пружиной; опц. чек из принтера справа (строки по триггерам, отрыв крупным планом). | vertical, horizontal, square, portrait |
| [`media.clip`](#mediaclip) | — | Кусок подкаста или интервью: видео исходника (или обложка к аудио) в рамке, звук исходника в микс, волна громкости, крупные караоке-подписи из расшифровки (слова загораются по времени), имя говорящего. | vertical, horizontal, square, portrait |
| [`media.image`](#mediaimage) | — | Фото: Ken Burns (медленный наезд и панорама), параллакс 2.5D по слоям (фон и вырезанный объект PNG), проявление по маске (шторка или круг), «до → после» шторкой. | vertical, horizontal, square, portrait |
| [`media.logo_sting`](#medialogo_sting) | — | Логотип-«стинг» (интро/аутро бренда): логотип выпрыгивает пружиной, за ним расходится свечение, по нему проходит блик, снизу — слоган. | vertical, horizontal, square, portrait |
| [`media.product_card`](#mediaproduct_card) | — | Карточка продукта: фото (медленный наезд) в карточке со скруглением бренд-кита, название, цена; старая цена зачёркивается, новая выпрыгивает пружиной, плашка скидки. 9:16 и 4:5 — фото сверху, 16:9 и 1:1 — фото слева. | vertical, horizontal, square, portrait |
| [`media.screen`](#mediascreen) | — | Запись экрана (видео или скриншот) в окне приложения: плавный зум на область по триггерам, выноски со стрелкой к точке, кольцо-подсветка клика. | vertical, horizontal, square, portrait |
| [`media.video`](#mediavideo) | — | Кусок видео внутри сцены: обрезка (start), скорость (speed), под обрез или целиком, рамка с формой, медленный наезд. | vertical, horizontal, square, portrait |
| [`kit.chapter_bumper`](#kitchapter_bumper) | `chapter_bumper` | Перебивка главы (1,5–3 с) для любой палитры: полоса цвета акцента проносится через кадр, номер главы крупно со свечением, надзаголовок и название; уходит полосой в другую сторону. | vertical, horizontal, square, portrait |
| [`kit.chart`](#kitchart) | `chart` | График из данных: столбики (bar), линия (line) или круг (pie). | vertical, horizontal, square, portrait |
| [`kit.compare`](#kitcompare) | `compare` | Сравнение двух вариантов по строкам: шапки колонок, в каждой строке подпись и два значения; победитель строки — цветом колонки и галочкой, проигравший приглушён. | vertical, horizontal, square, portrait |
| [`kit.cta_end`](#kitcta_end) | `cta_end` | Финальный призыв: логотип (файл или бренд-кит), заголовок, кнопка с пульсом и кликом курсора (текст меняется на done), ник канала; опц. места под «смотрите дальше» (конечная заставка YouTube). | vertical, horizontal, square, portrait |
| [`kit.lower_third`](#kitlower_third) | `lower_third` | Плашка «имя и кто он» внизу слева (или справа): полоса цвета акцента вырастает, имя выезжает из-за неё, роль — следом; уходит в обратном порядке. | vertical, horizontal, square, portrait |
| [`kit.map`](#kitmap) | `map` | Карта-заглушка: точечная сетка-проекция (без контуров стран), булавки по широте/долготе с подписями, маршрут дугами от точки к точке. | vertical, horizontal, square, portrait |
| [`kit.quote`](#kitquote) | `quote` | Цитата: крупная кавычка, текст (\*слово\* — акцент), автор и кто он; опц. фото автора в круге. | vertical, horizontal, square, portrait |
| [`kit.steps`](#kitsteps) | `steps` | Шаги процесса: номера в кружках, соединённые линией; шаг загорается по триггеру, пройденные остаются залитыми, линия к следующему растёт. | vertical, horizontal, square, portrait |
| [`kit.testimonial`](#kittestimonial) | `testimonial` | Отзыв клиента: карточка со звёздами (заполняются по одной, бывают половинки), текст, аватар (фото или инициалы), имя, кто он и откуда отзыв. | vertical, horizontal, square, portrait |
| [`kit.timeline`](#kittimeline) | `timeline` | Лента времени: ось растёт от события к событию, точка выпрыгивает, дата и подпись поднимаются. | vertical, horizontal, square, portrait |
| [`web.html`](#webhtml) | — | Сцена из HTML/CSS (второй движок, спайк C6): страница рисуется в headless Chromium с прозрачным фоном и ложится слоем на наш фон под субтитры. | vertical, horizontal, square, portrait |

### core.bullets

Заголовок + список пунктов с иконками; пункт i появляется на бите first_beat+i.

- **Биты:** заголовок — с первым битом, пункты — по битам
- **Форматы:** vertical, horizontal, square, portrait

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `header` | строка | `'Три шага'` | заголовок |
| `items` | список | `[{'icon': 'check', 'text': 'Пункт'}]` | пункты {icon, text, color} |
| `first_beat` | число | `1` | бит первого пункта |

### core.counter

Большое число, которое «набегает» от from до to во время бита, с подписью.

- **Биты:** счёт идёт в течение бита at_beat
- **Форматы:** vertical, horizontal, square, portrait

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `from` | число | `0` | начальное значение |
| `to` | число | `100` | конечное значение |
| `suffix` | строка | `''` | после числа (%) |
| `label` | строка | `'подпись'` | подпись под числом |
| `at_beat` | число | `0` | бит, во время которого идёт счёт |
| `color` | строка | `'amber'` | цвет числа |

### core.outro

Финальный текст с подписью; держится до конца ролика.

- **Биты:** текст появляется сразу или с первым битом
- **Форматы:** vertical, horizontal, square, portrait

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `text` | строка | `'Твоё *время* — твой выбор'` | финальный текст, \*слово\* — акцент |
| `sub` | строка | `''` | подпись |

### core.statement

Крупная фраза по центру (\*слово\* — акцент), опционально иконка сверху и подпись.

- **Биты:** фраза появляется на бите at_beat, подпись — на следующем
- **Форматы:** vertical, horizontal, square, portrait

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `text` | строка | `'Главная *мысль*'` | фраза, \*слово\* — акцент |
| `icon` | строка | `None` | иконка сверху (gfx.icon) |
| `color` | строка | `'accent'` | цвет акцента |
| `sub` | строка | `None` | подпись под фразой |
| `at_beat` | число | `0` | бит появления |

### core.title

Заставка/глава: маленький надзаголовок + крупный заголовок, неоновая линия.

- **Биты:** заголовок появляется с первым битом (или сразу)
- **Форматы:** vertical, horizontal, square, portrait

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `kicker` | строка | `'Глава 1'` | надзаголовок |
| `title` | строка | `'Заголовок с *акцентом*'` | заголовок, \*слово\* — акцент |

### phone.cards

Карточки с иконками сменяют друг друга в ритме речи (вылетают из телефона). Прошлые уходят в ряд-историю сверху.

- **Биты:** карточка i появляется на бите first_beat+i (если битов меньше — равномерно)
- **Форматы:** vertical, horizontal, square, portrait

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `cards` | список | `[{'icon': 'laugh', 'label': 'Смешное видео', 'color': 'lime'}]` | карточки {icon, label, color} |
| `first_beat` | число | `1` | бит первой карточки |
| `backdrop` | строка | `'phone'` | phone — телефон с лентой позади |
| `time` | строка | `'22:04'` | часы в статус-баре |

### phone.close

Приложение сворачивается в иконку на домашнем экране, телефон уходит, появляется финальный текст (держится до конца).

- **Биты:** на бите close_beat приложение сворачивается; финальный текст — после конца речи
- **Форматы:** vertical, horizontal, square, portrait

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `close_beat` | число | `-1` | бит, на котором приложение сворачивается |
| `final_text` | строка | `'Твоё *время* — твой выбор'` | финальный текст |
| `final_sub` | строка | `''` | подпись |
| `time` | строка | `'22:04'` | часы в статус-баре |
| `speed` | число | `0.0` | скорость ленты до сворачивания |

### phone.feed

Бесконечная лента в телефоне: свайп на каждый бит + между битами, motion blur, счётчик просмотренных постов над телефоном.

- **Биты:** каждый бит — сильный свайп
- **Форматы:** vertical, horizontal, square, portrait

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `swipe_every` | число | `0.75` | свайп между битами, с |
| `speed` | число | `1.0` | сила свайпа |
| `counter` | да/нет | `True` | счётчик постов над телефоном |
| `counter_label` | список \| строка | `['пост', 'поста', 'постов']` | подпись счётчика: строка или формы склонения |
| `time` | строка | `'22:04'` | часы в статус-баре |
| `stop` | да/нет | `False` | лента останавливается к концу сцены |

### phone.lock

Экран блокировки: уведомление прилетает, часы скачком перепрыгивают вперёд. В конце экран «разблокируется» вверх и под ним уже лента.

- **Биты:** бит 0 — уведомление (тап в конце бита), бит jump_beat — скачок часов
- **Форматы:** vertical, horizontal, square, portrait

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `time_from` | строка | `'21:04'` | часы до скачка |
| `time_to` | строка | `'22:04'` | часы после скачка |
| `date` | строка | `'вторник, 20 октября'` | дата под часами |
| `notif_app` | строка | `'Лента'` | приложение в уведомлении |
| `notif_title` | строка | `'Новое видео для тебя'` | заголовок уведомления |
| `notif_text` | строка | `'Посмотри, пока не удалили 👀'` | текст уведомления |
| `badge` | строка | `'+1 час'` | бейдж скачка |
| `jump_beat` | число | `1` | бит скачка часов |
| `time` | строка | `'22:04'` | часы в статус-баре ленты |

### phone.questions

Лента замедляется и останавливается, экран темнеет (пауза). Над телефоном по битам появляются вопросы-плашки.

- **Биты:** вопрос i появляется на бите first_beat+i
- **Форматы:** vertical, horizontal, square, portrait

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `questions` | список | `['Зачем я здесь?', 'На сколько минут?']` | вопросы-плашки |
| `first_beat` | число | `1` | бит первого вопроса |
| `time` | строка | `'22:04'` | часы в статус-баре |
| `icons` | список | `['question', 'clock']` | иконки плашек по кругу |

### lab.chapter

lab · Карточка главы: «световой веер» 6 кадров → «01» в контуре + черта + заголовок капсом + подзаголовок моно + прогресс точками «chapter 1 of 8». Держать ≥ 2,5 с (min_duration). Между главами.

- **Биты:** появляется сразу
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `LabTemplate`:** `chrome`, `keep`, `source`, `verdict`, `neuron`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `number` | число | `1` | номер главы |
| `total` | число | `8` | всего глав |
| `title` | строка | `'Wake up'` | заголовок |
| `subtitle` | строка | `'07:00 · facts 1–10'` | подзаголовок моно |

### lab.crowd

lab · Crowd: толпа из N иконок = реальная выборка, подсветка отдельных людей с ярлыками; опц. карточка исследования, шкала-диапазон и цифра слева (может морфить цифру прошлой сцены).

- **Биты:** элементы — по `at`; люди толпы появляются волной за ~0,6 с
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `LabTemplate`:** `chrome`, `keep`, `source`, `verdict`, `neuron`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `hero` | словарь | `{'value': 66, 'from_prev': True, 'caption': 'median days', 'sub': '', 'color': 'accent', 'at': '66', 'strike_at': 'w:took'}` | цифра слева {value, from, from_prev, caption, sub, color, at, strike_at} |
| `study` | словарь | `{'authors': 'Lally, van Jaarsveld, Potts & Wardle', 'where': 'Eur. J. of Social Psychology · 2010 · n = 96', 'evidence': 3, 'at': '2010'}` | карточка исследования {authors, where, evidence 1–3, at} |
| `crowd` | словарь | `{'n': 96, 'cols': 16, 'at': '96', 'highlight': [{'index': 19, 'label': '18 days', 'color': 'accent', 'at': '18'}]}` | толпа {n, cols, at, highlight[{index, label, color, at}]} |
| `range` | словарь | `{'min': 18, 'max': 254, 'mark': 66, 'min_label': '18 days', 'max_label': '~254 days', 'mark_label': '66 · median', 'at': '66'}` | шкала-диапазон {min, max, mark, \*_label, at} |

### lab.diagram

lab · Center Diagram: одна схема по центру (узел с иконкой и подписью), ярлыки вокруг, линии от центра; эффект, механизм.

- **Биты:** центр — по center.at, ярлык i — по своему `at`
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `LabTemplate`:** `chrome`, `keep`, `source`, `verdict`, `neuron`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `center` | словарь | `{'icon': 'flask', 'title': 'Habit loop', 'at': 0}` | узел по центру {icon, title, at} |
| `labels` | список | `[{'text': 'cue', 'at': 1}]` | ярлыки вокруг {text, at} |

### lab.flow

lab · Flow: 3 станции слева направо, соединены линиями с бегущими точками; процесс, «как это работает».

- **Биты:** станция i — по `at`; линия к ней рисуется перед её появлением
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `LabTemplate`:** `chrome`, `keep`, `source`, `verdict`, `neuron`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `stations` | список | `[{'icon': 'alarm', 'title': 'Cue', 'sub': 'same time, same place', 'at': 0}]` | станции {icon, title, sub, at} |

### lab.full_number

lab · Full Number: одна цифра на весь кадр + подпись; опц. «миф → реальность» (myth: зачёркнутое мифическое значение, счётчик доматывает до реального). Разрыв ритма, шок-факт.

- **Биты:** счёт — от `at`; myth: {value, strike_at}
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `LabTemplate`:** `chrome`, `keep`, `source`, `verdict`, `neuron`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `value` | число | `66` | реальное значение |
| `from` | число | `0` | с чего начинается счёт |
| `prefix` | строка | `''` | перед числом ($) |
| `suffix` | строка | `''` | после числа (%) |
| `caption` | строка | `'days'` | подпись |
| `sub` | строка | `''` | вторая строка подписи |
| `color` | строка | `'accent'` | цвет цифры |
| `at` | число \| строка | `0` | старт счёта: бит, секунды или слово |
| `myth` | словарь | `None` | «миф → реальность» {value, strike_at} |

### lab.hero_stack

lab · Hero + Stack: слева огромная цифра (счётчик, «миф → реальность»), справа стопка 3–4 карточек, линии с бегущими точками от цифры к карточкам; опц. карточка утверждения сверху-слева.

- **Биты:** каждый элемент — по своему `at` (слово/бит/секунды); без `at` — стаггер
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `LabTemplate`:** `chrome`, `keep`, `source`, `verdict`, `neuron`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `claim` | словарь | `{'label': 'VIRAL CLAIM', 'text': '“It takes *21 days* to build a habit.”', 'meta': '', 'at': 'w:says', 'qmark': True}` | карточка утверждения сверху-слева {label, text, meta, at, qmark} |
| `hero` | словарь | `{'value': 21, 'from': 0, 'caption': 'days', 'sub': 'the popular claim', 'color': 'text', 'at': '21'}` | цифра слева {value, from, caption, sub, color, at, from_prev, strike_at} |
| `cards` | список | `[{'icon': 'book', 'title': 'Title', 'sub': 'mono subtitle', 'chip': None, 'chip_color': 'noev', 'at': 'w:book'}]` | стопка карточек {icon, title, sub, chip, chip_color, at} |
| `lines` | да/нет | `True` | линии с бегущими точками от цифры к карточкам |

### lab.verdict

lab · Вердикт отдельной сценой: штамп TRUE/HALF-TRUE/MYTH/NO EVIDENCE падает пружиной, вспышка цвета вердикта, подпись; перенесённая цифра (keep: [hero]) видна приглушённой. Разрыв ритма.

- **Биты:** штамп — по verdict.at (по умолчанию 0,3 с)
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `LabTemplate`:** `neuron`, `chrome`, `keep`, `source`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `verdict` | словарь | `{'verdict': 'MYTH', 'sub': '21 days → median *66*', 'at': 'w:verdict'}` | штамп {verdict: TRUE\|HALF-TRUE\|MYTH\|NO EVIDENCE, sub, at} |

### lab.versus

lab · Versus: две колонки «Думают / Нашли», посередине разделитель; пункты — карточки по `at`. Для проверки мифа.

- **Биты:** пункты — по `at`, без `at` — стаггер
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `LabTemplate`:** `chrome`, `keep`, `source`, `verdict`, `neuron`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `left` | словарь | `{'title': 'THEY SAY', 'items': [{'text': '21 days', 'at': 0}]}` | колонка «думают» {title, items[{text, at}]} |
| `right` | словарь | `{'title': 'STUDIES FOUND', 'items': [{'text': '66 days (median)', 'at': 1}]}` | колонка «нашли» {title, items[{text, at}]} |

### commerce.number

lab · Full Number для цен и сумм: числа ≥ 1000 с запятыми ($14,550). Единица — prefix/suffix (0,77 $ → value 77 + suffix ¢).

- **Биты:** счёт — от `at`; myth: {value, strike_at}
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `LabTemplate`:** `chrome`, `keep`, `source`, `verdict`, `neuron`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `value` | число | `66` | реальное значение |
| `from` | число | `0` | с чего начинается счёт |
| `prefix` | строка | `''` | перед числом ($) |
| `suffix` | строка | `''` | после числа (%) |
| `caption` | строка | `'days'` | подпись |
| `sub` | строка | `''` | вторая строка подписи |
| `color` | строка | `'accent'` | цвет цифры |
| `at` | число \| строка | `0` | старт счёта: бит, секунды или слово |
| `myth` | словарь | `None` | «миф → реальность» {value, strike_at} |

### commerce.price_tag

Ценник-бирка на верёвочке: падает от гвоздика у верха зоны и качается, старая цена зачёркивается accent-2, новая выпрыгивает пружиной; опц. чек из принтера справа (строки по триггерам, отрыв крупным планом). Бирка и чек переходят через склейку (tag.from_prev / keep: [tag, receipt]).

- **Биты:** всё по словам-триггерам `at`; receipt.tear_at — чек отрывается и выезжает в tear_to (строка без «\|» — итог по центру)
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `LabTemplate`:** `chrome`, `keep`, `source`, `verdict`, `neuron`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `tag` | словарь | `{'was': '$199', 'now': '$99', 'x': 960, 'y': 200, 'scale': 1.0, 'at': 0, 'strike_at': None, 'now_at': None, 'from_prev': False}` | бирка {was, now, x, y, scale, at, strike_at, now_at, from_prev, was_label, now_label}; y — длина верёвки до люверса |
| `receipt` | словарь | `None` | чек {title, lines: [{text: 'СЛЕВА\|СПРАВА', at}], at, tear_at, tear_to}; пример: {'title': 'RECEIPT', 'lines': [{'text': 'ITEM\|$1', 'at': None}], 'tear_at': None, 'tear_to': {'x': 960, 'y': 560, 'scale': 1.7, 'rot': -4}} |

### media.clip

Кусок подкаста или интервью: видео исходника (или обложка к аудио) в рамке, звук исходника в микс, волна громкости, крупные караоке-подписи из расшифровки (слова загораются по времени), имя говорящего.

- **Биты:** всё по времени исходника: captions[].t — секунды от начала сцены (биты не нужны: голоса нет)
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `MediaTemplate`:** `box`, `shape`, `border`, `enter`, `exit`, `caption`, `kicker`, `caption_at`, `dim`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `file` | строка | `None` | видео (mp4/mov/webm) или картинка, путь от папки проекта (assets/…) |
| `start` | число | `0.0` | с какой секунды исходника |
| `speed` | число | `1.0` | скорость: 0,5 — вдвое медленнее, 2 — вдвое быстрее (звук — тем же темпом) |
| `fit` | строка | `'cover'` | cover — под обрез \| contain — целиком |
| `audio` | да/нет | `True` | звук исходника — в микс (речь ролика) |
| `volume_db` | число | `0.0` | громкость звука исходника, dB (итог всё равно нормализуется по LUFS) |
| `cover` | строка | `None` | картинка, если исходник — только звук (wav/mp3/m4a) |
| `speaker` | строка | `None` | плашка: имя говорящего |
| `role` | строка | `None` | плашка: кто он (вторая строка) |
| `captions` | список | `[]` | расшифровка: [{t: секунды сцены, text}] — фраза до следующей (или до t1); слова загораются равномерно по фразе |
| `wave` | да/нет | `True` | волна громкости звука исходника |

### media.image

Фото: Ken Burns (медленный наезд и панорама), параллакс 2.5D по слоям (фон и вырезанный объект PNG), проявление по маске (шторка или круг), «до → после» шторкой. Весь кадр под обрез или рамка с формой, подпись снизу.

- **Биты:** движение — на всю сцену; reveal и before_after — с `at` (бит, секунды или слово), слой — со своего `at`, подпись — с `caption_at`. Без голоса битов нет: `at: '1.2s'`. Сцена с `image:` (images.enabled) сама получает file/layers/after из готовых PNG (imagegen.scene_params)
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `MediaTemplate`:** `box`, `shape`, `border`, `enter`, `exit`, `caption`, `kicker`, `caption_at`, `dim`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `file` | строка | `None` | фото, путь от папки проекта (assets/…) |
| `layers` | список | `None` | parallax: слои от дальнего к ближнему [{file, depth 0–1, fit: cover\|contain, focus: [x, y], box: [x0, y0, x1, y1] — место на картинке в долях (раскладка), sticker: тень по альфе, at: появление}] — объект — PNG с прозрачностью |
| `sticker` | да/нет | `False` | файл — вырезанный объект: целиком, без обрезки рамкой, тень по альфе |
| `after` | строка | `None` | before_after: второе фото (после) |
| `motion` | строка | `'kenburns'` | kenburns \| parallax \| reveal \| before_after \| none |
| `zoom` | список | `[1.04, 1.14]` | масштаб в начале и в конце сцены (≥ 1) |
| `pan` | список | `[[-0.5, 0.3], [0.5, -0.3]]` | центр окна в начале и в конце, доли свободного хода −1…1 |
| `fit` | строка | `'cover'` | cover — под обрез \| contain — целиком |
| `focus` | список | `[0.5, 0.5]` | точка фото, что остаётся в кадре при обрезке (доли) |
| `at` | число \| строка | `0` | reveal / before_after: бит \| '1.5s' \| слово озвучки |
| `reveal` | строка | `'wipe'` | reveal: wipe (шторка слева направо) \| circle (круг из центра) |
| `labels` | список | `None` | before_after: ярлыки [до, после] |

### media.logo_sting

Логотип-«стинг» (интро/аутро бренда): логотип выпрыгивает пружиной, за ним расходится свечение, по нему проходит блик, снизу — слоган. Логотип — file или из бренд-кита (light на тёмном фоне, dark на светлом); нет ни того ни другого — имя бренда текстом.

- **Биты:** логотип — с `at` (по умолчанию сразу), блик — через 0,5 с, слоган — через 0,8 с
- **Форматы:** vertical, horizontal, square, portrait

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `file` | строка | `None` | логотип PNG/JPG (прозрачный фон), путь от папки проекта; нет — из бренд-кита |
| `text` | строка | `None` | логотип текстом, если файла нет (по умолчанию — имя бренд-кита) |
| `tagline` | строка | `None` | слоган под логотипом, \*слово\* — акцент |
| `size` | число | `None` | ширина логотипа, доля рабочей зоны (по умолчанию 0,8 в высоком кадре, 0,4 в широком) |
| `at` | число \| строка | `0.0` | когда логотип появляется: бит \| '1.5s' \| слово озвучки |
| `glow` | да/нет | `True` | свечение за логотипом цветом accent |
| `exit` | строка | `None` | cut \| fade (по умолчанию fade, у последней сцены — cut) |

### media.product_card

Карточка продукта: фото (медленный наезд) в карточке со скруглением бренд-кита, название, цена; старая цена зачёркивается, новая выпрыгивает пружиной, плашка скидки. 9:16 и 4:5 — фото сверху, 16:9 и 1:1 — фото слева. Числа ≥ 1000 — с запятыми (как commerce.number).

- **Биты:** карточка — с начала сцены, название — следом, цена — с `at`, зачёркивание — `strike_at`
- **Форматы:** vertical, horizontal, square, portrait

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `file` | строка | `None` | фото продукта, путь от папки проекта (assets/…) |
| `name` | строка | `'Product'` | название |
| `note` | строка | `None` | строка под названием (свойство, объём…) |
| `price` | строка | `None` | цена (новая) |
| `was` | строка | `None` | старая цена — зачёркивается |
| `badge` | строка | `None` | плашка в углу фото: «−50 %», «NEW» |
| `at` | число \| строка | `0` | когда появляется цена: бит \| '1.5s' \| слово озвучки |
| `strike_at` | число \| строка | `None` | когда зачёркивается старая цена (по умолчанию — с ценой) |
| `zoom` | список | `[1.0, 1.08]` | наезд на фото: масштаб в начале и в конце |
| `focus` | список | `[0.5, 0.5]` | точка фото, что остаётся в кадре при обрезке |

### media.screen

Запись экрана (видео или скриншот) в окне приложения: плавный зум на область по триггерам, выноски со стрелкой к точке, кольцо-подсветка клика. Для туториалов.

- **Биты:** зум, выноски и клики — по `at` (бит, секунды или слово озвучки); выноска держится до `until` или до следующей
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `MediaTemplate`:** `box`, `shape`, `border`, `enter`, `exit`, `caption`, `kicker`, `caption_at`, `dim`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `file` | строка | `None` | видео (mp4/mov/webm) или картинка, путь от папки проекта (assets/…) |
| `start` | число | `0.0` | с какой секунды исходника |
| `speed` | число | `1.0` | скорость: 0,5 — вдвое медленнее, 2 — вдвое быстрее (звук — тем же темпом) |
| `fit` | строка | `'cover'` | cover — под обрез \| contain — целиком |
| `audio` | да/нет | `False` | звук исходника — в микс (вместо голоса: клип, интервью) |
| `volume_db` | число | `0.0` | громкость звука исходника, dB (итог всё равно нормализуется по LUFS) |
| `frame` | строка | `'window'` | рамка: window (окно с тремя точками) \| none |
| `title` | строка | `None` | заголовок окна |
| `zoom` | список | `[]` | зум: [{at, box: [x0, y0, x1, y1] — доли записи; нет box — назад к целому}] |
| `callouts` | список | `[]` | выноски: [{at, text, x, y — точка в долях записи, until}] |
| `clicks` | список | `[]` | клики: [{at, x, y}] — кольцо расходится от точки |

### media.video

Кусок видео внутри сцены: обрезка (start), скорость (speed), под обрез или целиком, рамка с формой, медленный наезд. Звук исходника — по желанию (audio: true) в микс.

- **Биты:** видео идёт с начала сцены; подпись — с `caption_at`; после конца исходника — стоп-кадр
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `MediaTemplate`:** `box`, `shape`, `border`, `enter`, `exit`, `caption`, `kicker`, `caption_at`, `dim`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `file` | строка | `None` | видео (mp4/mov/webm) или картинка, путь от папки проекта (assets/…) |
| `start` | число | `0.0` | с какой секунды исходника |
| `speed` | число | `1.0` | скорость: 0,5 — вдвое медленнее, 2 — вдвое быстрее (звук — тем же темпом) |
| `fit` | строка | `'cover'` | cover — под обрез \| contain — целиком |
| `audio` | да/нет | `False` | звук исходника — в микс (вместо голоса: клип, интервью) |
| `volume_db` | число | `0.0` | громкость звука исходника, dB (итог всё равно нормализуется по LUFS) |
| `zoom` | список | `[1.0, 1.0]` | масштаб в начале и в конце сцены (медленный наезд: [1, 1.08]) |

### kit.chapter_bumper

Перебивка главы (1,5–3 с) для любой палитры: полоса цвета акцента проносится через кадр, номер главы крупно со свечением, надзаголовок и название; уходит полосой в другую сторону.

- **Биты:** всё — с `at`; уход — в последние 0,5 с сцены
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `KitTemplate`:** `color`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `number` | число \| строка | `1` | номер главы (число или строка) |
| `title` | строка | `'Название главы'` | название, \*слово\* — акцент |
| `kicker` | строка | `'Глава'` | надзаголовок над номером |
| `total` | число | `None` | всего глав: подпись «1 / 5» |
| `at` | число \| строка | `0` | начало: бит \| '1.5s' \| слово озвучки |

### kit.chart

График из данных: столбики (bar), линия (line) или круг (pie). Данные — CSV в assets/ (data, столбцы x/y) или values прямо в сценарии. Значения растут и набегают числами; выделенное — цветом accent2. В высоком кадре столбики лежат (подписи слева), в широком стоят.

- **Биты:** рост — с `at` за `grow` секунд; при first_beat — по значению на бит; выделенное значение вспыхивает в конце роста
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `KitTemplate`:** `title`, `color`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `type` | строка | `'bar'` | bar \| line \| pie |
| `data` | строка | `None` | CSV (первая строка — заголовки), путь от папки проекта: assets/data.csv; файл — в assets.yaml с источником |
| `x` | строка | `None` | столбец подписей (по умолчанию первый) |
| `y` | строка | `None` | столбец значений (по умолчанию второй) |
| `values` | список | `None` | данные в сценарии вместо CSV: [{label, value}] или [числа] |
| `prefix` | строка | `''` | перед числом ($) |
| `suffix` | строка | `''` | после числа (%, h, k) |
| `decimals` | число | `None` | знаков после точки (по умолчанию — как в данных) |
| `highlight` | строка \| число | `None` | выделить: подпись или номер с 0 (цвет accent2) |
| `max` | число | `None` | верх шкалы (по умолчанию — максимум данных) |
| `at` | число \| строка | `0` | начало роста: бит \| '1.5s' \| слово озвучки |
| `grow` | число | `1.6` | секунд на рост всех значений |
| `first_beat` | число | `None` | значение i — на бите first_beat + i (вместо общего роста) |
| `source` | строка | `None` | подпись источника под графиком |

### kit.compare

Сравнение двух вариантов по строкам: шапки колонок, в каждой строке подпись и два значения; победитель строки — цветом колонки и галочкой, проигравший приглушён.

- **Биты:** шапки — сразу, строка — по `at` или биту first_beat + i (иначе равномерно)
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `KitTemplate`:** `title`, `color`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `left` | словарь | `{'title': 'A', 'color': 'accent'}` | левая колонка {title, color} |
| `right` | словарь | `{'title': 'B', 'color': 'accent2'}` | правая колонка {title, color} |
| `rows` | список | `[{'label': 'Цена', 'left': '$10', 'right': '$15', 'win': 'left'}]` | строки [{label, left, right, win: left \| right, at}] (2–5) |
| `first_beat` | число | `None` | строка i — на бите first_beat + i, если у неё нет at |

### kit.cta_end

Финальный призыв: логотип (файл или бренд-кит), заголовок, кнопка с пульсом и кликом курсора (текст меняется на done), ник канала; опц. места под «смотрите дальше» (конечная заставка YouTube). Держится до конца ролика.

- **Биты:** всё — с `at`, кнопка пульсирует, клик — `click_at`
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `KitTemplate`:** `color`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `title` | строка | `'Спасибо, что *досмотрели*'` | заголовок, \*слово\* — акцент |
| `button` | строка | `'Подписаться'` | текст кнопки |
| `done` | строка | `None` | текст кнопки после клика |
| `handle` | строка | `None` | ник канала или сайт под кнопкой |
| `logo` | строка | `None` | логотип (assets/…); нет — из бренд-кита, если он есть |
| `next` | число | `0` | мест под «смотрите дальше» (0–2): рамки конечной заставки |
| `next_label` | строка | `'Смотрите дальше'` | подпись рамок «смотрите дальше» |
| `at` | число \| строка | `0` | появление: бит \| '1.5s' \| слово озвучки |
| `click_at` | число \| строка | `None` | клик по кнопке (по умолчанию — через 1,2 с после появления; false — без клика) |

### kit.lower_third

Плашка «имя и кто он» внизу слева (или справа): полоса цвета акцента вырастает, имя выезжает из-за неё, роль — следом; уходит в обратном порядке. Опц. фото на весь кадр под плашкой (медленный наезд).

- **Биты:** плашка — с `at`, уходит с `until`
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `KitTemplate`:** `color`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `name` | строка | `'Имя Фамилия'` | имя |
| `role` | строка | `None` | кто он (вторая строка) |
| `side` | строка | `'left'` | left \| right |
| `file` | строка | `None` | фото на весь кадр под плашкой (assets/…); нет — фон ролика |
| `at` | число \| строка | `0.3` | появление: бит \| '1.5s' \| слово озвучки |
| `until` | число \| строка | `None` | уход: бит \| '4s' \| слово (по умолчанию — держится до конца сцены) |

### kit.map

Карта-заглушка: точечная сетка-проекция (без контуров стран), булавки по широте/долготе с подписями, маршрут дугами от точки к точке. Для «где это было» и «откуда куда».

- **Биты:** булавка — по `at` или биту first_beat + i (иначе равномерно); дуга к ней рисуется перед её появлением
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `KitTemplate`:** `title`, `color`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `pins` | список | `[{'lat': 51.5, 'lon': -0.1, 'label': 'London'}]` | булавки [{lat, lon, label, at}] (или x, y — доли кадра карты) |
| `view` | список | `None` | область [lon0, lat0, lon1, lat1]; по умолчанию — вокруг булавок |
| `route` | да/нет | `False` | дуги между булавками по порядку |
| `first_beat` | число | `None` | булавка i — на бите first_beat + i, если у неё нет at |

### kit.quote

Цитата: крупная кавычка, текст (\*слово\* — акцент), автор и кто он; опц. фото автора в круге.

- **Биты:** кавычка и текст — с `at`, автор — с `author_at`
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `KitTemplate`:** `color`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `text` | строка | `'Цитата с *акцентом*'` | текст цитаты, \*слово\* — акцент |
| `author` | строка | `None` | автор |
| `role` | строка | `None` | кто он (вторая строка) |
| `photo` | строка | `None` | фото автора (assets/…, в assets.yaml) |
| `at` | число \| строка | `0` | появление текста: бит \| '1.5s' \| слово озвучки |
| `author_at` | число \| строка | `None` | появление автора (по умолчанию — через 0,8 с после текста) |

### kit.steps

Шаги процесса: номера в кружках, соединённые линией; шаг загорается по триггеру, пройденные остаются залитыми, линия к следующему растёт. В широком кадре — в ряд, в высоком — столбиком.

- **Биты:** шаг — по `at` или биту first_beat + i (иначе равномерно); текущий — с пульсирующим кольцом
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `KitTemplate`:** `title`, `color`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `steps` | список | `[{'title': 'Шаг', 'text': 'пояснение'}]` | шаги [{title, text, at}] (2–5) |
| `first_beat` | число | `None` | шаг i — на бите first_beat + i, если у него нет at |

### kit.testimonial

Отзыв клиента: карточка со звёздами (заполняются по одной, бывают половинки), текст, аватар (фото или инициалы), имя, кто он и откуда отзыв.

- **Биты:** карточка — с `at`, звёзды — по одной следом, автор — через 0,6 с
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `KitTemplate`:** `color`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `text` | строка | `'Отличный *продукт*'` | текст отзыва, \*слово\* — акцент |
| `author` | строка | `'Имя Фамилия'` | автор |
| `role` | строка | `None` | кто он (город, профессия) |
| `photo` | строка | `None` | фото автора (assets/…); нет — инициалы |
| `rating` | число | `5` | оценка 0–5 (можно 4.5) |
| `source` | строка | `None` | откуда отзыв (Google, App Store…) |
| `at` | число \| строка | `0` | появление карточки: бит \| '1.5s' \| слово озвучки |

### kit.timeline

Лента времени: ось растёт от события к событию, точка выпрыгивает, дата и подпись поднимаются. В широком кадре ось горизонтальная (подписи сверху и снизу по очереди), в высоком — вертикальная.

- **Биты:** событие — по `at` или биту first_beat + i (иначе равномерно); ось доходит до точки к её появлению
- **Форматы:** vertical, horizontal, square, portrait
- **Общие параметры `KitTemplate`:** `title`, `color`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `events` | список | `[{'date': '2010', 'text': 'Событие'}]` | события [{date, text, at}] (3–6) |
| `first_beat` | число | `None` | событие i — на бите first_beat + i, если у него нет at |

### web.html

Сцена из HTML/CSS (второй движок, спайк C6): страница рисуется в headless Chromium с прозрачным фоном и ложится слоем на наш фон под субтитры. Время — виртуальное: CSS-анимации и `window.seek(t)`. Нужен playwright с Chromium (не входит в requirements).

- **Биты:** странице: `--b0`…`--bN` в CSS и SCENE.beats (тексты и время битов), слова — SCENE.words
- **Форматы:** vertical, horizontal, square, portrait

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `file` | строка | `None` | страница .html, путь от папки проекта (assets/…); в ключе кэша — только этот файл: CSS, JS и картинки — внутри него или --force |
| `vars` | словарь | `None` | данные странице: window.SCENE.vars и CSS-переменные --v-<имя> |
| `fade` | да/нет | `True` | вход и выход сцены прозрачностью слоя (как у остальных шаблонов) |

### Общие параметры `LabTemplate`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `chrome` | словарь | `None` | шапка: рубрика, шаги, часы (переносится в следующие сцены) |
| `keep` | список | `[]` | что пережить склейку: [hero] |
| `source` | словарь | `None` | плашка источника {label, text, at} |
| `verdict` | словарь | `None` | штамп вердикта {verdict, sub, at} |
| `neuron` | словарь | `None` | «Нейрон» {mood, text, at} |

### Общие параметры `MediaTemplate`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `box` | список | `None` | рамка [x0, y0, x1, y1] в долях рабочей зоны (без полосы субтитров); нет — кадр целиком |
| `shape` | строка | `'rect'` | форма: rect \| round (радиус бренд-кита) \| circle |
| `border` | да/нет | `False` | обводка цветом accent |
| `enter` | строка | `None` | вход: cut \| fade \| rise \| zoom (по умолчанию: весь кадр — cut, рамка — rise) |
| `exit` | строка | `None` | выход: cut \| fade (по умолчанию: весь кадр — cut, рамка — fade) |
| `caption` | строка | `None` | подпись, \*слово\* — акцент |
| `kicker` | строка | `None` | надпись над подписью (мелко, accent2) |
| `caption_at` | число \| строка | `0` | когда появляется подпись: бит \| '1.5s' \| слово озвучки |
| `dim` | число | `None` | затемнение низа кадра под подпись 0–1 (по умолчанию 0,72 при подписи на весь кадр) |

### Общие параметры `KitTemplate`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `title` | строка | `None` | заголовок над содержимым, \*слово\* — акцент |
| `color` | строка | `'accent'` | цвет акцента: имя цвета палитры или #RRGGBB |
<!-- templates:end -->
