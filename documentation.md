# TBVM — Tiny Basic Virtual Machine

Архитектура 32-битной стековой ВМ с 8 регистрами и графическим выводом.

---

## 1. Архитектура

| Компонент | Размер | Описание |
|-----------|--------|----------|
| Регистры | 8 (`r0`–`r7`) | 32-битные `int`, регистр общего назначения |
| Флаг нуля | 1 бит | Устанавливается `CMP`/`CMPI`, проверяется `JZ`/`JNZ` |
| RAM | 1024 слова | `int32_t memory[1024]`, адреса 0–1023 |
| Стек вызовов | 256 | Для `CALL`/`RET`, глубина до 255 вложенных |
| VRAM | 128×128 | Кадровый буфер, 16,384 пикселя |
| Размер слова | 32 бита | `int32_t`, little-endian |
| Макс. код (C) | 4096 слов (16 KB) | Статический массив в `vm.c` |
| Макс. код (Rust) | безлимитный | `Vec<i32>` |

Регистры хранят 32-битные целые со знаком (`int32_t`/`i32`).

---

## 2. Система команд (17 инструкций)

Все три реализации (`vm.c`, `vm.rs`, `assembler.py`) используют одни и те же числовые значения опкодов.

### 2.1 Пересылка данных

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `MOV rN val` | 1 | `N` (0–7), `val` (int32) | 3 | `regs[N] = val` |
| `STORE addr rN` | 13 | `addr` (0–1023), `N` (0–7) | 3 | `memory[addr] = regs[N]` |
| `LOAD rN addr` | 14 | `N` (0–7), `addr` (0–1023) | 3 | `regs[N] = memory[addr]` |

### 2.2 Арифметика

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `ADD rN rM` | 2 | `N`, `M` | 3 | `regs[N] += regs[M]` |
| `ADDI rN val` | 3 | `N`, `val` | 3 | `regs[N] += val` |
| `SUB rN rM` | 4 | `N`, `M` | 3 | `regs[N] -= regs[M]` |
| `SUBI rN val` | 5 | `N`, `val` | 3 | `regs[N] -= val` |

### 2.3 Сравнение

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `CMP rN rM` | 6 | `N`, `M` | 3 | `flag_zero = (regs[N] == regs[M])` |
| `CMPI rN val` | 7 | `N`, `val` | 3 | `flag_zero = (regs[N] == val)` |

### 2.4 Управление

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `HALT` | 0 | — | 1 | Останов выполнения |
| `JMP addr` | 8 | `addr` (индекс слова) | 2 | Безусловный переход |
| `JZ addr` | 9 | `addr` | 2 | Переход если `flag_zero == true` |
| `JNZ addr` | 10 | `addr` | 2 | Переход если `flag_zero == false` |
| `CALL addr` | 11 | `addr` | 2 | Push IP на стек; `ip = addr` |
| `RET` | 12 | — | 1 | Pop IP со стека |

### 2.5 Ввод-вывод

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `PRINT rN` | 16 | `N` | 2 | Вывод `OUT: <regs[N]>\n` в stdout |
| `DRAW rX rY rC` | 15 | `X`, `Y`, `C` | 4 | Пиксель `(regs[X], regs[Y])` = `regs[C]` |

Формат цвета в `DRAW`: `0x00RRGGBB`. Выход за 128×128 игнорируется. Результат сохраняется в `output.ppm`.

---

## 3. Бинарный формат

Little-endian 32-битные `int`, упакованные подряд. Каждая инструкция = опкод + N операндов.

```
[опкод] [операнд1] [операнд2] ... [операндN]
```

Пример разбора на Python:
```python
import struct
data = open("program.bin", "rb").read()
words = list(struct.unpack(f"<{len(data)//4}i", data))
```

Пример сборки вручную:
```python
import struct
code = [1, 0, 42,   # MOV r0 42
        16, 0,       # PRINT r0
        0]           # HALT
open("program.bin", "wb").write(struct.pack(f"<{len(code)}i", *code))
```

---

## 4. Язык ассемблера

### Регистры
`r0`, `r1`, `r2`, `r3`, `r4`, `r5`, `r6`, `r7` — регистронезависимые.

### Метки
Начинаются с `.` в начале строки:
```asm
.loop
JMP .loop
```

Все метки собираются перед эмишеном кода — forward-ссылки работают.

### Комментарии
`;` или `#` — от символа до конца строки:
```asm
; это комментарий
MOV r0 1  # тоже комментарий
```

### Разделитель строк
В Telegram-боте можно использовать `|`:
```
/asm MOV r0 1 | PRINT r0 | HALT
```

### Числа
Любые целые `int32` со знаком (в т.ч. отрицательные): `MOV r0 -42`.

### Полный пример
```asm
; Sum 1 to 10
MOV r0 10     ; counter
MOV r1 0      ; sum
.loop
ADD r1 r0
SUBI r0 1
CMPI r0 0
JNZ .loop
PRINT r1      ; → OUT: 55
HALT
```

---

## 5. API ассемблера (Python)

