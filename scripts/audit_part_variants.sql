-- Part variant data audit (READ-ONLY)
-- 在线上数据库（allen_shop）跑一遍，看变体数据现状 + 迁移影响面。
-- 全部是 SELECT，不改任何数据。
--
-- 用法示例：
--   psql -U allen -h <host> -d allen_shop -f scripts/audit_part_variants.sql
-- 或复制到 pgAdmin 逐块执行。

\echo '============================================================'
\echo '1) 总览：parts 总数 + 根/变体分布'
\echo '============================================================'
SELECT
  count(*)                                          AS total_parts,
  count(*) FILTER (WHERE parent_part_id IS NULL)    AS roots,
  count(*) FILTER (WHERE parent_part_id IS NOT NULL) AS variants
FROM part;

\echo ''
\echo '============================================================'
\echo '2) 按类目拆分'
\echo '============================================================'
SELECT
  category,
  count(*)                                          AS total,
  count(*) FILTER (WHERE parent_part_id IS NULL)    AS roots,
  count(*) FILTER (WHERE parent_part_id IS NOT NULL) AS variants
FROM part
GROUP BY category
ORDER BY category;

\echo ''
\echo '============================================================'
\echo '3) 孤儿变体：名字像变体（含 _金色 / _白K / _玫瑰金）但没 parent_part_id'
\echo '   —— 这些是"龙链_金色 存在但 龙链 不存在"的那种'
\echo '============================================================'
SELECT id, name, category, color, spec
FROM part
WHERE parent_part_id IS NULL
  AND (
       name LIKE '%\_金色'    ESCAPE '\'
    OR name LIKE '%\_白K'     ESCAPE '\'
    OR name LIKE '%\_玫瑰金'  ESCAPE '\'
    OR name LIKE '%\_金色\_%' ESCAPE '\'
    OR name LIKE '%\_白K\_%'  ESCAPE '\'
    OR name LIKE '%\_玫瑰金\_%' ESCAPE '\'
  )
ORDER BY category, id;

SELECT count(*) AS orphan_variant_count
FROM part
WHERE parent_part_id IS NULL
  AND (
       name LIKE '%\_金色'    ESCAPE '\'
    OR name LIKE '%\_白K'     ESCAPE '\'
    OR name LIKE '%\_玫瑰金'  ESCAPE '\'
    OR name LIKE '%\_金色\_%' ESCAPE '\'
    OR name LIKE '%\_白K\_%'  ESCAPE '\'
    OR name LIKE '%\_玫瑰金\_%' ESCAPE '\'
  );

\echo ''
\echo '============================================================'
\echo '3b) Spec-only 孤儿（名字以 _45cm / _17.5cm 等结尾，但中间无颜色段）'
\echo '   —— `services/part.py:_looks_like_orphan_variant_name` 不覆盖此模式，'
\echo '      为避免误伤合法根名（如 D L:13cm）。这块需要 audit 单独把关。'
\echo '   —— 期望：0 行。非 0 行需人工核实是否真孤儿，可选清洗。'
\echo '============================================================'
SELECT id, name, category, color, spec
FROM part
WHERE parent_part_id IS NULL
  AND name ~ '_[0-9]+(\.[0-9]+)?(cm|mm|m)$'
  AND name !~ '_(金色|白K|玫瑰金)_'
ORDER BY category, id;

SELECT count(*) AS spec_only_orphan_count
FROM part
WHERE parent_part_id IS NULL
  AND name ~ '_[0-9]+(\.[0-9]+)?(cm|mm|m)$'
  AND name !~ '_(金色|白K|玫瑰金)_';

\echo ''
\echo '============================================================'
\echo '4) 悬空 parent 引用（parent_part_id 指向不存在的 part）'
\echo '   —— 理论上 FK 约束会阻止，但也检查一下'
\echo '============================================================'
SELECT p.id AS variant_id, p.name AS variant_name, p.parent_part_id AS dangling_parent
FROM part p
LEFT JOIN part r ON r.id = p.parent_part_id
WHERE p.parent_part_id IS NOT NULL
  AND r.id IS NULL;

\echo ''
\echo '============================================================'
\echo '5) 变体名字不是根名字前缀（数据语义不一致）'
\echo '   —— 迁移时这些重命名规则要特判'
\echo '============================================================'
SELECT
  v.id   AS variant_id,
  v.name AS variant_name,
  r.id   AS root_id,
  r.name AS root_name
