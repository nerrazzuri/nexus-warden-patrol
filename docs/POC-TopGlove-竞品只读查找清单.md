# POC Top Glove（11-17）：竞品主控只读查找清单

规矩：只看、只复制。不改文件、不删、不重启、不动 bridge、不装东西。登录用用户给的账号（竞品主控 firefly@192.168.113.101，经 Orin 或笔记本同网段）。

## A. 周一演练时先找位置（竞品不建图时也能做）

1. 进程和启动文件（看 lio_node、map_manage 从哪起、参数在哪）
   - `ps -eo pid,etime,cmd | grep -E 'lio_node|map_manage|oneway|roslaunch' | grep -v grep`
   - `ls -la ~/ ~/*/ 2>/dev/null | head -100`
   - 找 launch：`find / -xdev -name '*.launch' 2>/dev/null | xargs grep -l -E 'lio_node|map_manage' 2>/dev/null`
2. 参数里的保存路径
   - `rosparam list 2>/dev/null | grep -i -E 'save|path|dir|map|pcd'`
   - 对上面列出来的逐个 `rosparam get <名>`
3. 已有的地图文件在哪、多大
   - `find / -xdev \( -name '*.pcd' -o -name '*.pgm' -o -name '*.ply' \) -size +100k -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' 2>/dev/null | sort | tail -40`
   - 同目录的 yaml、轨迹（`*.txt` / `*.csv` / `*pose*` / `*traj*` / `*odom*`）：`ls -la <目录>`
4. 磁盘：`df -h`（我们只读，不占它的盘）

## B. 11-17 竞品建完图、导出之后

1. 再跑 A.3，只看比演示开始时间新的文件（`-newermt '2026-11-17 HH:MM'`）。
2. 从笔记本往回拉（竞品那边不写任何东西）：
   `scp -r firefly@192.168.113.101:<目录> ~/Projects/D1_Max/d1max-patrol/runs/topglove-1117/competitor/`
3. 要拉的：pcd（3D 点云）、pgm + yaml（2D 栅格）、轨迹 / 里程计记录（有就拉）、建图参数文件（A.1/A.2 找到的 yaml、launch）。
4. 拉完记 `sha256sum`，写进 `runs/topglove-1117/competitor/MANIFEST.txt`。

## C. 我们这边（Orin，同时进行）

- 竞品开始建图前开录（只录包，不在线建图，低优先级），竞品结束后停。
- 录的就是竞品建图用的原始输入：前后雷达、雷达 IMU、里程计、tf。
- 录完把包拉回笔记本：`runs/topglove-1117/ours/`。

## 对比时看什么（回来做）

墙清不清楚（厚度）、绕一圈回来首尾对不对得上、有没有缺块、室外巷道（长走廊退化）、会移动的托盘、2D 栅格能不能直接用来导航。
