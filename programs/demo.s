; Demo: draw diagonal line + count
MOV r0 0    ; x
MOV r1 0    ; y
MOV r2 255  ; color (blue)
.loop
DRAW r0 r1 r2
ADDI r0 1
ADDI r1 1
CMPI r0 64
JNZ .loop
PRINT r0
HALT