FROM part v
JOIN part r ON r.id = v.parent_part_id
WHERE v.parent_part_id IS NOT NULL
  AND position(r.name in v.name) <> 1
ORDER BY v.id;

\echo ''
\echo '============================================================'
\echo '6) spec（规格）取值分布'
\echo '   —— 非空 spec 的全部样本，检查是否都能被 \d+(\.\d+)?(cm|mm|m) 覆盖'
\echo '============================================================'
SELECT spec, count(*) AS n
FROM part
WHERE spec IS NOT NULL AND spec <> ''
GROUP BY spec
ORDER BY n DESC, spec;

\echo ''
\echo '   不符合 \d+(\.\d+)?(cm|mm|m) 规则的 spec 值：'
SELECT DISTINCT spec
FROM part
WHERE spec IS NOT NULL AND spec <> ''
  AND spec !~ '^[0-9]+(\.[0-9]+)?(cm|mm|m)$'
ORDER BY spec;

\echo ''
\echo '============================================================'
\echo '7) color 取值分布（检查有无脏值 / 预期外颜色）'
\echo '============================================================'
SELECT color, count(*) AS n
FROM part
WHERE color IS NOT NULL AND color <> ''
GROUP BY color
ORDER BY n DESC;

\echo ''
\echo '============================================================'
\echo '8) 迁移影响面：所有引用 part.id 的表 + 行数'
\echo '   —— 如果走 "路线 B + 一次性迁移"，这些表的相关行都要级联改 ID'
\echo '============================================================'
-- 8a: 通过 FK 约束引用 part.id 的表
SELECT
  tc.table_name,
  kcu.column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
  ON tc.constraint_name = ccu.constraint_name
 AND tc.table_schema = ccu.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND ccu.table_name = 'part'
  AND ccu.column_name = 'id'
  AND tc.table_schema = 'public'
ORDER BY tc.table_name;

-- 8b: inventory_log 是多态引用（无 FK），单独统计
SELECT 'inventory_log (item_type=part)' AS source, count(*) AS rows_referencing_parts
FROM inventory_log
WHERE item_type = 'part';

\echo ''
\echo '============================================================'
\echo '9) 每个变体引用面（样本）：单个变体被多少行业务数据引用'
\echo '   —— 帮助判断迁移脚本的 UPDATE 量级'
\echo '============================================================'
WITH variants AS (
  SELECT id FROM part WHERE parent_part_id IS NOT NULL
),
inv AS (
  SELECT item_id AS part_id, count(*) AS n
  FROM inventory_log WHERE item_type = 'part' GROUP BY item_id
),
poi AS (
  SELECT part_id, count(*) AS n FROM plating_order_item GROUP BY part_id
),
hpi AS (
  SELECT part_id, count(*) AS n FROM handcraft_part_item GROUP BY part_id
),
bomt AS (
  SELECT part_id, count(*) AS n FROM bom GROUP BY part_id
)
SELECT
  v.id AS variant_id,
  coalesce(inv.n, 0)  AS inventory_log_rows,
  coalesce(poi.n, 0)  AS plating_item_rows,
  coalesce(hpi.n, 0)  AS handcraft_item_rows,
  coalesce(bomt.n, 0) AS bom_rows,
  (coalesce(inv.n,0) + coalesce(poi.n,0) + coalesce(hpi.n,0) + coalesce(bomt.n,0)) AS total_refs
FROM variants v
LEFT JOIN inv  ON inv.part_id  = v.id
LEFT JOIN poi  ON poi.part_id  = v.id
LEFT JOIN hpi  ON hpi.part_id  = v.id
LEFT JOIN bomt ON bomt.part_id = v.id
ORDER BY total_refs DESC
LIMIT 20;

\echo ''
\echo '============================================================'
\echo '10) 按根分组的变体数（找最"开枝散叶"的根）'
\echo '============================================================'
SELECT
  r.id   AS root_id,
  r.name AS root_name,
  count(v.id) AS variant_count
FROM part r
LEFT JOIN part v ON v.parent_part_id = r.id
WHERE r.parent_part_id IS NULL
GROUP BY r.id, r.name
HAVING count(v.id) > 0
ORDER BY variant_count DESC, r.id
LIMIT 20;

\echo ''
\echo '审计完成。'
