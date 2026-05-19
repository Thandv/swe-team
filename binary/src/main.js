// Phase-2 desktop shell — placeholder wiring.
//
// The submit button calls the `build_idea` Tauri command, which currently
// just echoes the input back. Phase 2 replaces the Rust-side handler with
// the real orchestrator driver (embedding the Claude Agent SDK).
//
// No bundler is in play, so we use the runtime-injected global
// `window.__TAURI__.core.invoke` instead of importing from the JS API
// package (a bare ES module specifier the browser can't resolve).

const invoke = window.__TAURI__?.core?.invoke;

const ideaEl = document.getElementById("idea");
const submitEl = document.getElementById("submit");
const outputEl = document.getElementById("output");

async function handleSubmit() {
  const idea = ideaEl.value.trim();
  if (!idea) {
    outputEl.textContent = "(please enter something to build)";
    return;
  }

  submitEl.disabled = true;
  outputEl.textContent = "working...";
  try {
    const result = await invoke("build_idea", { idea });
    outputEl.textContent = result;
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
