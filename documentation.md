# TBVM — Tiny Basic Virtual Machine

Архитектура 32-битной стековой ВМ с 8 регистрами и графическим выводом. Ядро написано на **Rust** (zero `unsafe`).

---

## 1. Архитектура

| Компонент | Размер | Описание |
|-----------|--------|----------|
| Регистры | 8 (`r0`–`r7`) | 32-битные `i32`, регистры общего назначения |
| Флаг нуля | 1 бит | Устанавливается `CMP`/`CMPI`, проверяется `JZ`/`JNZ` |
| RAM | 1024 слова | `memory[1024]`, адреса 0–1023 |
| Стек вызовов | 256 | Для `CALL`/`RET`, глубина до 255 вложенных |
| VRAM | 128×128 | Кадровый буфер, 16,384 пикселя |
| Размер слова | 32 бита | `i32`, little-endian |
| Макс. код | безлимитный | `Vec<i32>` |
| **Режимы** | 2 | **0=kernel, 1=user** (защищённые инструкции) |
| **IVT** | в памяти | Interrupt Vector Table, по умолчанию `memory[0..]` |
| **Стек прерываний** | 64 слова | Для INT/IRET (3 слова на фрейм) |
| **Таймер** | interval | Периодическое прерывание (INT 3) |

Регистры хранят 32-битные целые со знаком (`i32`).

---

## 2. Система команд (27 инструкций)

### 2.1 Пересылка данных

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `MOV rN val` | 1 | `N` (0–7), `val` (int32) | 3 | `regs[N] = val` |
| `STORE addr rN` | 13 | `addr` (0–1023), `N` (0–7) | 3 | `memory[addr] = regs[N]` |
| `LOAD rN addr` | 14 | `N` (0–7), `addr` (0–1023) | 3 | `regs[N] = memory[addr]` |
| `KEY rN` | 19 | `N` (0–7) | 2 | `regs[N]` = ASCII-код клавиши (блокирующий) |

### 2.2 Арифметика

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `ADD rN rM` | 2 | `N`, `M` | 3 | `regs[N] += regs[M]` |
| `ADDI rN val` | 3 | `N`, `val` | 3 | `regs[N] += val` |
| `SUB rN rM` | 4 | `N`, `M` | 3 | `regs[N] -= regs[M]` |
| `SUBI rN val` | 5 | `N`, `val` | 3 | `regs[N] -= val` |
| `RAND rN mod` | 18 | `N`, `mod` | 3 | `regs[N] = rand() % mod` |

### 2.3 Сравнение

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `CMP rN rM` | 6 | `N`, `M` | 3 | `flag_zero = (regs[N] == regs[M])` |
| `CMPI rN val` | 7 | `N`, `val` | 3 | `flag_zero = (regs[N] == val)` |

### 2.4 Управление

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `HALT` | 0 | — | 1 | Останов выполнения |
| `CLS` | 17 | — | 1 | Заливка VRAM чёрным |
| `JMP addr` | 8 | `addr` (индекс слова) | 2 | Безусловный переход |
| `JZ addr` | 9 | `addr` | 2 | Переход если `flag_zero == true` |
| `JNZ addr` | 10 | `addr` | 2 | Переход если `flag_zero == false` |
| `CALL addr` | 11 | `addr` | 2 | Push IP на стек; `ip = addr` |
| `RET` | 12 | — | 1 | Pop IP со стека |

### 2.5 Графика, случайные числа, ввод

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `PRINT rN` | 16 | `N` | 2 | Вывод `OUT: <regs[N]>\n` в stdout |
| `DRAW rX rY rC` | 15 | `X`, `Y`, `C` | 4 | Пиксель `(regs[X], regs[Y])` = `regs[C]` |
| `CLS` | 17 | — | 1 | Заливка VRAM чёрным (`0x000000`) |
| `RAND rN mod` | 18 | `N`, `mod` (int32) | 3 | `regs[N] = rand() % mod` |
| `KEY rN` | 19 | `N` | 2 | Ожидание клавиши → `regs[N]` = ASCII-код |

### 2.6 Системные инструкции (поддержка ОС)

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `INT vec` | 20 | `vec` (0–1023) | 2 | Программное прерывание |
| `IRET` | 21 | — | 1 | Возврат из прерывания |
| `CLI` | 22 | — | 1 | Запретить прерывания |
| `STI` | 23 | — | 1 | Разрешить прерывания |
| `SETMODE rN` | 24 | `N` (0–7) | 2 | `mode = regs[N]` (0=kernel, 1=user, только kernel) |
| `EXIT rN` | 25 | `N` (0–7) | 2 | Останов с кодом `regs[N]` |
| `TIMER n` | 26 | `n` | 2 | Установить интервал таймера (в инструкциях, 0=выкл) |

### 2.7 Механизм прерываний и режимы

**Режимы привилегий:**
- `mode = 0` — режим ядра (kernel). Доступны все инструкции.
- `mode = 1` — пользовательский режим (user). `SETMODE`, `TIMER` и `IRET` вызывают fault.

