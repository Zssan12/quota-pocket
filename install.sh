#!/bin/bash
# macOS installer. Does not install system tools or remove files.
set -euo pipefail

main() {
  local repo='' ref='v0.1.3' source_dir='' install_root="$HOME/Library/Application Support/QuotaPocket"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --repo|--ref|--source|--install-dir)
        [[ $# -ge 2 && -n "$2" ]] || { echo "参数缺少值：$1" >&2; return 1; }
        case "$1" in
          --repo) repo="$2";; --ref) ref="$2";;
          --source) source_dir="$2";; --install-dir) install_root="$2";;
        esac
        shift 2;;
      *) echo "未知参数：$1" >&2; return 1;;
    esac
  done
  [[ "$(uname -s)" == Darwin ]] || { echo 'Quota Pocket 当前只支持 macOS。' >&2; return 1; }
  [[ "$EUID" -ne 0 ]] || { echo '请使用自己的账户运行，不要使用 sudo。' >&2; return 1; }
  [[ "$install_root" == /* && ! -L "$install_root" ]] || { echo '安装目录必须是绝对路径且不能是符号链接。' >&2; return 1; }
  echo '[1/4] 检查 Python、Node.js 和 npm……'
  local python_bin node_bin missing=0
  python_bin=$(command -v python3 || true)
  # Avoid invoking Apple's developer-tools stub on an unprepared Mac.
  if [[ "$python_bin" == /usr/bin/python3 ]] && ! /usr/bin/xcode-select -p >/dev/null 2>&1; then python_bin=''; fi
  if [[ -z "$python_bin" ]] || ! "$python_bin" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
    echo '缺少 Python 3.9 或更新版本。'; missing=1
  fi
  node_bin=$(command -v node || true)
  if [[ -z "$node_bin" ]] || ! "$node_bin" -e 'process.exit(Number(process.versions.node.split(".")[0]) < 20)' >/dev/null 2>&1; then
    echo '缺少 Node.js 20 或更新版本。'; missing=1
  fi
  if ! command -v npm >/dev/null; then echo '缺少 npm（随 Node.js 安装）。'; missing=1; fi
  if [[ "$missing" -ne 0 ]]; then
    if command -v brew >/dev/null; then
      echo '请先运行：brew install python node'
    else
      echo '请先安装 Python：https://www.python.org/downloads/macos/'
      echo '以及 Node.js LTS：https://nodejs.org/en/download'
      echo '也可以使用 Homebrew：https://brew.sh/'
    fi
    echo '安装后重新打开终端，再运行同一条安装命令；也可把 README 中的安装提示词交给本地 Agent。'
    return 1
  fi
  if [[ -f "$install_root/install.py" && -f "$install_root/server.py" && ! -f "$install_root/.install-pending" ]]; then
    echo '找到已安装的 Quota Pocket，正在打开配置网页……'
    exec "$python_bin" "$install_root/install.py" --install-dir "$install_root"
  fi
  if [[ -z "$source_dir" ]]; then
    [[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ && "$ref" =~ ^[A-Za-z0-9_.-]+$ ]] || {
      echo '请使用项目 README 中包含 --repo 的完整安装命令。' >&2; return 1;
    }
  else
    [[ -f "$source_dir/install.py" && -f "$source_dir/server.py" ]] || {
      echo '源码目录不完整。' >&2; return 1;
    }
    source_dir=$(cd "$source_dir" && pwd)
  fi
  umask 077
  mkdir -p "$install_root/.installer"
  echo '[2/4] 准备项目文件……'
  if [[ -z "$source_dir" ]]; then
    local work_dir
    work_dir=$(mktemp -d "$install_root/.installer/run.XXXXXXXX")
    /usr/bin/curl --fail --show-error --silent --location --proto '=https' --tlsv1.2 \
      --connect-timeout 15 --max-time 600 --retry 2 \
      "https://codeload.github.com/$repo/tar.gz/$ref" -o "$work_dir/source.tar.gz"
    mkdir "$work_dir/source"
    /usr/bin/tar -xzf "$work_dir/source.tar.gz" --strip-components=1 -C "$work_dir/source"
    source_dir="$work_dir/source"
  fi
  "$python_bin" "$source_dir/install.py" --source "$source_dir" --install-dir "$install_root"
}

main "$@"
