#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#define RAM_SIZE 1024
#define NUM_REGS 8

enum { HALT = 0, MOV = 1, PRINT = 2, EXEC = 3 };

int regs[NUM_REGS];

#ifdef _WIN32
#include <windows.h>

void run_command_safely(const char* cmd, const char* resolved_dir) {
    if (!SetCurrentDirectory(resolved_dir)) {
        fprintf(stderr, "ERROR: cannot chdir to '%s'\n", resolved_dir);
        return;
    }
    HANDLE hJob = CreateJobObject(NULL, NULL);
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION jeli = { 0 };
    jeli.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_PROCESS_TIME | JOB_OBJECT_LIMIT_JOB_MEMORY;
    jeli.BasicLimitInformation.PerProcessUserTimeLimit.QuadPart = 50000000;
    jeli.JobMemoryLimit = 32 * 1024 * 1024;
    SetInformationJobObject(hJob, JobObjectExtendedLimitInformation, &jeli, sizeof(jeli));

    STARTUPINFO si = { sizeof(si) };
    PROCESS_INFORMATION pi;
    char full_cmd[512];
    snprintf(full_cmd, sizeof(full_cmd), "cmd.exe /c %s", cmd);

    if (CreateProcess(NULL, full_cmd, NULL, NULL, FALSE, CREATE_SUSPENDED | CREATE_NEW_CONSOLE, NULL, NULL, &si, &pi)) {
        AssignProcessToJobObject(hJob, pi.hProcess);
        ResumeThread(pi.hThread);
        WaitForSingleObject(pi.hProcess, 5000);
        TerminateProcess(pi.hProcess, 0);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    }
    CloseHandle(hJob);
}

#else
#include <unistd.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <signal.h>
#include <limits.h>

static pid_t child_pid = 0;

static void timeout_handler(int sig) {
    (void)sig;
    if (child_pid > 0)
        kill(child_pid, SIGKILL);
}

void run_command_safely(const char* cmd, const char* resolved_dir) {
    child_pid = fork();
    if (child_pid == 0) {
        struct rlimit cpu = { 5, 5 };
        struct rlimit mem = { 32 * 1024 * 1024, 32 * 1024 * 1024 };
        setrlimit(RLIMIT_CPU, &cpu);
        setrlimit(RLIMIT_AS, &mem);
        if (chdir(resolved_dir) != 0) {
            fprintf(stderr, "ERROR: cannot chdir to '%s'\n", resolved_dir);
            _exit(127);
        }
        execl("/bin/sh", "sh", "-c", cmd, (char*)NULL);
        _exit(127);
    } else if (child_pid > 0) {
        signal(SIGALRM, timeout_handler);
        alarm(5);
        waitpid(child_pid, NULL, 0);
        alarm(0);
        child_pid = 0;
    }
}

#endif

static int safe_reg(int r) {
    if (r < 0 || r >= NUM_REGS) {
        fprintf(stderr, "ERROR: invalid register r%d (0-%d)\n", r, NUM_REGS - 1);
        return 0;
    }
    return 1;
}

#ifndef _WIN32
static int resolve_dir(const char* raw, char* out, size_t out_sz) {
    if (raw == NULL) return -1;
    char* r = realpath(raw, NULL);
    if (r == NULL) {
        fprintf(stderr, "ERROR: cannot resolve directory '%s'\n", raw);
        return -1;
    }
    size_t len = strlen(r);
    if (len >= out_sz) {
        free(r);
        return -1;
    }
    memcpy(out, r, len + 1);
    free(r);
    return 0;
}
#endif

void run_vm(int* code, int size, const char* resolved_dir) {
    int ip = 0;
    while (ip < size) {
        int op = code[ip++];
        switch (op) {
            case MOV: {
                if (ip + 2 > size) { fprintf(stderr, "ERROR: unexpected end of code\n"); return; }
                int r = code[ip++];
                int val = code[ip++];
                if (safe_reg(r)) regs[r] = val;
                break;
            }
            case PRINT: {
                if (ip + 1 > size) { fprintf(stderr, "ERROR: unexpected end of code\n"); return; }
                int r = code[ip++];
                if (safe_reg(r)) printf("REG[%d] = %d\n", r, regs[r]);
                break;
            }
            case EXEC: {
                char* cmd_str = (char*)&code[ip];
                size_t max_len = (size - ip) * sizeof(int);
                size_t slen = strnlen(cmd_str, max_len);
                if (slen >= max_len) {
                    fprintf(stderr, "ERROR: EXEC string exceeds code bounds\n");
                    return;
                }
                fprintf(stderr, "WARNING: executing system command from bytecode\n");
                printf(">> %s\n", cmd_str);
                run_command_safely(cmd_str, resolved_dir);
                ip += (int)(slen / sizeof(int)) + 1;
                if (ip > size) ip = size;
                break;
            }
            case HALT:
                return;
            default:
                fprintf(stderr, "ERROR: unknown opcode %d at ip=%d\n", op, ip - 1);
                return;
        }
    }
}

int main(int argc, char** argv) {
    if (argc < 3) {
        fprintf(stderr, "Usage: %s <bytecode.bin> <directory>\n", argv[0]);
        return 1;
    }

    struct stat st;
    if (stat(argv[1], &st) != 0) {
        fprintf(stderr, "ERROR: cannot access '%s'\n", argv[1]);
        return 1;
    }
    if (!S_ISREG(st.st_mode)) {
        fprintf(stderr, "ERROR: '%s' is not a regular file\n", argv[1]);
        return 1;
    }

    FILE* f = fopen(argv[1], "rb");
    if (!f) {
        fprintf(stderr, "ERROR: cannot open '%s'\n", argv[1]);
        return 1;
    }
    int code[4096];
    size_t read_count = fread(code, sizeof(int), 4096, f);
    if (read_count == 0 && ferror(f)) {
        fprintf(stderr, "ERROR: read error on '%s'\n", argv[1]);
        fclose(f);
        return 1;
    }
    int size = (int)read_count;
    fclose(f);

#ifdef _WIN32
    run_vm(code, size, argv[2]);
#else
    char resolved_dir[PATH_MAX];
    if (resolve_dir(argv[2], resolved_dir, sizeof(resolved_dir)) != 0) {
        return 1;
    }
    run_vm(code, size, resolved_dir);
#endif
    return 0;
}
