#!/usr/bin/env python3
"""
S-GLOBAL DOMINION — Читает логи Docker контейнера и сохраняет в файл
Запускать: python3 read_docker_logs.py
"""
import subprocess
import sys
import json
import os

OUTPUT_FILE = "/home/armsp/dominion/app_crash.log"

def run(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return result.stdout + result.stderr

lines = []

lines.append("=" * 60)
lines.append("=== DOCKER PS ===")
lines.append(run("docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'"))

lines.append("=" * 60)
lines.append("=== ЛОГИ dominion_app (последние 100 строк) ===")
lines.append(run("docker logs dominion_app --tail 100 2>&1"))

lines.append("=" * 60)
lines.append("=== ПРОЦЕССЫ В КОНТЕЙНЕРЕ ===")
lines.append(run("docker exec dominion_app ps aux 2>&1"))

lines.append("=" * 60)
lines.append("=== ПОРТЫ В КОНТЕЙНЕРЕ ===")
lines.append(run("docker exec dominion_app ss -tlnp 2>&1"))

lines.append("=" * 60)
lines.append("=== ТЕСТ API ИЗНУТРИ КОНТЕЙНЕРА ===")
lines.append(run("docker exec dominion_app curl -s -o /dev/null -w 'HTTP_CODE:%{http_code}' http://localhost:8001/ 2>&1"))

lines.append("=" * 60)
lines.append("=== ENV ПЕРЕМЕННЫЕ В КОНТЕЙНЕРЕ (без секретов) ===")
env_out = run("docker exec dominion_app env 2>&1")
# Фильтруем секреты
safe_lines = []
for line in env_out.split('\n'):
    key = line.split('=')[0] if '=' in line else line
    if any(s in key.upper() for s in ['PASSWORD', 'SECRET', 'KEY', 'TOKEN']):
        safe_lines.append(f"{key}=***HIDDEN***")
    else:
        safe_lines.append(line)
lines.append('\n'.join(safe_lines))

content = '\n'.join(lines)

# Записываем в файл
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Логи записаны в {OUTPUT_FILE}")
print(f"Размер: {len(content)} байт")
print("\n--- ПЕРВЫЕ 3000 СИМВОЛОВ ---")
print(content[:3000])
