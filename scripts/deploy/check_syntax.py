#!/usr/bin/env python3
"""Check sidecar for syntax errors."""
import py_compile
try:
    py_compile.compile('/home/raspberry/homephone-sidecar.py', doraise=True)
    print('OK: No syntax errors')
except py_compile.PyCompileError as e:
    print(f'ERROR: {e}')
