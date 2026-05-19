// Prevents an extra console window from opening on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::Stdio;
use std::sync::Arc;

use serde::Serialize;
use serde_json::Value;
use tauri::ipc::Channel;
use tauri::{AppHandle, Manager, State};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, Command};
use tokio::sync::Mutex;
use tokio::task;

/// Resolve the SWE root and driver invocation. In a release build the agent
/// files ship as Tauri resources and the driver ships as a PyInstaller
/// sidecar; in dev we fall back to the source tree + `python3 driver.py`.
struct DriverPaths {
    /// Directory containing `team-brief.md`, `orchestrator.md`, and `agents/`.
    swe_root: PathBuf,
    /// The command to invoke. Either a bundled sidecar exe or `python3
    /// orchestrator_driver.py`.
    command: PathBuf,
    /// Extra args to prepend (e.g. the driver script path for python3).
    leading_args: Vec<String>,
}

fn resolve_driver(app: &AppHandle) -> Result<DriverPaths, String> {
    // 1. Production: look for the bundled sidecar + resource files.
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("resource_dir: {e}"))?;
    let resource_brief = resource_dir.join("team-brief.md");
    if resource_brief.is_file() {
        // Tauri 2 renames sidecars to drop the `-<triple>` suffix when copying
        // into the bundle. Look for `driver` and `driver.exe`.
        for candidate in ["driver", "driver.exe"] {
            let p = resource_dir.join(candidate);
            if p.is_file() {
                return Ok(DriverPaths {
                    swe_root: resource_dir,
                    command: p,
                    leading_args: vec![],
                });
            }
        }
        return Err(format!(
            "found bundled SWE root at {} but no sidecar `driver` binary next to it",
            resource_dir.display()
        ));
    }

    // 2. Dev: source tree two levels up from CARGO_MANIFEST_DIR.
    let dev_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .map(PathBuf::from)
        .ok_or("dev swe_root: cannot derive parent")?;
    let dev_driver = dev_root
        .join("binary")
        .join("driver")
        .join("orchestrator_driver.py");
    if !dev_driver.is_file() {
        return Err(format!(
            "dev driver script not found at {}",
            dev_driver.display()
        ));
    }
    Ok(DriverPaths {
        swe_root: dev_root,
        command: PathBuf::from("python3"),
        leading_args: vec![dev_driver.to_string_lossy().into_owned()],
    })
}

/// One active driver session. Held in app state so `answer_question` can find
/// the stdin of the running driver process.
struct Session {
    stdin: ChildStdin,
    child: Child,
}

#[derive(Default)]
struct AppState {
    session: Mutex<Option<Session>>,
}

#[derive(Serialize)]
struct DriverRequest {
    command: &'static str,
    idea: String,
    swe_root: String,
    parent_dir: String,
    dry_run: bool,
}

