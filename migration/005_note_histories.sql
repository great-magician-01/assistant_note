-- ============================================================================
-- 智能笔记 (AI Note) — 005: 笔记历史记录表
-- 说明: 每次笔记变更(创建/更新/删除/回滚)都写入一份完整快照, 区分人为(manual)
--       与 AI(ai) 来源, 用于后续版本回滚。表为只追加, 不做软删除。
--       note_id/user_id 关联在应用层校验(无 FK)。
-- ============================================================================

-- 表在限定 schema(= .env 中 DB_SCHEMA) 内, 不使用 public。
-- schema 不存在时自动创建。运行方式: psql -v schema=<DB_SCHEMA> -f migration/005_note_histories.sql
-- CREATE SCHEMA IF NOT EXISTS :"schema";
-- SET search_path TO :"schema";

-- ---------------------------------------------------------------------------
-- 笔记历史表: 记录每次变更后的完整快照
-- ---------------------------------------------------------------------------
CREATE TABLE note_histories (
    history_id      BIGINT          NOT NULL,
    note_id         BIGINT          NOT NULL,
    user_id         BIGINT          NOT NULL,
    category_id     BIGINT,
    note_title      VARCHAR(255)    NOT NULL,
    note_content    TEXT,
    note_summary    VARCHAR(500),
    note_tags       JSONB           NOT NULL DEFAULT '[]'::jsonb,
    note_word_count INTEGER         NOT NULL DEFAULT 0,
    is_pinned       SMALLINT        NOT NULL DEFAULT 0,
    change_type     SMALLINT        NOT NULL,
    change_source   SMALLINT        NOT NULL DEFAULT 1,
    remark          VARCHAR(500),
    created_at      TIMESTAMP       NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP       NOT NULL DEFAULT now(),

    CONSTRAINT pk_note_histories PRIMARY KEY (history_id)
);

COMMENT ON TABLE  note_histories                  IS '笔记历史记录表(每次变更一份完整快照,只追加)';
COMMENT ON COLUMN note_histories.history_id       IS '历史ID(雪花ID)';
COMMENT ON COLUMN note_histories.note_id          IS '笔记ID(应用层校验,无FK)';
COMMENT ON COLUMN note_histories.user_id          IS '所属用户ID(冗余便于按用户过滤,无FK)';
COMMENT ON COLUMN note_histories.category_id      IS '快照:所属分类ID';
COMMENT ON COLUMN note_histories.note_title       IS '快照:笔记标题';
COMMENT ON COLUMN note_histories.note_content     IS '快照:笔记正文(Markdown)';
COMMENT ON COLUMN note_histories.note_summary     IS '快照:AI生成摘要';
COMMENT ON COLUMN note_histories.note_tags        IS '快照:标签数组';
COMMENT ON COLUMN note_histories.note_word_count  IS '快照:字数';
COMMENT ON COLUMN note_histories.is_pinned        IS '快照:是否置顶(0-否 1-是)';
COMMENT ON COLUMN note_histories.change_type      IS '变更类型(1-创建 2-更新 3-删除 4-回滚)';
COMMENT ON COLUMN note_histories.change_source    IS '变更来源(1-人为 2-AI)';
COMMENT ON COLUMN note_histories.remark           IS '备注(如AI编辑说明)';
COMMENT ON COLUMN note_histories.created_at       IS '创建时间';
COMMENT ON COLUMN note_histories.updated_at       IS '更新时间';

-- 按笔记拉取历史列表(按时间倒序)
CREATE INDEX ix_note_histories_note_created ON note_histories (note_id, created_at DESC);
-- 按用户聚合统计
CREATE INDEX ix_note_histories_user         ON note_histories (user_id);
