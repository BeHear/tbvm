; Animated bouncing pixel demo — great for GIF export
MOV r0 0     ; x
MOV r1 0     ; y
MOV r2 1     ; dx
MOV r3 1     ; dy
MOV r4 255   ; color (blue)
.loop
DRAW r0 r1 r4  ; draw pixel
ADD r0 r2       ; x += dx
ADD r1 r3       ; y += dy
CMPI r0 127     ; bounce off right wall
JNZ .skip_x
MOV r2 -1
.skip_x
CMPI r0 0       ; bounce off left wall
JNZ .skip_x2
MOV r2 1
.skip_x2
CMPI r1 127     ; bounce off bottom wall
JNZ .skip_y
MOV r3 -1
.skip_y
CMPI r1 0       ; bounce off top wall
JNZ .skip_y2
MOV r3 1
.skip_y2
JMP .loop
