# План: тест стиля lab

## Идея в одном предложении
Сцена «Myth on Trial № 07» из `channel/style-demo.html` — миф «21 день» → 66 дней (Lally et al., 2010) → MYTH —
собранная реальным конвейером студии.

## Сквозные решения
- Язык: en. Голос: edge `en-US-AndrewMultilingualNeural` (мужской), rate 104 (тест; для канала — ElevenLabs).
- Стиль: пресет `lab`. Шаблоны: s01 — `lab_hero_stack` (утверждение + «21» + 3 карточки), s02 — `lab_crowd`
  (исследование, толпа n = 96, «21» зачёркивается → 66, шкала 18–254, вердикт MYTH, «Нейрон»).
- Цифра «21» переносится из s01 в s02 через state (`keep: [hero]`).

## Источники
- Maltz M. (1960). Psycho-Cybernetics — «минимум около 21 дня» (источник мифа).
- Lally P., van Jaarsveld C., Potts H., Wardle J. (2010). How are habits formed: Modelling habit formation in the real
  world. European Journal of Social Psychology, 40(6), 998–1009. n = 96, медиана 66 дней, разброс 18–254,
  один пропуск почти не влиял.
