use std::os::unix::process::CommandExt;
use std::path::Path;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

#[derive(Debug)]
pub enum SandboxError {
    Spawn,
    Timeout,
    Wait,
}

fn apply_sandbox_limits() {
    let _ = std::panic::catch_unwind(|| {
        let mut lim: libc::rlimit = libc::rlimit { rlim_cur: 0, rlim_max: 0 };
        // Memory limit: 64 MB
        lim.rlim_cur = 64 * 1024 * 1024;
        lim.rlim_max = 64 * 1024 * 1024;
        unsafe { libc::setrlimit(libc::RLIMIT_AS, &lim); }
        // CPU limit: 3 seconds
        lim.rlim_cur = 3;
        lim.rlim_max = 3;
        unsafe { libc::setrlimit(libc::RLIMIT_CPU, &lim); }
        // No core dumps
        lim.rlim_cur = 0;
        lim.rlim_max = 0;
        unsafe { libc::setrlimit(libc::RLIMIT_CORE, &lim); }
        // Number of processes: only 1 (prevent fork bombs)
        lim.rlim_cur = 1;
        lim.rlim_max = 1;
        unsafe { libc::setrlimit(libc::RLIMIT_NPROC, &lim); }
    });
}

pub fn run_isolated(cmd: &str, dir: &Path) -> Result<(), SandboxError> {
    let mut child = unsafe {
        Command::new("sh")
            .arg("-c")
            .arg(cmd)
            .current_dir(dir)
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .process_group(0)
            .pre_exec(|| {
                apply_sandbox_limits();
                Ok(())
            })
            .spawn()
    }
    .map_err(|_| SandboxError::Spawn)?;

    let start = Instant::now();
    let timeout = Duration::from_secs(5);

    loop {
        match child.try_wait() {
            Ok(Some(_)) => return Ok(()),
            Ok(None) => {
                if start.elapsed() > timeout {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(SandboxError::Timeout);
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            Err(_) => return Err(SandboxError::Wait),
        }
    }
}
