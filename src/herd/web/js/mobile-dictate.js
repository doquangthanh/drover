// Phone message box: a microphone button that dictates into it with the browser's speech recognition.
// Only added where the browser has it (Chrome, Safari); the key strip itself is built in workspace.js.
import { h } from "./dom.js";

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const MIC = '<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">'
  + '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>';

function addMic(row) {
  row.dataset.dict = "1";
  const input = row.querySelector(".compose");
  const send = row.querySelector(".kb-send");
  if (!input || !send) return;
  let rec = null;
  const mic = h("button", { type: "button", class: "kb-mic", "aria-label": "Dictate", "aria-pressed": "false" });
  mic.innerHTML = MIC; // static icon markup
  const stop = () => { mic.setAttribute("aria-pressed", "false"); rec = null; };
  mic.addEventListener("click", () => {
    if (rec) { rec.stop(); return; }
    try {
      rec = new Recognition();
      rec.lang = navigator.language || "en-US";
      rec.interimResults = false;
      rec.onresult = (e) => {
        const text = Array.from(e.results).map((r) => r[0].transcript).join(" ").trim();
        if (text) input.value = input.value ? `${input.value} ${text}` : text;
      };
      rec.onend = stop;
      rec.onerror = stop;
      rec.start();
      mic.setAttribute("aria-pressed", "true");
    } catch { stop(); }
  });
  row.insertBefore(mic, send);
}

/** Watch the workspace: key strips are rebuilt whenever the layout changes. */
export function watchKeybars() {
  const root = document.getElementById("workspace");
  if (!Recognition || !root) return;
  const scan = () => root.querySelectorAll(".kb-compose:not([data-dict])").forEach(addMic);
  new MutationObserver(scan).observe(root, { childList: true, subtree: true });
  scan();
}
