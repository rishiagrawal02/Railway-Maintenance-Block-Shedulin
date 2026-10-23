#!/usr/bin/env bash
set -e

ruff check .
pytest -m "not slow"
