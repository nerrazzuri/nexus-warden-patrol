import "./oldkeys";
import "./fonts.css";
import "./styles.css";
import { render } from "preact";
import { App } from "./app";
import { installErrorLog } from "./errlog";
import { installStyleCheck } from "./stylecheck";
import { lang, setLang } from "./i18n";
import { followSystem } from "./theme";
import { installValidity } from "./validity";

followSystem();
installErrorLog();
installValidity();
installStyleCheck();
setLang(lang.value);
// 第 3 轮 layout N4:先清掉 index.html 里「没载入完整」那句(脚本载上了就用不着)
const root = document.getElementById("app")!;
root.textContent = "";
render(<App />, root);
