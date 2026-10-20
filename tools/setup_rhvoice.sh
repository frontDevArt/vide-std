#!/usr/bin/env bash
# Сборка RHVoice (офлайн-TTS, русские голоса) ОДИН РАЗ на машину.
# Результат кэшируется в tools/rhvoice/ внутри проекта — повторный запуск мгновенный.
#
# Все фиксы взяты из реального прогона (см. docs/LESSONS.md, раздел TTS):
#   - нужны сабмодули cmake/thirdParty/{sanitizers,CCache} и external/*
#   - shallow clone без тегов ломает VersionFromGit -> ставим локальный тег
#   - пустые каталоги несобранных голосов/языков валят cmake -> удаляем
#   - boost лежит по частям в external/libs/boost/libs/*/include -> собираем в один include
#   - tclap: конструктор ValueArg<T>(...) не компилируется в новом gcc -> sed
#
# Использование:  bash tools/setup_rhvoice.sh            (голос по умолчанию aleksandr-hq)
#                 VOICES="aleksandr-hq elena" bash tools/setup_rhvoice.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="$ROOT/tools/rhvoice"
SRC="$ROOT/tools/.build/RHVoice"
VOICES="${VOICES:-aleksandr-hq}"

if [ -x "$PREFIX/bin/RHVoice-test" ] && [ -f "$PREFIX/rhvoice" ]; then
  echo "[rhvoice] уже установлен: $PREFIX"; exit 0
fi

for t in git cmake make perl awk; do
  command -v "$t" >/dev/null || { echo "[rhvoice] нет $t — установите (Linux: build-essential cmake git; macOS: xcode-select --install && brew install cmake)"; exit 1; }
done
command -v g++ >/dev/null || command -v clang++ >/dev/null || { echo "[rhvoice] нет C++ компилятора"; exit 1; }
# nproc есть не везде (macOS)
JOBS="${JOBS:-$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)}"

mkdir -p "$ROOT/tools/.build"
if [ ! -d "$SRC/.git" ]; then
  echo "[rhvoice] clone..."
  git clone --depth 1 https://github.com/RHVoice/RHVoice.git "$SRC"
fi
cd "$SRC"

subs="data/languages/Russian cmake/thirdParty/sanitizers cmake/thirdParty/CCache"
for v in $VOICES; do subs="$subs data/voices/$v"; done
subs="$subs $(awk '$1=="path" && $3 ~ /^external\// {print $3}' .gitmodules | tr '\n' ' ')"
echo "[rhvoice] submodules (это самая долгая часть)..."
# shellcheck disable=SC2086
git submodule update --init --depth 1 $subs </dev/null

git tag 1.16.0 2>/dev/null || true
for d in data/voices/* data/languages/*; do
  [ -d "$d" ] && [ -z "$(ls -A "$d")" ] && rmdir "$d"
done

BOOST="$ROOT/tools/.build/boostinc"
mkdir -p "$BOOST"
for l in external/libs/boost/libs/*/include; do cp -r "$l/boost" "$BOOST/" 2>/dev/null || true; done

# perl -pi вместо sed -i: одинаково работает на Linux и macOS
perl -pi -e 's/ValueArg<T>\(const ValueArg<T>& rhs\);/ValueArg(const ValueArg<T>& rhs);/' src/third-party/tclap/tclap/ValueArg.h
perl -pi -e 's/MultiArg<T>\(const MultiArg<T>& rhs\);/MultiArg(const MultiArg<T>& rhs);/' src/third-party/tclap/tclap/MultiArg.h

rm -rf build && mkdir build && cd build
echo "[rhvoice] cmake..."
CXXFLAGS="-I$BOOST" CFLAGS="-I$BOOST" cmake .. -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" > cfg.log 2>&1 || { tail -30 cfg.log; exit 1; }
echo "[rhvoice] make -j$JOBS..."
make -j"$JOBS" > mk.log 2>&1 || { grep -E ' error' mk.log | head -20; exit 1; }
make install > in.log 2>&1

# Обёртка: правильный LD_LIBRARY_PATH и чтение текста ТОЛЬКО из файла.
cat > "$PREFIX/rhvoice" <<'EOF'
#!/usr/bin/env bash
# rhvoice <voice> <rate%> <in.txt> <out.wav>
# Внимание: пути к данным голосов вшиты при сборке — после переноса папки студии запустите setup заново.
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export LD_LIBRARY_PATH="$D/lib:${LD_LIBRARY_PATH:-}"
export DYLD_LIBRARY_PATH="$D/lib:${DYLD_LIBRARY_PATH:-}"
exec "$D/bin/RHVoice-test" -p "$1" -q max -r "$2" -i "$3" -o "$4" </dev/null >/dev/null 2>&1
EOF
chmod +x "$PREFIX/rhvoice"

echo "Проверка." > /tmp/rhv_check.txt
"$PREFIX/rhvoice" "${VOICES%% *}" 100 /tmp/rhv_check.txt /tmp/rhv_check.wav
[ -s /tmp/rhv_check.wav ] && echo "[rhvoice] OK -> $PREFIX" || { echo "[rhvoice] синтез не работает"; exit 1; }
# Исходники (~300 МБ) больше не нужны. KEEP_BUILD=1 — оставить (например, чтобы доустановить голоса).
[ "${KEEP_BUILD:-0}" = "1" ] || rm -rf "$ROOT/tools/.build"
