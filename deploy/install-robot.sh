#!/usr/bin/env bash
# D1 Max 机器人一键装机 / 重装(用户 2026-11-23:「装机脚本可以做一下，能不能做成一键式的？这样对客户也简单」)。
#
# 发行目录里跟 <包名>.tar.gz 并排放着 <包名>.install-robot.sh(就是这个文件)。把这两个(最好连
# <包名>.SHA256SUMS.txt)拷到机器人上同一个目录,一条命令:
#
#   sudo bash 2026-11-22-5262cd3b.install-robot.sh
#
# 它做的事:核 .tar.gz 的指纹(有 SHA256SUMS 就核,对不上就停)→ 解到服务账号家目录下的包目录 →
# 跑包里的 deploy/install.sh(新装、重装、补系统设置都是它;它能重跑,已经在跑这一版就不切换)。
# 也可以显式给 .tar.gz:sudo bash install-robot.sh /路径/2026-11-22-5262cd3b.tar.gz
# 离线轮子、账号名照装机脚本的规矩透传(NEXWAR_PIP_ARGS、NEXWAR_USER)。
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "要 root:sudo bash $0 $*" >&2
  exit 2
fi

SELF=$(basename "$0")
HERE=$(cd "$(dirname "$0")" && pwd)
TGZ=${1:-}
if [[ -z "$TGZ" ]]; then
  base=${SELF%.install-robot.sh}
  if [[ "$base" == "$SELF" ]]; then
    echo "用法: sudo bash <包名>.install-robot.sh   或   sudo bash $SELF <包名>.tar.gz" >&2
    exit 2
  fi
  TGZ="$HERE/$base.tar.gz"
fi
if [[ ! -f "$TGZ" ]]; then
  echo "错误: 找不到发行包 $TGZ(要跟这个脚本放在同一个目录,或者显式给路径)" >&2
  exit 2
fi
TGZ=$(cd "$(dirname "$TGZ")" && pwd)/$(basename "$TGZ")
NAME=$(basename "$TGZ" .tar.gz)
# 包名规矩跟装机脚本、engine/release.py 的 _NAME_RE 一字不差:<日期>-<6 到 12 位十六进制>
if [[ ! "$NAME" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9a-f]{6,12}$ ]]; then
  echo "错误: 包名不对: $NAME(应是 <日期>-<6 到 12 位十六进制>.tar.gz,别改发行包的文件名)" >&2
  exit 2
fi

echo ">>> 1/3 核发行包 $NAME.tar.gz"
SUMS="$(dirname "$TGZ")/$NAME.SHA256SUMS.txt"
if [[ -f "$SUMS" ]]; then
  want=$(awk -v f="$NAME.tar.gz" '$2 == f {print $1}' "$SUMS")
  got=$(sha256sum "$TGZ" | cut -d' ' -f1)
  if [[ -z "$want" || "$want" != "$got" ]]; then
    echo "错误: $NAME.tar.gz 的指纹跟 $NAME.SHA256SUMS.txt 对不上(拷坏了?重新下载)" >&2
    exit 3
  fi
  echo "  指纹对上了"
else
  echo "  没有 $NAME.SHA256SUMS.txt,不核文件指纹(下一步装机照样验发行签名和内容指纹)"
fi
# 包里只许有 <包名>/ 底下的东西(防路径穿越、防解到别处)
if tar -tzf "$TGZ" | grep -v -E "^$NAME(/|\$)" | grep -q .; then
  echo "错误: $NAME.tar.gz 里有 $NAME/ 以外的东西,不是我们的发行包" >&2
  exit 3
fi

RUN_USER=${NEXWAR_USER:-robot}
if ! HOME_DIR=$(getent passwd "$RUN_USER" | cut -d: -f6) || [[ -z "$HOME_DIR" || ! -d "$HOME_DIR" ]]; then
  echo "错误: 这台机器上没有账号 $RUN_USER(或者它没有家目录)" >&2
  exit 2
fi
DEST="$HOME_DIR/$NAME"
echo ">>> 2/3 解包到 $DEST"
WORK=$(mktemp -d "$HOME_DIR/.$NAME.XXXXXX")
trap 'rm -rf "$WORK"' EXIT
tar -xzf "$TGZ" -C "$WORK" --no-same-owner --no-same-permissions
rm -rf "$DEST"
mv "$WORK/$NAME" "$DEST"

echo ">>> 3/3 跑装机脚本(能重跑;已经在跑这一版就不切换,只补服务单元、系统设置)"
bash "$DEST/deploy/install.sh" "$DEST"
