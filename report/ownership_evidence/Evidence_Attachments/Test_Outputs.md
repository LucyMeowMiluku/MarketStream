# 当前测试与静态检查输出

运行日期：2026-09-17  
工作目录：MarketStream 项目根目录  
基准 HEAD：`bb0df67fad42ef6cf4c544b5e3711d57cd32f3fd`

## pytest

命令：

```bash
uv run pytest -q
```

结果：

```text
platform darwin -- Python 3.12.10, pytest-9.0.3
collected 62 items

tests/test_alpaca_history.py .............. 4 passed
tests/test_baseline_persistence.py ........ 7 passed
tests/test_cep_golden_trace.py ............ 1 passed
tests/test_data_quality.py ................ 4 passed
tests/test_db.py .......................... 4 passed
tests/test_event_metrics.py ............... 4 passed
tests/test_event_models.py ................ 3 passed
tests/test_factor_cep.py .................. 16 passed
tests/test_isolation_forest_baseline.py ... 3 passed
tests/test_lightweight_factor_engine.py ... 9 passed
tests/test_real_replay.py ................. 1 passed
tests/test_replay_consistency.py .......... 2 passed
tests/test_replay_labels.py ............... 4 passed

62 passed in 4.85s
```

说明：旧材料中的 `160 passed` 属于简化前代码。当前测试数量为 62，不能混用。

## Ruff

命令：

```bash
uv run ruff check .
```

结果：

```text
All checks passed!
```

## synthetic evaluation

命令：

```bash
uv run python -m evaluation.run_synthetic \
  --seeds 20 \
  --output report/ownership_evidence/reproduction_outputs/factor_cep_current_20260917.json
```

退出状态：0。完整输出保存在对应 JSON。摘要见 `../03_Experiment_Reproducibility_CN.md`。

## Kafka/database soak 环境检查

```text
docker compose ps
→ docker: unknown command: docker compose

docker-compose ps
→ Cannot connect to the Docker daemon at
  unix:///Users/[REDACTED]/.colima/default/docker.sock.
  Is the docker daemon running?
```

因此本轮没有生成新的 soak 输出。该阻塞是环境状态，不作为系统通过或失败的检测结果。
