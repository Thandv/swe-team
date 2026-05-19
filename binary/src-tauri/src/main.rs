// Prevents an extra console window from opening on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};

use serde::Serialize;

/// Resolve the SWE repo root (where `agents/`, `team-brief.md`, `orchestrator.md`
/// live). For now, derived relative to the binary's source tree. Once we ship
/// real installer bundles, this becomes a bundled-resource lookup via
/// `tauri::AppHandle::path()`.
fn swe_root() -> PathBuf {
    // CARGO_MANIFEST_DIR points at binary/src-tauri/ at compile time.
    // Two levels up gets us to the SWE repo root.
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent() // binary/
        .and_then(|p| p.parent()) // SWE/
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

#[derive(Serialize)]
struct DriverRequest {
    command: &'static str,
    idea: String,
    swe_root: String,
    parent_dir: String,
    dry_run: bool,
}

/// Spawn the Python driver, write the JSON request to its stdin, collect
/// stdout (JSON-line events) and return it to the frontend as a single
/// newline-separated string.
///
/// Streaming events to the UI live-as-they-arrive is the obvious next step —
/// it requires emitting Tauri events from a tokio task reading stdout. The
/// blocking first cut keeps the shape testable end-to-end first.
#[tauri::command]
async fn build_idea(idea: String, dry_run: Option<bool>) -> Result<String, String> {
    let root = swe_root();
    let driver = root.join("binary").join("driver").join("orchestrator_driver.py");

    if !driver.is_file() {
        return Err(format!("driver not found: {}", driver.display()));
    }

    let request = DriverRequest {
        command: "build",
        idea,
        swe_root: root.to_string_lossy().into_owned(),
        parent_dir: root.to_string_lossy().into_owned(),
        dry_run: dry_run.unwrap_or(true),
    };
    let body = serde_json::to_string(&request).map_err(|e| format!("encode: {e}"))?;

    let mut child = Command::new("python3")
        .arg(&driver)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("spawn driver: {e}"))?;

    {
        let stdin = child.stdin.as_mut().ok_or("no stdin on driver")?;
        stdin
            .write_all(body.as_bytes())
            .map_err(|e| format!("write stdin: {e}"))?;
    }
    // Closing stdin signals EOF to the driver.
    drop(child.stdin.take());

    let output = child
        .wait_with_output()
        .map_err(|e| format!("wait driver: {e}"))?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();

    if !output.status.success() {
        return Err(format!(
            "driver exited {}\n--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}",
            output.status.code().unwrap_or(-1)
        ));
    }
    Ok(stdout)
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![build_idea])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
