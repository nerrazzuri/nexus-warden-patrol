#!/usr/bin/env bash
# 12-03 演讲会 A 方案:机器人自己走 4G,经 Tailscale 连站点笔记本(docs/POC-1203-演讲会-路上画面.md 第〇节)。
# 用户 11-23:「把 tailscale 的配置做成一个脚本」。
#
# 在**站点笔记本**上跑(它连着机器人热点,ssh 得到 Orin 和 RK3588):
#
#   tools/link_4g.sh status                       看现在是哪套连法(只读)
#   tools/link_4g.sh prepare                      一次:站点证书加上笔记本的 Tailscale 地址、重签(手机要重新添加站点)
#   tools/link_4g.sh up   --ssid <随身Wi-Fi名> [--hours 6]
#                                                 切到 A:RK3588 临时连随身 Wi-Fi、Orin 默认路线指向 RK3588、
#                                                 代理和画面改连笔记本的 Tailscale 地址。机器人重启过就再跑一次
#   tools/link_4g.sh down                         切回 B(热点):全部改回,删厂家脚本建的 sta.conf
#
#   加 --dry-run:只打印要做的事,不连机器人、不改东西
#
# - 随身 Wi-Fi 口令在终端里问(不回显),不进命令行历史、不进日志。
# - RK3588 只用厂家脚本临时连(不 enable、不 save);RK3588 和 Orin 上都先排好到点自动改回(--hours,
#   缺省 6 小时;彩排用 --hours 0.25)。到点前跑 down 会把排好的取消。
# - 都是临时改动:机器人重启后 RK3588 和 Orin 自己回到 B;站点上的 srt_host 和 Orin 的 env 要 down 改回。
# - 不碰 Tailscale 本身的登录、不开 funnel、不改厂家的任何配置文件。
set -euo pipefail

ORIN="${ORIN:-robot@192.168.168.100}"           # 经机器人热点(笔记本的连接带 192.168.168.0/24 路由)
RK="${RK:-robot@192.168.234.1}"
RK_STA="${RK_STA:-/opt/runtime/bin/robot_sta.sh}"
ORIN_IF="${ORIN_IF:-enP8p1s0}"
ORIN_GW_B="${ORIN_GW_B:-192.168.113.1}"         # 平时经 R300S(11-23 实测)
ORIN_GW_A="${ORIN_GW_A:-192.168.168.168}"       # RK3588
HOTSPOT_IP="${HOTSPOT_IP:-192.168.234.232}"     # 笔记本在机器人热点上的固定地址
SITE_HOME="${SITE_HOME:-/var/lib/nexwar_site}"
SITE_CLI="${SITE_CLI:-nexwar_site}"
SSH_OPTS=(-o ConnectTimeout=8 -o ServerAliveInterval=5)

DRY=0; CMD=""; SSID=""; HOURS=6
while [ $# -gt 0 ]; do
  case "$1" in
    status|prepare|up|down) CMD="$1" ;;
    --ssid) SSID="${2:-}"; shift ;;
    --hours) HOURS="${2:-}"; shift ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "不认识的参数:$1(--help 看用法)" >&2; exit 2 ;;
  esac
  shift
done
[ -n "$CMD" ] || { sed -n '2,24p' "$0"; exit 2; }

say() { printf '== %s\n' "$*"; }
die() { printf '!! %s\n' "$*" >&2; exit 1; }

# 远端跑一段 bash(要 sudo 的地方 -t,让 sudo 能问密码)
on() {  # on <主机> <说明> <脚本>
  local host="$1" what="$2" script="$3"
  say "$what($host)"
  if [ "$DRY" = 1 ]; then printf '%s\n' "$script" | sed 's/^/   | /'; return 0; fi
  ssh -t "${SSH_OPTS[@]}" "$host" "bash -c $(printf %q "$script")"
}
local_do() {  # local_do <说明> <脚本>
  say "$1(笔记本)"
  if [ "$DRY" = 1 ]; then printf '%s\n' "$2" | sed 's/^/   | /'; return 0; fi
  bash -c "$2"
}

