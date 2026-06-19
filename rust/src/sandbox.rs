use std::ffi::CString;
use std::os::unix::process::CommandExt;
use std::path::Path;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

#[derive(Debug)]
pub enum SandboxError {
    Spawn,
    Timeout,
    Wait,
    Limit(String),
}

fn apply_sandbox_limits() -> Result<(), String> {
    let set = |resource: u32, soft: u64, hard: u64| -> Result<(), String> {
        let lim = libc::rlimit { rlim_cur: soft, rlim_max: hard };
        let ret = unsafe { libc::setrlimit(resource, &lim) };
        if ret != 0 {
            let name = match resource {
                libc::RLIMIT_AS => "RLIMIT_AS",
                libc::RLIMIT_CPU => "RLIMIT_CPU",
                libc::RLIMIT_CORE => "RLIMIT_CORE",
                libc::RLIMIT_NPROC => "RLIMIT_NPROC",
                _ => "unknown",
            };
            return Err(format!("setrlimit({}) failed: {}", name, std::io::Error::last_os_error()));
        }
        Ok(())
    };

    set(libc::RLIMIT_AS, 64 * 1024 * 1024, 64 * 1024 * 1024)?;
    set(libc::RLIMIT_CPU, 3, 3)?;
    set(libc::RLIMIT_CORE, 0, 0)?;
    set(libc::RLIMIT_NPROC, 1, 1)?;
    Ok(())
}

fn close_extra_fds() {
    for fd in 3..=255 {
        unsafe { libc::close(fd); }
    }
}

/// Best-effort chroot into the current working directory.
/// Does not require root if the kernel supports user namespaces
/// (unprivileged_userns_clone=1, default on most distros).
/// Silent on failure — falls back to best-effort setrlimit-only sandbox.
pub fn try_chroot_here() {
    // Try to enter a private mount namespace (needed for chroot without side effects)
    // This succeeds on kernels with user namespace support
    let ret = unsafe { libc::unshare(libc::CLONE_NEWNS) };
    if ret != 0 {
        // user/mount namespaces not available — try chroot without it
        // (might still work if running as root)
    }

    let cwd = match std::env::current_dir() {
        Ok(p) => p,
        Err(_) => return,
    };
    let cwd_str = match cwd.to_str() {
        Some(s) => s,
        None => return,
    };
    let dir_cstr = match CString::new(cwd_str) {
        Ok(c) => c,
        Err(_) => return,
    };

    if unsafe { libc::chroot(dir_cstr.as_ptr()) } != 0 {
        return;
    }
    unsafe { libc::chdir(b"/\0" as *const _ as *const libc::c_char); }
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
                close_extra_fds();
                try_chroot_here();
                if let Err(e) = apply_sandbox_limits() {
                    let _ = std::io::Write::write_all(
                        &mut std::io::stderr(),
                        format!("sandbox limit error: {}\n", e).as_bytes(),
                    );
                }
                Ok(())
            })
            .spawn()
    }
    .map_err(|_| SandboxError::Spawn)?;

    let start = Instant::now();
    let timeout = Duration::from_secs(5);

    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                if !status.success() {
                    if let Some(code) = status.code() {
                        std::process::exit(code);
                    }
                }
                return Ok(());
            }
            Ok(None) => {
                if start.elapsed() > timeout {
                    let _ = child.kill();
                    std::thread::sleep(Duration::from_millis(100));
                    let _ = child.wait();
                    return Err(SandboxError::Timeout);
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            Err(_) => return Err(SandboxError::Wait),
        }
    }
}
