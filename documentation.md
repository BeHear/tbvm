# TBVM — Telegram Bot Virtual Machine

Архитектура 32-битной виртуальной машины с 8 регистрами общего назначения, графическим выводом 128×128 и поддержкой привилегированных режимов (kernel/user). Ядро написано на **Rust** (zero `unsafe`). После выполнения программы кадровый буфер экспортируется в **PNG**.

---

## 1. Архитектура

### 1.1 Компоненты

| Компонент | Размер | Тип | Описание |
|-----------|--------|-----|----------|
| Регистры | 8 (`r0`–`r7`) | `i32` | Общего назначения |
| Флаг нуля | 1 бит | `bool` | Устанавливается `CMP`/`CMPI`, проверяется `JZ`/`JNZ` |
| RAM | 1024 слова | `[i32; 1024]` | Адресуемая память 0–1023 |
| Стек вызовов | 256 | `[usize; 256]` | Для `CALL`/`RET` (глубина до 255) |
| VRAM | 128×128 = 16 384 | `[i32; 16384]` | Кадровый буфер, пиксель = `0xRRGGBB` |
| Стек прерываний | 64 слова | `[usize; 64]` | Для `INT`/`IRET` (3 слова на фрейм) |
| IVT | В RAM | `memory[ivt_base..]` | Interrupt Vector Table |
| Таймер | 1 счётчик | 2× `i32` | Периодическое прерывание INT 3 |
| Размер слова | 32 бита | `i32` | Little-endian |
| Размер кода | Неограничен | `Vec<i32>` | Динамический |

### 1.2 Регистры

Все 8 регистров (`r0`–`r7`) 32-битные знаковые. Используются для хранения данных, адресов, цветов. Регистр `r7` может использоваться для передачи аргументов в обработчики прерываний (по соглашению).

### 1.3 VRAM и цвет

VRAM — одномерный массив из 16 384 элементов `i32`. Каждый элемент кодирует цвет пикселя:

```
0xRRGGBB
  └┬┘└┬┘└┬┘
  red grn blu
```

- `0xFF0000` — красный
- `0x00FF00` — зелёный
- `0x0000FF` — синий
- `0xFFFFFF` — белый
- `0x000000` — чёрный (значение по умолчанию после CLS)

Пиксель `(x, y)` находится в `vram[y * 128 + x]`.

### 1.4 Экспорт в PNG

После выполнения `Vm::run()` кадровый буфер экспортируется в PNG через `write_png()` / `write_png_file()`. Используется библиотека `image` (crate `image = "0.25"`), кодировщик `PngEncoder`. На выходе — полноценный PNG размером 128×128 пикселей, 24-bit RGB.

PNG записывается в файл `output.png` (CLI) или возвращается как `bytes` (Telegram бот).

---

## 2. Система команд (26 инструкций)

### 2.1 Пересылка данных

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `MOV rN val` | 1 | `N` (0–7), `val` (int32) | 3 | `regs[N] = val` |
| `STORE addr rN` | 13 | `addr` (0–1023), `N` (0–7) | 3 | `memory[addr] = regs[N]` |
| `LOAD rN addr` | 14 | `N` (0–7), `addr` (0–1023) | 3 | `regs[N] = memory[addr]` |
| `KEY rN` | 19 | `N` (0–7) | 2 | Чтение ASCII-кода клавиши (блокирующее) |

### 2.2 Арифметика

Арифметика **wrapping** — переполнение не приводит к panic (семантика Rust `wrapping_add`/`wrapping_sub`).

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `ADD rN rM` | 2 | `N`, `M` | 3 | `regs[N] += regs[M]` |
| `ADDI rN val` | 3 | `N`, `val` | 3 | `regs[N] += val` |
| `SUB rN rM` | 4 | `N`, `M` | 3 | `regs[N] -= regs[M]` |
| `SUBI rN val` | 5 | `N`, `val` | 3 | `regs[N] -= val` |
| `RAND rN mod` | 18 | `N`, `mod` | 3 | `regs[N] = LCG_rand() % mod` |

#### Генератор случайных чисел

Используется встроенный LCG (Linear Congruential Generator):

```
state = state.wrapping_mul(1103515245).wrapping_add(12345)
result = (state >> 16) as i32 % mod
```

Начальное состояние — количество наносекунд с UNIX epoch.

### 2.3 Сравнение

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `CMP rN rM` | 6 | `N`, `M` | 3 | `flag_zero = (regs[N] == regs[M])` |
| `CMPI rN val` | 7 | `N`, `val` | 3 | `flag_zero = (regs[N] == val)` |

