#!/bin/bash
# Получить логи dominion_app и сохранить в workspace
docker logs dominion_app 2>&1 | tail -100 > /home/armsp/dominion/app_crash.log
echo "=== ENTRYPOINT LOGS ===" >> /home/armsp/dominion/app_crash.log
docker logs dominion_app 2>&1 | grep -E "(ERROR|FATAL|Exception|Traceback|ImportError|ModuleNotFound|uvicorn|started|DOMINION|PostgreSQL)" | tail -50 >> /home/armsp/dominion/app_crash.log
echo "=== PROCESS CHECK ===" >> /home/armsp/dominion/app_crash.log
docker exec dominion_app ps aux 2>&1 >> /home/armsp/dominion/app_crash.log
echo "=== PORT CHECK ===" >> /home/armsp/dominion/app_crash.log
docker exec dominion_app ss -tlnp 2>&1 >> /home/armsp/dominion/app_crash.log
echo "DONE" >> /home/armsp/dominion/app_crash.log
