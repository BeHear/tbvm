#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

#define RAM_SIZE 1024

// Команды нашей VM
enum { HALT = 0, MOV = 1, PRINT = 2, EXEC = 3 };

int regs[8];

// Функция запуска команды в изоляции
void run_command_safely(const char* cmd) {
    // 1. Создаем Job Object для ограничения ресурсов
    HANDLE hJob = CreateJobObject(NULL, NULL);
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION jeli = { 0 };
    
    // Ограничиваем время (5 секунд) и память (32 МБ)
    jeli.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_PROCESS_TIME | JOB_OBJECT_LIMIT_JOB_MEMORY;
    jeli.BasicLimitInformation.PerProcessUserTimeLimit.QuadPart = 50000000; // 5 сек
    jeli.JobMemoryLimit = 32 * 1024 * 1024; // 32 MB
    SetInformationJobObject(hJob, JobObjectExtendedLimitInformation, &jeli, sizeof(jeli));

    // 2. Подготовка процесса (запуск через cmd.exe /c)
    STARTUPINFO si = { sizeof(si) };
    PROCESS_INFORMATION pi;
    char full_cmd[512];
    sprintf(full_cmd, "cmd.exe /c %s", cmd);

    // Запускаем процесс в "подвешенном" состоянии
    if (CreateProcess(NULL, full_cmd, NULL, NULL, FALSE, CREATE_SUSPENDED | CREATE_NEW_CONSOLE, NULL, NULL, &si, &pi)) {
        AssignProcessToJobObject(hJob, pi.hProcess); // Привязываем к песочнице
        ResumeThread(pi.hThread); // Запускаем
        
        WaitForSingleObject(pi.hProcess, 5000); // Ждем максимум 5 сек
        
        TerminateProcess(pi.hProcess, 0); // На всякий случай убиваем после таймаута
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    }
    CloseHandle(hJob);
}

void run_vm(int* code, int size, const char* user_dir) {
    // "Запираем" VM в папке пользователя
    SetCurrentDirectory(user_dir);
    
    int ip = 0;
    while (ip < size) {
        int op = code[ip++];
        switch (op) {
            case MOV: {
                int r = code[ip++];
                regs[r] = code[ip++];
                break;
            }
            case PRINT: {
                printf("REG[%d] = %d\n", code[ip], regs[code[ip]]);
                ip++;
                break;
            }
            case EXEC: {
                // Команда берется из следующего "блока" кода как строка
                char* cmd_str = (char*)&code[ip];
                printf(">> Выполнение системной команды: %s\n", cmd_str);
                run_command_safely(cmd_str);
                // Пропускаем длину строки в байт-коде
                ip += (strlen(cmd_str) / sizeof(int)) + 1;
                break;
            }
            case HALT: return;
        }
    }
}

int main(int argc, char** argv) {
    if (argc < 3) return 1;
    
    const char* bin_file = argv[1];
    const char* user_dir = argv[2];

    FILE *f = fopen(bin_file, "rb");
    int code[4096];
    int size = fread(code, sizeof(int), 4096, f);
    fclose(f);

    run_vm(code, size, user_dir);
    return 0;
}