### 2.4 Управление потоком

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `HALT` | 0 | — | 1 | Останов с кодом 0 |
| `JMP addr` | 8 | `addr` (индекс слова) | 2 | `ip = addr` |
| `JZ addr` | 9 | `addr` | 2 | `ip = addr` если `flag_zero == true` |
| `JNZ addr` | 10 | `addr` | 2 | `ip = addr` если `flag_zero == false` |
| `CALL addr` | 11 | `addr` | 2 | Push `ip` на стек; `ip = addr` |
| `RET` | 12 | — | 1 | Pop `ip` со стека |
| `EXIT rN` | 25 | `N` (0–7) | 2 | Останов с кодом `regs[N]` |

**Ошибки стека:**
- `StackOverflow` — если `CALL` при `sp >= STACK_SIZE` (256)
- `StackUnderflow` — если `RET` при `sp == 0`

### 2.5 Графика

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `DRAW rX rY rC` | 15 | `X`, `Y`, `C` | 4 | Пиксель `(regs[X], regs[Y])` = `regs[C]` |
| `CLS` | 17 | — | 1 | Заливка VRAM чёрным (`0x000000`) |
| `PRINT rN` | 16 | `N` | 2 | Вывод `OUT: <regs[N]>\n` |

**DRAW:**
- Если `x < 0 || x >= 128 || y < 0 || y >= 128` — пиксель не рисуется (без ошибки)
- Цвет берётся из `regs[rc]`, формат `0xRRGGBB`
- Размер: 4 слова (опкод + 3 регистра)

### 2.6 Системные инструкции (поддержка ОС)

| Инструкция | Опкод | Операнды | Слов | Действие |
|------------|-------|----------|------|----------|
| `INT vec` | 20 | `vec` (0–255) | 2 | Программное прерывание |
| `IRET` | 21 | — | 1 | Возврат из прерывания |
| `CLI` | 22 | — | 1 | Запретить прерывания (`int_enabled = false`) |
| `STI` | 23 | — | 1 | Разрешить прерывания (`int_enabled = true`) |
| `SETMODE rN` | 24 | `N` (0–7) | 2 | `mode = regs[N]` (0=kernel, 1=user) |
| `TIMER n` | 26 | `n` | 2 | Интервал таймера в инструкциях (0 = выкл) |

### 2.7 Механизм прерываний и режимы

#### Режимы привилегий

| Режим | Значение | Доступные инструкции |
|-------|----------|---------------------|
| Kernel | `mode = 0` | Все |
| User | `mode = 1` | Все, кроме `SETMODE`, `TIMER`, `IRET` |

Попытка выполнить привилегированную инструкцию в user-mode вызывает fault (вектор 1).

#### IVT (Interrupt Vector Table)

Таблица векторов прерываний располагается в памяти, начиная с `ivt_base` (по умолчанию 0). Каждый entry — одно слово `i32`: адрес обработчика в коде (IP).

```
memory[ivt_base + vec] = handler_ip
```

Если `handler_ip == 0` или `handler_ip >= code.len()` — `UnhandledInterrupt`.

#### Стандартные векторы

| Вектор | Назначение | Генерируется |
|--------|------------|-------------|
| 0 | Invalid opcode fault | При неизвестном опкоде |
| 1 | Privilege violation fault | При привилегированной инструкции в user-mode |
| 2 | Memory bounds fault | Зарезервирован |
| 3 | Timer interrupt | Автоматически при срабатывании таймера |
| 4+ | Пользовательские | По `INT n` |

#### Последовательность прерывания

1. Сохранить `ip`, `mode`, `int_enabled` на стек прерываний (3 слова)
2. Установить `mode = 0` (kernel), `int_enabled = false`
3. Загрузить `ip = memory[ivt_base + vector]`

#### IRET

1. Восстановить `ip`, `mode`, `int_enabled` со стека прерываний
2. Доступна только в режиме ядра (иначе fault 1)

#### Double Fault

Если fault происходит при `mode == 0` (kernel) — ВМ немедленно останавливается с ошибкой `DoubleFault`. Это аналог kernel panic.

#### Таймер

Счётчик увеличивается после каждой инструкции, если `int_enabled && timer_interval > 0`. При достижении `timer_interval` счётчик сбрасывается и генерируется прерывание INT 3 (если в IVT есть обработчик).

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

### 2.9 Примечания по инструкциям

