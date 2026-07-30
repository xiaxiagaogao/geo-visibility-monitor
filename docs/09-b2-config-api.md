# B2 — 配置域 API（品牌 / 别名 / 竞品 / Prompt）

## 范围

| 资源 | 方法 |
|------|------|
| brands | GET 列表、POST 创建、GET/PATCH/DELETE 详情 |
| aliases | PUT 全量替换 `/v1/brands/{id}/aliases` |
| competitors | PUT 全量替换 `/v1/brands/{id}/competitors` |
| prompts | GET 列表（可 `brand_id`）、POST、GET/PATCH/DELETE |

## 约定（B2 默认，有异议可改）

- 删除：**硬删除**（级联按 DB FK）
- 别名/竞品：PUT **全量替换**（不是增量 patch）
- 竞品：存的是**另一品牌的 id**（需先创建竞品品牌）
- 单 workspace，默认 `workspace_id=1`
- 无鉴权（学习阶段）

## 运行

VPS：`docker compose up -d postgres api`  
公网：`http://<VPS_IP>:8200/docs`

## 快速验收

```bash
BASE=http://127.0.0.1:8200
# 或公网 BASE=http://96.9.213.230:8200

curl -s $BASE/health
curl -s $BASE/health/db

curl -s -X POST $BASE/v1/brands -H 'Content-Type: application/json' \
  -d '{"name":"土巴兔","aliases":["土巴兔","Tubatu"],"industry":"家装"}'

curl -s $BASE/v1/brands
```
