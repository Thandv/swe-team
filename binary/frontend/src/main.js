// Phase 2 desktop shell — streaming + Q&A wiring.
//
// build_idea streams driver events through a Tauri Channel. The UI renders
// each event live. When a user_question event arrives, an input shows up
// underneath; submitting it calls answer_question, which writes back to the
// driver's stdin.

const invoke = window.__TAURI__?.core?.invoke;
const Channel = window.__TAURI__?.core?.Channel;

const ideaEl = document.getElementById("idea");
const submitEl = document.getElementById("submit");
const cancelEl = document.getElementById("cancel");
const outputEl = document.getElementById("output");
const dryRunEl = document.getElementById("dryRun");
const questionEl = document.getElementById("question");

function appendLine(text) {
  outputEl.textContent += (outputEl.textContent ? "\n" : "") + text;
  outputEl.scrollTop = outputEl.scrollHeight;
}

function fmtEvent(event) {
  switch (event.event) {
    case "project_initialized":
      return `📁 project root: ${event.project_root}`;
    case "agent_started":
      return `▶ ${event.role}…`;
    case "agent_completed": {
      const arts = event.artifacts?.length ? `\n   wrote: ${event.artifacts.join(", ")}` : "";
      const notes = event.notes ? `\n   note: ${event.notes}` : "";
      return `✔ ${event.role} → ${event.handoff_target}${arts}${notes}`;
    }
    case "user_question":
      return `❓ ${event.role} asks: ${event.question}`;
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

function showQuestionPrompt(text) {
  questionEl.style.display = "block";
  questionEl.innerHTML = "";

  const label = document.createElement("div");
  label.textContent = text;
  label.style.marginBottom = "0.5rem";
  questionEl.appendChild(label);

  const input = document.createElement("textarea");
  input.placeholder = "Type your answer…";
  input.style.minHeight = "4rem";
  questionEl.appendChild(input);

  const send = document.createElement("button");
  send.textContent = "Send answer";
  send.style.marginTop = "0.5rem";
  send.addEventListener("click", async () => {
    const answer = input.value.trim();
    if (!answer) return;
    send.disabled = true;
    try {
      await invoke("answer_question", { answer });
      appendLine(`📤 you: ${answer}`);
    } catch (err) {
      appendLine(`✖ failed to send answer: ${err}`);
      send.disabled = false;
      return;
    }
    questionEl.style.display = "none";
    questionEl.innerHTML = "";
  });
  questionEl.appendChild(send);
  input.focus();
}

async function handleSubmit() {
  const idea = ideaEl.value.trim();
  if (!idea) {
    outputEl.textContent = "(please enter something to build)";
    return;
  }
  if (!Channel) {
    outputEl.textContent = "error: this build is missing the Tauri Channel API";
    return;
  }

  submitEl.disabled = true;
  cancelEl.style.display = "inline-block";
  outputEl.textContent = "spawning driver…";
  questionEl.style.display = "none";

  const channel = new Channel();
  channel.onmessage = (event) => {
    appendLine(fmtEvent(event));
    if (event.event === "user_question") {
      showQuestionPrompt(event.question);
    }
  };

  try {
    await invoke("build_idea", {
      idea,
      dryRun: dryRunEl?.checked ?? true,
      onEvent: channel,
    });
  } catch (err) {
    appendLine(`✖ ${err}`);
  } finally {
    submitEl.disabled = false;
    cancelEl.style.display = "none";
  }
}

async function handleCancel() {
  try {
    await invoke("cancel_build");
    appendLine("· cancelled");
  } catch (err) {
    appendLine(`✖ cancel failed: ${err}`);
  }
}

submitEl.addEventListener("click", handleSubmit);
cancelEl.addEventListener("click", handleCancel);
ideaEl.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    event.preventDefault();
    handleSubmit();
  }
});
