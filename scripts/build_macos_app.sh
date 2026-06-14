#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="SwCSI"
VERSION="V1.0.2"
DIST_DIR="$ROOT/dist"
BUILD_DIR="$ROOT/build/pyinstaller_macos"
OUT_DIR="$ROOT/dist_installer"
APP_PATH="$DIST_DIR/$APP_NAME.app"
DMG_PATH="$OUT_DIR/${APP_NAME}_${VERSION}_macOS.dmg"

cd "$ROOT"
mkdir -p "$OUT_DIR"

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt pyinstaller pillow

rm -rf "$BUILD_DIR" "$APP_PATH"

python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --icon "$ROOT/assets/swcsi_icon.icns" \
  --paths "$ROOT/tools" \
  --add-data "$ROOT/assets:assets" \
  --add-data "$ROOT/docs:docs" \
  --distpath "$DIST_DIR" \
  --workpath "$BUILD_DIR" \
  "$ROOT/tools/csi_workbench.py"

if [[ ! -d "$APP_PATH" ]]; then
  echo "Missing app bundle: $APP_PATH" >&2
  exit 1
fi

rm -f "$DMG_PATH"
hdiutil create \
  -volname "$APP_NAME $VERSION" \
  -srcfolder "$APP_PATH" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo "App bundle: $APP_PATH"
echo "DMG image: $DMG_PATH"
