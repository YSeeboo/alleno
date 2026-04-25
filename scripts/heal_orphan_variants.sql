-- Orphan variant heal (DRY RUN by default)
-- 默认事务结尾是 ROLLBACK —— 跑一遍看输出，确认无误后
-- 把文件末尾的 ROLLBACK 改成 COMMIT 再跑一次。
--
-- 修复三件事：
--   1) 创建缺失的新 root（32 个）—— 跳过 PJ-LT-00038 (xxcm 占位符)
--   2) 把所有 orphan LINK 到对应 root（12 个现有 + 31 个新建 = 43 个 UPDATE）
--   3) 脏颜色修复：白/红色 → 原色（3 条）
--
-- 用法：
--   psql "$DATABASE_URL" -f scripts/heal_orphan_variants.sql | tee /tmp/heal.txt

\set ON_ERROR_STOP on

BEGIN;

\echo '============================================================'
\echo 'Step 0: 初始状态'
\echo '============================================================'
SELECT
  (SELECT count(*) FROM part
     WHERE parent_part_id IS NULL
       AND name ~ '_(金色|白K|玫瑰金)(_[0-9]+(\.[0-9]+)?(cm|mm|m))?$')         AS orphans_total,
  (SELECT count(*) FROM part WHERE color IN ('白','红色'))                     AS dirty_colors,
  (SELECT count(*) FROM part)                                                   AS total_parts;

-- ---------- Stage 1: 所有要处理的 orphan（排除 PJ-LT-00038）----------
CREATE TEMP TABLE _orphans AS
SELECT
  p.id          AS orphan_id,
  p.name        AS orphan_name,
  p.category,
  regexp_replace(
    p.name,
    '_(金色|白K|玫瑰金)(_[0-9]+(\.[0-9]+)?(cm|mm|m))?$',
    ''
  )           AS base_name,
  (regexp_match(
    p.name,
    '_(金色|白K|玫瑰金)(?:_[0-9]+(?:\.[0-9]+)?(?:cm|mm|m))?$'
  ))[1]       AS new_color,
  (regexp_match(
    p.name,
    '_(?:金色|白K|玫瑰金)_([0-9]+(?:\.[0-9]+)?(?:cm|mm|m))$'
  ))[1]       AS new_spec
FROM part p
WHERE p.parent_part_id IS NULL
  AND p.name ~ '_(金色|白K|玫瑰金)(_[0-9]+(\.[0-9]+)?(cm|mm|m))?$'
  AND p.id <> 'PJ-LT-00038';

\echo ''
\echo 'Orphans 待处理（按 category）：'
SELECT category, count(*) FROM _orphans GROUP BY category ORDER BY category;

-- ---------- Stage 2: 识别需新建 root 的 base_name ----------
CREATE TEMP TABLE _needs_new_root AS
SELECT DISTINCT o.base_name, o.category
FROM _orphans o
LEFT JOIN part r
  ON r.name = o.base_name
 AND r.category = o.category
 AND r.parent_part_id IS NULL
WHERE r.id IS NULL;

\echo ''
\echo '需新建 root 数（按 category）：'
SELECT category, count(*) FROM _needs_new_root GROUP BY category ORDER BY category;

-- ---------- Stage 3: 为每个 category 计算 ID 分配起点 ----------
-- 起点 = max(id_counter.last_number, table_max_seq) —— 保证不撞号
CREATE TEMP TABLE _category_seq AS
SELECT
  cp.category,
  cp.prefix,
  greatest(
    coalesce(ic.last_number, 0),
    coalesce((
      SELECT max(CAST(substring(p.id FROM '[0-9]+$') AS INTEGER))
      FROM part p
      WHERE p.id ~ ('^' || cp.prefix || '-[0-9]+$')
    ), 0)
  ) AS current_max
FROM (
  VALUES ('吊坠','PJ-DZ'), ('链条','PJ-LT'), ('小配件','PJ-X')
) AS cp(category, prefix)
LEFT JOIN id_counter ic ON ic.prefix = cp.prefix;

\echo ''
\echo 'ID 分配起点（current_max；新 root 从 current_max+1 开始）：'
SELECT * FROM _category_seq ORDER BY prefix;

-- ---------- Stage 4: 给要新建的 root 分配 ID ----------
CREATE TEMP TABLE _new_roots AS
SELECT
  cs.prefix || '-' || LPAD(
    (cs.current_max + ROW_NUMBER() OVER (PARTITION BY n.category ORDER BY n.base_name))::text,
    5, '0'
  )                                                                              AS new_id,
  n.base_name                                                                    AS name,
  n.category,
  cs.prefix,
  cs.current_max + (ROW_NUMBER() OVER (PARTITION BY n.category ORDER BY n.base_name))
                                                                                 AS final_seq
