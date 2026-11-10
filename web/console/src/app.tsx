import { useEffect, useState } from "preact/hooks";
import { api, ApiError, onUnauthorized } from "./api";
import { Console } from "./console";
import type { Guide } from "./guide";
import { t } from "./i18n";
import { Login } from "./login";
import { BrandMark, loadThemePref, pinFor } from "./shell";
import { pinScheme, systemIsDark } from "./theme";

export interface Me {
  name: string;
  role: string;
  display_name: string;
  site_name: string;
  /** W53:上手向导看过哪一版(老站点没有)。 */
  guide?: Guide;
}

export function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [expired, setExpired] = useState(false);
  const [down, setDown] = useState(false);
  // P1-67:改完密码回登录页时写「密码已改,用新密码登录」,不写「会话已过期」
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    onUnauthorized.cb = () => {
      setExpired(true);
      setMe(null);
    };
    // 第 3 轮 admin N6:连不上站点(网络错、5xx)不是没登录 —— 不显示成普通登录页,写「连不上,正在重试」,隔几秒再问
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const ask = () => api<Me>("GET", "/api/me")
      .then((m) => { if (alive) { setDown(false); setMe(m); } })
      .catch((e) => {
        if (!alive) return;
        if (e instanceof ApiError && (e.status === 401 || e.status === 403)) { setDown(false); setMe(null); return; }
        console.warn(e);
        setDown(true);
        timer = setTimeout(ask, 3000);
      });
    void ask();
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, []);

  // 第 4 轮 admin N3:登录前(启动、连不上、登录页)也按用户选的外观上色(默认深色),不先白一下
  useEffect(() => {
    if (!me) pinScheme(pinFor("duty", loadThemePref(), systemIsDark()));
  }, [me]);

  if (me === undefined) {
    return down
      ? <div class="boot boot-down" role="alert" data-site-down="1"><BrandMark /><p>{t("bootDown")}</p></div>
      : <div class="boot" aria-busy="true"><p class="boot-wait muted">{t("loading")}</p></div>;
  }
  if (me === null)
    return (
      <Login
        expired={expired}
        note={note}
        onIn={(m) => {
          setExpired(false);
          setNote(null);
          setMe(m);
        }}
      />
    );
  return <Console me={me} onOut={(n) => { setNote(n ?? null); setExpired(false); setMe(null); }} />;
}
