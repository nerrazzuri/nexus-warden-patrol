#!/usr/bin/env bash
# 停用:把我们装在机器人上的东西全部停掉、关掉开机自启。**一个文件都不删**,能撤回。
# 用于客户不再用我们的平台(用户 11-11:C40221 客户改用竞品)。在机器人的 Orin 上跑:
#   sudo bash disable.sh            停用(先列出要做的事,输入 yes 才动手)
#   sudo bash disable.sh --yes      停用,不问
#   bash disable.sh --dry-run       只列出会做什么,什么都不动
#   bash disable.sh --check         只看:还有没有我们的东西会起来(干净退 0,不干净退 1)
#   sudo bash disable.sh --undo     按停用时的记录恢复
# 做的事:旁路交还控制权;我们关过自启的厂家服务开回去;我们的服务(nexwar*,以及老名字 d1max*
# 里确实指向我们程序的)停掉并关自启;我们的对时片段挪走;crontab 里我们的行注释掉;留记录和日志。
# 停用之后要**整机断电重启一次**(Orin 和 RK3588 一起),厂家/竞品才能重新拿到控制权。
set -u
R="${NEXWAR_DISABLE_ROOT:-}"
WAIT="${NEXWAR_DISABLE_WAIT:-3}"
MODE=disable
YES=0
for a in "$@"; do
  case "$a" in
    --yes) YES=1 ;;
    --dry-run) MODE=dry ;;
    --check) MODE=check ;;
    --undo) MODE=undo ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "不认识的参数: $a(看 --help)" >&2; exit 64 ;;
  esac
done

if { [ "$MODE" = disable ] || [ "$MODE" = undo ]; } && [ -z "$R" ] && [ "$(id -u)" != 0 ]; then
  echo "!! 要用 root 跑: sudo bash $0 $*  (什么都还没动)" >&2
  exit 2
fi

DIS="$R/etc/nexwar/disabled"
STATE="$DIS/state.txt"
MOVED="$DIS/moved.txt"
OURS='/opt/(d1max|nexwar)|nexwar|d1max-motion|d1max_(patrol|site|ops|localizer|obstacles|persons|nav2)|patrol_agent|field-agent'

say() { printf '%s\n' "$*"; }

# 我们的 systemd 单元。nexwar* 是我们的牌子,直接算;d1max* 是 11 月前的老名字,厂家产品也叫
# D1 Max,所以只算单元内容里指向我们程序的那些,免得误关厂家的服务。
our_units() {
  local u
  systemctl list-unit-files --no-legend 'nexwar*' 'd1max*' 2>/dev/null | awk '{print $1}' |
    sort -u | while read -r u; do
      case "$u" in
        nexwar*) say "$u" ;;
        d1max*) systemctl cat "$u" 2>/dev/null | grep -qE "$OURS" && say "$u" ;;
      esac
    done
  if systemctl is-enabled wg-quick@nexwar.service >/dev/null 2>&1; then
    say wg-quick@nexwar.service
  fi
}

unit_state() { systemctl is-enabled "$1" 2>/dev/null | head -n 1; }

fifos() {
  find "$R/home" "$R/root" -maxdepth 5 -type p -name '*agent*.fifo' 2>/dev/null
}

vendor_records() {
  local f
  for f in "$R/var/lib/nexwar/vendor-autostart-off.json" "$R/var/lib/d1max/vendor-autostart-off.json"; do
    [ -f "$f" ] && say "$f"
  done
}

vendor_units() { grep -oE '"[A-Za-z0-9@._-]+\.service"' "$1" | tr -d '"'; }

conf_files() {
  local f
  for f in "$R"/etc/chrony/conf.d/nexwar*.conf "$R"/etc/chrony/conf.d/d1max*.conf \
           "$R"/etc/systemd/timesyncd.conf.d/nexwar*.conf "$R"/etc/systemd/timesyncd.conf.d/d1max*.conf \
           "$R"/etc/cron.d/nexwar* "$R"/etc/cron.d/d1max*; do
    [ -e "$f" ] && say "$f"
  done
}

