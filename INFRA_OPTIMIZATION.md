# INFRASTRUCTURE OPTIMIZATION SPECIFICATION v200.16
## Project: S-GLOBAL DOMINION
## Target Hardware: 128GB RAM, RTX 5070 Ti (WSL2)

### 1. PostgreSQL Tuning (dominion_db)
Current state: Default alpine/postgres settings.
Target state:
- `shared_buffers`: 32GB
- `effective_cache_size`: 96GB
- `maintenance_work_mem`: 2GB
- `work_mem`: 64MB
- `max_connections`: 500
- `random_page_cost`: 1.1 (SSD optimization)
- `effective_io_concurrency`: 200

### 2. Redis Tuning (dominion_redis)
Current state: No memory limits defined in compose.
Target state:
- `maxmemory`: 8gb
- `maxmemory-policy`: allkeys-lru

### 3. SQLAlchemy Pool (app/database.py)
Current state: `pool_size=5`, `max_overflow=10`.
Target state:
- `pool_size`: 50
- `max_overflow`: 20
- `pool_recycle`: 3600
- `pool_pre_ping`: True

### 4. Asterisk (dominion_asterisk)
Current state: `mem_limit: 512m`.
Target state:
- `mem_limit`: 2g
- `volumes`: Ensure `/var/spool/asterisk` has enough space for recordings.

### 5. Ollama (dominion_ollama)
Current state: `OLLAMA_NUM_PARALLEL=4`.
Target state:
- Keep current, as it utilizes GPU. Verify `nvidia-container-runtime` health.
