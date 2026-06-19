-- ============================================================================
-- 智能笔记 (AI Note) — 002: 部分唯一索引 + note_tags GIN 索引
-- ============================================================================

-- 表在限定 schema(= .env 中 DB_SCHEMA) 内, 不使用 public。
-- 运行方式: psql -v schema=<DB_SCHEMA> -f migration/002_partial_unique_and_tags_index.sql
-- SET search_path TO :"schema";

-- ---------------------------------------------------------------------------
-- categories: 将普通唯一约束改为部分唯一索引
--   原约束 UNIQUE (user_id, category_name, parent_id) 会把软删除的行也算进去,
--   导致"删除后同名重建"触发唯一约束违反。部分唯一索引只约束未删除行。
--   (约束名与索引名共享同一命名空间, 沿用原名)
-- ---------------------------------------------------------------------------
ALTER TABLE categories DROP CONSTRAINT IF EXISTS uq_category_user_name_parent;

CREATE UNIQUE INDEX uq_category_user_name_parent
    ON categories (user_id, category_name, parent_id)
    WHERE is_deleted = 0;

-- ---------------------------------------------------------------------------
-- notes: note_tags 的 GIN 索引, 支持按标签筛选 (note_tags @> '["tag"]')
-- ---------------------------------------------------------------------------
CREATE INDEX ix_notes_note_tags ON notes USING GIN (note_tags);
