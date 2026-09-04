#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP=Meridian
DIST="$ROOT/dist"
APPDIR="$DIST/${APP}.AppDir"
TOOLS="$ROOT/.appimage-tools"
ARCH="$(uname -m)"
FONTS_SRC="$ROOT/resources/fonts"
# Standalone AppImage path — outside usr/bin / PyInstaller tree (UFL-friendly).
FONTS_DST="$APPDIR/usr/share/fonts/truetype/meridian"
DOC_ROOT="$APPDIR/usr/share/doc/meridian"
DOC_FONTS="$DOC_ROOT/ubuntu-font-licence"
DOC_THIRD="$DOC_ROOT/third-party"
LICENSE_FALLBACKS="$ROOT/resources/licenses"

PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Create .venv first (python3 -m venv --system-site-packages .venv && pip install mutagen numpy aubio pyinstaller)"
  exit 1
fi

run_py() {
  env -i \
    HOME="${HOME}" \
    USER="${USER:-}" \
    PATH="${ROOT}/.venv/bin:/usr/bin:/bin:/usr/local/bin" \
    PYTHONPATH="${ROOT}" \
    LANG="${LANG:-C.UTF-8}" \
    QT_QPA_PLATFORM=offscreen \
    "$PYTHON" "$@"
}

run_py - <<'PY'
from pathlib import Path
from PySide6.QtGui import QImage, QPainter, QGuiApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QRectF, Qt
import sys

