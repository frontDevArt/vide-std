# Бриф ролика

## 1. Тема *(обязательно)*
**Is it true that a crossed-out “was” price makes you think it’s a deal — even when the old price is fake?**
По-русски: правда ли, что зачёркнутая «старая цена» заставляет нас видеть выгоду, даже если эта цена выдумана, — и почему мы уверены, что на нас это не действует.

- Рубрика: Money Brain (тема №1 радара `research/radar/2026-W43.md`; повод — Black Friday 27.11.2026, публикация 13–20.11.2026)
- Вердикт: **TRUE** — эффект «якоря» от указанной старой цены подтверждён лабораторными экспериментами, метаанализом и данными реальных магазинов; он работает и на скептиков. Важная оговорка: совсем абсурдная «старая цена» может дать обратный эффект, а настоящая история цены рядом этот эффект гасит.

## 2. Язык, длительность и формат *(длительность обязательна)*
- Язык ролика: en
- Длительность: 9 минут (Money Brain — 8–15 мин)
- Формат: horizontal
- Точная длительность важна? нет (по речи)

## 3. Зритель и результат
- Кто смотрит: зрители канала Notes From The Mind — взрослые англоязычные зрители, интересующиеся психологией и деньгами, без научной подготовки; многие собираются что-то купить на Black Friday.
- Что зритель должен вынести (1–3 пункта):
  - Зачёркнутая цена — это «якорь»: она сдвигает ощущение ценности, даже когда мы ей не верим и даже у профессионалов.
  - Чувство «на меня это не действует» — само по себе известное искажение (слепое пятно к собственным искажениям).
  - Рабочее противоядие одно: сравнивать не со «старой ценой» магазина, а с реальной историей цены — и спрашивать себя, купил бы я это за эту цену без зачёркнутой цифры.
- Тон: спокойный, любопытный, с лёгкой иронией; без «вас обманывают, вы наивны». Честная калибровка: "one experiment", "a meta-analysis of twenty papers", "a consumer group's price tracking" (раздел 14 позиционирования).

## 4. Стиль (один на весь ролик, потом не меняется)
- Пресет или свой: lab (палитра, шрифты, тайминги — `channel/STYLE.md`, эталон движения — `channel/style-demo.html`)
- Описание своего стиля: — (каркас lab без изменений; своё — только визуальная идея ниже)
- Референсы: — (нет)
- Чего в визуале НЕ надо: реальных людей и лиц; логотипов магазинов и брендов (в т. ч. Which? — только обобщённая «бумажная карточка» с доменом); скриншотов чужих сайтов и интерфейсов интернет-магазинов; фото; настоящих рекламных баннеров; капслока «SALE!!!» в стиле реальной рекламы; цветов вердиктов не по назначению (красная зачёркивающая линия — это цвет `accent-2`/нейтральный, а не красный MYTH, чтобы не путать с вердиктом).
- Шаблоны композиции по сценам:
  - хук — Center Diagram (ценник по центру, зачёркивание «WAS $199», ярлыки вокруг: «deal?», «real?»);
  - откуда взялось — Flow (колесо → число → оценка) + Full Number «25% vs 45%» (разрыв ритма);
  - агенты недвижимости — Versus («list price $119,900» / «$149,900» → оценки агентов);
  - Urbany 1988 — Center Diagram (шкала «perceived value», якорь тянет стрелку);
  - метаанализ 20 работ — Hero + Stack («20» + карточки: большие скидки / неправдоподобные / проценты > доллары);
  - Ngwe 2018 — Full Number «77¢» (разрыв ритма) → Hero + Stack (что значит «за каждый доллар»);
  - давление времени — Flow (таймер → спешка → «старая цена» действует сильнее);
  - Which? — Full Number «83%» + бумажная карточка источника;
  - вердикт — Verdict (TRUE);
  - почему миф живёт — Versus («Others get fooled» / «I don’t»);
  - эксперимент на 900 человек — Crowd (90 иконок × 10) + Versus («with ‘was’ price» / «with true normal price»);
  - что делать — Flow (3 станции: price history → would I buy it at this price? → consider the opposite);
  - разрыв ритма — каждые 20–30 с (Full Number или смена шаблона), один шаблон не больше 2 раз подряд.

