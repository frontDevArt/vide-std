# Демо типов роликов (ROADMAP C1)

По проекту на каждый готовый тип из `studio/kinds.py`: `python -m studio selftest --kinds` проводит каждый через
validate → voice → render → assemble → qa (голос `fake` или `none`, офлайн); `tests/test_kinds.py` — validate и тайминг.
Тип с `needs` (data-story — C4) получит демо вместе с недостающим слоем.

`music` (ROADMAP C3) — 20 с под ритм-трек кодом 112 уд/мин, `music.sync: beat`: склейки и пункты `bullets` в долю, QA
«Склейки в долю трека» — по звуку готового файла, ±1 кадр.

Медиа-демо (ROADMAP C2): `promo` — 3 фото продукта + логотип, выходы TikTok 9:16 и квадрат 1:1; `slideshow` — Ken Burns,
параллакс, «до → после», рамка; `tutorial` — запись экрана с зумом и выносками; `clip` — «подкаст»: звук исходника в
миксе, волна, караоке. Файлы в `<тип>/assets/` нарисованы кодом — `python tools/make_demo_assets.py` (CC0, записаны
в `assets.yaml`); перезаписывать только при намеренной смене демо.
