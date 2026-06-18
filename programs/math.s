; Sum of numbers 1 to 10
MOV r0 10    ; counter
MOV r1 0     ; sum
.loop
ADD r1 r0
SUBI r0 1
CMPI r0 0
JNZ .loop
PRINT r1
HALT