**IVT (Interrupt Vector Table):**
- Расположена в памяти, начиная с адреса `ivt_base` (по умолчанию 0).
- Каждый entry — одно слово: адрес обработчика (IP).
- Если адрес обработчика 0 или вне кода — `UnhandledInterrupt`.

**Стандартные векторы прерываний:**
| Вектор | Назначение |
|--------|------------|
| 0 | Invalid opcode fault |
| 1 | Privilege violation fault |
| 2 | Memory bounds fault |
| 3 | Timer interrupt |
| 4+ | Пользовательские (INT n) |

**Последовательность прерывания:**
1. Сохранить `ip`, `mode`, `int_enabled` на стек прерываний
2. Установить `mode = 0` (kernel), `int_enabled = false`
3. Загрузить `ip = memory[ivt_base + vector]`

**IRET:**
1. Восстановить `ip`, `mode`, `int_enabled` со стека прерываний
2. Доступна только в режиме ядра

**Double fault:** Если fault происходит в режиме ядра — ВМ останавливается с `DoubleFault` (kernel panic).

### 2.8 Пример загрузчика ОС

```asm
; Установка IVT
MOV r0 .fault_handler   ; вектор 0 — invalid opcode
STORE 0 r0
MOV r0 .timer_handler   ; вектор 3 — таймер
STORE 3 r0

; Настройка таймера (прерывание каждые 50 инструкций)
TIMER 50
STI                     ; разрешить прерывания

; Переключение в user mode
MOV r7 1
SETMODE r7

; Пользовательский код:
; ... (любые инструкции, защищённые от привилегированных)

.fault_handler
; Обработчик fault (kernel mode)
; ... логирование, завершение процесса
IRET

.timer_handler
; Обработчик таймера (kernel mode)
; ... переключение задач, планировщик
IRET
```

### 2.9 Примечания

- `KEY` блокирует выполнение до нажатия клавиши.
- В песочнице бота (`/run`) `KEY` всегда возвращает `-1` (stdin недоступен).
- `RAND` использует встроенный LCG (Rust).
- Все арифметические операции (`ADD`, `SUB` и т.д.) используют wrapping-арифметику (без panic при переполнении).
- Для работы ОС необходимо инициализировать IVT в памяти (например, `STORE` адреса обработчиков).

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

```
tbvm run program.bin         # полноценная ВМ (19 опкодов)
tbvm isolate program.bin dir # изолированный движок (4 опкода)
tbvm disasm program.bin      # дизассемблер
```

---

## 8. Telegram Bot

Два бота: основной `bot_aiogram.py` и легаси `bot.py`.

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие |
| `/help` | Справка по всем 19 инструкциям |
| `/asm <code>` | Собрать → `program.bin` + дизассемблер |
| `/run <code>` | Собрать + исполнить в песочнице (stdout + PPM) |
| `/example` | Пример countdown.bin |
| Загрузка `.s`/`.asm`/`.txt` | Ассемблирование файла |

Песочница `/run`: `TemporaryDirectory`, `setrlimit(RLIMIT_AS=64MB, RLIMIT_CPU=3s)`, таймаут 3s, лимит 5s на пользователя.

Порядок поиска бинарника ВМ:
1. `./tbvm run`
2. `rust/target/release/tbvm run`

---

## 9. Реализация (Rust)

- `enum Op` + `match` — гарантирует обработку всех опкодов
- `Result<VmError>` — все ошибки через `?`
- `Vec<i32>` — динамический размер кода
- **Zero `unsafe`**
- **Поддержка ОС**: режимы kernel/user, IVT, INT/IRET, таймер, fault-ы
- **wrapping_ арифметика**: ADD/SUB не вызывают panic при переполнении

---

## 10. Сборка

```sh
make           # cargo build --release → ./tbvm
make clean     # удалить бинарник + output.ppm
```

---

## 11. Запуск тестов

```sh
python3 test_bot.py
```

33+ теста: нормализация кода, rate-limit, ассемблер (все инструкции + ошибки), песочница (выполнение, таймаут, PPM, ошибки).

---

## 12. ISO Engine (изолированный движок)

Отдельная мини-ВМ для безопасного выполнения shell-команд (доступна через `tbvm isolate`).

| Опкод | Инструкция | Слов | Действие |
|-------|------------|------|----------|
| 0 | `HALT` | 1 | Останов |
| 1 | `MOV rN val` | 3 | `regs[N] = val` |
| 2 | `PRINT rN` | 2 | `REG[N] = ...` в stdout |
| 3 | `EXEC <string>` | 1 + ceil((N+1)/4) | `sh -c <string>` |

Строчка для `EXEC` хранится инлайн — ASCII-байты, упакованные в `i32`, с null-терминатором.

Формирование байткода `EXEC` на Python:
```python
import struct
cmd = "ls -la"
data = b""
data += struct.pack("<i", 3)  # opcode EXEC
cmd_bytes = cmd.encode() + b"\x00"
while len(cmd_bytes) % 4:
    cmd_bytes += b"\x00"
for i in range(0, len(cmd_bytes), 4):
    data += struct.pack("<i", int.from_bytes(cmd_bytes[i:i+4], 'little'))
```
