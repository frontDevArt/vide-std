# Озвучка: бэкенды

Выбирается в `project.yaml → tts.backend`. Тайминги, субтитры и микс от бэкенда не зависят.
`python -m studio doctor` честно проверяет каждый бэкенд реальным синтезом.

| Бэкенд | Качество | Офлайн | Установка | Статус в студии |
|---|---|---|---|---|
| `rhvoice` | хорошее, «дикторское» | да | `bash tools/setup_rhvoice.sh` (сборка ~5–10 мин, один раз) | проверен end-to-end |
| `edge` | очень естественное (нейросеть Microsoft) | нет, нужен интернет | `pip install edge-tts` | код готов, в облачной песочнице не проверялся (сеть закрыта) |
| `elevenlabs` | лучшее, голос канала | нет, платно | ключ и голос в `.env` (см. ниже) | код готов, без ключа не проверялся |
| `piper` | естественное, нейросеть | да | бинарник piper + модель `.onnx` в `tools/piper-voices/` | код готов, не проверялся |

Язык ролика — `language` в `project.yaml` (ru по умолчанию). При `tts.voice: auto` голос берётся из профиля
языка в `studio/lang.py` (там же фраза проверки, ориентир слов/мин и надписи шаблонов). Новый язык = запись в `LANGS`.

Голоса (ru):
- rhvoice: `aleksandr-hq` (мужской, спокойный). Другие: `VOICES="aleksandr-hq elena" KEEP_BUILD=1 bash tools/setup_rhvoice.sh`
  (при уже установленном — удалить `tools/rhvoice` и запустить снова).
- edge: `ru-RU-DmitryNeural` (мужской), `ru-RU-SvetlanaNeural` (женский).
- piper: `ru_RU-dmitri-medium`, `ru_RU-denis-medium`, `ru_RU-ruslan-medium` (файлы `<имя>.onnx` + `.onnx.json`).

Голоса (en):
- rhvoice: `slt` (женский), `bdl`, `alan` — сборка: `VOICES="aleksandr-hq slt" LANGUAGES="Russian English" bash tools/setup_rhvoice.sh`.
- edge: `en-US-GuyNeural`, `en-US-AriaNeural`, `en-GB-RyanNeural`.
- piper: `en_US-lessac-medium`, `en_US-ryan-medium`.

Английский путь пока не проверялся end-to-end: голоса по умолчанию и `wpm: 155` — оценка, уточнить на первом ролике.

Темп `rate` — проценты: 100 = норма бэкенда. Для edge переводится в `--rate=+N%`, для piper — в `length_scale`.

Если бэкенд недоступен — студия падает с понятной ошибкой на фазе voice. **Никогда не заменять
озвучку молча субтитрами** — сообщить пользователю и предложить вариант установки.

Произношение: если слово звучит неверно — перепишите фонетически или синонимом в `lines`
(субтитры можно оставить правильными, сделав для этой сцены отдельный шаблонный текст).
Латиницу и аббревиатуры `validate` подсвечивает.

## ElevenLabs (голос канала Notes From The Mind)
1. `.env` в корне студии (он в `.gitignore`, образец — `.env.example`):
   `ELEVENLABS_API_KEY=…`, `ELEVENLABS_VOICE_ID=…` (ID голоса из elevenlabs.io → Voices), опц. `ELEVENLABS_MODEL_ID`.
2. `project.yaml`: `tts: {backend: elevenlabs, voice: auto, rate: 100}` — `voice: auto` берёт `ELEVENLABS_VOICE_ID`.
   Темп — **только числом** (подбор `auto` синтезировал бы текст несколько раз — это деньги). `rate/100` → `voice_settings.speed`,
   ограничено 0,7–1,2. Необязательно: `model`, `stability`, `similarity_boost`, `style`, `use_speaker_boost` — входят в ключ кэша.
3. `python -m studio voice <проект>` сначала печатает, сколько символов уйдёт в синтез (кэш не считается), и **не синтезирует**
   без `--yes`. `doctor`/`probe` проверяют ключ и голос бесплатными запросами (`/v1/user`, `/v1/voices/{id}`).
4. Эндпоинт `POST /v1/text-to-speech/{voice_id}/with-timestamps` → mp3 + времена символов → слова
   (`build/tts/<hash>.words.json`). 401/403/429 — понятная ошибка без ретраев.

## Таймкоды слов
Нужны для слов-триггеров шаблонов `lab_*` и караоке-субтитров. ElevenLabs — из ответа API, edge — события WordBoundary
(Python API edge-tts), piper/rhvoice — оценка по слогам внутри битов. Времена сдвигаются на срезанную в начале тишину.
В `timeline.json` у каждой сцены — `words: [{w, t0, t1, line}]`.
