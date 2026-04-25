-- Orphan variant heal preview (READ-ONLY)
-- 预览孤儿变体 + 脏颜色值的修复计划，不执行任何 UPDATE。
--
-- 修复规则：
--   1) 孤儿变体（parent_part_id IS NULL 且名字以 _金色 / _白K / _玫瑰金 结尾
--      或 _色_规格 结尾）：
--      - 从 name 剥掉色/规格后缀 → base_name
--      - 在同 category 找 name = base_name 且 parent_part_id IS NULL 的 root
--        - 找到 → 计划 LINK（setup parent_part_id、color、spec）
--        - 没找到 → 计划 CREATE ROOT（用 base_name 创建新 root，再 LINK）
--   2) 脏颜色值：白 / 红色 → 原色
--
-- 用法：
--   psql "$DATABASE_URL" -f scripts/preview_orphan_heal.sql | tee /tmp/heal_preview.txt

\echo '============================================================'
\echo 'A) 总体计划数'
\echo '============================================================'
WITH orphan AS (
  SELECT
    p.id, p.name, p.category,
    regexp_replace(
      p.name,
      '_(金色|白K|玫瑰金)(_[0-9]+(\.[0-9]+)?(cm|mm|m))?$',
      ''
    ) AS base_name
  FROM part p
  WHERE p.parent_part_id IS NULL
    AND p.name ~ '_(金色|白K|玫瑰金)(_[0-9]+(\.[0-9]+)?(cm|mm|m))?$'
)
SELECT
  (SELECT count(*) FROM orphan o
     JOIN part r ON r.name = o.base_name
                AND r.category = o.category
                AND r.parent_part_id IS NULL) AS orphan_link_count,
  (SELECT count(*) FROM orphan o
     LEFT JOIN part r ON r.name = o.base_name
                    AND r.category = o.category
                    AND r.parent_part_id IS NULL
     WHERE r.id IS NULL) AS orphan_create_root_count,
  (SELECT count(*) FROM part WHERE color IN ('白','红色')) AS dirty_color_count;

\echo ''
\echo '============================================================'
\echo 'B) 可直接 LINK 到现有 root 的孤儿'
\echo '   动作：UPDATE part SET parent_part_id=<root_id>,'
\echo '        color=<extracted>, spec=<extracted> WHERE id=<orphan>'
\echo '============================================================'
WITH orphan AS (
  SELECT
    p.id,
    p.name,
    p.category,
    p.color AS current_color,
    p.spec  AS current_spec,
    regexp_replace(
      p.name,
      '_(金色|白K|玫瑰金)(_[0-9]+(\.[0-9]+)?(cm|mm|m))?$',
      ''
    ) AS base_name,
    (regexp_match(
      p.name,
      '_(金色|白K|玫瑰金)(?:_[0-9]+(?:\.[0-9]+)?(?:cm|mm|m))?$'
    ))[1] AS extracted_color,
    (regexp_match(
      p.name,
      '_(?:金色|白K|玫瑰金)_([0-9]+(?:\.[0-9]+)?(?:cm|mm|m))$'
    ))[1] AS extracted_spec
  FROM part p
  WHERE p.parent_part_id IS NULL
    AND p.name ~ '_(金色|白K|玫瑰金)(_[0-9]+(\.[0-9]+)?(cm|mm|m))?$'
)
SELECT
  o.id                           AS orphan_id,
  o.name                         AS orphan_name,
  o.category,
  r.id                           AS target_root_id,
  r.name                         AS target_root_name,
  o.extracted_color              AS will_set_color,
  o.extracted_spec               AS will_set_spec,
  o.current_color                AS existing_color,
  o.current_spec                 AS existing_spec
FROM orphan o
JOIN part r
  ON r.name = o.base_name
 AND r.category = o.category
 AND r.parent_part_id IS NULL
ORDER BY o.category, o.id;

\echo ''
\echo '============================================================'
\echo 'C) 找不到 root 的孤儿 —— 需要先 CREATE 新 root 再 LINK'
\echo '   动作：(1) INSERT INTO part (id, name, category, parent_part_id=NULL)'
\echo '        其中 id = _next_id_by_category(category)'
\echo '        (2) 把对应 orphan 的 parent_part_id 指向新建 root'
\echo '============================================================'
WITH orphan AS (
  SELECT
    p.id,
    p.name,
    p.category,
    p.color AS current_color,
    p.spec  AS current_spec,
    regexp_replace(
      p.name,
      '_(金色|白K|玫瑰金)(_[0-9]+(\.[0-9]+)?(cm|mm|m))?$',
      ''
    ) AS base_name,
    (regexp_match(
      p.name,
      '_(金色|白K|玫瑰金)(?:_[0-9]+(?:\.[0-9]+)?(?:cm|mm|m))?$'
    ))[1] AS extracted_color,
    (regexp_match(
      p.name,
      '_(?:金色|白K|玫瑰金)_([0-9]+(?:\.[0-9]+)?(?:cm|mm|m))$'
    ))[1] AS extracted_spec
  FROM part p
  WHERE p.parent_part_id IS NULL
    AND p.name ~ '_(金色|白K|玫瑰金)(_[0-9]+(\.[0-9]+)?(cm|mm|m))?$'
)
SELECT
  o.id                    AS orphan_id,
  o.name                  AS orphan_name,
  o.category,
  o.base_name             AS new_root_name,
  o.extracted_color       AS will_set_color,
  o.extracted_spec        AS will_set_spec