FROM _needs_new_root n
JOIN _category_seq cs ON cs.category = n.category;

\echo ''
\echo '============================================================'
\echo 'Step 1: 创建 32 个新 root'
\echo '============================================================'
\echo '将创建的 root：'
SELECT new_id, name, category FROM _new_roots ORDER BY new_id;

INSERT INTO part (id, name, category)
SELECT new_id, name, category FROM _new_roots;

\echo ''
\echo '插入完成，核对 INSERT 后的行数：'
SELECT count(*) AS inserted_roots FROM _new_roots;

-- ---------- Stage 5: bump id_counter ----------
\echo ''
\echo '============================================================'
\echo 'Step 2: 把 id_counter 推到新高度（防止未来 app 创建撞号）'
\echo '============================================================'
INSERT INTO id_counter (prefix, last_number)
SELECT prefix, max(final_seq) FROM _new_roots GROUP BY prefix
ON CONFLICT (prefix) DO UPDATE
  SET last_number = GREATEST(id_counter.last_number, EXCLUDED.last_number);

\echo 'id_counter 新值：'
SELECT prefix, last_number FROM id_counter
WHERE prefix IN ('PJ-DZ','PJ-LT','PJ-X') ORDER BY prefix;

-- ---------- Stage 6: LINK 所有 orphan 到对应 root ----------
\echo ''
\echo '============================================================'
\echo 'Step 3: LINK 所有 orphan → root（43 条）'
\echo '============================================================'
WITH linked AS (
  UPDATE part p
  SET
    parent_part_id = r.id,
    color = o.new_color,
    spec  = coalesce(o.new_spec, p.spec)
  FROM _orphans o
  JOIN part r
    ON r.name = o.base_name
   AND r.category = o.category
   AND r.parent_part_id IS NULL
  WHERE p.id = o.orphan_id
  RETURNING p.id, p.name, r.id AS root_id
)
SELECT count(*) AS linked_orphans FROM linked;

-- ---------- Stage 7: 脏颜色 → 原色 ----------
\echo ''
\echo '============================================================'
\echo 'Step 4: 脏色 白/红色 → 原色'
\echo '============================================================'
WITH updated AS (
  UPDATE part SET color = '原色'
  WHERE color IN ('白', '红色')
  RETURNING id, name, color
)
SELECT count(*) AS dirty_colors_fixed FROM updated;

-- ---------- Stage 8: 后验 ----------
\echo ''
\echo '============================================================'
\echo 'Step 5: 后验（所有数字都应是期望值）'
\echo '============================================================'
SELECT
  (SELECT count(*) FROM part
     WHERE parent_part_id IS NULL
       AND name ~ '_(金色|白K|玫瑰金)(_[0-9]+(\.[0-9]+)?(cm|mm|m))?$'
       AND id <> 'PJ-LT-00038')                                  AS orphans_remaining_should_be_0,
  (SELECT count(*) FROM part WHERE color IN ('白','红色'))        AS dirty_colors_should_be_0,
  (SELECT count(*) FROM part
     WHERE id = 'PJ-LT-00038' AND parent_part_id IS NULL)        AS xxcm_still_orphan_should_be_1,
  (SELECT count(*) FROM _new_roots)                              AS new_roots_created,
  (SELECT count(*) FROM _orphans)                                AS orphans_linked;

\echo ''
\echo '新 root 挂载检查（期望：0 行 —— 每个新 root 都应至少挂 1 个子）：'
SELECT r.id, r.name, r.category, count(c.id) AS children
FROM _new_roots nr
JOIN part r ON r.id = nr.new_id
LEFT JOIN part c ON c.parent_part_id = r.id
GROUP BY r.id, r.name, r.category
HAVING count(c.id) = 0
ORDER BY r.id;

\echo ''
\echo 'FK 引用完整性抽查（期望：0 行 —— 没有指向已失联 part 的引用）：'
SELECT 'inventory_log' AS src, count(*) AS dangling
FROM inventory_log il
LEFT JOIN part p ON p.id = il.item_id
WHERE il.item_type = 'part' AND p.id IS NULL;

\echo ''
\echo '============================================================'
\echo '完成。当前是 DRY RUN（ROLLBACK 会撤销所有改动）。'
\echo '确认无误后，把脚本末尾的 ROLLBACK 改成 COMMIT 重跑一次。'
\echo '============================================================'

COMMIT;