cron_files() {
  local f
  for f in "$R"/var/spool/cron/crontabs/*; do
    [ -f "$f" ] && grep -vE '^[[:space:]]*#' "$f" | grep -qE "$OURS" && say "$f"
  done
}

# 别的地方也提到我们程序的(只报,不改):开机脚本、桌面自启、登录脚本
other_mentions() {
  local f
  for f in "$R/etc/rc.local" "$R"/etc/profile.d/* "$R"/home/*/.config/autostart/* \
           "$R"/home/*/.bashrc "$R"/home/*/.profile; do
    [ -f "$f" ] && grep -vE '^[[:space:]]*#' "$f" | grep -qE 'nexwar|d1max|patrol_agent|field-agent' && say "$f"
  done
}

tag_of() {  # /etc/chrony/conf.d/nexwar.conf → chrony-conf.d-nexwar.conf
  local p=${1#"$R"}
  case "$p" in
    /etc/chrony/conf.d/*) say "chrony-conf.d-${p##*/}" ;;
    /etc/systemd/timesyncd.conf.d/*) say "timesyncd.conf.d-${p##*/}" ;;
    /etc/cron.d/*) say "cron.d-${p##*/}" ;;
    *) say "file-${p##*/}" ;;
  esac
}

bridge_note() {
  if pgrep -f 'ros1_bridge|bridge_start' >/dev/null 2>&1; then
    say "  竞品的雷达桥(ros1_bridge)在跑。"
  else
    say "  竞品的雷达桥(ros1_bridge)没在跑:11-05 我们停过它的进程、没改它的自启;整机重启后还没起来就告诉竞品。"
  fi
}

# ------------------------------------------------------------------ 只看
do_check() {
  local bad=0 u en act f
  say "== 检查:我们的东西还会不会起来"
  for u in $(our_units); do
    en=$(unit_state "$u"); act=$(systemctl is-active "$u" 2>/dev/null | head -n 1)
    case "$en" in
      enabled|enabled-runtime|linked|linked-runtime|alias) say "  ✗ $u 还开着开机自启($en)"; bad=1 ;;
    esac
    if [ "$act" = active ] || [ "$act" = activating ]; then say "  ✗ $u 正在跑"; bad=1; fi
  done
  if pgrep -f '(^|/)patrol_agent( |$)' >/dev/null 2>&1; then say "  ✗ 旁路 patrol_agent 进程还在"; bad=1; fi
  for f in $(conf_files); do say "  ✗ 还在: ${f#"$R"}"; bad=1; done
  for f in $(cron_files); do say "  ✗ crontab 里还有我们的行: ${f#"$R"}"; bad=1; done
  for f in $(other_mentions); do say "  ! 这里也提到了我们的程序(没改,请把这一处发回来): ${f#"$R"}"; done
  bridge_note
  if [ "$bad" = 0 ]; then say "== 通过:我们的东西都不会再起来了。"; return 0; fi
  say "== 没通过:上面打 ✗ 的还在。先重跑一次停用;还不行就把这一屏拍下来发回来。"
  return 1
}

# ------------------------------------------------------------------ 报告(发回给我们看)
REPORT="$R/var/log/nexwar-disable-report.txt"
PROCS='nexwar|d1max|patrol_agent|field-agent|super_?lio|Super-LIO|bt_navigator|controller_server|planner_server'