ts_ip() {
  if [ "$DRY" = 1 ]; then echo "100.69.130.19"; return; fi
  command -v tailscale >/dev/null || die "笔记本上没装 Tailscale(docs/POC-1203 第〇节第 1 步)"
  local ip; ip="$(tailscale ip -4 2>/dev/null | head -1)"
  [[ "$ip" =~ ^100\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "拿不到笔记本的 Tailscale 地址:tailscale up 了吗"
  echo "$ip"
}

hours_s() {
  python3 -c "import sys; h=float(sys.argv[1]); assert 0.05<=h<=24; print(int(h*3600))" "$HOURS" 2>/dev/null \
    || die "--hours 要在 0.05–24 之间:$HOURS"
}

# site.json:读 / 改(以站点账号跑,不改属主)
site_json_py() {  # site_json_py <python 片段,变量 d 是 site.json>
  printf 'sudo -u nexwar_site python3 - %q <<'"'"'PY'"'"'\nimport json, sys\np = sys.argv[1] + "/site.json"\nd = json.load(open(p))\n%s\nPY\n' "$SITE_HOME" "$1"
}

# 站点对时也发给 Tailscale 地址(装站点时只放了私网;旧站点、升级过的站点补一行,有了不动)
CHRONY_SITE_CONF="${CHRONY_SITE_CONF:-/etc/chrony/conf.d/nexwar_site.conf}"
chrony_allow_ts() {
  local_do "站点对时也给 Tailscale 地址(100.64.0.0/10)发" \
"if grep -qx 'allow 100.64.0.0/10' $CHRONY_SITE_CONF 2>/dev/null; then echo '已经有了'; else
  echo 'allow 100.64.0.0/10' | sudo tee -a $CHRONY_SITE_CONF >/dev/null && sudo systemctl restart chrony && echo '加上了,chrony 重启了'; fi"
}

case "$CMD" in
status)
  TS="$(ts_ip)"
  say "笔记本 Tailscale 地址:$TS"
  local_do "站点证书里有没有它、画面连哪" "$(site_json_py "print('hostnames:', d.get('hostnames')); print('video.srt_host:', (d.get('video') or {}).get('srt_host', '(缺省 = hostnames[0])'))")"
  on "$ORIN" "Orin:默认路线、代理连哪、Tailscale" \
    "ip route show default; grep -E '^NEXWAR_SITE_(MQTT|NTP)=' /etc/nexwar/env; tailscale status 2>/dev/null | head -5; chronyc sources 2>/dev/null | grep -E '^\^' ; systemctl list-timers --all 2>/dev/null | grep -E 'nexwar-4g' || true"
  on "$RK" "RK3588:wlan0、热点" \
    "wpa_cli -i wlan0 status 2>/dev/null | grep -E 'wpa_state|ssid|ip_address' || echo 'wpa_supplicant 没在跑'; iw dev | grep -E 'Interface|ssid|channel'; systemctl list-timers --all 2>/dev/null | grep -E 'nexwar-sta' || true"
  ;;

prepare)
  TS="$(ts_ip)"
  say "站点证书加上 $TS,重签。**重签以后每部手机要重新添加站点(扫配对码)**,机器人不用动。"
  if [ "$DRY" = 0 ]; then read -r -p "继续?(yes/no) " ok; [ "$ok" = yes ] || die "没做"; fi
  local_do "备份 site.json、hostnames 末尾加 $TS" \
    "sudo cp -a $SITE_HOME/site.json $SITE_HOME/site.json.bak-\$(date +%Y%m%d-%H%M%S)
$(site_json_py "h = d['hostnames']
if '$TS' in h: print('已经有了,不改'); sys.exit(0)
h.append('$TS')
json.dump(d, open(p + '.tmp', 'w'), ensure_ascii=False, indent=2); open(p + '.tmp', 'a').write('\n')
import os; os.replace(p + '.tmp', p); print('hostnames:', h)")"
  local_do "重签站点证书、重启站点" \
    "sudo -u nexwar_site $SITE_CLI --home $SITE_HOME vpn reissue-cert
sudo systemctl restart nexwar_mosquitto nexwar_site"
  chrony_allow_ts
  say "做完:每部手机重新添加站点;以后 up / down 都不用再重签"
  ;;

up)
  [ -n "$SSID" ] || die "要给 --ssid <随身 Wi-Fi 名>"
  [[ "$SSID" =~ ^[A-Za-z0-9_.\ -]{1,32}$ ]] || die "Wi-Fi 名只认字母数字和 _ . - 空格:$SSID"
  TS="$(ts_ip)"; SECS="$(hours_s)"
  PW="dry-run-password"
  chrony_allow_ts
  if [ "$DRY" = 0 ]; then
    local_do "站点证书里要有 $TS(没有先跑 prepare)" \
      "$(site_json_py "sys.exit(0 if '$TS' in d['hostnames'] else 'site.json 的 hostnames 里没有 $TS:先跑 tools/link_4g.sh prepare')")"
    read -r -s -p "随身 Wi-Fi「$SSID」的口令(不回显):" PW; echo
    [ -n "$PW" ] || die "口令是空的"
  fi
  QS="$(printf %q "$SSID")"; QP="$(printf %q "$PW")"
  on "$RK" "① RK3588:排好 ${HOURS} 小时后自动断开,再临时连「$SSID」(不 enable、不 save)" \
"set -e
sudo systemctl stop nexwar-sta-revert.timer 2>/dev/null || true
sudo systemd-run --on-active=${SECS}s --unit=nexwar-sta-revert sh -c 'systemctl stop wpa_supplicant; ip link set wlan0 down'
sudo ip link set wlan0 up
sudo systemctl start wpa_supplicant 2>/dev/null || true
for i in 1 2 3; do sudo wpa_cli -i wlan0 scan >/dev/null 2>&1 || true; sleep 6
  sudo wpa_cli -i wlan0 scan_results | grep -qF -- $QS && break; done
