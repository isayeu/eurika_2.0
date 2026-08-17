#!/usr/bin/env bash
set -euo pipefail

desktop_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repository_root="$(cd "$desktop_root/.." && pwd)"
binary="$desktop_root/release/linux-unpacked/eurika-desktop"
target="${XDG_DATA_HOME:-$HOME/.local/share}/applications/eurika.desktop"
python_bin="${EURIKA_PYTHON:-}"

if [[ -z "$python_bin" && -x "$repository_root/../venv/bin/python" ]]; then
  python_bin="$repository_root/../venv/bin/python"
fi
if [[ -z "$python_bin" ]]; then
  python_bin="$(command -v python3)"
fi

if [[ ! -x "$binary" ]]; then
  echo "Build Eurika Desktop first: npm --prefix \"$desktop_root\" run dist:linux" >&2
  exit 1
fi

mkdir -p "$(dirname "$target")"
cat >"$target" <<EOF
[Desktop Entry]
Type=Application
Name=Eurika
Comment=Standalone local coding agent
Exec=env -u ELECTRON_RUN_AS_NODE EURIKA_PYTHON="$python_bin" "$binary"
Terminal=false
Categories=Development;IDE;
StartupNotify=true
EOF
echo "Installed $target"
