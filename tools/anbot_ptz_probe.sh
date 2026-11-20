#!/bin/bash
# 竞品云台探查(真机 11-20 P07:我们发 /anbot/ptz/pose/set 回「收下」,云台不动 —— 格式是 11-06 按话题列表
# 推断的,没在真机对过)。登录竞品主控,列出跟云台有关的话题、类型、谁在收谁在发,然后录 40 秒:
# **这 40 秒里用竞品自己的 App 把云台左右、上下各转一下**,录到的就是它真用的格式。
# 用法(笔记本或 Orin,能 ssh 竞品主控的那台):
#   bash tools/anbot_ptz_probe.sh anbot@192.168.113.101 [秒数=40]
# 结果写 runs/field-logs/anbot-ptz-<时间>.txt。只读:不往竞品发任何东西。
set -u
HOST=${1:?要竞品主控的 账号@地址}
SECS=${2:-40}
OUT=runs/field-logs/anbot-ptz-$(date +%m%d-%H%M%S).txt
mkdir -p runs/field-logs
echo "开始:$SECS 秒内请用竞品自己的 App 把云台左右、上下各转一下(雨刷也点一下)" >&2
ssh -o ConnectTimeout=5 "$HOST" "SECS=$SECS bash -s" <<'REMOTE' | tee "$OUT"
for f in /opt/ros/*/setup.bash; do . "$f"; done
[ -f ~/catkin_ws/devel/setup.bash ] && . ~/catkin_ws/devel/setup.bash
echo "== ROS_MASTER_URI=${ROS_MASTER_URI:-}"
topics=$(rostopic list 2>/dev/null | grep -i -E 'ptz|gimbal|pan|tilt|yuntai|camera_ctrl|wiper')
echo "== 话题"; echo "$topics"
for t in $topics; do
  echo "== $t"; rostopic info "$t" 2>&1 | sed 's/^/  /'
  ty=$(rostopic type "$t" 2>/dev/null); [ -n "$ty" ] && rosmsg show "$ty" 2>&1 | sed 's/^/    /'
done
echo "== 服务"; rosservice list 2>/dev/null | grep -i -E 'ptz|gimbal|pan|tilt|wiper'
echo "== 录 ${SECS} 秒(现在转云台)"
for t in $topics; do timeout "$SECS" rostopic echo -p "$t" 2>/dev/null | sed "s|^|$t,|" & done
wait
echo "== 完"
REMOTE
echo "写到 $OUT" >&2
