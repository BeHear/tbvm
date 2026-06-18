import asyncio
import io
import logging
import os
import tempfile
import time

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message

from assembler import Assembler, AssembleError

TOKEN = os.environ.get("TBVM_BOT_TOKEN", "")
asm = Assembler()

HELP_TEXT = """\
🤖 <b>TBVM Assembler Bot</b>

Преобразует текст программы в байткод для Tiny Basic VM.

<b>Команды:</b>
/asm &lt;код&gt; — собрать программу, получить .bin
/run &lt;код&gt; — собрать и выполнить в песочнице
/help — список инструкций
/example — пример программы
📁 Загрузи .s / .asm / .txt файл — получу .bin

<b>Инструкции:</b>
<code>HALT</code> — останов
<code>MOV rN val</code> — rN = val
<code>ADD rN rM</code> — rN += regs[rM]
<code>ADDI rN val</code> — rN += val
<code>SUB rN rM</code> — rN -= regs[rM]
<code>SUBI rN val</code> — rN -= val
<code>CMP rN rM</code> — flag = (rN == rM)
<code>CMPI rN val</code> — flag = (rN == val)
<code>JMP addr</code> — прыжок
<code>JZ addr</code> — прыжок если flag
<code>JNZ addr</code> — прыжок если !flag
<code>CALL addr</code> — вызов подпрограммы
<code>RET</code> — возврат
<code>STORE addr rN</code> — memory[addr] = rN
<code>LOAD rN addr</code> — rN = memory[addr]
<code>DRAW rX rY rC</code> — пиксель (regs[rX], regs[rY]) цвета regs[rC]
<code>PRINT rN</code> — вывод regs[rN]
<code>CLS</code> — очистка экрана
<code>RAND rN val</code> — rN = случайное число (0..val-1)
<code>KEY rN</code> — чтение клавиши (ASCII) в rN

<b>Синтаксис:</b>
Метки: <code>.имя</code>
Комментарии: <code>;</code> или <code>#</code>
Регистры: <code>r0</code>-<code>r7</code>
Разделитель строк: <code>|</code>"""

EXAMPLE_CODE = """\
; Countdown from 10 to 1
MOV r0 10
.loop
PRINT r0
SUBI r0 1
CMPI r0 0
JNZ .loop
HALT"""

def _normalize_code(raw: str) -> str:
    """Split inline `|` separators; preserve `;` and `#` as comments only."""
    return raw.replace("|", "\n")
MAX_FILE_SIZE = 64 * 1024

# ── Sandboxed VM execution ──────────────────────────────────────────

VM_CMD = None
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
for _bin, _args in [
    (os.path.join(_SCRIPT_DIR, "tbvm"), ["run"]),
    (os.path.join(_SCRIPT_DIR, "vm"), []),
    (os.path.join(_SCRIPT_DIR, "rust/target/release/tbvm"), ["run"]),
]:
    if os.path.isfile(_bin):
        VM_CMD = [_bin] + _args
        break

SANDBOX_TIMEOUT = 3.0
SANDBOX_MEMORY = 64 * 1024 * 1024
SANDBOX_CPU = 3

_last_run: dict[int, float] = {}
RATE_LIMIT_SEC = 5


def _setrlimit():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (SANDBOX_MEMORY, SANDBOX_MEMORY))
        resource.setrlimit(resource.RLIMIT_CPU, (SANDBOX_CPU, SANDBOX_CPU))
    except (ImportError, RuntimeError):
        pass


async def _run_sandboxed(data: bytes) -> dict:
    with tempfile.TemporaryDirectory(prefix="tbvm_") as tmpdir:
        bin_path = os.path.join(tmpdir, "program.bin")
        with open(bin_path, "wb") as f:
            f.write(data)

        proc = await asyncio.create_subprocess_exec(
            *VM_CMD, bin_path,
            cwd=tmpdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=_setrlimit if os.name != "nt" else None,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=SANDBOX_TIMEOUT,
            )
            timed_out = False
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            stdout, stderr = b"", b""
            timed_out = True

        ppm_data = None
        ppm_path = os.path.join(tmpdir, "output.ppm")
        if os.path.isfile(ppm_path):
            sz = os.path.getsize(ppm_path)
            if 0 < sz < 512 * 1024:
                ppm_data = open(ppm_path, "rb").read()

        return {
            "stdout": stdout,
            "stderr": stderr,
            "timeout": timed_out,
            "ppm": ppm_data,
        }


def _check_rate_limit(user_id: int) -> int | None:
    now = time.monotonic()
    last = _last_run.get(user_id)
    if last is not None:
        remaining = RATE_LIMIT_SEC - (now - last)
        if remaining > 0:
            return int(remaining) + 1
    _last_run[user_id] = now
    return None


# ── Handlers ────────────────────────────────────────────────────────

dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    prefix = "🏃 /run тоже работает!" if VM_CMD else "ℹ️ Собери проект (<code>make</code>) чтобы использовать /run"
    await message.answer(
        "🤖 <b>TBVM Assembler Bot</b>\n\n"
        "Ассемблирует программы для Tiny Basic Virtual Machine.\n\n"
        "<code>/help</code> — справка\n"
        "<code>/asm MOV r0 42 | PRINT r0 | HALT</code> — собрать\n"
        "<code>/run MOV r0 42 | PRINT r0 | HALT</code> — собрать и выполнить\n"
        "<code>/example</code> — пример\n\n"
        f"{prefix}\n\n"
        "📁 <b>Загрузи</b> <code>.s</code> / <code>.asm</code> / <code>.txt</code> файл — получу <code>.bin</code>",
    )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@dp.message(Command("example"))