FROM orphan o
LEFT JOIN part r
  ON r.name = o.base_name
 AND r.category = o.category
 AND r.parent_part_id IS NULL
WHERE r.id IS NULL
ORDER BY o.category, o.id;

\echo ''
\echo '============================================================'
\echo 'D) C 中"同名新 root"的聚合 —— 多个孤儿可能共享同一个 base_name'
\echo '   这些 base_name 只需创建一次新 root，多个孤儿挂同一个父'
\echo '============================================================'
WITH orphan AS (
  SELECT
    p.id, p.name, p.category,
    regexp_replace(
      p.name,
      '_(金色|白K|玫瑰金)(_[0-9]+(\.[0-9]+)?(cm|mm|m))?$',
      ''
    ) AS base_name
  FROM part p
  WHERE p.parent_part_id IS NULL
    AND p.name ~ '_(金色|白K|玫瑰金)(_[0-9]+(\.[0-9]+)?(cm|mm|m))?$'
),
need_create AS (
  SELECT o.*
  FROM orphan o
  LEFT JOIN part r
    ON r.name = o.base_name
   AND r.category = o.category
   AND r.parent_part_id IS NULL
  WHERE r.id IS NULL
)
SELECT
  category,
  base_name                AS new_root_name,
  count(*)                 AS will_host_n_orphans,
  string_agg(id, ', ' ORDER BY id) AS orphan_ids
FROM need_create
GROUP BY category, base_name
ORDER BY category, base_name;

\echo ''
\echo '============================================================'
\echo 'E) 脏颜色值修复 —— 白/红色 → 原色'
\echo '   动作：UPDATE part SET color=''原色'' WHERE color IN (''白'',''红色'')'
\echo '============================================================'
SELECT
  id,
  name,
  category,
  color             AS current_color,
  '原色'            AS proposed_color,
  parent_part_id    AS has_parent
FROM part
WHERE color IN ('白', '红色')
ORDER BY color, id;

\echo ''
\echo '============================================================'
\echo 'F) 健全性检查：是否有同 base_name 已存在 root 但被重复创建的风险'
\echo '   （这些是计划里已 match 到 root 的 base_name，在 D 里不应出现）'
\echo '============================================================'
WITH orphan AS (
  SELECT
    regexp_replace(
      p.name,
      '_(金色|白K|玫瑰金)(_[0-9]+(\.[0-9]+)?(cm|mm|m))?$',
      ''
    ) AS base_name,
    p.category
  FROM part p
  WHERE p.parent_part_id IS NULL
    AND p.name ~ '_(金色|白K|玫瑰金)(_[0-9]+(\.[0-9]+)?(cm|mm|m))?$'
)
SELECT
  o.base_name,
  o.category,
  count(r.id) AS matching_root_count
FROM orphan o
LEFT JOIN part r
  ON r.name = o.base_name
 AND r.category = o.category
 AND r.parent_part_id IS NULL
GROUP BY o.base_name, o.category
HAVING count(r.id) > 1;

\echo ''
\echo '============================================================'
\echo 'G) 剥离规则正确性抽查 —— 显示每个孤儿的"剥离"结果'
\echo '   肉眼审核 base_name / extracted_color / extracted_spec 是否合理'
\echo '============================================================'
SELECT
  p.id,
  p.name,
  regexp_replace(
    p.name,
    '_(金色|白K|玫瑰金)(_[0-9]+(\.[0-9]+)?(cm|mm|m))?$',
    ''
  ) AS base_name,
  (regexp_match(
    p.name,
    '_(金色|白K|玫瑰金)(?:_[0-9]+(?:\.[0-9]+)?(?:cm|mm|m))?$'
  ))[1] AS extracted_color,
  (regexp_match(
    p.name,
    '_(?:金色|白K|玫瑰金)_([0-9]+(?:\.[0-9]+)?(?:cm|mm|m))$'
  ))[1] AS extracted_spec
FROM part p
WHERE p.parent_part_id IS NULL
  AND p.name ~ '_(金色|白K|玫瑰金)(_[0-9]+(\.[0-9]+)?(cm|mm|m))?$'
ORDER BY p.category, p.id;

\echo ''
\echo '预览完成。'