**Визуальная идея ролика**
- Главная метафора: **ценник-бирка на верёвочке, к которой привязан корабельный якорь.** Зачёркнутая старая цена — буквально якорь (anchoring): он тянет вниз стрелку «сколько это стоит» в голове. Тот же ценник — на превью.
- Цветовое настроение: `ember` (тёплое «торговое» свечение `glow-warm` `#FF9F6B`, `accent-2` роза `#F78FB3`) — азарт и возбуждение распродажи. Оттенки глав: «откуда взялось» и «вердикт» — базовая подсветка `ember`; «почему миф живёт» — сдвиг подсветки к `glow-cool` (холодный взгляд на себя), переход через `state`.
- Новые элементы (1–2):
  1. **Ценник-бирка** — качается на верёвочке; старая цена зачёркивается «от руки» линией цвета `accent-2`, новая цена выпрыгивает пружиной. Кандидат в `lab_*`.
  2. **Якорь на цепи + шкала ценности** — якорь опускается на горизонтальную шкалу «perceived value» и тянет стрелку; чем выше «старая цена», тем дальше ползёт стрелка. Повторяется в 3–4 сценах как сквозной «прибор».
- Мотив рубрики: Money Brain — ценники и чеки. Факты «пробиваются» строками на длинном чеке, который растёт сбоку кадра (`ITEM: anchor … $0.77`); в финале чек отрывается: `TOTAL: you paid for the anchor`.
- Открывающая сцена: тёмный кадр, сверху на верёвочке опускается ценник `$199`, линия зачёркивает его, рядом выпрыгивает `$99` — и тут же к верёвке «пристёгивается» якорь. Журнал `channel/visuals-log.md` пуст — повторов нет.
- Демо 10–15 с: ценник опускается → зачёркивание → `$99` → якорь падает на шкалу «perceived value» и тянет стрелку → строка на чеке пробивается → штамп **TRUE** (зелёный) с вспышкой; настроение `ember`.

## 5. Голос и звук
- Голос: elevenlabs (тот же голос, что во всех роликах канала; ключ и голос — в `.env`)
- Темп: обычный (en ~155 слов/мин → ~1 400 слов на 9 минут)
- Музыка: да
- Субтитры: да

## 6. Структура (по желанию)
1. **Хук** (0:00–0:20) — зачёркнутая цена, «I know it’s a trick — it doesn’t work on me». Обещание проверки.
2. **Откуда это взялось** (0:20–1:50) — эффект якоря: колесо фортуны (Tversky & Kahneman, 1974) и агенты недвижимости (Northcraft & Neale, 1987).
3. **Что нашли проверки** (1:50–5:00) — Urbany et al., 1988 (скептики тоже); метаанализ Krishna et al., 2002; данные аутлетов (Ngwe, 2018); давление времени (Krishnan et al., 2013); граница эффекта — абсурдные цены (Wolk & Spann, 2008); реальные цены распродаж (Which?, 2025). Призыв подписаться — на стыке с вердиктом (~4:00–4:30).
4. **Вердикт** (5:00–5:20) — штамп TRUE + одна фраза оговорки.
5. **Почему миф «на меня не действует» живёт** (5:20–6:50) — слепое пятно (Pronin et al., 2002); половина американцев уверены, что скидки фейковые (YouGov), — и всё равно работает. Вопрос для комментариев — здесь.
6. **Что полезного** (6:50–8:40) — эксперимент на 900 людях: настоящая «обычная цена» гасит эффект (Staelin, Urbany & Ngwe, 2023); «consider the opposite» (Mussweiler et al., 2000); три шага перед покупкой.
7. **Финал** (8:40–9:00) — чек отрывается, итог, напоминание про вопрос.