| Инструкция | Особенности |
|------------|------------|
| `KEY` | Блокирует выполнение до нажатия клавиши. В песочнице `/run` всегда возвращает `-1` (stdin недоступен) |
| `RAND` | LCG, начальное состояние от наносекунд системного времени |
| `ADD`/`SUB` | Wrapping-арифметика (без panic при переполнении) |
| `DRAW` | Выход за границы (x/y вне 0..127) игнорируется |
| `INT` | `vec` проверяется на `vec < 256`; `ivt_base + vec` не должен выходить за `MEM_SIZE` |
| `TIMER` | Доступна только в режиме kernel, иначе fault 1 |

---

## 3. Бинарный формат

Little-endian 32-битные `i32`, упакованные подряд. Каждая инструкция кодируется как опкод, за которым следуют операнды:

```
[опкод] [операнд1] [операнд2] ... [операндN]
```

| Инструкция | Байткод (LE i32) |
|------------|------------------|
| `HALT` | `00 00 00 00` |
| `MOV r0 42` | `01 00 00 00` `00 00 00 00` `2A 00 00 00` |
| `PRINT r0` | `10 00 00 00` `00 00 00 00` |

API для ручной сборки на Python:

```python
import struct
code = [1, 0, 42,   # MOV r0 42
        16, 0,       # PRINT r0
        0]           # HALT
open("program.bin", "wb").write(struct.pack(f"<{len(code)}i", *code))
```

Чтение существующего байткода:

```python
import struct
data = open("program.bin", "rb").read()
words = list(struct.unpack(f"<{len(data)//4}i", data))
```

Валидация:
- Размер файла должен быть кратен 4
- Максимальный размер байткода: 4 MiB (`MAX_BYTECODE_SIZE`)

---

## 4. Язык ассемблера

### 4.1 Синтаксис

```
[метка:] <инструкция> [операнды]
```

### 4.2 Регистры

`r0`–`r7`, регистронезависимые: `r0`, `R0`, `R5` — всё корректно.

### 4.3 Метки

Начинаются с `.` в начале строки:

```asm
.loop
JMP .loop
```

- Все метки собираются перед эмишеном кода (двухпроходный ассемблер)
- Forward-ссылки работают (можно прыгать на метку ниже по коду)
- Дубликат метки → `AssembleError`

### 4.4 Комментарии

`;` или `#` — от символа до конца строки:

```asm
; это комментарий
MOV r0 1  # тоже комментарий
MOV r1 2 ; и это комментарий
```

### 4.5 Разделитель строк

В Telegram-боте можно использовать `|` вместо перевода строки:

```
/asm MOV r0 1 | PRINT r0 | HALT
```

### 4.6 Числа

Любые целые `int32` со знаком: `42`, `-42`, `0xFF`, `0b1010`.

### 4.7 Полный пример

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

### 4.8 Сборка вручную

```python
from assembler import Assembler

asm = Assembler()
data = asm.assemble("MOV r0 42\nPRINT r0\nHALT")
open("program.bin", "wb").write(data)
```

---

## 5. API ассемблера (Python)

```python
from assembler import Assembler, AssembleError

asm = Assembler()

# Собрать текст в байткод
data = asm.assemble("MOV r0 42\nPRINT r0\nHALT")
# → bytes (little-endian int32)

# Дизассемблировать байткод в текст
text = asm.disassemble(data)
# → "  MOV r0 42\n  PRINT r0\n  HALT"

# Описание: количество слов и байт
asm.describe(data)
# → "Instructions: 6 words / 24 bytes"
```

**Исключения `AssembleError`:**
- Неизвестная инструкция
- Неверный регистр (`r9` и т.п.)
- Неверное количество операндов
- Некорректное число
- Дубликат метки
- Неизвестная метка (forward-ссылка не нашлась)

---

## 6. Примеры программ

### 6.1 Счётчик 10→1 (`programs/countdown.s`)

```asm
; Countdown from 10 to 1
MOV r0 10
.loop
PRINT r0
SUBI r0 1
CMPI r0 0
JNZ .loop
HALT
```

Вывод:
```
OUT: 10
OUT: 9
...
OUT: 1
```

### 6.2 Сумма 1..10 (`programs/math.s`)

```asm
; Sum of 1 to 10
MOV r0 10     ; counter
MOV r1 0      ; accumulator
.loop
ADD r1 r0
SUBI r0 1
CMPI r0 0
JNZ .loop
PRINT r1
HALT
```

Вывод: `OUT: 55`

### 6.3 Диагональная линия (`programs/demo.s`)

```asm
; Diagonal line — draws 64 pixels
MOV r0 0       ; x
MOV r1 0       ; y
MOV r2 255     ; color: 0x0000FF (blue)
.loop
DRAW r0 r1 r2
ADDI r0 1
ADDI r1 1
CMPI r0 64
JNZ .loop
PRINT r0
HALT
```

