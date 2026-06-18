#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RAM_SIZE 1024
#define NUM_REGS 8

enum { HALT = 0, MOV = 1, PRINT = 2, EXEC = 3 };

int regs[NUM_REGS];

#ifdef _WIN32
#include <windows.h>

void run_command_safely(const char* cmd, const char* user_dir) {
    SetCurrentDirectory(user_dir);
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

static pid_t child_pid = 0;

static void timeout_handler(int sig) {
    (void)sig;
    if (child_pid > 0)
        kill(child_pid, SIGKILL);
}

void run_command_safely(const char* cmd, const char* user_dir) {
    child_pid = fork();
    if (child_pid == 0) {
        struct rlimit cpu = { 5, 5 };
        struct rlimit mem = { 32 * 1024 * 1024, 32 * 1024 * 1024 };
        setrlimit(RLIMIT_CPU, &cpu);
        setrlimit(RLIMIT_AS, &mem);
        if (user_dir)
            chdir(user_dir);
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

void run_vm(int* code, int size, const char* user_dir) {
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
                printf(">> %s\n", cmd_str);
                run_command_safely(cmd_str, user_dir);
                ip += (int)(slen / sizeof(int)) + 1;
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

    FILE* f = fopen(argv[1], "rb");
    if (!f) {
        fprintf(stderr, "ERROR: cannot open '%s'\n", argv[1]);
        return 1;
    }
    int code[4096];
    int size = (int)fread(code, sizeof(int), 4096, f);
    fclose(f);

    run_vm(code, size, argv[2]);
    return 0;
}