async def cmd_example(message: Message) -> None:
    data = asm.assemble(EXAMPLE_CODE)
    dis = asm.disassemble(data)
    await message.answer_document(
        document=BufferedInputFile(data, filename="countdown.bin"),
        caption=f"📄 Обратный отсчёт от 10 ({len(data)} bytes)",
    )
    if len(dis) < 3500:
        await message.answer(f"<b>Исходник:</b>\n<pre>{EXAMPLE_CODE.strip()}</pre>\n<b>Байткод:</b>\n<pre>{dis}</pre>")


@dp.message(Command("asm"))
async def cmd_asm(message: Message, command: CommandObject) -> None:
    args = command.args
    if not args:
        await message.answer(
            "Использование: <code>/asm MOV r0 42 | PRINT r0 | HALT</code>\n"
            "Можно разделять строки через <code>|</code> или многострочным сообщением."
        )
        return

    code = _normalize_code(args)
    try:
        data = asm.assemble(code)
        dis = asm.disassemble(data)
        caption = f"✅ Собрано: {len(data)} bytes ({len(data)//4} instructions)"
        await message.answer_document(
            document=BufferedInputFile(data, filename="program.bin"),
            caption=caption,
        )
        if len(dis) < 3500:
            await message.answer(f"<pre>{dis}</pre>")
    except AssembleError as e:
        await message.answer(f"❌ {e}")
    except Exception as e:
        await message.answer(f"❌ Internal error: {e}")


@dp.message(Command("run"))
async def cmd_run(message: Message, command: CommandObject) -> None:
    if not VM_CMD:
        await message.answer(
            "❌ VM бинарник не найден.\n"
            "Собери проект на сервере: <code>make</code> или <code>make tbvm</code>"
        )
        return

    args = command.args
    if not args:
        await message.answer(
            "Использование: <code>/run MOV r0 42 | PRINT r0 | HALT</code>\n\n"
            "Собирает и сразу выполняет программу в изолированной среде."
        )
        return

    remaining = _check_rate_limit(message.from_user.id)
    if remaining is not None:
        await message.answer(f"⏳ Подожди {remaining}с перед следующим запуском")
        return

    code = _normalize_code(args)
    try:
        data = asm.assemble(code)
    except AssembleError as e:
        await message.answer(f"❌ {e}")
        return

    msg = await message.answer("⏳ Собираю и выполняю...")

    result = None
    try:
        result = await _run_sandboxed(data)
    except FileNotFoundError:
        await msg.edit_text("❌ VM бинарник не найден по пути: " + " ".join(VM_CMD))
        return
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка выполнения: {e}")
        return

    lines = []
    if result["timeout"]:
        lines.append("⏰ Программа превысила лимит и была остановлена.")

    stdout = result["stdout"].decode("utf-8", errors="replace").strip()
    stderr = result["stderr"].decode("utf-8", errors="replace").strip()

    if stdout:
        lines.append(f"<b>Вывод:</b>\n<pre>{stdout}</pre>")
    if stderr:
        lines.append(f"<b>Stderr:</b>\n<pre>{stderr}</pre>")

    if not lines:
        lines.append("✅ Программа выполнена (нет вывода на PRINT)")

    text = "\n\n".join(lines)
    if len(text) > 4096:
        text = text[:4093] + "..."

    await msg.edit_text(text)

    if result["ppm"]:
        await message.answer_document(
            document=BufferedInputFile(result["ppm"], filename="output.ppm"),
            caption="🖼 VRAM (PPM)",
        )


@dp.message(F.document)
async def handle_file(message: Message, bot: Bot) -> None:
    doc = message.document
    if not doc or not doc.file_name:
        return

    ext = os.path.splitext(doc.file_name)[1].lower()
    if ext not in SUPPORTED_EXT:
        await message.answer(f"❌ Поддерживаются только: {', '.join(SUPPORTED_EXT)}")
        return

    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await message.answer(f"❌ Файл слишком большой (макс. {MAX_FILE_SIZE // 1024} KB)")
        return

    msg = await message.answer("⏳ Ассемблирую...")
    try:
        file = await bot.get_file(doc.file_id)
        raw = await bot.download_file(file.file_path)
        code = raw.read().decode("utf-8")
    except Exception:
        await msg.edit_text("❌ Не удалось прочитать файл. Убедись, что он в UTF-8.")
        return

    try:
        data = asm.assemble(code)
        base = os.path.splitext(os.path.basename(doc.file_name))[0]
        base = "".join(c for c in base if c.isalnum() or c in "._- ")
        if not base:
            base = "program"
        caption = f"✅ {doc.file_name} → {base}.bin ({len(data)} bytes, {len(data)//4} instr)"
        await message.answer_document(
            document=BufferedInputFile(data, filename=f"{base}.bin"),
            caption=caption,
        )
        await msg.delete()
        dis = asm.disassemble(data)
        if len(dis) < 3500:
            await message.answer(f"<pre>{dis}</pre>")
    except AssembleError as e:
        await msg.edit_text(f"❌ {e}")
    except Exception as e:
        await msg.edit_text(f"❌ Internal error: {e}")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    if not TOKEN:
        print("❌ Укажите токен: export TBVM_BOT_TOKEN=ваш_токен")
        return

    if VM_CMD:
        logging.info("VM binary: %s", " ".join(VM_CMD))
    else:
        logging.warning("No VM binary found — /run will be unavailable")

    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