write_report() {
  local u en act pid f boot rec
  mkdir -p "$R/var/log" "$R/tmp"
  {
    say "nexwar 停用报告  $(date '+%F %T %z')  主机 $(hostname 2>/dev/null)  模式 $MODE"
    boot=$(( $(date +%s) - $(cut -d. -f1 /proc/uptime) ))
    say "这次开机: $(date -d "@$boot" '+%F %T' 2>/dev/null)"
    if [ -f "$STATE" ]; then
      rec=$(stat -c %Y "$STATE")
      say "停用记录: $(date -d "@$rec" '+%F %T' 2>/dev/null)"
      if [ "$boot" -gt "$rec" ]; then say "停用之后整机重启过: 是"; else say "停用之后整机重启过: 否(还没重启)"; fi
    else
      say "停用记录: 没有(还没停用过,或已撤回)"
    fi
    say "装的版本: $(readlink "$R/opt/nexwar/current" 2>/dev/null || say -) / 老目录 $(readlink "$R/opt/d1max/current" 2>/dev/null || say -)"
    say ""
    do_check
    say ""
    say "== 我们的单元(开机自启 / 现在 / 进程号)"
    for u in $(our_units); do
      en=$(unit_state "$u"); act=$(systemctl is-active "$u" 2>/dev/null | head -n 1)
      pid=$(systemctl show -p MainPID --value "$u" 2>/dev/null | head -n 1)
      printf '  %-36s %-10s %-10s %s\n' "$u" "${en:--}" "${act:--}" "${pid:--}"
    done
    say ""
    say "== 进程(名字里带我们程序的;没有就是空)"
    ps -eo pid,etime,args 2>/dev/null | grep -E "$PROCS" | grep -vE 'nexwar-disable|grep -E' | cut -c1-200
    say ""
    say "== 监听端口(8090 是旁路)"
    ss -ltnp 2>/dev/null | grep -E ':8090 |patrol|nexwar|d1max' | cut -c1-200
    say ""
    say "== 对时"
    ls "$R/etc/chrony/conf.d" 2>/dev/null | sed 's/^/  conf.d: /'
    chronyc -n sources 2>/dev/null | cut -c1-120
    say ""
    say "== 我们开回去的厂家服务"
    for f in "$R"/var/lib/nexwar/vendor-autostart-off.json.restored "$R"/var/lib/d1max/vendor-autostart-off.json.restored; do
      [ -f "$f" ] || continue
      for u in $(vendor_units "$f"); do
        say "  $u  $(unit_state "$u") / $(systemctl is-active "$u" 2>/dev/null | head -n 1)"
      done
    done
    say ""
    say "== 停用记录(/etc/nexwar/disabled/)"
    ls -l "$DIS" 2>/dev/null
    [ -f "$STATE" ] && sed 's/^/  原来: /' "$STATE"
    [ -f "$MOVED" ] && sed 's/^/  挪走: /' "$MOVED"
    say ""
    f=$(ls -t "$R"/var/log/nexwar-disable-2*.log 2>/dev/null | head -n 1)
    if [ -n "$f" ]; then say "== 最近一次停用/撤回的日志 ${f#"$R"}"; tail -n 60 "$f"; say ""; fi
    say "== 我们的单元这次开机以来的日志(每个最多 15 行)"
    for u in $(our_units); do
      say "-- $u"
      journalctl -b -u "$u" -n 15 --no-pager -o short-iso 2>/dev/null | cut -c1-200
    done
  } > "$REPORT" 2>&1
  # 打成 tar.gz 发回给我们:报告 + 停用日志 + 停用记录 + 每个单元更长的日志 + 单元、进程快照。
  # 放 /tmp 下、谁都能读,Windows 那头不用 sudo 就能拷走。不带 /etc/nexwar/env(里面有站点地址等现场值)。
  local d="$R/tmp/nexwar-disable-report" tgz="$R/tmp/nexwar-disable-report.tar.gz"
  rm -rf "$d"; mkdir -p "$d/journal"
  cp "$REPORT" "$d/report.txt"
  cp "$R"/var/log/nexwar-disable-2*.log "$d/" 2>/dev/null
  [ -d "$DIS" ] && cp -r "$DIS" "$d/disabled" 2>/dev/null
  systemctl list-unit-files --no-legend 2>/dev/null > "$d/unit-files.txt"
  systemctl list-units --all --no-legend 2>/dev/null > "$d/units.txt"
  ps -eo pid,ppid,user,lstart,args 2>/dev/null > "$d/ps.txt"
  for u in $(our_units); do
    journalctl -b -u "$u" -n 300 --no-pager -o short-iso 2>/dev/null > "$d/journal/$u.txt"
  done
  tar czf "$tgz" -C "$R/tmp" nexwar-disable-report 2>/dev/null && chmod 644 "$tgz"
  rm -rf "$d"
  say "检查报告: ${REPORT#"$R"}(打包: ${tgz#"$R"})"
}

# ------------------------------------------------------------------ 列计划
show_plan() {
  local u f
  say "要做的事:"
  for f in $(fifos); do say "  1. 往 ${f#"$R"} 写 shutdown,让旁路交还控制权"; done
  for f in $(vendor_records); do
    for u in $(vendor_units "$f"); do say "  2. 厂家的 $u 开机自启开回去、当场起来"; done
  done
  for u in $(our_units); do say "  3. 停掉并关开机自启: $u(现在 $(unit_state "$u"))"; done
  for f in $(conf_files); do say "  4. 挪到 /etc/nexwar/disabled/: ${f#"$R"}"; done
  for f in $(cron_files); do say "  5. 注释掉 crontab 里我们的行: ${f#"$R"}"; done
  say "  文件一个都不删;记录放在 /etc/nexwar/disabled/,撤回用 --undo。"
}

