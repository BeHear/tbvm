#include <stdio.h>
#include <stdlib.h>

#define VRAM_WIDTH 128
#define VRAM_HEIGHT 128

enum {
    HALT = 0, MOV, ADD, ADDI, SUB, SUBI, 
    CMP, CMPI, JMP, JZ, JNZ, 
    CALL, RET, STORE, LOAD, DRAW, PRINT
};

int regs[8];
int memory[1024];
int call_stack[256];
int csp = -1;
int flag_zero = 0;
int vram[VRAM_WIDTH * VRAM_HEIGHT];

void run(int* code, int size) {
    int ip = 0;
    while (ip < size) {
        int op = code[ip++];
        switch (op) {
            case MOV:  { int r = code[ip++]; regs[r] = code[ip++]; break; }
            case ADD:  { int r1 = code[ip++]; int r2 = code[ip++]; regs[r1] += regs[r2]; break; }
            case ADDI: { int r1 = code[ip++]; int val = code[ip++]; regs[r1] += val; break; } // Прибавить число
            case SUBI: { int r1 = code[ip++]; int val = code[ip++]; regs[r1] -= val; break; }
            case CMP:  { int r1 = code[ip++]; int r2 = code[ip++]; flag_zero = (regs[r1] == regs[r2]); break; }
            case CMPI: { int r1 = code[ip++]; int val = code[ip++]; flag_zero = (regs[r1] == val); break; } // Сравнить с числом
            case JMP:  { ip = code[ip++]; break; }
            case JZ:   { int target = code[ip++]; if (flag_zero) ip = target; break; }
            case JNZ:  { int target = code[ip++]; if (!flag_zero) ip = target; break; }
            case CALL: { call_stack[++csp] = ip + 1; ip = code[ip]; break; }
            case RET:  { ip = call_stack[csp--]; break; }
            case STORE: { int addr = code[ip++]; int r = code[ip++]; memory[addr] = regs[r]; break; }
            case LOAD:  { int r = code[ip++]; int addr = code[ip++]; regs[r] = memory[addr]; break; }
            case DRAW: {
                int x = regs[code[ip++]]; 
                int y = regs[code[ip++]]; 
                int color_reg = code[ip++]; // Берем номер регистра
                int color = regs[color_reg]; // Берем сам цвет из этого регистра
                if (x >= 0 && x < VRAM_WIDTH && y >= 0 && y < VRAM_HEIGHT)
                    vram[y * VRAM_WIDTH + x] = color;
                break;
            }
            case PRINT: { printf("OUT: %d\n", regs[code[ip++]]); break; }
            case HALT: return;
        }
    }
}

int main(int argc, char** argv) {
    if (argc < 2) return 1;
    FILE *f = fopen(argv[1], "rb");
    int code[4096];
    int size = fread(code, sizeof(int), 4096, f);
    fclose(f);
    run(code, size);
    FILE *img = fopen("output.ppm", "wb");
    fprintf(img, "P3\n%d %d\n255\n", VRAM_WIDTH, VRAM_HEIGHT);
    for (int i = 0; i < VRAM_WIDTH * VRAM_HEIGHT; i++) {
        fprintf(img, "%d %d %d ", (vram[i] >> 16) & 0xFF, (vram[i] >> 8) & 0xFF, vram[i] & 0xFF);
    }
    fclose(img);
    return 0;
}