## 7. Содержание
- Обязательно упомянуть (факты, примеры, истории) — по порядку, текст для озвучки на английском:
  1. **(Хук)** "In the United States, about half of people say brands regularly run fake discounts" — 52% (YouGov, 2023/2024 — год опроса уточнить (?) ).
  2. **Якорь, исходный эксперимент:** "Researchers spun a rigged wheel of fortune that stopped at either ten or sixty-five, then asked people what share of United Nations members are African countries. People who saw ten guessed twenty-five percent. People who saw sixty-five guessed forty-five." (Tversky & Kahneman, 1974)
  3. **Даже эксперты:** "Real estate agents toured the same house. Given a listing price of one hundred nineteen thousand nine hundred dollars, they valued it at about one hundred fourteen thousand. Given one hundred forty-nine thousand nine hundred, about one hundred twenty-nine thousand. And they said the list price hadn't influenced them." — 47 агентов и 54 студента; оценки в среднем $114,204 vs $128,754 (Northcraft & Neale, 1987)
  4. **Скептики тоже:** "In a simulated shopping experiment, adding a 'regular price' raised people's guess of the store's usual price and how good the deal felt. An exaggerated regular price worked about as well as a believable one — even on the most skeptical shoppers." (Urbany, Bearden & Weilbaker, 1988)
  5. **Метаанализ:** "A meta-analysis of twenty published papers found that showing a regular price next to the sale price boosts the sense of savings for big deals — and even for implausible ones. Only small, believable discounts didn't gain much." (Krishna, Briesch, Lehmann & Yuan, 2002)
  6. **Проценты сильнее долларов:** "In the same analysis, the percentage off moved people more than the dollar amount." (Krishna et al., 2002)
  7. **Реальные магазины:** "A Harvard Business School researcher studied a major clothing brand's outlet stores, where some items were made for the outlet and never sold at the 'original price' at all. In an experiment, every extra dollar on the fake 'original price' made people willing to pay about seventy-seven cents more. Infrequent shoppers were the easiest to sway." (Ngwe, 2018 — рабочий доклад HBS; знали ли участники, что цена фиктивна, — уточнить (?) )
  8. **Спешка усиливает:** "Exaggerated reference prices work much better when people feel time pressure while deciding." — countdown timers, doorbusters (Krishnan, Dutta & Jha, 2013)
  9. **Граница эффекта:** "There is a limit. In online auctions, an exaggerated reference price raised bids when people found it believable — but lowered them when it looked unbelievable." (Wolk & Spann, 2008)
  10. **Что на самом деле с ценами в Black Friday:** "A UK consumer group tracked 175 products from eight retailers for a full year. Eighty-three percent were the same price or cheaper at least once outside the Black Friday sales. On Black Friday itself, not one deal was the lowest price of the year." (Which?, 2025 — потребительская организация, не научное исследование; так и сказать в озвучке)
  11. **Почему «на меня не действует»:** "People rate themselves as less biased than the average person — and keep insisting on it even after the bias is explained to them. Psychologists call it the bias blind spot." (Pronin, Lin & Ross, 2002; успешно повторено — BPS Research Digest)
  12. **Противоядие №1:** "In an experiment with nine hundred people, a 'was' price next to the sale price made them more likely to buy. But when researchers also showed the true normal price — the price the item actually sold for most of the time — the effect of the 'was' price was largely wiped out." (Staelin, Urbany & Ngwe, 2023 — по источнику «largely eliminates», Notre Dame Mendoza, пресс-релиз; не «disappeared», поправлено 2026-10-21)
  13. **Противоядие №2:** "Deliberately thinking of reasons why the anchor might be wrong — 'consider the opposite' — weakens its pull." (Mussweiler, Strack & Pfeiffer, 2000) — формулировать как «ослабляет», не «убирает».
- Не упоминать / избегать:
  - Названия конкретных магазинов и брендов (в т. ч. ретейлеров из отчёта Which?) и судебные дела против конкретных компаний.
  - Утверждение, что «все скидки Black Friday фейковые» — данные Which? британские и про конкретную выборку товаров.
  - «Science proved» — только "experiments found", "a meta-analysis found".
  - Ariely, Loewenstein & Prelec (2003, якорь от номера соцстрахования) — не использовать без проверенных цифр.
  - Советы по финансам и кредитам; медицинские темы («шопоголизм» как расстройство).
