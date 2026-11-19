package com.nexwar.nexwar_patrol

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import android.os.PowerManager
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/** 后台值守（W17）的开关在 Dart 那边（`lib/net/background_watch.dart`），这里只转给 [WatchService]。 */
class MainActivity : FlutterActivity() {
    /** 商业化 A6:App 被杀以后点厂商通道的推送通知,拉起的 intent 带着参数,Flutter 3.29 起会当深链接
     *  去找路由、找不到就白屏(极光插件说明)。我们不用深链接:关掉。 */
    override fun shouldHandleDeeplinking(): Boolean = false

    private var watch: MethodChannel? = null
    /** 后台值守拉起的来报警(还没交给 Dart 的那一条)。 */
    private var ring: Map<String, String>? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        takeRing(intent)
        super.onCreate(savedInstanceState)
        // FCM 推送进 watch_p1(清单里的默认渠道):一启动就建好,不等后台值守(真机 11-20 vivo:没建时进了
        // Firebase 自己的「Misc」,只有状态栏小图标、不弹悬浮)。语言跟后台值守上次记下的一样。
        val lang = getSharedPreferences(WatchService.PREFS, Context.MODE_PRIVATE).getString("lang", "zh") ?: "zh"
        WatchService.ensureChannels(applicationContext, lang)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        // App 开着(Dart 早就在听):直接交过去;引擎还没起来的留着等 Dart 启动时来拿
        val ch = watch
        if (takeRing(intent) && ch != null) {
            ring?.let { r -> ch.invokeMethod("ring", r) }
            ring = null
        }
    }

    /** App V2 来报警全屏页:值守服务的全屏通知拉起来的 —— 锁屏上也显示、亮屏,把那一条记下给 Dart。 */
    private fun takeRing(i: Intent?): Boolean {
        val key = i?.getStringExtra(WatchService.EXTRA_RING_KEY) ?: return false
        ring = mapOf("key" to key, "alert" to (i.getStringExtra(WatchService.EXTRA_RING_ALERT) ?: "{}"),
            "site" to (i.getStringExtra(WatchService.EXTRA_RING_SITE) ?: ""),
            "url" to (i.getStringExtra(WatchService.EXTRA_RING_URL) ?: ""),
            "fingerprint" to (i.getStringExtra(WatchService.EXTRA_RING_FP) ?: ""))
        if (Build.VERSION.SDK_INT >= 27) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON)
        }
        return true
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val ch = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "nexwar/watch")
        watch = ch
        ch.setMethodCallHandler { call, result ->
            when (call.method) {
                // 启动时问一次:是不是被来报警拉起来的(拿了就清掉)
                "pendingRing" -> {
                    result.success(ring)
                    ring = null
                }
                "mute" -> {
                    if (WatchService.running) {
                        startService(Intent(this, WatchService::class.java).setAction(WatchService.ACTION_MUTE)
                            .putExtra("key", call.argument<String>("key") ?: ""))
                    }
                    result.success(WatchService.running)
                }
                // 页面处理完了:锁屏上不再显示
                "ringDone" -> {
                    if (Build.VERSION.SDK_INT >= 27) {
                        setShowWhenLocked(false)
                        setTurnScreenOn(false)
                    } else {
                        // 外审 App-V2-2 N5:24–26 走的是窗口标志,也要清掉(不然以后的页面一直显示在锁屏上)
                        @Suppress("DEPRECATION")
                        window.clearFlags(WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON)
                    }
                    result.success(true)
                }
                "start" -> {
                    askOnce()
                    val i = Intent(this, WatchService::class.java).setAction(WatchService.ACTION_START)
                    for (k in listOf("site", "url", "fingerprint", "token", "lang", "titles")) i.putExtra(k, call.argument<String>(k) ?: "")
                    if (Build.VERSION.SDK_INT >= 26) startForegroundService(i) else startService(i)
                    result.success(true)
                }
                "stop" -> {
                    if (WatchService.running) {
                        val i = Intent(this, WatchService::class.java).setAction(WatchService.ACTION_STOP)
                        if (Build.VERSION.SDK_INT >= 26) startForegroundService(i) else startService(i)
                    }
                    result.success(true)
                }
                // 通知上点过静音的:告警键 → 静到几点(前台的铃对一下)
                "mutes" -> {
                    val now = System.currentTimeMillis()
                    result.success(HashMap(WatchService.mutedUntil.filterValues { it > now }))
                }
                "running" -> result.success(WatchService.running)
                // 手机 App 测试 M01:底部导航页按返回键 = 退到后台,不结束 Activity(结束会退出登录)
                "background" -> result.success(moveTaskToBack(true))
                else -> result.notImplemented()
            }
        }
        // W42:连机器人的热点(添加机器人、换 WiFi、工程师解绑)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "nexwar/hotspot").setMethodCallHandler { call, result ->
            when (call.method) {
                "join" -> RobotHotspot.join(applicationContext, call.argument<String>("ssid") ?: "",
                    call.argument<String>("psk") ?: "") { ok -> result.success(ok) }
                "leave" -> {
                    RobotHotspot.leave(applicationContext)
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
        // W55:从站点下载的新版 App 交给系统安装
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "nexwar/install").setMethodCallHandler { call, result ->
            when (call.method) {
                "apk" -> {
                    val path = call.argument<String>("path") ?: ""
                    Thread {                                  // 几十 MB 写进系统:别卡住界面
                        try {
                            val r = ApkInstaller.install(this, path)
                            runOnUiThread { result.success(r) }
                        } catch (e: Exception) {
                            runOnUiThread { result.error("install_failed", e.message, null) }
                        }
                    }.start()
                }
                else -> result.notImplemented()
            }
        }
        // RC 加固 H9:FCM 的推送号。Firebase 的参数由 Dart 那边带过来(打包时 --dart-define 给的)。
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "nexwar/push").setMethodCallHandler { call, result ->
            when (call.method) {
                "fcmToken" -> FcmToken.get(
                    applicationContext,
                    call.argument<String>("appId") ?: "", call.argument<String>("apiKey") ?: "",
                    call.argument<String>("projectId") ?: "", call.argument<String>("senderId") ?: "",
                ) { token -> runOnUiThread { result.success(token) } }
                else -> result.notImplemented()
            }
        }
    }

    /** 弹通知要权限（Android 13+）；后台常驻最好不被省电杀掉：都只在开值守时问，拒了不再缠着问。 */
    private fun askOnce() {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 17)
        }
        val prefs = getSharedPreferences("nexwar_ui", MODE_PRIVATE)
        val pm = getSystemService(PowerManager::class.java)
        if (Build.VERSION.SDK_INT >= 23 && !pm.isIgnoringBatteryOptimizations(packageName) &&
            !prefs.getBoolean("asked_battery", false)) {
            prefs.edit().putBoolean("asked_battery", true).apply()
            try {
                startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                    .setData(Uri.parse("package:$packageName")))
            } catch (e: Exception) {
                // 有的系统没有这个页面:算了,文档里写着让值守的人手动设「不限制」
            }
        }
    }
}
