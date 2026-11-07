import { useEffect, useState } from "preact/hooks";
import { api, ApiError, onUnauthorized } from "./api";
import { Console } from "./console";
import type { Guide } from "./guide";
import { Login } from "./login";

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
  // P1-67:改完密码回登录页时写「密码已改,用新密码登录」,不写「会话已过期」
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    onUnauthorized.cb = () => {
      setExpired(true);
      setMe(null);
    };
    api<Me>("GET", "/api/me")
      .then(setMe)
      .catch((e) => {
        if (!(e instanceof ApiError) || e.status !== 401) console.warn(e);
        setMe(null);
      });
  }, []);

  if (me === undefined) return <div class="boot" aria-busy="true" />;
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