После выполнения: `output.png` — синяя диагональ (0,0)–(63,63) на чёрном фоне.

### 6.4 RGB-палитра

```asm
; Draw 3 colour lines
MOV r0 0
MOV r1 0
.loop_r
MOV r2 0xFF0000    ; red
DRAW r0 r1 r2
ADDI r0 1
CMPI r0 128
JNZ .loop_r

MOV r0 0
MOV r1 42
.loop_g
MOV r2 0x00FF00    ; green
DRAW r0 r1 r2
ADDI r0 1
CMPI r0 128
JNZ .loop_g

MOV r0 0
MOV r1 84
.loop_b
MOV r2 0x0000FF    ; blue
DRAW r0 r1 r2
ADDI r0 1
CMPI r0 128
JNZ .loop_b

HALT
```

После выполнения: `output.png` — три горизонтальные линии (red, green, blue).

---

## 7. CLI

### 7.1 Использование

```
tbvm run program.bin              # Полноценная ВМ (26 инструкций)
tbvm isolate program.bin dir/     # Изолированный движок (4 инструкции)
tbvm disasm program.bin           # Дизассемблер
```

### 7.2 Команда `run`

1. Читает байткод из файла (макс. 4 MiB)
2. Создаёт экземпляр `Vm` и выполняет `vm.run()`
3. После выполнения экспортирует VRAM в `output.png` (если были вызовы DRAW/CLS)
4. Выводит код возврата (если != 0)

Защита: файл `output.png` создаётся с флагом `O_NOFOLLOW` (symlink-атаки).

### 7.3 Команда `disasm`

Дизассемблирует байткод в человекочитаемый ассемблерный листинг:

```
  MOV r0 10
.loop
  PRINT r0
  SUBI r0 1
  CMPI r0 0
  JNZ .loop
  HALT
```

### 7.4 Команда `isolate`

Мини-движок для безопасного выполнения shell-команд. Поддерживает только 4 инструкции:

| Опкод | Инструкция | Слов | Действие |
|-------|------------|------|----------|
| 0 | `HALT` | 1 | Останов |
| 1 | `MOV rN val` | 3 | `regs[N] = val` |
| 2 | `PRINT rN` | 2 | Печать `REG[N] = ...` |
| 3 | `EXEC <string>` | 1 + ceil((N+1)/4) | `sh -c <string>` |

Исполнение команды происходит через `sandbox::run_isolated()` с `fork()` и `setrlimit()`.

---

## 8. Telegram Bot

### 8.1 Архитектура

- **Основной бот**: `bot_aiogram.py` (aiogram 3.x, async)
- **Легаси**: `bot.py` (python-telegram-bot, синхронный)

### 8.2 Команды

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие |
| `/help` | Справка по всем инструкциям |
| `/asm <code>` | Собрать → `program.bin` |
| `/run <code>` | Собрать + выполнить в песочнице (stdout + PNG) |
| `/example` | Пример countdown.bin |
| Загрузка `.s`/`.asm`/`.txt` | Ассемблирование файла |

### 8.3 Песочница `/run`

```
TemporaryDirectory → tbvm run → чтение output.png
```

**Ограничения:**
- `RLIMIT_AS` = 64 MB
- `RLIMIT_CPU` = 3 секунды
- Таймаут выполнения: 3 секунды
- Рейт-лимит: 5 секунд между вызовами на пользователя

**Защита:**
- `preexec_fn=_setrlimit` — ресурсы ограничиваются до fork
- Чтение `output.png` через `O_NOFOLLOW` + `stat S_ISREG`
- Максимальный размер PNG: 512 KB
- `ProcessLookupError` при kill после таймаута

**Поток данных:**
1. Ассемблирование кода в `bytes`
2. Запись во `TemporaryDirectory` как `program.bin`
3. Запуск `tbvm run program.bin` в `cwd=tmpdir`
4. Чтение `output.png` из `tmpdir`
5. Отправка пользователю: stdout + PNG (если есть)

### 8.4 Поиск бинарника ВМ

```
1. rust/target/release/tbvm run
2. ./tbvm run
```

---

## 9. Реализация (Rust)

### 9.1 Модули

| Файл | Назначение |
|------|-----------|
| `vm.rs` | VM engine: 26 инструкций, VRAM, PNG-экспорт |
| `main.rs` | CLI: `run`, `isolate`, `disasm` |
| `sandbox.rs` | Изолированное выполнение через `fork()` + `setrlimit` |
| `error.rs` | `VmError` — все типы ошибок ВМ |

