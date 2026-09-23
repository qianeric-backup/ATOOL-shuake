#!/usr/bin/env bash
cd "$(dirname "$0")"
bash build.sh > build.log 2>&1
echo "exit=$?"
