import functools
import html
import http.server
import json
import logging
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any

from elegoo.episode import EPISODE_FILE, RUNS_DIR, STEPS_FILE

HOST = "127.0.0.1"
PORT = 8000
NOTES_FILE = "notes.json"
EPISODE_NOTE_KEY = "episode"
TEXT_BLOCK = "text"
HTML_TYPE = "text/html; charset=utf-8"
STYLE = """\
:root { color-scheme: light dark; --line: #8884; }
body { font: 14px/1.4 system-ui, sans-serif; margin: 16px; max-width: 1100px; }
table { border-collapse: collapse; width: 100%; }
td, th { border-bottom: 1px solid var(--line); padding: 6px; text-align: left; vertical-align: top; }
img { width: 320px; display: block; }
pre { white-space: pre-wrap; margin: 0; }
textarea { width: 100%; box-sizing: border-box; font: inherit; }
textarea + small { display: block; height: 1.4em; }
.success { color: #2a2; } .failure { color: #d33; }"""
# Saves a note 0.5 s after the last key press, to send one request per pause.
SAVE_SCRIPT = """\
for (const area of document.querySelectorAll("textarea")) {
  let timer;
  area.addEventListener("input", () => {
    clearTimeout(timer);
    area.nextElementSibling.textContent = "";
    timer = setTimeout(async () => {
      const body = JSON.stringify({key: area.dataset.key, text: area.value});
      const response = await fetch(location.href, {method: "POST", body});
      area.nextElementSibling.textContent = response.ok ? "saved" : "not saved";
    }, 500);
  });
}"""

logger = logging.getLogger(__name__)


class _Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        episode_dir = self._episode_dir()
        if urllib.parse.urlsplit(self.path).path == "/":
            self._send_html(_index_page(Path(self.directory)))
        elif episode_dir is not None:
            self._send_html(_episode_page(episode_dir))
        else:
            super().do_GET()

    def do_POST(self) -> None:
        episode_dir = self._episode_dir()
        if episode_dir is None:
            self.send_error(http.HTTPStatus.NOT_FOUND)
            return
        note = self._read_note()
        if note is None:
            self.send_error(http.HTTPStatus.BAD_REQUEST)
            return
        notes = {key: text for key, text in (_read_notes(episode_dir) | note).items() if text.strip()}
        (episode_dir / NOTES_FILE).write_text(json.dumps(notes, indent=2) + "\n")
        self.send_response(http.HTTPStatus.NO_CONTENT)
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug(format, *args)

    def _read_note(self) -> dict[str, str] | None:
        """Returns {key: text} from a body {"key": "episode" or a step index, "text": str}, or None if it is invalid."""
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        except ValueError:
            return None
        if not isinstance(body, dict):
            return None
        key, text = body.get("key"), body.get("text")
        if not isinstance(key, str) or not (key == EPISODE_NOTE_KEY or key.isdigit()) or not isinstance(text, str):
            return None
        return {key: text}

    def _episode_dir(self) -> Path | None:
        root = Path(self.directory)
        parts = [part for part in urllib.parse.urlsplit(self.path).path.split("/") if part]
        if len(parts) == 1 and parts[0] in _episode_names(root):
            return root / parts[0]
        return None

    def _send_html(self, page: str) -> None:
        body = page.encode()
        self.send_response(http.HTTPStatus.OK)
        self.send_header("Content-Type", HTML_TYPE)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_server(root: Path, *, port: int = PORT) -> http.server.HTTPServer:
    """Serves the episodes in `root` and saves the notes to notes.json in each episode directory."""
    return http.server.HTTPServer((HOST, port), functools.partial(_Handler, directory=str(root)))


def _episode_names(root: Path) -> set[str]:
    return {path.parent.name for path in root.glob(f"*/{EPISODE_FILE}")}


def _read_episode(episode_dir: Path) -> dict[str, Any]:
    return json.loads((episode_dir / EPISODE_FILE).read_text())


def _read_steps(episode_dir: Path) -> list[dict[str, Any]]:
    steps_path = episode_dir / STEPS_FILE
    if not steps_path.exists():
        return []
    return [json.loads(line) for line in steps_path.read_text().splitlines()]


def _read_notes(episode_dir: Path) -> dict[str, str]:
    notes_path = episode_dir / NOTES_FILE
    if not notes_path.exists():
        return {}
    return json.loads(notes_path.read_text())