### 9.2 VM engine (`vm.rs`)

- `enum Op` + `match` — гарантирует обработку всех 26 опкодов (компилятор проверяет)
- `Result<VmError>` — все ошибки пробрасываются через `?`
- `Vec<i32>` — динамический размер кода
- Zero `unsafe` — type-safe гарантии

**Rust-специфика:**
- `wrapping_mul` / `wrapping_add` / `wrapping_sub` — без panic
- `Read` / `Write` трейты — для KEY (stdin) и PNG-экспорта
- `libc::O_NOFOLLOW` — защита от symlink при записи output

### 9.3 PNG-экспорт

Зависимость: `image = "0.25"` (crates.io).

```rust
// encode_png_inner — конвертирует VRAM [i32; 16384] в PNG bytes
fn encode_png_inner(&self) -> std::io::Result<Vec<u8>> {
    use image::RgbImage;
    use std::io::Cursor;

    let mut img = RgbImage::new(128, 128);
    for (i, &p) in self.vram.iter().enumerate() {
        let x = (i % 128) as u32;
        let y = (i / 128) as u32;
        img.put_pixel(x, y, image::Rgb([
            ((p >> 16) & 0xFF) as u8,
            ((p >> 8) & 0xFF) as u8,
            (p & 0xFF) as u8,
        ]));
    }

    let mut buf = Cursor::new(Vec::new());
    img.write_to(&mut buf, image::ImageFormat::Png)?;
    Ok(buf.into_inner())
}
```

### 9.4 VmError

```rust
pub enum VmError {
    OutOfCode,
    InvalidOpcode(i32, usize),
    InvalidRegister(usize),
    InvalidMemory(usize),
    InvalidJump(usize, usize),
    StackOverflow,
    StackUnderflow,
    InvalidInterrupt(usize),
    IntStackOverflow,
    IntStackUnderflow,
    UnhandledInterrupt(usize),
    InvalidMode(i32),
    DoubleFault(usize),
}
```

---

## 10. Сборка

```bash
make                 # cargo build --release → ./tbvm
make clean           # удалить бинарник + output.png
```

### Зависимости

| Крипт | Назначение |
|-------|-----------|
| `libc = "0.2"` | `O_NOFOLLOW`, `setrlimit`, `RLIMIT_*` |
| `image = "0.25"` | PNG-кодирование (PngEncoder) |

### Системные требования

- Rust nightly (используется `custom_flags` из `std::os::unix`)
- `libc` (есть на любом Linux)
- Python 3.10+ для ассемблера и бота

---

## 11. Запуск тестов

```bash
python3 test_bot.py
```

42 теста (все проходят):

| Категория | Количество | Что проверяет |
|-----------|-----------|---------------|
| `_normalize_code` | 8 | Разделители `\|`, комментарии `;`/`#`, пустые строки |
| `_check_rate_limit` | 4 | Рейт-лимит, сброс, разные пользователи |
| Ассемблер | 16 | Все инструкции, ошибки, round-trip, метки, long/neg/zero |
| Песочница | 10 | Выполнение, таймаут, PNG, stderr, countdown, RAND, KEY |
| CLS/RAND/KEY | 4 | Кодирование, round-trip, ошибки |

---

## 12. ISO Engine (изолированный движок)

Отдельная мини-ВМ безопасного выполнения shell-команд. Доступна через `tbvm isolate`.

### Система команд

| Опкод | Инструкция | Слов | Действие |
|-------|------------|------|----------|
| 0 | `HALT` | 1 | Останов |
| 1 | `MOV rN val` | 3 | `regs[N] = val` |
| 2 | `PRINT rN` | 2 | `REG[N] = ...` в stdout |
| 3 | `EXEC <string>` | 1 + ceil((N+1)/4) | `sh -c <string>` |

### Формат EXEC

Строка команды хранится инлайн, ASCII-байты упакованы в `i32` (little-endian), null-терминирована, дополнена нулями до кратности 4.

```python
import struct
cmd = "ls -la"
data = struct.pack("<i", 3)  # opcode EXEC
cmd_bytes = cmd.encode() + b"\x00"
while len(cmd_bytes) % 4:
    cmd_bytes += b"\x00"
for i in range(0, len(cmd_bytes), 4):
    data += struct.pack("<i", int.from_bytes(cmd_bytes[i:i+4], 'little'))
```

### Выполнение

`sandbox::run_isolated(command, dir)` — `fork()` + `setrlimit()`, выполнение в указанной директории. Аргумент `dir` должен быть каноническим путём (`fs::canonicalize`).
