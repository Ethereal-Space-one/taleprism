#!/usr/bin/env bash
cd "$(dirname "$0")"
exec backend/.venv/bin/python tools/open_workbench.py
