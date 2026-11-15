# 手机 App V2 施工记录（redesign/app-v2 分支）

依据 design/app-v2/README.md（规则 + 58 项对照表）、boards/*.dc.html、.impeccable/surfaces/mobile-lib.md。
做法跟网页一样：分期、每期提交、每期更新 PARITY（对照表的「状态」列改成 已做 / 部分 + 原因）；全部做完送 codex 外审到没有 Important。

## 分期
1. 外壳：顶栏（站点名 · 布防状态 · 时钟）+「现在 | 现场」两段开关；「现在」深色、右下角拇指区「全部急停」；「现场」浅色目录（按角色四套），目录项先接到老页面；进入页先沿用。老的五栏底部导航删掉。
2. 「现在」页（N-normal / N-nomap / N-mgr / V-now）：事件条或一切正常、一路画面（前 / 后 / 热像）、机器人格、小地图、今晚巡逻、设备与运营、交班留言、最新活动、底部「有新版本」。
3. 这件事（N-alarm 全屏来报警、N-incident、N-multi、N-dispatch 派去看一眼、N-refuse 派单被拒、N-estop 急停后、N-ring）。
4. 机器人控制（N-robot、M-robot）+ 遥控横屏沿用 + 机器人列表 / 机器人设置 / 添加机器人（S-robots、S-robot-set、S-add）。
5. 现场各页按稿重排：概况（S-home / S-home-m）、人员、布防与巡逻、地图与布置（S-layout、S-zones、S-routes、S-route 临时路线、S-points）、记录（S-alarms、S-alarm-rec、S-runs、S-video、S-notes）、地图管理与建图（S-maps、S-wizard）、站点体检、软件升级、设置、使用教程 / 报问题、经理 / 只读目录（S-mgr、S-viewer）。
6. 进入页（E-sites、E-login、E-add、E-register）。
7. 后端补齐 + 用词：Handled → Resolved、Stop all → E-STOP ALL、Take ownership；alert_titles.g.dart 补 backup_requested；自动驱离分级状态 + 结束驱离、派单被拒原因、急停没确认再发、App 自更新提示、交班留言、报警演练 —— 照网页已有接口。
8. 「部分 / 没画」4 项照老功能：跟随时看不到人、建图向导其余步、建图预览、我在现场监护。
9. 逐条过 58 项、截图核对、外审。

## 规矩（HANDOFF 同款）
- 英文默认、正式用语，词跟 design/console-v2/en/dict.json + gen/app_dict.json 一致；中文第二。
- 四种颜色各一个意思；角色没有的功能不显示；同一行按钮等宽；不弹窗（再输密码除外）；遥控只横屏。
- 真机测试那边（易用性测试）按期知会。

## 进展
