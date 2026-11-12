#!/bin/sh
set -eu

if [ "$(id -u)" -eq 0 ]; then
    echo "Run install.sh as your desktop user; it will request sudo only for system installation." >&2
    exit 1
fi

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$project_dir"

build_venv="$project_dir/.build-venv"
python3 -m venv "$build_venv"
"$build_venv/bin/python" -m pip install --upgrade build
"$build_venv/bin/python" -m build --wheel --outdir "$project_dir/dist" "$project_dir"

version=$(sed -n 's/^version = "\([^"]*\)"/\1/p' pyproject.toml | head -n 1)
wheel="$project_dir/dist/xfce_util-$version-py3-none-any.whl"
if [ ! -f "$wheel" ]; then
    echo "Built wheel not found: $wheel" >&2
    exit 1
fi

sudo install -d -m 755 /opt/xfceutil
if [ ! -x /opt/xfceutil/venv/bin/python ]; then
    sudo python3 -m venv /opt/xfceutil/venv
fi
sudo chown -R root:root /opt/xfceutil
sudo chmod -R go-w /opt/xfceutil
sudo /opt/xfceutil/venv/bin/python -m pip install \
    --only-binary=:all: --upgrade --force-reinstall "$wheel"
sudo chown -R root:root /opt/xfceutil
sudo chmod -R go-w /opt/xfceutil
sudo install -Dm644 "$project_dir/xfce-util.svg" \
    /usr/local/share/icons/hicolor/scalable/apps/xfce-util.svg
sudo install -d -m 755 /usr/local/share/pixmaps
sudo /opt/xfceutil/venv/bin/python -c \
    'import sys, cairosvg; cairosvg.svg2png(url=sys.argv[1], write_to=sys.argv[2], output_width=128, output_height=128)' \
    "$project_dir/xfce-util.svg" /usr/local/share/pixmaps/xfce-util.png
sudo install -Dm755 "$project_dir/xfce-util-launcher" /usr/local/bin/xfce-util
sudo install -Dm644 "$project_dir/xfce-util.desktop" \
    /usr/local/share/applications/xfce-util.desktop

printf 'Installed XFCE Utility. Launch it from the applications menu or run: xfce-util\n'
