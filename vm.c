#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/select.h>
#include <unistd.h>
#include <time.h>

#define VRAM_WIDTH 128
#define VRAM_HEIGHT 128
#define NUM_REGS 8
#define MEM_SIZE 1024
#define STACK_SIZE 256

enum {
    HALT = 0, MOV, ADD, ADDI, SUB, SUBI,
    CMP, CMPI, JMP, JZ, JNZ,
    CALL, RET, STORE, LOAD, DRAW, PRINT,
    CLS, RAND, KEY
};

int regs[NUM_REGS];
int memory[MEM_SIZE];
int call_stack[STACK_SIZE];
int csp = -1;
int flag_zero = 0;
int vram[VRAM_WIDTH * VRAM_HEIGHT];

static int safe_reg(int r) {
    if (r < 0 || r >= NUM_REGS) {
        fprintf(stderr, "ERROR: invalid register r%d (0-%d)\n", r, NUM_REGS - 1);
        return 0;
    }
    return 1;
}

static int safe_addr(int a) {
    if (a < 0 || a >= MEM_SIZE) {
        fprintf(stderr, "ERROR: invalid memory address %d (0-%d)\n", a, MEM_SIZE - 1);
        return 0;
    }
    return 1;
}

static int safe_ip(int ip, int need, int size) {
    if (ip + need > size) {
        fprintf(stderr, "ERROR: unexpected end of code at ip=%d (need %d words, have %d)\n", ip, need, size - ip);
        return 0;
    }
    return 1;
}

static int safe_jump(int target, int size) {
    if (target < 0 || target >= size) {
        fprintf(stderr, "ERROR: invalid jump target %d (code size %d)\n", target, size);
        return 0;
    }
    return 1;
}

