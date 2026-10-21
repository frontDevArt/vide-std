# Формат сценария `script/chNN.yaml`

```yaml
chapter: ch01
title: "Название главы"
scenes:
  - id: s01                 # уникален в главе
    template: phone_lock    # см. python -m studio templates
    lines:                  # что говорит диктор; строка = синтез целиком
      - "Зашёл проверить одно уведомление."
      - "Очнулся — прошёл час."
    params: {...}           # параметры шаблона
    min_duration: 0         # жёсткий минимум длительности сцены, с
    want_duration: 0        # мягкое желание: получает запас времени, если он есть (при target_duration)
    hold: 0                 # секунды после речи (например, финальный титр)
    voice: {style: 0.4}     # необязательно: акцент голоса на сцену (только elevenlabs, docs/TTS.md)
```
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
- `*слово*` в текстах шаблонов (title/statement/outro…) — акцентный цвет.
- В `lines` разметка `*` и `|` удаляется перед синтезом и в субтитрах.
- `lines` и тексты в `params` — на языке проекта (`language`). Умолчания params в шаблонах русские —
  для другого языка задавать тексты явно. Надписи, которые шаблон рисует сам (шапка «Лента»), берутся из
  `ui` профиля языка в `studio/lang.py`. Склонения (`counter_label`): ru `[пост, поста, постов]`, en `[post, posts]`.

## Шаблоны (встроенные)
| Шаблон | Для чего | Биты |
|---|---|---|
| `title` | заставка/глава | появление с битом 0 |
| `statement` | крупная мысль, иконка, подпись | `at_beat`, подпись на следующем |
| `bullets` | список с иконками | пункт i на `first_beat+i` |
| `cards` | карточки-обещания, смена в ритме речи | карточка i на `first_beat+i` |
| `counter` | число набегает | в течение бита `at_beat` |
| `questions` | пауза + вопросы-плашки | вопрос i на `first_beat+i` |
| `outro` | финальный текст | с бита 0 |
| `phone_lock` | блокировка, уведомление, скачок часов | бит 0 — уведомление, `jump_beat` — скачок |
| `phone_feed` | бесконечная лента | свайп на каждый бит |
| `phone_close` | приложение сворачивается, финальный титр | `close_beat` |

Иконки (рисуются кодом): clock, laugh, book/story, news, question, bell, heart, play/video, check, bolt,
eye, chart, star, phone, hourglass, target, brain, lock.

## Свой шаблон для проекта
Файл `projects/<slug>/templates/my.py`:
```python
from studio.templates import Template, template
from studio import gfx as G

@template("big_quote", doc="Цитата", params={"text": ""}, beats="с бита 0")
class BigQuote(Template):
    def setup(self):
        self.spr = G.text_sprite(self.p.get("text", ""), int(80 * self.u), "black", glow=int(18 * self.u),
                                 maxw=int(self.W * 0.8))
    def draw(self, img, t, T):
        k = G.prog(t, self.bt(0, 0.2), self.bt(0, 0.2) + 0.5)
        G.blitc(img, self.spr, self.W / 2, self.H * 0.42, G.eo(k) * self.io(t))
```
Правила: дорогое — в `setup`; `draw` только композиция; всё, что должно продолжаться через склейку,
передавать через `state` (как `feed_offset`, `screen_dim`), а не начинать заново.

## Шаблоны канала: пресет `lab` (Notes From The Mind)
Включаются `style.palette: lab` в `project.yaml`. Правила стиля — `channel/STYLE.md`, эталон движения —
`channel/style-demo.html`, тестовый проект — `projects/style-test`, галерея всех шаблонов — `projects/lab-gallery`.
Код: `studio/lab.py` (фон, элементы, шаблоны), `studio/motion.py` (кривые и тайминги в кадрах @30), `studio/sfx.py` (звуки).

| Шаблон (§5 STYLE) | Для чего | Главные params |
|---|---|---|
| `lab_hero_stack` | Hero + Stack: факт с цифрой и следствиями | `claim`, `hero`, `cards[]`, `lines` |
| `lab_flow` | Flow: процесс из 3 станций, линии с бегущими точками | `stations[]` |
| `lab_versus` | Versus: «Думают / Нашли» | `left{title, items[]}`, `right{…}` |
| `lab_crowd` | Crowd: толпа = реальная выборка (+ исследование, шкала, цифра) | `study`, `crowd{n, cols, highlight[]}`, `range`, `hero` |
| `lab_diagram` | Center Diagram: схема по центру, ярлыки вокруг | `center`, `labels[]` |
| `lab_full_number` | Full Number: разрыв ритма, шок-факт, «миф → реальность» | `value`, `caption`, `myth{value, at, strike_at}` |
| `lab_chapter` | карточка главы (веер → «01» → заголовок → прогресс) | `number`, `total`, `title`, `subtitle`; `min_duration: 3` |
| `lab_verdict` | вердикт отдельной сценой | `verdict{verdict, sub, at}` |

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
Ненайденное слово — предупреждение в логе `stills`/`render` и запасное время (стаггер).

**Цветовое настроение** (`channel/STYLE.md` §14) — на весь ролик, в `project.yaml`:
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
Shorts (vertical) для `lab_*` пока не свёрстаны отдельно (STYLE §12) — делать горизонталь.