def _page(title: str, body: str) -> str:
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
        f"<style>{STYLE}</style></head><body>{body}</body></html>\n"
    )


def _verdict_cell(episode: dict[str, Any]) -> str:
    verdict = episode.get("verdict")
    if verdict is None:
        return "no verdict"
    outcome = "success" if verdict["success"] else "failure"
    flags = [name for name in ("contact", "intervention") if verdict[name]]
    return f'<span class="{outcome}">{outcome}</span> {" ".join(flags)}'


def _note_area(notes: dict[str, str], key: str) -> str:
    return (
        f'<textarea rows="3" data-key="{key}" placeholder="Note">{html.escape(notes.get(key, ""))}</textarea>'
        "<small></small>"
    )


def _index_page(root: Path) -> str:
    rows = []
    for number, name in enumerate(sorted(_episode_names(root)), start=1):
        episode_dir = root / name
        episode = _read_episode(episode_dir)
        note = _read_notes(episode_dir).get(EPISODE_NOTE_KEY, "")
        rows.append(
            f'<tr><td>{number}</td><td><a href="{name}/">{name}</a></td>'
            f"<td>{html.escape(episode['model_id'])}</td><td>{html.escape(episode['instruction'])}</td>"
            f"<td>{episode.get('result', 'not closed')}</td><td>{_verdict_cell(episode)}</td>"
            f"<td>{len(_read_steps(episode_dir))}</td><td>{html.escape(note)}</td></tr>"
        )
    table = (
        "<table><tr><th>#</th><th>Episode</th><th>Model</th><th>Instruction</th><th>Result</th><th>Verdict</th>"
        "<th>Steps</th><th>Note</th></tr>" + "".join(rows) + "</table>"
    )
    return _page("Episodes", f"<h1>Episodes</h1>{table}")


def _episode_page(episode_dir: Path) -> str:
    episode = _read_episode(episode_dir)
    steps = _read_steps(episode_dir)
    notes = _read_notes(episode_dir)
    system = next((step["decision"]["request"]["system"] for step in steps if step["decision"]), "")
    header = (
        f"<p><a href='../'>All episodes</a></p><h1>{episode_dir.name}</h1>"
        f"<p>{html.escape(episode['instruction'])} · {html.escape(episode['model_id'])} · "
        f"result {episode.get('result', 'not closed')} · {_verdict_cell(episode)} · battery {episode['batt_mv']} mV</p>"
        f"<details><summary>System prompt</summary><pre>{html.escape(system)}</pre></details>"
        f"<p>{_note_area(notes, EPISODE_NOTE_KEY)}</p>"
    )
    rows = "".join(_step_row(step, notes) for step in steps)
    table = f"<table><tr><th>Frame</th><th>Step</th></tr>{rows}</table>"
    return _page(episode_dir.name, f"{header}{table}<script>{SAVE_SCRIPT}</script>")


def _step_row(step: dict[str, Any], notes: dict[str, str]) -> str:
    tele = step["tele_before"]
    lines = [f"<b>#{step['index']}</b> sonar {tele['sonar_cm']} cm · yaw {tele['yaw_deg']}°"]
    decision = step["decision"]
    if decision is not None:
        texts = [block["text"] for block in decision["response"]["content"] if block["type"] == TEXT_BLOCK]
        lines.append(f"<pre>{html.escape(' '.join(texts))}</pre>")
        lines.append(f"<b>{html.escape(json.dumps(decision['call']))}</b>")
        lines.append(f"{decision['latency_ms']} ms · {decision['input_tokens']}/{decision['output_tokens']} tokens")
    lines.append(f"outcome {step['outcome']} · stop {step['stop_reason']}")
    if step["error"] is not None:
        lines.append(f'<span class="failure">{html.escape(step["error"])}</span>')
    frame = html.escape(step["frame"])
    return (
        f'<tr><td><a href="{frame}"><img src="{frame}"></a></td>'
        f"<td>{'<br>'.join(lines)}{_note_area(notes, str(step['index']))}</td></tr>"
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with make_server(RUNS_DIR) as server:
        url = f"http://{HOST}:{server.server_port}/"
        logger.info("Serve %s at %s, press Ctrl+C to stop", RUNS_DIR, url)
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logger.info("Stop the server")


if __name__ == "__main__":
    main()
