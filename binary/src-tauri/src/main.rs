// Prevents an extra console window from opening on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

/// Placeholder command. The frontend submit button calls this with the
/// user's idea text. Phase 2 replaces the body with the real orchestrator
/// driver that embeds the Claude Agent SDK and runs the agent team end
/// to end. The command name and signature are the seam — keep them
/// stable so the frontend doesn't need to change.
#[tauri::command]
fn build_idea(idea: String) -> String {
    format!("received: {idea}")
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![build_idea])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
