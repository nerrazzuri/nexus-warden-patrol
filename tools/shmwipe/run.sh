# 台式机复现 11-20 Nav2 失联:3 个 FastDDS 进程跑 25 s 后删掉它们的 /dev/shm 文件(= logind RemoveIPC),
# 看服务调用从此全部超时。用法:cd tools/shmwipe && bash run.sh

source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=63 ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE=/home/liang/Projects/D1_Max/d1max-patrol/deploy/nav2/fastdds_nav2.xml
python3 srv.py s0 & P0=$!
python3 srv.py s1 & P1=$!
python3 probe.py 75 > probe.log 2>&1 & PP=$!
echo "$P0 $P1 $PP" > pids
sleep 25
# 模拟 logind RemoveIPC:删掉这几个进程打开 / 映射的 /dev/shm 文件
for p in $P0 $P1 $PP; do
  { ls -l /proc/$p/fd 2>/dev/null | grep -o "/dev/shm/[^ ]*"; grep -o "/dev/shm/[^ ]*" /proc/$p/maps 2>/dev/null; } 
done | sort -u > wiped.txt
echo "wipe at $(date +%T): $(wc -l < wiped.txt) files"; xargs -r rm -f < wiped.txt
wait $PP
kill $P0 $P1; wait 2>/dev/null