- Источники и цифры, которым доверять:
  - Tversky, A., & Kahneman, D. (1974). Judgment under uncertainty: Heuristics and biases. Science, 185(4157), 1124–1131. — колесо 10/65 → медианы 25%/45%.
  - Northcraft, G. B., & Neale, M. A. (1987). Experts, amateurs, and real estate: An anchoring-and-adjustment perspective on property pricing decisions. Organizational Behavior and Human Decision Processes, 39(1), 84–97. https://ideas.repec.org/a/eee/jobhdp/v39y1987i1p84-97.html — 47 агентов, 54 студента; $119,900 → $114,204; $149,900 → $128,754.
  - Urbany, J. E., Bearden, W. O., & Weilbaker, D. C. (1988). The effect of plausible and exaggerated reference prices on consumer perceptions and price search. Journal of Consumer Research, 15(1), 95–110. https://ideas.repec.org/r/oup/jconrs/v15y1988i1p95-110.html — размер выборки уточнить (?).
  - Krishna, A., Briesch, R., Lehmann, D. R., & Yuan, H. (2002). A meta-analysis of the impact of price presentation on perceived savings. Journal of Retailing, 78(2), 101–118. https://scholar.smu.edu/business_marketing_research/23 — 20 статей.
  - Ngwe, D. (2018). Fake discounts drive real revenues in retail. Harvard Business School working paper. https://www.library.hbs.edu/working-knowledge/bargain-hunters-beware-a-store-s-original-price-might-not-be-after-all — 77 центов на $1.
  - Krishnan, B. C., Dutta, S., & Jha, S. (2013). Effectiveness of exaggerated advertised reference prices: The role of decision time pressure. Journal of Retailing, 89(1), 105–113. https://digitalcommons.memphis.edu/facpubs/11777
  - Wolk, A., & Spann, M. (2008). The effects of reference prices on bidding behavior in interactive pricing mechanisms. Journal of Interactive Marketing, 22(4), 2–18. https://ideas.repec.org/a/eee/joinma/v22y2008i4p2-18.html — название статьи сверить (?).
  - Which? (2025). Don’t believe the hype: most Black Friday deals the same price or cheaper at other times of the year. https://www.which.co.uk/policy-and-insight/article/dont-believe-the-hype-most-black-friday-deals-the-same-price-or-cheaper-at-other-times-of-the-year-which-finds-a3TbD5x5KADs — 175 товаров, 8 ретейлеров, май 2024 — май 2025, 83%.
  - Pronin, E., Lin, D. Y., & Ross, L. (2002). The bias blind spot: Perceptions of bias in self versus others. Personality and Social Psychology Bulletin, 28(3), 369–381. https://bps.org.uk/research-digest/bias-blind-spot-everyone-else-more-biased-me-just-replicated
  - YouGov (2023/2024 (?)). Deceptive deals or real savings? 51% of consumers say brands regularly float fake discounts. https://yougov.com/articles/49460-deceptive-deals-or-real-savings-51-of-consumers-say-brands-regularly-float-fake-discounts — 17 рынков; США 52%.
  - Staelin, R., Urbany, J. E., & Ngwe, D. (2023). Competition and the regulation of fictitious pricing. Journal of Marketing. https://doi.org/10.1177/00222429231164640 — 900 участников; «true normal price» гасит эффект.
  - Mussweiler, T., Strack, F., & Pfeiffer, T. (2000). Overcoming the inevitable anchoring effect: Considering the opposite compensates for selective accessibility. Personality and Social Psychology Bulletin, 26(9), 1142–1150. https://www.london.edu/faculty-and-research/academic-research/o/overcoming-the-inevitable-anchoring-effect--considering-the-opposi

## 8. Термины и произношение
| Пишется | Читать как |
|---|---|
| Tversky | tuh-VER-skee |
| Kahneman | KAHN-uh-muhn |
| Northcraft and Neale | NORTH-craft and NEEL |
| Urbany | UR-buh-nee (?) уточнить |
| Weilbaker | WILE-bay-ker (?) уточнить |
| Krishna | KRISH-nuh |
| Ngwe | n-GWAY (?) уточнить |
| Staelin | STAY-lin |
| Pronin | PRO-nin |
| Mussweiler | MOOS-vy-ler |
| Which? | "Which" — the UK consumer group (знак вопроса не читать) |
| $119,900 / $149,900 | one hundred nineteen thousand nine hundred / one hundred forty-nine thousand nine hundred |
| 77¢ | seventy-seven cents |