app = QGuiApplication(sys.argv)
svg = Path("resources/meridian.svg").read_bytes()
renderer = QSvgRenderer(svg)
image = QImage(256, 256, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
painter = QPainter(image)
renderer.render(painter, QRectF(0, 0, 256, 256))
painter.end()
image.save("resources/meridian.png")
print("wrote resources/meridian.png")
PY

if [[ ! -f "$FONTS_SRC/UbuntuSans[wdth,wght].ttf" ]] \
   || [[ ! -f "$FONTS_SRC/UbuntuCondensed-Regular.ttf" ]]; then
  echo "Bundled fonts missing — fetching…"
  bash "$ROOT/packaging/fetch-fonts.sh"
fi

# Ensure UFL text is present next to the font files before packaging.
if [[ ! -f "$FONTS_SRC/UBUNTU-FONT-LICENCE-1.0.txt" ]]; then
  if [[ -f "$FONTS_SRC/LICENCE.txt" ]]; then
    cp -f "$FONTS_SRC/LICENCE.txt" "$FONTS_SRC/UBUNTU-FONT-LICENCE-1.0.txt"
  else
    echo "Missing Ubuntu Font Licence text in $FONTS_SRC" >&2
    exit 1
  fi
fi
if [[ ! -f "$FONTS_SRC/COPYRIGHT.txt" ]]; then
  bash "$ROOT/packaging/fetch-fonts.sh"
fi

for required in LICENSE COPYING COPYRIGHT.txt THIRD_PARTY_NOTICES.txt SOURCE_OFFER.txt; do
  if [[ ! -f "$ROOT/$required" ]]; then
    echo "Missing required project licence file: $required" >&2
    exit 1
  fi
done

run_py -m PyInstaller --noconfirm --clean "$ROOT/packaging/meridian.spec"

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$FONTS_DST" "$DOC_FONTS" "$DOC_THIRD"

cp -a "$DIST/$APP/." "$APPDIR/usr/bin/"
cp "$ROOT/resources/meridian.desktop" "$APPDIR/usr/share/applications/${APP}.desktop"
cp "$ROOT/resources/meridian.desktop" "$APPDIR/${APP}.desktop"
cp "$ROOT/resources/meridian.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/meridian.png"
cp "$ROOT/resources/meridian.png" "$APPDIR/meridian.png"
ln -sf meridian.png "$APPDIR/.DirIcon"

# --- Meridian GPL-3 + notices (required for binary redistribution) ---
install -m 0644 "$ROOT/LICENSE" "$DOC_ROOT/LICENSE"
install -m 0644 "$ROOT/COPYING" "$DOC_ROOT/COPYING"
install -m 0644 "$ROOT/COPYRIGHT.txt" "$DOC_ROOT/COPYRIGHT.txt"
install -m 0644 "$ROOT/THIRD_PARTY_NOTICES.txt" "$DOC_ROOT/THIRD_PARTY_NOTICES.txt"
install -m 0644 "$ROOT/SOURCE_OFFER.txt" "$DOC_ROOT/SOURCE_OFFER.txt"
# Also at AppDir root for easy discovery when extracting the AppImage.
install -m 0644 "$ROOT/LICENSE" "$APPDIR/LICENSE"
install -m 0644 "$ROOT/THIRD_PARTY_NOTICES.txt" "$APPDIR/THIRD_PARTY_NOTICES.txt"
install -m 0644 "$ROOT/SOURCE_OFFER.txt" "$APPDIR/SOURCE_OFFER.txt"

# Collect licence texts from installed wheels / site-packages.
run_py "$ROOT/packaging/collect_third_party_licenses.py" "$DOC_THIRD" \
  || echo "WARN: some package licence files missing; installing fallbacks" >&2

install -m 0644 "$LICENSE_FALLBACKS/qt-for-python-NOTICE.txt" "$DOC_THIRD/qt-for-python-NOTICE.txt"
if [[ ! -d "$DOC_THIRD/mutagen" ]] || [[ -z "$(ls -A "$DOC_THIRD/mutagen" 2>/dev/null || true)" ]]; then
  mkdir -p "$DOC_THIRD/mutagen"
  install -m 0644 "$LICENSE_FALLBACKS/mutagen-NOTICE.txt" "$DOC_THIRD/mutagen/NOTICE.txt"
fi
if [[ ! -d "$DOC_THIRD/numpy" ]] || [[ -z "$(ls -A "$DOC_THIRD/numpy" 2>/dev/null || true)" ]]; then
  mkdir -p "$DOC_THIRD/numpy"
  install -m 0644 "$LICENSE_FALLBACKS/numpy-NOTICE.txt" "$DOC_THIRD/numpy/NOTICE.txt"
fi
if [[ ! -d "$DOC_THIRD/aubio" ]] || [[ -z "$(ls -A "$DOC_THIRD/aubio" 2>/dev/null || true)" ]]; then
  mkdir -p "$DOC_THIRD/aubio"
  install -m 0644 "$LICENSE_FALLBACKS/aubio-NOTICE.txt" "$DOC_THIRD/aubio/NOTICE.txt"
fi
if [[ ! -d "$DOC_THIRD/pyinstaller" ]] || [[ -z "$(ls -A "$DOC_THIRD/pyinstaller" 2>/dev/null || true)" ]]; then
  mkdir -p "$DOC_THIRD/pyinstaller"
  install -m 0644 "$LICENSE_FALLBACKS/pyinstaller-NOTICE.txt" "$DOC_THIRD/pyinstaller/NOTICE.txt"
fi
if [[ ! -d "$DOC_THIRD/pyside6" ]] || [[ -z "$(ls -A "$DOC_THIRD/pyside6" 2>/dev/null || true)" ]]; then
  mkdir -p "$DOC_THIRD/pyside6"
  install -m 0644 "$LICENSE_FALLBACKS/qt-for-python-NOTICE.txt" "$DOC_THIRD/pyside6/NOTICE.txt"
fi

# Install Font Software as ordinary files in the AppImage filesystem.
# Do not place these under the PyInstaller onedir (usr/bin) or embed in the EXE.
install -m 0644 "$FONTS_SRC/"*.ttf "$FONTS_DST/"
install -m 0644 "$FONTS_SRC/UBUNTU-FONT-LICENCE-1.0.txt" "$FONTS_DST/"
install -m 0644 "$FONTS_SRC/UBUNTU-FONT-LICENCE-1.0.txt" "$DOC_FONTS/"
if [[ -f "$FONTS_SRC/UFL.txt" ]]; then
  install -m 0644 "$FONTS_SRC/UFL.txt" "$FONTS_DST/"
  install -m 0644 "$FONTS_SRC/UFL.txt" "$DOC_FONTS/"
fi
if [[ -f "$FONTS_SRC/LICENCE.txt" ]]; then
  install -m 0644 "$FONTS_SRC/LICENCE.txt" "$FONTS_DST/"
  install -m 0644 "$FONTS_SRC/LICENCE.txt" "$DOC_FONTS/"
fi
install -m 0644 "$FONTS_SRC/COPYRIGHT.txt" "$FONTS_DST/"
install -m 0644 "$FONTS_SRC/COPYRIGHT.txt" "$DOC_FONTS/"
if [[ -f "$FONTS_SRC/README.txt" ]]; then
  install -m 0644 "$FONTS_SRC/README.txt" "$FONTS_DST/"
fi

# Guard: refuse to ship if fonts somehow landed inside the PyInstaller tree.
if find "$APPDIR/usr/bin" \( -iname '*ubuntu*.ttf' -o -iname '*UbuntuSans*' \) 2>/dev/null | grep -q .; then
  echo "ERROR: Ubuntu fonts must not be inside usr/bin (PyInstaller tree)" >&2
  find "$APPDIR/usr/bin" \( -iname '*ubuntu*.ttf' -o -iname '*UbuntuSans*' \) >&2
  exit 1
fi
if [[ ! -f "$FONTS_DST/UbuntuCondensed-Regular.ttf" ]] \
   || [[ ! -f "$FONTS_DST/UBUNTU-FONT-LICENCE-1.0.txt" ]] \
   || [[ ! -f "$FONTS_DST/COPYRIGHT.txt" ]]; then
  echo "ERROR: incomplete standalone font install in $FONTS_DST" >&2
  ls -la "$FONTS_DST" >&2 || true
  exit 1
fi

# Guard: Meridian + third-party docs must be present.
for f in \
  "$DOC_ROOT/LICENSE" \
  "$DOC_ROOT/COPYRIGHT.txt" \
  "$DOC_ROOT/THIRD_PARTY_NOTICES.txt" \
  "$DOC_ROOT/SOURCE_OFFER.txt" \
  "$DOC_THIRD/qt-for-python-NOTICE.txt"
do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: missing documentation file in AppDir: $f" >&2
    exit 1
  fi
done
if [[ -z "$(ls -A "$DOC_THIRD/mutagen" 2>/dev/null || true)" ]] \
   || [[ -z "$(ls -A "$DOC_THIRD/numpy" 2>/dev/null || true)" ]] \
   || [[ -z "$(ls -A "$DOC_THIRD/aubio" 2>/dev/null || true)" ]] \
   || [[ -z "$(ls -A "$DOC_THIRD/pyinstaller" 2>/dev/null || true)" ]]; then
  echo "ERROR: incomplete third-party licence tree under $DOC_THIRD" >&2
  find "$DOC_THIRD" -type f >&2 || true
  exit 1
fi

cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "$0")")"
export APPDIR="${APPDIR:-$HERE}"
export MERIDIAN_FONTS_DIR="${HERE}/usr/share/fonts/truetype/meridian"
export QT_PLUGIN_PATH="${HERE}/usr/bin/PySide6/Qt/plugins:${QT_PLUGIN_PATH:-}"
export QT_QPA_PLATFORM_PLUGIN_PATH="${HERE}/usr/bin/PySide6/Qt/plugins/platforms"
export QT_MEDIA_BACKEND="${QT_MEDIA_BACKEND:-ffmpeg}"
exec "${HERE}/usr/bin/Meridian" "$@"
EOF
chmod +x "$APPDIR/AppRun" "$APPDIR/usr/bin/Meridian"

mkdir -p "$TOOLS"
TOOL="$TOOLS/appimagetool-${ARCH}.AppImage"
if [[ ! -x "$TOOL" ]]; then
  URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
  echo "Downloading appimagetool…"
  curl -L --fail -o "$TOOL" "$URL"
  chmod +x "$TOOL"
fi

export ARCH
export APPIMAGE_EXTRACT_AND_RUN=1
"$TOOL" "$APPDIR" "$DIST/${APP}-${ARCH}.AppImage"
chmod +x "$DIST/${APP}-${ARCH}.AppImage"
echo "Built $DIST/${APP}-${ARCH}.AppImage"
echo "Licences:  usr/share/doc/meridian/  (+ LICENSE at AppDir root)"
echo "Fonts/UFL: usr/share/fonts/truetype/meridian/"
