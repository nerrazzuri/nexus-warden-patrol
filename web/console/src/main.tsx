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
render(<App />, document.getElementById("app")!);
