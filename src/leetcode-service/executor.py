import ast
import asyncio
import os
import tempfile
import textwrap


async def run_code(user_code: str, test_code: str = "") -> dict:
    # Линтер
    try:
        ast.parse(user_code)
    except SyntaxError as e:
        error_msg = f"Syntax Error on line {e.lineno}:\n{e.text or ''}{' ' * (e.offset - 1 if e.offset else 0)}^\n{e.msg}"
        return {
            "success": False,
            "output": "",
            "error": error_msg,
            "stage": "linting",
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": f"Pre-flight check failed: {str(e)}",
            "stage": "linting",
        }

    # Выполнение кода

    test_code = test_code.replace('if __name__ == "__main__":', "")
    indented_test_code = textwrap.indent(test_code.strip(), "        ")

    full_script = f"""
import sys
from typing import *
import collections
import math
import itertools
import bisect
import heapq

# --- User Code ---
{user_code}

# --- Test Code ---
if __name__ == "__main__":
    try:
{indented_test_code}
        print("SUCCESS_MARKER")
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(full_script)
        tmp_path = tmp.name

    try:
        cmd = ["python3", tmp_path]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=5.0
            )

            output = stdout.decode().strip()
            error = stderr.decode().strip()

            is_success = "SUCCESS_MARKER" in output and process.returncode == 0
            clean_output = output.replace("SUCCESS_MARKER", "").strip()

            return {
                "success": is_success,
                "output": clean_output,
                "error": error,
                "stage": "runtime",
            }

        except asyncio.TimeoutError:
            process.kill()
            return {
                "success": False,
                "error": "Time Limit Exceeded (5s). Possible infinite loop.",
                "output": "",
                "stage": "runtime",
            }

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