confirm() {
  [ "$YES" = 1 ] && return 0
  local ans
  read -r -p "输入 yes 继续,别的都算不做: " ans || ans=
  [ "$ans" = yes ]
}

start_log() {
  mkdir -p "$R/var/log" "$DIS"
  LOG="$R/var/log/nexwar-disable-$(date +%Y%m%d-%H%M%S).log"
  exec > >(tee -a "$LOG") 2>&1
}

# ------------------------------------------------------------------ 停用
do_disable() {
  local u f n
  show_plan
  confirm || { say "没动手。"; exit 1; }
  start_log
  say "== 停用开始 $(date '+%F %T')"
  for f in $(fifos); do
    if timeout 5 bash -c 'printf "shutdown\n" > "$1"' _ "$f" 2>/dev/null; then
      say "  已让旁路交还控制权(${f#"$R"})"
    else
      say "  ${f#"$R"} 没人在读(旁路没在跑),跳过"
    fi
  done
  sleep "$WAIT"
  for f in $(vendor_records); do
    for u in $(vendor_units "$f"); do
      systemctl enable --now "$u" >/dev/null 2>&1 || true
      say "  厂家的 $u 开机自启开回去了"
    done
    mv "$f" "$f.restored"
  done
  if [ ! -f "$STATE" ]; then  # 第二次停用不覆盖第一次的记录,撤回要的是最初的样子
    for u in $(our_units); do say "$u $(unit_state "$u")"; done > "$STATE"
  fi
  for u in $(our_units); do
    systemctl disable --now "$u" >/dev/null 2>&1 || true
    say "  停掉并关了开机自启: $u"
  done
  for f in $(conf_files); do
    n="$DIS/$(tag_of "$f")"
    mv "$f" "$n" && printf '%s\t%s\n' "${f#"$R"}" "${n#"$R"}" >> "$MOVED"
    say "  挪走了 ${f#"$R"}"
  done
  systemctl try-restart chrony >/dev/null 2>&1 || true
  systemctl try-restart systemd-timesyncd >/dev/null 2>&1 || true
  for f in $(cron_files); do
    cp -p "$f" "$DIS/crontab-${f##*/}"
    sed -i -E "/^[[:space:]]*#/! { \\%$OURS% s/^/#nexwar-disabled# / }" "$f"
    say "  注释掉了 crontab 里我们的行: ${f#"$R"}"
  done
  for f in $(other_mentions); do say "  ! 这里也提到了我们的程序(没改,请把这一处发回来): ${f#"$R"}"; done
  say "== 停用做完。日志: ${LOG#"$R"}"
  say ""
  say ">> 现在把机器人整机断电重启一次(Orin 和 RK3588 一起),厂家/竞品才能重新拿到控制权。"
  say ">> 开机 3 分钟后再跑一次检查(双击程序选 2,或 bash disable.sh --check)。"
}

# ------------------------------------------------------------------ 撤回
do_undo() {
  local u st orig new f
  [ -f "$STATE" ] || { say "没有停用记录($STATE),没什么可撤回的。"; exit 1; }
  say "撤回:按 /etc/nexwar/disabled/ 里的记录,把原来开着的开机自启开回去、挪走的文件放回去。"
  confirm || { say "没动手。"; exit 1; }
  start_log
  while read -r u st; do
    case "$st" in
      enabled|enabled-runtime) systemctl enable "$u" >/dev/null 2>&1 || true; say "  开回开机自启: $u" ;;
    esac
  done < "$STATE"
  if [ -f "$MOVED" ]; then
    while IFS="$(printf '\t')" read -r orig new; do
      [ -e "$R$new" ] && mv "$R$new" "$R$orig" && say "  放回 $orig"
    done < "$MOVED"
    rm -f "$MOVED"
  fi
  for f in "$DIS"/crontab-*; do
    [ -f "$f" ] && cp -p "$f" "$R/var/spool/cron/crontabs/${f##*/crontab-}" && rm -f "$f" && say "  crontab 放回 ${f##*/crontab-}"
  done
  rm -f "$STATE"
  systemctl try-restart chrony >/dev/null 2>&1 || true
  say "== 撤回做完(厂家服务的自启没再关)。整机重启以后我们的服务按原来的样子起来。"
}

case "$MODE" in
  check) do_check; rc=$?; write_report; exit "$rc" ;;
  dry) show_plan; say "(--dry-run:什么都没动)" ;;
  disable) do_disable; write_report ;;
  undo) do_undo; write_report ;;
esac
