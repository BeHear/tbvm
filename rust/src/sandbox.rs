use std::path::Path;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

#[derive(Debug)]
pub enum SandboxError {
    Spawn,
    Timeout,
    Wait,
    KillFailed,
}

pub fn run_isolated(cmd: &str, dir: &Path) -> Result<(), SandboxError> {
    let mut child = Command::new("sh")
        .arg("-c")
        .arg(cmd)
        .current_dir(dir)
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|_| SandboxError::Spawn)?;

    let start = Instant::now();
    let timeout = Duration::from_secs(5);

    loop {
        match child.try_wait() {
            Ok(Some(_)) => return Ok(()),
            Ok(None) => {
                if start.elapsed() > timeout {
                    child.kill().map_err(|_| SandboxError::KillFailed)?;
                    child.wait().ok();
                    return Err(SandboxError::Timeout);
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            Err(_) => return Err(SandboxError::Wait),
        }
    }
}
