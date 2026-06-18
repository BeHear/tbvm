# TBVM — Tiny Basic Virtual Machine

Экспериментальная виртуальная машина с минимальным набором инструкций, графическим выводом (128×128 VRAM, PPM) и ассемблером. Реализована на **C** и **Rust** — выбирай любой вариант.

## Возможности

- **8 регистров** (r0–r7), **1024 слова** памяти, **256 вызовов** стека
- **17 инструкций**: MOV, ADD/ADDI, SUB/SUBI, CMP/CMPI, JMP/JZ/JNZ, CALL/RET, STORE/LOAD, DRAW, PRINT, HALT
- **Графический вывод** 128×128 пикселей в PPM (портлет) через инструкцию DRAW
- **Rust VM** — type-safe, zero `unsafe`, гарантированная защита памяти на уровне компилятора
- **Изолированный движок** — Windows (Job Object) / Linux (setrlimit + fork)
- **Ассемблер** (Python) — превращает текст в байткод
- **Telegram бот** — создание программ прямо из мессенджера
- **[Документация](documentation.md)** — полный справочник по архитектуре ВМ

## Быстрый старт

```bash
# Сборка
make

# Ассемблирование
python3 -c "
from assembler import Assembler
a = Assembler()
data = a.assemble('MOV r0 42\\nPRINT r0\\nHALT')
open('program.bin', 'wb').write(data)
"

# C-VM
./vm program.bin

# Rust-VM (type-safe)
./tbvm run program.bin
```

## Инструкции

| Инструкция | Описание |
|-----------|----------|
| `HALT` | Останов |
| `MOV rN val` | rN = val |
| `ADD rN rM` | rN += regs[rM] |
| `ADDI rN val` | rN += val |
| `SUB rN rM` | rN -= regs[rM] |
| `SUBI rN val` | rN -= val |
| `CMP rN rM` | flag = (rN == rM) |
| `CMPI rN val` | flag = (rN == val) |
| `JMP addr` | Безусловный прыжок |
| `JZ addr` | Прыжок если flag == 1 |
| `JNZ addr` | Прыжок если flag == 0 |
| `CALL addr` | Вызов подпрограммы |
| `RET` | Возврат |
| `STORE addr rN` | memory[addr] = rN |
| `LOAD rN addr` | rN = memory[addr] |
| `DRAW rX rY rC` | Пиксель в (regs[rX], regs[rY]) цвета regs[rC] |
| `PRINT rN` | Вывод regs[rN] |

## Примеры

```asm
; Обратный отсчёт от 10 до 1
MOV r0 10
.loop
PRINT r0
SUBI r0 1
CMPI r0 0
JNZ .loop
HALT
```

```asm
; Сумма чисел от 1 до 10
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

```asm
; Диагональная линия (графика)
MOV r0 0
MOV r1 0
MOV r2 255
.loop
DRAW r0 r1 r2
ADDI r0 1
ADDI r1 1
CMPI r0 64
JNZ .loop
HALT
```

## Telegram бот

Позволяет ассемблировать программы в байткод TBVM прямо из Telegram и скачать `.bin` файл.

### Для новичков: пошаговая инструкция

**Шаг 1. Установи Python** (если ещё не установлен)

Проверь:
```bash
python3 --version
```
Должно быть Python 3.8 или новее. Если нет — скачай с [python.org](https://python.org).

**Шаг 2. Скачай проект**

```bash
git clone https://github.com/BeHear/tbvm.git
cd tbvm
```

**Шаг 3. Установи зависимости**

```bash
pip install -r requirements.txt
```
Эта команда установит библиотеку `python-telegram-bot`.

**Шаг 4. Создай бота в Telegram**

1. Открой Telegram, найди [@BotFather](https://t.me/BotFather)
2. Напиши `/newbot`
3. BotFather попросит имя — введи любое, например `TBVM Assembler`
4. Потом попросит username — введи что-то вроде `tbvm_assembler_bot`
5. Готово! BotFather пришлёт **токен** — строку вида `1234567890:ABCdefGHIjklmNOpqrsTUVwxyz`

**Шаг 5. Запусти бота**

```bash
export TBVM_BOT_TOKEN=1234567890:ABCdefGHIjklmNOpqrsTUVwxyz
python bot.py
```
Замени `1234567890:...` на свой токен.

**Шаг 6. Пользуйся**

Открой Telegram, найди своего бота и напиши `/start`.

### Команды бота

| Команда | Что делает |
|---------|-----------|
| `/start` | Приветствие |
| `/help` | Список всех инструкций с описанием |
| `/asm MOV r0 42 ; PRINT r0 ; HALT` | Собрать программу и получить `.bin` файл |
| `/example` | Пример программы (обратный отсчёт) |

### Пример использования в боте

Напиши боту:
```
/asm MOV r0 10 & .loop PRINT r0 & SUBI r0 1 & CMPI r0 0 & JNZ .loop & HALT
```
(символ `;` разделяет инструкции. В Telegram можно писать весь код в одну строку через `;` или отправлять многострочным сообщением.)

Бот вернёт файл `program.bin` — его можно запустить на VM:
```bash
./vm program.bin
```

## Rust VM

Реализация на Rust с нулевым `unsafe` кодом — все обращения к памяти, регистрам и стеку проверяются на этапе компиляции и рантайме.

```bash
# Сборка
make tbvm          # или: cargo build --release --manifest-path rust/Cargo.toml

# Исполнение
./tbvm run program.bin

# Дизассемблирование
./tbvm disasm program.bin

# Изолированный запуск (песочница)
./tbvm isolate program.bin /tmp/sandbox_dir
```

Отличия от C-VM:
- Векторный код вместо сырых массивов — никаких переполнений буфера
- `enum Op` с pattern matching — никаких switch без default
- `Result<T, VmError>` вместо fprintf — все ошибки возвращаются, а не печатаются
- `try_wait()` с таймаутом — корректное завершение процессов в песочнице

## Структура проекта

```
tbvm/
├── vm.c               # C VM (кросс-платформенная)
├── iso_engine.c       # C изолятор (Windows/Linux)
├── assembler.py       # Ассемблер/дизассемблер
├── bot.py             # Telegram бот
├── Makefile           # Сборка
├── rust/              # Rust VM
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs    # CLI (run, isolate, disasm)
│       ├── vm.rs      # VM engine (type-safe)
│       ├── sandbox.rs # Песочница (fork + setrlimit)
│       └── error.rs   # VmError
├── programs/          # Примеры программ
└── requirements.txt
```

## Лицензия

MIT
