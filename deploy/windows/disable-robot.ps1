# 停用机器人上我们的软件(用户 11-11:客户改用竞品平台,我们的东西「可以不删,但是不能启动」)。
# 现场工程师在 Windows 电脑上双击 disable-robot.cmd:连上机器人的 Wi-Fi 就行,不用自己登录机器人。
# 它把同一个文件夹里的 disable.sh 送到机器人的 Orin 上用 sudo 跑;看到 password: 就输入机器人的
# 登录密码(厂家默认密码),一共会问 2~3 次。用的是 Windows 10/11 自带的 ssh,不用装别的。
param([switch]$SelfTest, [string]$Orin = '192.168.168.100', [string]$Gateway = '192.168.234.1',
      [string]$User = 'robot')

[Console]::OutputEncoding = [Text.Encoding]::UTF8
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$sh = Join-Path $here 'disable.sh'

function Fail($msg) { Write-Host ''; Write-Host "!! $msg" -ForegroundColor Red; exit 1 }

function Remote-Command([string]$mode) {
  # 去掉 Windows 换行(\r),整个脚本 base64 成一条命令发过去,机器人上还原成文件再跑
  $bytes = [IO.File]::ReadAllBytes($sh) | Where-Object { $_ -ne 13 }
  $b64 = [Convert]::ToBase64String([byte[]]$bytes)
  return "printf %s $b64 | base64 -d > /tmp/nexwar-disable.sh && sudo bash /tmp/nexwar-disable.sh $mode; " +
         "rc=`$?; rm -f /tmp/nexwar-disable.sh; exit `$rc"
}

function Test-Port([string]$h) {
  $c = New-Object Net.Sockets.TcpClient
  try { $ar = $c.BeginConnect($h, 22, $null, $null); return ($ar.AsyncWaitHandle.WaitOne(3000) -and $c.Connected) }
  catch { return $false } finally { $c.Close() }
}

if (-not (Test-Path $sh)) { Fail "同一个文件夹里没有 disable.sh。整个压缩包解压到一个文件夹里再双击。" }

if ($SelfTest) {
  $cmd = Remote-Command '--check'
  Write-Host "selftest ok: command length $($cmd.Length)"
  if ($cmd.Length -gt 30000) { exit 1 }
  exit 0
}

$ssh = Get-Command ssh.exe -ErrorAction SilentlyContinue
if (-not $ssh) {
  Fail "这台电脑没有 ssh。打开 设置 → 应用 → 可选功能 → 添加功能,装「OpenSSH 客户端」,再双击一次。"
}

Write-Host '=============================================================='
Write-Host ' 停用机器人上我们(nexwar)的软件:停掉、关开机自启,文件都不删'
Write-Host '=============================================================='
Write-Host ' 1  停用(默认)'
Write-Host ' 2  检查:整机重启以后跑一次,看是不是都关干净了'
Write-Host ' 3  撤回:按停用时的记录恢复'
$choice = Read-Host '选哪个?直接回车 = 1'
switch ($choice) {
  { $_ -eq '' -or $_ -eq '1' } { $mode = '--yes'; break }
  '2' { $mode = '--check'; break }
  '3' { $mode = '--undo --yes'; break }
  default { Fail "没有 $choice 这一项,什么都没做。" }
}
if ($mode -eq '--yes') {
  Write-Host ''
  Write-Host '开始前:机器人趴下(或在充电位上)、旁边没有人。停用时我们会交还对机器人的控制。'
  if ((Read-Host '准备好了输入 yes') -ne 'yes') { Fail '没输入 yes,什么都没做。' }
}

$opts = @('-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null', '-o', 'LogLevel=ERROR',
          '-o', 'ConnectTimeout=8')
Write-Host ''
Write-Host "找机器人($Orin)…"
if (Test-Port $Orin) {
  $via = @()
} elseif (Test-Port $Gateway) {
  Write-Host "  直接到不了 Orin,经机器人 Wi-Fi 的网关 $Gateway 转过去(会多问一次密码)"
  $via = @('-o', "ProxyCommand=$($ssh.Source) -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -W %h:%p $User@$Gateway")
} else {
  Fail "连不上机器人。先连上机器人的 Wi-Fi(XG2WIFI_ 开头,C40221 的是 XG2WIFI_C40221),再双击一次。"
}

Write-Host '看到 password: 就输入机器人的登录密码(输的时候屏幕上不显示,输完回车)。'
Write-Host ''
& $ssh.Source -t @opts @via "$User@$Orin" (Remote-Command $mode)
$rc = $LASTEXITCODE
Write-Host ''
if ($rc -eq 0) {
  if ($mode -eq '--yes') { Write-Host '>> 停用做完了。现在把机器人整机断电重启;开机 3 分钟后再双击本程序,选 2 检查。' -ForegroundColor Green }
  elseif ($mode -eq '--check') { Write-Host '>> 检查通过:我们的软件不会再启动。' -ForegroundColor Green }
  else { Write-Host '>> 撤回做完了。整机重启以后我们的软件按原来的样子起来。' -ForegroundColor Green }
} elseif ($rc -eq 255) {
  Fail '登录机器人没成功(密码不对,或网络断了)。确认密码再双击一次。'
} else {
  Fail "没做完(返回 $rc)。把这一屏拍照发回来。"
}
