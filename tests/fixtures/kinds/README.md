# Демо типов роликов (ROADMAP C1)

По проекту на каждый готовый тип из `studio/kinds.py`: `python -m studio selftest --kinds` проводит каждый через
validate → voice → render → assemble → qa (голос `fake` или `none`, офлайн); `tests/test_kinds.py` — validate и тайминг.
Типы с `needs` (slideshow, tutorial, clip — C2; data-story — C4) получат демо вместе с недостающим слоем.