sudo $RK_STA connect $QS $QP >/dev/null
for i in \$(seq 1 20); do sudo wpa_cli -i wlan0 status | grep -q '^wpa_state=COMPLETED' && break; sleep 1; done
sudo wpa_cli -i wlan0 status | grep -E 'wpa_state|^ssid|ip_address'
iw dev | grep -E 'Interface|ssid|channel'
ping -c3 -W2 -I wlan0 1.1.1.1 | tail -2"
  unset PW QP
  on "$ORIN" "② Orin:排好 ${HOURS} 小时后自动改回,默认路线指向 RK3588" \
"set -e
ip route show default | tee ~/default-route-before-4g.txt
sudo systemctl stop nexwar-4g-revert.timer 2>/dev/null || true
sudo systemd-run --on-active=${SECS}s --unit=nexwar-4g-revert ip route replace default via $ORIN_GW_B dev $ORIN_IF proto static metric 102
sudo ip route replace default via $ORIN_GW_A dev $ORIN_IF proto static metric 102
ip route get 1.1.1.1 | head -1
timeout 20 sudo tailscale ping -c 3 $TS || echo '!! tailscale ping 不通:笔记本这时只连着机器人热点、上不了网的话是正常的,换连能上网的 Wi-Fi 以后跑 status 再看'"
  on "$ORIN" "③ Orin:代理、对时改连 $TS,重启开机准备和代理" \
"set -e
[ -f /etc/nexwar/env.bak-B ] || sudo cp -a /etc/nexwar/env /etc/nexwar/env.bak-B
sudo sed -i -e 's#^NEXWAR_SITE_MQTT=.*#NEXWAR_SITE_MQTT=mqtts://$TS:8883#' -e 's#^NEXWAR_SITE_NTP=.*#NEXWAR_SITE_NTP=$TS#' /etc/nexwar/env
grep -E '^NEXWAR_SITE_(MQTT|NTP)=' /etc/nexwar/env
sudo systemctl restart nexwar_boot nexwar_agent"
  local_do "④ 站点:画面改收 $TS,重启站点" \
"$(site_json_py "v = d.setdefault('video', {})
v['srt_host'] = '$TS'
json.dump(d, open(p + '.tmp', 'w'), ensure_ascii=False, indent=2); open(p + '.tmp', 'a').write('\n')
import os; os.replace(p + '.tmp', p); print('video:', v)")
sudo systemctl restart nexwar_site"
  say "切到 A 了。等 1 分钟看网页上机器人在线、画面出来;tools/link_4g.sh status 看细节"
  say "机器人重启过:RK3588 和 Orin 回到原样,连上热点再跑一次 up"
  ;;

down)
  on "$ORIN" "① Orin:代理、对时改回热点,默认路线改回 R300S,取消定时" \
"set -e
if [ -f /etc/nexwar/env.bak-B ]; then sudo cp -a /etc/nexwar/env.bak-B /etc/nexwar/env; else
  sudo sed -i -e 's#^NEXWAR_SITE_MQTT=.*#NEXWAR_SITE_MQTT=mqtts://$HOTSPOT_IP:8883#' -e 's#^NEXWAR_SITE_NTP=.*#NEXWAR_SITE_NTP=$HOTSPOT_IP#' /etc/nexwar/env; fi
grep -E '^NEXWAR_SITE_(MQTT|NTP)=' /etc/nexwar/env
sudo systemctl stop nexwar-4g-revert.timer 2>/dev/null || true
sudo ip route replace default via $ORIN_GW_B dev $ORIN_IF proto static metric 102
ip route show default
sudo systemctl restart nexwar_boot nexwar_agent"
  on "$RK" "② RK3588:断开随身 Wi-Fi,删厂家脚本建的 sta.conf,取消定时" \
"sudo systemctl stop nexwar-sta-revert.timer 2>/dev/null || true
sudo systemctl stop wpa_supplicant 2>/dev/null || true
sudo ip link set wlan0 down
sudo rm -f /userdata/config/sta.conf
iw dev | grep -E 'Interface|ssid|channel'"
  local_do "③ 站点:画面改回缺省(热点地址),重启站点" \
"$(site_json_py "v = d.get('video') or {}
v.pop('srt_host', None)
if 'video' in d and not v: d.pop('video')
json.dump(d, open(p + '.tmp', 'w'), ensure_ascii=False, indent=2); open(p + '.tmp', 'a').write('\n')
import os; os.replace(p + '.tmp', p); print('video:', d.get('video'))")
sudo systemctl restart nexwar_site"
  say "切回 B 了。站点证书里的 Tailscale 地址留着不影响"
  ;;
esac
