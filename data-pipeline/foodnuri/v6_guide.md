# V6 가이드라인 — recipe_embeddings 데이터 적재

## 사전 준비

docker-compose.yml 이미지 교체 후 컨테이너 재시작 (V5와 동일)

```yaml
image: pgvector/pgvector:pg16
```

```bash
docker compose down && docker compose up -d
```

---

## Step 1 — 테이블 생성

```bash
docker exec -i <컨테이너명> psql -U farmily -d farmily < "V6 create pgvector tables.sql"
```

## Step 2 — 의존성 설치

```bash
pip install psycopg2-binary
```

## Step 3 — JSON 데이터 INSERT

`raw_10000recipe.json`과 `insert_recipes.py`가 같은 폴더에 있어야 합니다.

```bash
python3 insert_recipes.py
```

## Step 4 — 확인

```sql
SELECT COUNT(*) FROM recipe_embeddings;
SELECT crop_name, dish_name, recipe_name FROM recipe_embeddings LIMIT 10;
```
