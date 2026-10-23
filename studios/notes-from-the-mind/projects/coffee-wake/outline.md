# План ролика coffee-wake (фаза 2)

## Идея в одном предложении
Утренний кофе у тех, кто пьёт его каждый день, в основном не «заряжает», а возвращает к норме после ночной ломки
(withdrawal reversal), но небольшой настоящий эффект и эффект ожидания тоже есть → **HALF-TRUE**.

Рубрика: Myth on Trial (дело № 01), короткий формат ~2 мин — пробный ролик канала и материал для нарезки (ROADMAP B4).
Название: «Does Coffee Wake You Up? What the Research Says» (формула POSITIONING §11, вердикт не искажает).

## Хронометраж и бюджет слов
Голос ElevenLabs, замер на демо: ~178 слов/мин в речи; паузы между сценами и фразами ≈ 15–20 с на ролик.
| Глава | Файл | О чём | Длительность | Слов |
|---|---|---|---|---|
| 1 | ch01 | крючок → утверждение → ночная ломка → исследования → вердикт → вопрос | 0:00–~2:00 | ~300 |

Ход: крючок (кружка) → claim (versus) → ломка за ночь (кружка вниз) → обзор 57 экспериментов (hero_stack) →
Bristol, 379 человек (crowd) → кофеин возвращает только к норме (кружка) → «+0» (full_number, разрыв ритма) →
withdrawal reversal + подписка (diagram) → но непьющим тоже помогает (versus, Haskell) → эффект ожидания (flow, Dawkins) →
вердикт HALF-TRUE (verdict) → «твоя настоящая норма» + вопрос (кружка).

## Источники (в описание ролика)
- Rogers, P. J., et al. (2010). Association of the anxiogenic and alerting effects of caffeine with ADORA2A and ADORA1
  polymorphisms and habitual level of caffeine consumption. *Neuropsychopharmacology*, 35, 1973–1983. n = 379, 16 ч без кофеина.
- Juliano, L. M., & Griffiths, R. R. (2004). A critical review of caffeine withdrawal. *Psychopharmacology*, 176, 1–29.
  57 экспериментальных и 9 опросных исследований.
- James, J. E., & Rogers, P. J. (2005). Effects of caffeine on performance and mood: withdrawal reversal is the most
  plausible explanation. *Psychopharmacology*, 182, 1–8.
- Haskell, C. F., Kennedy, D. O., Wesnes, K. A., & Scholey, A. B. (2005). Cognitive and mood improvements of caffeine in
  habitual consumers and habitual non-consumers of caffeine. *Psychopharmacology*, 179, 813–825. 24 + 24 человека.
- Dawkins, L., Shahzad, F.-Z., Ahmed, S. S., & Edmonds, C. J. (2011). Expectation of having consumed caffeine can improve
  performance and mood. *Appetite*, 57, 597–600. n = 88.

## Призывы
Подписка: сцена s08 (~45 % ролика), сразу после первой ценности (withdrawal reversal), одна фраза.
Вопрос для комментариев: «How many cups does it take before you feel like yourself?» — в финальной сцене s12.

## Визуальная идея — утверждено (2026-10-23)
- Метафора: кружка-шкала бодрости — уровень жидкости = alertness, пунктир baseline = норма без кофеина. Предмет превью.
- Настроение: `night` (glow_cool #5B7CFF, accent2 #6D7CFF индиго).
- Новый элемент: шаблон `lab_mug` (`templates/mug.py`): ниже нормы жидкость accent-2 (ломка), выше — циан с паром;
  уровень переходит через склейку (`keep: [mug]` + `mug.from_prev`).
- Мотив рубрики: Myth on Trial — «дело № 01» в шапке, шаги CLAIM → EVIDENCE → VERDICT.
- Открывающая сцена: кружка на норме, «буст» вверх по слову «coffee».
- Демо: `projects/coffee-wake-demo/build/final/coffee-wake-demo.mp4` (12 с, утверждено пользователем).

## Визуальная линия
Кружка — сквозной прибор (s01, s03, s06, s12); между ними — шаблоны lab по очереди (versus, hero_stack, crowd,
full_number, diagram, versus, flow, verdict). Разрывы ритма: s07 «+0», s11 вердикт.

## Сквозные решения (не менять между сессиями)
Язык en; голос ElevenLabs (`voice: auto`), `rate: 100`; акценты голоса — только s01 (крючок) и s11 (вердикт);
пресет lab, mood night; 16:9; субтитры 1 строка, 36 px; громкость −14 LUFS.