## 9. Начало и конец
- Крючок в первые секунды: "That red line through the old price? You know it's a trick. Half of Americans say stores fake their discounts. Researchers tested what that 'old price' does to people who know it's a trick — and it still works."
- Финал / призыв: чек отрывается: "So this Black Friday, the question isn't 'how much am I saving?' It's 'would I pay this if nobody had ever shown me the old price?'" + напоминание вопроса для комментариев.

## 10. Призывы внутри ролика (по умолчанию — да)
- Призыв подписаться в середине: да (~4:00–4:30, после фактов о магазинах, перед вердиктом)
- Своя формулировка (если есть): "If you'd rather know how your brain gets priced before you shop, subscribe to Notes From The Mind — next, we'll look at why 'I'm not fooled' is exactly what a fooled brain says."
- Вопрос для комментариев: "What's the one 'deal' you bought on Black Friday that you later saw cheaper?"
- Где задать вопрос: в блоке «почему миф живёт» (~6:30), коротко напомнить в финале.

## 11. Прочее
- Дедлайн: публикация 13–20.11.2026 (Black Friday — 27.11.2026). Ролик в работу на неделе W44–W45.
- Варианты названия (≤ 60 символов, вердикт TRUE):
  - "Why Fake Discounts Work on You (It's Not What You Think)"
  - "Your Brain on Black Friday: What Researchers Actually Found"
  - "Is It True Crossed-Out Prices Fool Us? What the Research Says"
- Превью: ценник на верёвочке с зачёркнутой «$199» и привязанным якорем + зелёная плашка **TRUE**, текст «WAS $199».
- Shorts из ролика (у каждого свой факт): 1) колесо фортуны и 25% vs 45%; 2) агенты недвижимости, которые «не поддались»; 3) 77 центов за каждый «фальшивый» доллар; 4) Which?: в сам Black Friday — ни одного минимума года.
- Источники для описания ролика:
  - Tversky, A., & Kahneman, D. (1974). Judgment under uncertainty: Heuristics and biases. Science.
  - Northcraft, G. B., & Neale, M. A. (1987). Experts, amateurs, and real estate. Organizational Behavior and Human Decision Processes. https://ideas.repec.org/a/eee/jobhdp/v39y1987i1p84-97.html
  - Urbany, J. E., Bearden, W. O., & Weilbaker, D. C. (1988). The effect of plausible and exaggerated reference prices on consumer perceptions and price search. Journal of Consumer Research.
  - Krishna, A., Briesch, R., Lehmann, D. R., & Yuan, H. (2002). A meta-analysis of the impact of price presentation on perceived savings. Journal of Retailing. https://scholar.smu.edu/business_marketing_research/23
  - Ngwe, D. (2018). Fake discounts drive real revenues in retail. HBS working paper. https://www.library.hbs.edu/working-knowledge/bargain-hunters-beware-a-store-s-original-price-might-not-be-after-all
  - Krishnan, B. C., Dutta, S., & Jha, S. (2013). Effectiveness of exaggerated advertised reference prices. Journal of Retailing.
  - Wolk, A., & Spann, M. (2008). Journal of Interactive Marketing. https://ideas.repec.org/a/eee/joinma/v22y2008i4p2-18.html
  - Staelin, R., Urbany, J. E., & Ngwe, D. (2023). Competition and the regulation of fictitious pricing. Journal of Marketing. https://doi.org/10.1177/00222429231164640
  - Pronin, E., Lin, D. Y., & Ross, L. (2002). The bias blind spot. Personality and Social Psychology Bulletin.
  - Mussweiler, T., Strack, F., & Pfeiffer, T. (2000). Overcoming the inevitable anchoring effect. Personality and Social Psychology Bulletin.
  - Which? (2025). Black Friday price tracking. https://www.which.co.uk/policy-and-insight/article/dont-believe-the-hype-most-black-friday-deals-the-same-price-or-cheaper-at-other-times-of-the-year-which-finds-a3TbD5x5KADs
  - YouGov. Deceptive deals or real savings? https://yougov.com/articles/49460-deceptive-deals-or-real-savings-51-of-consumers-say-brands-regularly-float-fake-discounts