void run(int* code, int size) {
    int ip = 0;
    while (ip < size) {
        int op = code[ip++];
        switch (op) {
            case MOV:
                if (!safe_ip(ip, 2, size)) return;
                { int r = code[ip++]; int val = code[ip++];
                  if (safe_reg(r)) regs[r] = val; }
                break;
            case ADD:
                if (!safe_ip(ip, 2, size)) return;
                { int r1 = code[ip++]; int r2 = code[ip++];
                  if (safe_reg(r1) && safe_reg(r2)) regs[r1] += regs[r2]; }
                break;
            case ADDI:
                if (!safe_ip(ip, 2, size)) return;
                { int r1 = code[ip++]; int val = code[ip++];
                  if (safe_reg(r1)) regs[r1] += val; }
                break;
            case SUB:
                if (!safe_ip(ip, 2, size)) return;
                { int r1 = code[ip++]; int r2 = code[ip++];
                  if (safe_reg(r1) && safe_reg(r2)) regs[r1] -= regs[r2]; }
                break;
            case SUBI:
                if (!safe_ip(ip, 2, size)) return;
                { int r1 = code[ip++]; int val = code[ip++];
                  if (safe_reg(r1)) regs[r1] -= val; }
                break;
            case CMP:
                if (!safe_ip(ip, 2, size)) return;
                { int r1 = code[ip++]; int r2 = code[ip++];
                  if (safe_reg(r1) && safe_reg(r2)) flag_zero = (regs[r1] == regs[r2]); }
                break;
            case CMPI:
                if (!safe_ip(ip, 2, size)) return;
                { int r1 = code[ip++]; int val = code[ip++];
                  if (safe_reg(r1)) flag_zero = (regs[r1] == val); }
                break;
            case JMP:
                if (!safe_ip(ip, 1, size)) return;
                { int target = code[ip++];
                  if (safe_jump(target, size)) ip = target; }
                break;
            case JZ:
                if (!safe_ip(ip, 1, size)) return;
                { int target = code[ip++];
                  if (flag_zero && safe_jump(target, size)) ip = target; }
                break;
            case JNZ:
                if (!safe_ip(ip, 1, size)) return;
                { int target = code[ip++];
                  if (!flag_zero && safe_jump(target, size)) ip = target; }
                break;
            case CALL:
                if (!safe_ip(ip, 1, size)) return;
                if (csp + 1 >= STACK_SIZE) {
                    fprintf(stderr, "ERROR: call stack overflow (%d)\n", STACK_SIZE);
                    return;
                }
                call_stack[++csp] = ip + 1;
                { int target = code[ip];
                  if (safe_jump(target, size)) ip = target; }
                break;
            case RET:
                if (csp < 0) {
                    fprintf(stderr, "ERROR: call stack underflow\n");
                    return;
                }
                ip = call_stack[csp--];
                break;
            case STORE:
                if (!safe_ip(ip, 2, size)) return;
                { int addr = code[ip++]; int r = code[ip++];
                  if (safe_addr(addr) && safe_reg(r)) memory[addr] = regs[r]; }
                break;
            case LOAD:
                if (!safe_ip(ip, 2, size)) return;
                { int r = code[ip++]; int addr = code[ip++];
                  if (safe_reg(r) && safe_addr(addr)) regs[r] = memory[addr]; }
                break;
            case DRAW:
                if (!safe_ip(ip, 3, size)) return;
                { int rx = code[ip++]; int ry = code[ip++]; int cr = code[ip++];
                  if (safe_reg(rx) && safe_reg(ry) && safe_reg(cr)) {
                      int x = regs[rx]; int y = regs[ry];
                      if (x >= 0 && x < VRAM_WIDTH && y >= 0 && y < VRAM_HEIGHT)
                          vram[y * VRAM_WIDTH + x] = regs[cr];
                  } }
                break;
            case PRINT:
                if (!safe_ip(ip, 1, size)) return;
                { int r = code[ip++];
                  if (safe_reg(r)) printf("OUT: %d\n", regs[r]); }
                break;
            case CLS:
                memset(vram, 0, sizeof(vram));
                break;
            case RAND:
                if (!safe_ip(ip, 2, size)) return;
                { int r = code[ip++]; int mod = code[ip++];
                  if (safe_reg(r)) regs[r] = mod > 0 ? rand() % mod : 0; }
                break;
            case KEY:
                if (!safe_ip(ip, 1, size)) return;
                { int r = code[ip++];
                  if (safe_reg(r)) {
                      struct timeval tv = {0, 0};
                      fd_set fds;
                      FD_ZERO(&fds);
                      FD_SET(STDIN_FILENO, &fds);
                      if (select(1, &fds, NULL, NULL, &tv) > 0) {
                          char c;
                          if (read(STDIN_FILENO, &c, 1) > 0)
                              regs[r] = (unsigned char)c;
                          else
                              regs[r] = -1;
                      } else {
                          regs[r] = -1;
                      }
                  } }
                break;
            case HALT:
                return;
            default:
                fprintf(stderr, "ERROR: unknown opcode %d at ip=%d\n", op, ip - 1);
                return;
        }
    }
}

int main(int argc, char** argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <bytecode.bin>\n", argv[0]);
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

    FILE *f = fopen(argv[1], "rb");
    if (!f) {
        fprintf(stderr, "ERROR: cannot open '%s'\n", argv[1]);
        return 1;
    }
    int code[4096];
    int size = (int)fread(code, sizeof(int), 4096, f);
    fclose(f);

    srand((unsigned int)time(NULL));

    run(code, size);

    struct stat out_st;
    if (lstat("output.ppm", &out_st) == 0 && S_ISLNK(out_st.st_mode)) {
        fprintf(stderr, "ERROR: output.ppm is a symlink, refusing to overwrite\n");
        return 1;
    }
    FILE *img = fopen("output.ppm", "wb");
    if (img) {
        fprintf(img, "P3\n%d %d\n255\n", VRAM_WIDTH, VRAM_HEIGHT);
        for (int i = 0; i < VRAM_WIDTH * VRAM_HEIGHT; i++) {
            fprintf(img, "%d %d %d ",
                (vram[i] >> 16) & 0xFF,
                (vram[i] >> 8) & 0xFF,
                vram[i] & 0xFF);
        }
        fclose(img);
    }
    return 0;
}
