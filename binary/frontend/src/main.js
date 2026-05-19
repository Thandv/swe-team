// Phase 2 desktop shell wiring.
//
// The submit button calls the Rust `build_idea` command, which spawns the
// Python driver subprocess (binary/driver/orchestrator_driver.py). The driver
// emits one JSON event per line on stdout; we collect those and render them
// as a per-step log so the user can see what each agent did.
//
// Real-time streaming (events arriving as each agent finishes, rather than
// at the end) is the obvious next iteration. The Rust side returns the full
// stdout for now; phase 2.1 will swap to Tauri event emit + frontend listen.

const invoke = window.__TAURI__?.core?.invoke;

const ideaEl = document.getElementById("idea");
const submitEl = document.getElementById("submit");
const outputEl = document.getElementById("output");
const dryRunEl = document.getElementById("dryRun");

function fmt(event) {
  switch (event.event) {
    case "project_initialized":
      return `📁 project root: ${event.project_root}`;
    case "agent_started":
      return `▶ ${event.role}…`;
    case "agent_completed":
      return `✔ ${event.role} → ${event.handoff_target}` +
        (event.artifacts?.length ? `\n   wrote: ${event.artifacts.join(", ")}` : "") +
        (event.notes ? `\n   note: ${event.notes}` : "");
    case "user_question":
      return `❓ ${event.role}: ${event.question}`;
    case "log":
      return `· [${event.level}] ${event.message}`;
    case "error":
      return `✖ error: ${event.message}`;
    case "done":
      return `🏁 done — ${event.project_root}` +
        (event.summary ? `\n   ${event.summary}` : "");
    default:
      return JSON.stringify(event);
  }
}

async function handleSubmit() {
  const idea = ideaEl.value.trim();
  if (!idea) {
    outputEl.textContent = "(please enter something to build)";
    return;
  }

  submitEl.disabled = true;
  outputEl.textContent = "spawning driver…\n";

  try {
    const stdout = await invoke("build_idea", {
      idea,
      dryRun: dryRunEl?.checked ?? true,
    });
    const lines = stdout.split("\n").filter(Boolean);
    const events = lines.map((line) => {
      try { return JSON.parse(line); }
      catch { return { event: "log", level: "warn", message: `unparseable: ${line}` }; }
    });
    outputEl.textContent = events.map(fmt).join("\n");
  } catch (err) {
    outputEl.textContent = `error: ${err}`;
  } finally {
    submitEl.disabled = false;
  }
}

submitEl.addEventListener("click", handleSubmit);
ideaEl.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    event.preventDefault();
    handleSubmit();
  }
});
