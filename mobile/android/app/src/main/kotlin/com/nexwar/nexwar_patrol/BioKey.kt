package com.nexwar.nexwar_patrol

import android.annotation.TargetApi
import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import android.hardware.biometrics.BiometricManager
import android.hardware.biometrics.BiometricPrompt
import android.os.Build
import android.os.CancellationSignal
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyPermanentlyInvalidatedException
import android.security.keystore.KeyProperties
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/**
 * 手机指纹登录(用户 11-20):Android Keystore 里一把 P-256 私钥,**要按指纹(强生物识别)才能签名**,
 * 录了新指纹就作废;私钥出不了这部手机。站点只存公钥,登录时出一次性随机数让这里签。
 *
 * 用系统自带的 `android.hardware.biometrics.BiometricPrompt`(Android 9 起),不加 androidx 依赖、
 * 主界面也不用换成 FragmentActivity。Android 9 以下当作不支持(照旧输密码)。
 * 结果都用字符串说:`ok`、`cancelled`(按了「用密码」或返回)、`invalidated`(录了新指纹、锁屏关了,
 * 钥匙作废了,删掉重新登记)、`lockout`(错太多次)、`error`。
 */
object BioKey {
    private const val STORE = "AndroidKeyStore"

    fun available(ctx: Context): Boolean {
        if (Build.VERSION.SDK_INT < 28) return false
        if (Build.VERSION.SDK_INT >= 30) {
            val bm = ctx.getSystemService(BiometricManager::class.java) ?: return false
            return bm.canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG) ==
                BiometricManager.BIOMETRIC_SUCCESS
        }
        // Android 9、10:只认指纹。10 的 canAuthenticate() 不分强弱,只录了弱人脸也说能用,
        // 钥匙却要强生物识别(外审指纹-2 Minor 2);指纹传感器都是强的
        if (!ctx.packageManager.hasSystemFeature(PackageManager.FEATURE_FINGERPRINT)) return false
        @Suppress("DEPRECATION")
        val fm = ctx.getSystemService(android.hardware.fingerprint.FingerprintManager::class.java)
        @Suppress("DEPRECATION")
        return fm != null && fm.isHardwareDetected && fm.hasEnrolledFingerprints()
    }

    /** 新建(同名的先删掉),回公钥的 SubjectPublicKeyInfo DER。只在 [available] 是真时调(Android 9 起)。 */
    @TargetApi(28)
    fun create(alias: String): ByteArray {
        if (Build.VERSION.SDK_INT < 28) throw IllegalStateException("needs Android 9")
        delete(alias)
        val b = KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setUserAuthenticationRequired(true)
            .setInvalidatedByBiometricEnrollment(true)
        if (Build.VERSION.SDK_INT >= 30) {
            // 每次签名都要按一次,只认强生物识别(不认锁屏密码)
            b.setUserAuthenticationParameters(0, KeyProperties.AUTH_BIOMETRIC_STRONG)
        }
        val g = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, STORE)
        g.initialize(b.build())
        return g.generateKeyPair().public.encoded
    }

    fun delete(alias: String) {
        try {
            val ks = KeyStore.getInstance(STORE).apply { load(null) }
            if (ks.containsAlias(alias)) ks.deleteEntry(alias)
        } catch (_: Exception) {
        }
    }

    /** 弹系统的指纹框,按对了签 [data]。[done] 在主线程回 (结果, 签名 DER)。 */
    @TargetApi(28)
    fun sign(activity: Activity, alias: String, data: ByteArray, title: String, subtitle: String,
             cancel: String, done: (String, ByteArray?) -> Unit) {
        if (Build.VERSION.SDK_INT < 28) return done("error", null)
        val sig: Signature
        try {
            val ks = KeyStore.getInstance(STORE).apply { load(null) }
            val key = ks.getKey(alias, null) as? PrivateKey ?: return done("invalidated", null)
            sig = Signature.getInstance("SHA256withECDSA")
            sig.initSign(key)
        } catch (_: KeyPermanentlyInvalidatedException) {
            delete(alias)
            return done("invalidated", null)
        } catch (_: Exception) {
            return done("error", null)
        }
        var finished = false
        fun finish(r: String, s: ByteArray?) {
            if (finished) return
            finished = true
            done(r, s)
        }
        val exec = activity.mainExecutor
        val prompt = BiometricPrompt.Builder(activity).setTitle(title).setSubtitle(subtitle)
            .setNegativeButton(cancel, exec) { _, _ -> finish("cancelled", null) }
            .build()
        prompt.authenticate(BiometricPrompt.CryptoObject(sig), CancellationSignal(), exec,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    try {
                        val s = result.cryptoObject?.signature ?: return finish("error", null)
                        s.update(data)
                        finish("ok", s.sign())
                    } catch (_: Exception) {
                        finish("error", null)
                    }
                }

                override fun onAuthenticationError(code: Int, msg: CharSequence) {
                    finish(when (code) {
                        BiometricPrompt.BIOMETRIC_ERROR_USER_CANCELED,
                        BiometricPrompt.BIOMETRIC_ERROR_CANCELED -> "cancelled"
                        BiometricPrompt.BIOMETRIC_ERROR_LOCKOUT,
                        BiometricPrompt.BIOMETRIC_ERROR_LOCKOUT_PERMANENT -> "lockout"
                        BiometricPrompt.BIOMETRIC_ERROR_NO_BIOMETRICS -> "invalidated"
                        else -> "error"
                    }, null)
                }
                // 没按对(onAuthenticationFailed):系统框自己说「再试一次」,不结束
            })
    }
}
