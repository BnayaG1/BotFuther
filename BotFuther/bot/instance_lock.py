# -*- coding: utf-8 -*-
"""מניעת הרצת שני מופעי בוט במקביל (גורם ל-409 Conflict בטלגרם)."""
from __future__ import annotations

import atexit
import logging
import os
import subprocess
from pathlib import Path

from bot.config import APP_DIR

log = logging.getLogger("beam_telegram_bot")

_LOCK_PATH = APP_DIR / "_bot_temp_images" / ".bot_instance.lock"
_lock_handle = None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) == 0:
                return False
            return int(code.value) == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _process_tree_pids(root_pid: int) -> set[int]:
    """PID של התהליך, הורה, ילדים (מופע python -m bot הוא לעיתים שני תהליכים)."""
    tree = {root_pid}
    if os.name != "nt":
        return tree

    try:
        raw = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "$root = "
                    + str(root_pid)
                    + "; "
                    "$all = Get-CimInstance Win32_Process | "
                    "Where-Object { $_.Name -like 'python*' }; "
                    "$kids = @{}; foreach ($p in $all) { "
                    "$kids[$p.ParentProcessId] = @($kids[$p.ParentProcessId]) + $p.ProcessId }; "
                    "$out = [System.Collections.Generic.HashSet[int]]::new(); "
                    "[void]$out.Add($root); "
                    "$p = $root; while ($true) { "
                    "$proc = $all | Where-Object { $_.ProcessId -eq $p } | Select-Object -First 1; "
                    "if (-not $proc -or -not $proc.ParentProcessId) { break }; "
                    "$pp = [int]$proc.ParentProcessId; if ($out.Contains($pp)) { break }; "
                    "[void]$out.Add($pp); $p = $pp }; "
                    "$stack = New-Object System.Collections.Stack; $stack.Push($root); "
                    "while ($stack.Count -gt 0) { "
                    "$p = [int]$stack.Pop(); "
                    "foreach ($c in @($kids[$p])) { "
                    "if ($out.Add([int]$c)) { $stack.Push([int]$c) } } }; "
                    "$out -join ','"
                ),
            ],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=8,
        )
        for part in raw.strip().split(","):
            part = part.strip()
            if part.isdigit():
                tree.add(int(part))
    except Exception as exc:
        log.debug("Process tree scan failed: %s", exc)
    return tree


def _other_bot_pids() -> list[int]:
    """מחזיר PIDs של python -m bot שאינם בעץ התהליך הנוכחי."""
    mine = _process_tree_pids(os.getpid())
    found: list[int] = []

    if os.name == "nt":
        try:
            raw = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "Get-CimInstance Win32_Process | "
                        "Where-Object { $_.Name -like 'python*' -and "
                        "$_.CommandLine -match ' -m bot(\\s|$)' } | "
                        "Select-Object -ExpandProperty ProcessId"
                    ),
                ],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=8,
            )
            for line in raw.splitlines():
                line = line.strip()
                if line.isdigit():
                    pid = int(line)
                    if pid not in mine and _pid_alive(pid):
                        found.append(pid)
        except Exception as exc:
            log.debug("Bot process scan failed: %s", exc)
        return found

    try:
        raw = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="], text=True, timeout=8)
        for line in raw.splitlines():
            if " -m bot" not in line:
                continue
            pid_s = line.strip().split(None, 1)[0]
            if pid_s.isdigit():
                pid = int(pid_s)
                if pid not in mine and _pid_alive(pid):
                    found.append(pid)
    except Exception as exc:
        log.debug("Bot process scan failed: %s", exc)
    return found


def _exit_already_running(*, other_pids: list[int] | None = None, telegram: bool = False) -> None:
    if telegram:
        msg = (
            "הבוט כבר מחובר לטלגרם ממקום אחר (מחשב אחר, שרת, או טרמינל פתוח).\n"
            "עצור את המופע הקיים — רק מופע אחד יכול לרוץ בכל זמן."
        )
    elif other_pids:
        msg = (
            "הבוט כבר רץ במחשב הזה "
            f"(pid={', '.join(str(p) for p in other_pids)}).\n"
            "עצור את הטרמינל הקיים לפני הפעלה מחדש."
        )
    else:
        msg = (
            "הבוט כבר רץ.\n"
            "עצור את המופע הקיים לפני הפעלה מחדש."
        )
    log.error(msg.replace("\n", " "))
    raise SystemExit(msg)


def _try_exclusive_file_lock() -> bool:
    global _lock_handle
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    _lock_handle = open(_LOCK_PATH, "a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt

            _lock_handle.seek(0)
            msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(_lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        if _lock_handle is not None:
            try:
                _lock_handle.close()
            except OSError:
                pass
            _lock_handle = None
        return False
    return True


def acquire_bot_instance_lock() -> None:
    """יוצא אם מופע אחר של הבוט כבר רץ (מקומי או בטלגרם)."""
    others = _other_bot_pids()
    if others:
        _exit_already_running(other_pids=others)

    if not _try_exclusive_file_lock():
        others = _other_bot_pids()
        if others:
            _exit_already_running(other_pids=others)
        _exit_already_running()

    assert _lock_handle is not None
    _lock_handle.seek(0)
    _lock_handle.truncate()
    _lock_handle.write(str(os.getpid()))
    _lock_handle.flush()
    log.info("Bot instance lock acquired (pid=%s)", os.getpid())
    atexit.register(release_bot_instance_lock)


def release_bot_instance_lock() -> None:
    global _lock_handle
    if _lock_handle is None:
        return
    try:
        if os.name == "nt":
            import msvcrt

            _lock_handle.seek(0)
            msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(_lock_handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        _lock_handle.close()
    except OSError:
        pass
    _lock_handle = None
    if _LOCK_PATH.is_file():
        try:
            if int(_LOCK_PATH.read_text(encoding="utf-8").strip()) == os.getpid():
                _LOCK_PATH.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass


def abort_if_telegram_poller_active() -> None:
    """בדיקה מול Telegram — אם מישהו אחר כבר עושה polling, לא מתחילים."""
    from telegram.error import Conflict

    from bot.config import TELEGRAM_KEY_NAMES
    from bot.env import require_env

    token = require_env(*TELEGRAM_KEY_NAMES, label="Telegram bot token")

    async def _probe() -> None:
        from telegram.ext import Application

        app = Application.builder().token(token).build()
        try:
            await app.initialize()
            await app.bot.delete_webhook(drop_pending_updates=True)
            await app.bot.get_updates(offset=-1, timeout=1, allowed_updates=[])
        except Conflict:
            release_bot_instance_lock()
            _exit_already_running(telegram=True)
        finally:
            try:
                await app.shutdown()
            except Exception:
                pass

    import asyncio

    try:
        asyncio.run(_probe())
    except SystemExit:
        raise
    except Exception as exc:
        log.warning("Telegram single-instance probe skipped: %s", exc)