/// Build an idea using the agent team. Streams each driver event back through
/// the channel as it arrives — UI listens to render progress live.
///
/// Returns immediately once the chain finishes (`done`) or errors out.
#[tauri::command]
async fn build_idea(
    app: AppHandle,
    state: State<'_, Arc<AppState>>,
    idea: String,
    dry_run: Option<bool>,
    on_event: Channel<Value>,
) -> Result<(), String> {
    // Refuse to start a second build while one is active. Simple lock model;
    // multi-build support is a different feature.
    {
        let guard = state.session.lock().await;
        if guard.is_some() {
            return Err("a build is already running; cancel it first".into());
        }
    }

    let paths = resolve_driver(&app)?;

    let request = DriverRequest {
        command: "build",
        idea,
        swe_root: paths.swe_root.to_string_lossy().into_owned(),
        // For now, projects land in the user's home dir under SWE-projects.
        // Once the UI exposes a "where should this go?" picker, plumb that
        // value through here.
        parent_dir: app
            .path()
            .home_dir()
            .map(|p| p.join("SWE-projects").to_string_lossy().into_owned())
            .unwrap_or_else(|_| paths.swe_root.to_string_lossy().into_owned()),
        dry_run: dry_run.unwrap_or(true),
    };
    // Best-effort: create the projects dir so the driver doesn't choke.
    if let Ok(home) = app.path().home_dir() {
        let _ = std::fs::create_dir_all(home.join("SWE-projects"));
    }
    let body = serde_json::to_string(&request).map_err(|e| format!("encode: {e}"))?;

    let mut cmd = Command::new(&paths.command);
    for arg in &paths.leading_args {
        cmd.arg(arg);
    }
    let mut child = cmd
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true)
        .spawn()
        .map_err(|e| format!("spawn driver: {e}"))?;

    let mut stdin = child.stdin.take().ok_or("no stdin on driver")?;
    let stdout = child.stdout.take().ok_or("no stdout on driver")?;
    let stderr = child.stderr.take().ok_or("no stderr on driver")?;

    // Send the initial request.
    stdin
        .write_all(body.as_bytes())
        .await
        .map_err(|e| format!("write request: {e}"))?;
    stdin.write_all(b"\n").await.ok();

    // Stash stdin in state so answer_question can write to it later.
    {
        let mut guard = state.session.lock().await;
        *guard = Some(Session { stdin, child });
    }

    // Pump stderr in the background so the driver doesn't block on a full pipe.
    task::spawn(async move {
        let mut reader = BufReader::new(stderr).lines();
        while let Ok(Some(line)) = reader.next_line().await {
            eprintln!("[driver stderr] {line}");
        }
    });

    // Read stdout line by line and stream each event to the UI.
    let mut reader = BufReader::new(stdout).lines();
    let mut final_event_was_error = false;
    let mut error_message = String::new();

    while let Some(line) = reader
        .next_line()
        .await
        .map_err(|e| format!("read stdout: {e}"))?
    {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        // Parse each line as a JSON event so the UI gets typed values.
        let event: Value = match serde_json::from_str(trimmed) {
            Ok(v) => v,
            Err(_) => serde_json::json!({
                "event": "log",
                "level": "warn",
                "message": format!("unparseable driver line: {trimmed}"),
            }),
        };

        if event.get("event").and_then(|v| v.as_str()) == Some("error") {
            final_event_was_error = true;
            error_message = event
                .get("message")
                .and_then(|v| v.as_str())
                .unwrap_or("unspecified")
                .to_string();
        }

        on_event
            .send(event)
            .map_err(|e| format!("channel send: {e}"))?;
    }

    // Driver closed stdout — wait for the process to fully exit, then clear state.
    let exit_status = {
        let mut guard = state.session.lock().await;
        if let Some(mut session) = guard.take() {
            session.child.wait().await.map_err(|e| format!("wait: {e}"))?
        } else {
            return Err("session vanished".into());
        }
    };

    if final_event_was_error {
        return Err(format!("driver reported error: {error_message}"));
    }
    if !exit_status.success() {
        return Err(format!(
            "driver exited {}",
            exit_status.code().unwrap_or(-1)
        ));
    }
    Ok(())
}

/// Write a user answer back to the active driver's stdin. Called by the UI
/// in response to a `user_question` event.
#[tauri::command]
async fn answer_question(
    state: State<'_, Arc<AppState>>,
    answer: String,
) -> Result<(), String> {
    let mut guard = state.session.lock().await;
    let session = guard.as_mut().ok_or("no active build session")?;
    let payload = serde_json::json!({"command": "user_answer", "answer": answer});
    let line = serde_json::to_string(&payload).map_err(|e| e.to_string())? + "\n";
    session
        .stdin
        .write_all(line.as_bytes())
        .await
        .map_err(|e| format!("write to driver stdin: {e}"))?;
    Ok(())
}

/// Cancel the active build. Closes stdin and signals the child.
#[tauri::command]
async fn cancel_build(state: State<'_, Arc<AppState>>) -> Result<(), String> {
    let mut guard = state.session.lock().await;
    if let Some(mut session) = guard.take() {
        // Send the driver a clean cancel so it exits with code 3 if it was
        // waiting on a user answer.
        let _ = session
            .stdin
            .write_all(b"{\"command\":\"cancel\"}\n")
            .await;
        // kill_on_drop will reap if the cancel doesn't take.
        let _ = session.child.start_kill();
    }
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            app.manage(Arc::new(AppState::default()));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            build_idea,
            answer_question,
            cancel_build,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
