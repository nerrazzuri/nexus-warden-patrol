"""第三档 #41(用户 11-14):常用喊话。管理员维护一张全站的常用喊话(语言 + 文字),保安在机器人的
「警灯与喊话」里点一下就让机器人念出来(走 ``tts:<语言>:<文字>``,跟打字喊话同一条路)。
缺省带「警告，您已进入受限制区域，请立即离开。」。真 HTTP。"""

from __future__ import annotations

import pytest
from test_site_api import PW, 站

from nexwar_site.site_settings import DEFAULT_VOICE_PRESETS, VOICE_PRESETS_MAX_N, SiteSettings


@pytest.fixture
def 站点(tmp_path):
    s = 站(tmp_path)
    s.accounts.add("gina", PW, role="guard")
    yield s
    s.close()


def _登(s, name):
    code, d = s.req("POST", "/api/login", {"name": name, "password": PW})
    assert code == 200, d
    return d["token"]


def test_缺省有一句受限制区域警告():
    assert {"lang": "zh", "text": "警告，您已进入受限制区域，请立即离开。"} in DEFAULT_VOICE_PRESETS
    assert all(set(p) == {"lang", "text"} for p in DEFAULT_VOICE_PRESETS)


def test_保安能看_只有管理员能改_整张换掉_记审计(站点):
    s = 站点
    alice, gina = _登(s, "alice"), _登(s, "gina")
    code, d = s.req("GET", "/api/voice-presets", token=gina)
    assert code == 200 and d == {"presets": DEFAULT_VOICE_PRESETS}, d
    new = [{"lang": "ms", "text": "Amaran: kawasan larangan."},
           {"lang": "zh", "text": "  请离开  "}]
    assert s.req("POST", "/api/voice-presets", {"presets": new}, token=gina)[0] == 403
    code, d = s.req("POST", "/api/voice-presets", {"presets": new}, token=alice)
    # 两头空白去掉
    assert code == 200 and d == {"presets": [new[0], {"lang": "zh", "text": "请离开"}]}, d
    assert s.req("GET", "/api/voice-presets", token=gina)[1]["presets"][1]["text"] == "请离开"
    assert any(r["action"] == "POST /api/voice-presets" for r in s.api.audit.list())


def test_可以清空(站点):
    s = 站点
    alice = _登(s, "alice")
    got = s.req("POST", "/api/voice-presets", {"presets": []}, token=alice)
    assert got == (200, {"presets": []})
    assert s.req("GET", "/api/voice-presets", token=alice)[1] == {"presets": []}


@pytest.mark.parametrize("bad", [
    {}, {"presets": 1}, {"presets": ["x"]},
    {"presets": [{"lang": "fr", "text": "x"}]},
    {"presets": [{"lang": "zh", "text": ""}]},
    {"presets": [{"lang": "zh", "text": "   "}]},
    {"presets": [{"lang": "zh", "text": "x" * 301}]},
    {"presets": [{"lang": "zh", "text": "a\nb"}]},
    {"presets": [{"lang": "zh", "text": 3}]},
    {"presets": [{"lang": "zh", "text": "同一句"}, {"lang": "zh", "text": "同一句"}]},
    {"presets": [{"lang": "zh", "text": f"第 {i} 句"} for i in range(VOICE_PRESETS_MAX_N + 1)]},
])
def test_写得不对回400_原来的不动(站点, bad):
    s = 站点
    alice = _登(s, "alice")
    assert s.req("POST", "/api/voice-presets", bad, token=alice)[0] == 400, bad
    assert s.req("GET", "/api/voice-presets", token=alice)[1] == {"presets": DEFAULT_VOICE_PRESETS}


def test_库里存坏了按缺省(站点):
    s = 站点
    st = SiteSettings(s.db)
    st.put("voice_presets", [{"lang": "xx"}])
    assert st.voice_presets() == DEFAULT_VOICE_PRESETS
