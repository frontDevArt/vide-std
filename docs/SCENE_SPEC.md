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
```

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