```python
from assembler import Assembler, AssembleError

asm = Assembler()

# Собрать
data = asm.assemble("MOV r0 42\nPRINT r0\nHALT")
# → bytes (little-endian int32)

# Дизассемблировать
text = asm.disassemble(data)
# → "  MOV r0 42\n  PRINT r0\n  HALT"

# Количество слов/байт
asm.describe(data)
# → "Instructions: 6 words / 24 bytes"
```

Исключения: `AssembleError` — неизвестная инструкция, дубликат метки, неверный регистр, плохое число.

---

## 6. Примеры программ

Счётчик 10→1 (`programs/countdown.s`):
```asm
MOV r0 10
.loop PRINT r0
SUBI r0 1
CMPI r0 0
JNZ .loop
HALT
```

Сумма 1..10 (`programs/math.s`):
```asm
MOV r0 10
MOV r1 0
.loop
ADD r1 r0
SUBI r0 1
CMPI r0 0
JNZ .loop
PRINT r1
HALT
```

Диагональная линия (`programs/demo.s`):
```asm
MOV r0 0     ; x
MOV r1 0     ; y
MOV r2 255   ; color (blue)
.loop
DRAW r0 r1 r2
ADDI r0 1
ADDI r1 1
CMPI r0 64
JNZ .loop
PRINT r0
HALT
```

---

## 7. CLI

### C VM (`vm.c`)
```
./vm program.bin
```
Читает до 4096 слов, исполняет, пишет `output.ppm`. Отказывается писать, если `output.ppm` — симлинк.

### C ISO Engine (`iso_engine.c`)
```
./iso_engine bytecode.bin /tmp/sandbox
```
Исполняет 4 опкода (HALT=0, MOV=1, PRINT=2, EXEC=3) в изолированном окружении.
`EXEC` хранит строчку  `sh -c` инлайн в байткоде и выполняет её в заданной директории.
Ограничения: 5s CPU, 32MB RAM. Поддержка Linux + Windows.

### Rust VM (`rust/target/release/tbvm`)
```
tbvm run program.bin         # полноценная ВМ (17 опкодов)
tbvm isolate program.bin dir # изолированный движок (4 опкода)
tbvm disasm program.bin      # дизассемблер
```

---

## 8. Telegram Bot

Два бота: основной `bot_aiogram.py` и легаси `bot.py`.

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие |
| `/help` | Справка по всем 17 инструкциям |
| `/asm <code>` | Собрать → `program.bin` + дизассемблер |
| `/run <code>` | Собрать + исполнить в песочнице (stdout + PPM) |
| `/example` | Пример countdown.bin |
| Загрузка `.s`/`.asm`/`.txt` | Ассемблирование файла |

Песочница `/run`: `TemporaryDirectory`, `setrlimit(RLIMIT_AS=64MB, RLIMIT_CPU=3s)`, таймаут 3s, лимит 5s на пользователя.

Порядок поиска бинарника ВМ:
1. `./tbvm run`
2. `./vm`
3. `rust/target/release/tbvm run`

---

## 9. Реализации

### C (`vm.c`)
- `int code[4096]` — статический массив инструкций
- `int regs[8]`, `int memory[1024]`, `int call_stack[256]`, `int vram[128][128]`
- Проверки границ: `safe_reg()`, `safe_addr()`, `safe_ip()`
- Ошибки: `fprintf(stderr, ...)` + `return`
- ⚠️ `fread` в `int*` — единственное небезопасное место

### Rust (`rust/src/vm.rs`)
- `enum Op` + `match` — гарантирует обработку всех опкодов
- `Result<VmError>` — все ошибки через `?`
- `Vec<i32>` — динамический размер кода
- `bool flag_zero`
- **Zero `unsafe`**

---

## 10. Сборка

```sh
make vm          # gcc vm.c → ./vm
make tbvm        # cargo build --release → ./tbvm
make iso_engine  # gcc iso_engine.c → ./iso_engine
make all         # всё выше
make clean       # удалить бинарники + output.ppm
```

---

## 11. Запуск тестов

```sh
python3 test_bot.py
```

33 теста: нормализация кода, rate-limit, ассемблер (все инструкции + ошибки), песочница (выполнение, таймаут, PPM, ошибки).

---

## 12. ISO Engine (изолированный движок)

Отдельная мини-ВМ для безопасного выполнения shell-команд.

| Опкод | Инструкция | Слов | Действие |
|-------|------------|------|----------|
| 0 | `HALT` | 1 | Останов |
| 1 | `MOV rN val` | 3 | `regs[N] = val` |
| 2 | `PRINT rN` | 2 | `REG[N] = ...` в stdout |
| 3 | `EXEC <string>` | 1 + ceil((N+1)/4) | `sh -c <string>` |

Строчка для `EXEC` хранится инлайн — ASCII-байты, упакованные в `int32_t`, с null-терминатором.

Формирование байткода `EXEC` на Python:
```python
import struct
cmd = "ls -la"
data = b""
data += struct.pack("<i", 3)  # opcode EXEC
# команда + null-терминатор, выровнено до 4 байт
cmd_bytes = cmd.encode() + b"\x00"
# добавить padding до кратности 4
while len(cmd_bytes) % 4:
    cmd_bytes += b"\x00"
for i in range(0, len(cmd_bytes), 4):
    data += struct.pack("<i", int.from_bytes(cmd_bytes[i:i+4], 'little'))
```
