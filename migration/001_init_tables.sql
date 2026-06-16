-- ============================================================================
-- 智能笔记 (AI Note) — 初始化建表脚本
-- 数据库: PostgreSQL
-- 注意: 无外键约束，关联关系在应用层维护
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 用户表
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    user_id         BIGINT          NOT NULL,
    user_account    VARCHAR(50)     NOT NULL,
    user_name       VARCHAR(100)    NOT NULL,
    user_password   VARCHAR(255)    NOT NULL,
    is_active       SMALLINT        NOT NULL DEFAULT 1,
    created_at      TIMESTAMP       NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP       NOT NULL DEFAULT now(),

    CONSTRAINT pk_users PRIMARY KEY (user_id),
    CONSTRAINT uq_users_account UNIQUE (user_account)
);

COMMENT ON TABLE  users                IS '用户表';
COMMENT ON COLUMN users.user_id        IS '用户ID(雪花ID)';
COMMENT ON COLUMN users.user_account   IS '账号';
COMMENT ON COLUMN users.user_name      IS '用户名称';
COMMENT ON COLUMN users.user_password  IS '密码(bcrypt)';
COMMENT ON COLUMN users.is_active      IS '是否启用(0-禁用 1-启用)';
COMMENT ON COLUMN users.created_at     IS '创建时间';
COMMENT ON COLUMN users.updated_at     IS '更新时间';

-- ---------------------------------------------------------------------------
-- 分类表
-- ---------------------------------------------------------------------------
CREATE TABLE categories (
    category_id     BIGINT          NOT NULL,
    user_id         BIGINT          NOT NULL,
    category_name   VARCHAR(100)    NOT NULL,
    category_icon   VARCHAR(50),
    category_sort   INTEGER         NOT NULL DEFAULT 0,
    parent_id       BIGINT,
    is_deleted      SMALLINT        NOT NULL DEFAULT 0,
    created_at      TIMESTAMP       NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP       NOT NULL DEFAULT now(),

    CONSTRAINT pk_categories PRIMARY KEY (category_id),
    CONSTRAINT uq_category_user_name_parent UNIQUE (user_id, category_name, parent_id)
);

COMMENT ON TABLE  categories                IS '分类表';
COMMENT ON COLUMN categories.category_id    IS '分类ID(雪花ID)';
COMMENT ON COLUMN categories.user_id        IS '所属用户ID';
COMMENT ON COLUMN categories.category_name  IS '分类名称';
COMMENT ON COLUMN categories.category_icon  IS '图标标识';
COMMENT ON COLUMN categories.category_sort  IS '排序序号';
COMMENT ON COLUMN categories.parent_id      IS '父分类ID(NULL为顶级分类)';
COMMENT ON COLUMN categories.is_deleted     IS '是否删除(0-正常 1-已删除)';
COMMENT ON COLUMN categories.created_at     IS '创建时间';
COMMENT ON COLUMN categories.updated_at     IS '更新时间';

CREATE INDEX ix_categories_user_id ON categories (user_id);
CREATE INDEX ix_categories_parent_id ON categories (parent_id);

-- ---------------------------------------------------------------------------
-- 笔记表
-- ---------------------------------------------------------------------------
CREATE TABLE notes (
    note_id         BIGINT          NOT NULL,
    user_id         BIGINT          NOT NULL,
    category_id     BIGINT,
    note_title      VARCHAR(255)    NOT NULL,
    note_content    TEXT,
    note_summary    VARCHAR(500),
    note_tags       JSONB           NOT NULL DEFAULT '[]'::jsonb,
    search_vector   TSVECTOR,
    is_pinned       SMALLINT        NOT NULL DEFAULT 0,
    is_deleted      SMALLINT        NOT NULL DEFAULT 0,
    note_word_count INTEGER         NOT NULL DEFAULT 0,
    created_at      TIMESTAMP       NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP       NOT NULL DEFAULT now(),

    CONSTRAINT pk_notes PRIMARY KEY (note_id)
);

COMMENT ON TABLE  notes                IS '笔记表';
COMMENT ON COLUMN notes.note_id        IS '笔记ID(雪花ID)';
COMMENT ON COLUMN notes.user_id        IS '所属用户ID';
COMMENT ON COLUMN notes.category_id    IS '所属分类ID';
COMMENT ON COLUMN notes.note_title     IS '笔记标题';
COMMENT ON COLUMN notes.note_content   IS 'Markdown内容';
COMMENT ON COLUMN notes.note_summary   IS 'AI生成摘要';
COMMENT ON COLUMN notes.note_tags      IS '标签数组';
COMMENT ON COLUMN notes.search_vector  IS '全文搜索向量';
COMMENT ON COLUMN notes.is_pinned      IS '是否置顶(0-否 1-是)';
COMMENT ON COLUMN notes.is_deleted     IS '是否删除(0-正常 1-已删除)';
COMMENT ON COLUMN notes.note_word_count IS '字数统计';
COMMENT ON COLUMN notes.created_at     IS '创建时间';
COMMENT ON COLUMN notes.updated_at     IS '更新时间';

-- 索引: 用户笔记列表查询
CREATE INDEX ix_notes_user_deleted_updated ON notes (user_id, is_deleted, updated_at DESC);
CREATE INDEX ix_notes_category_id ON notes (category_id);

-- 全文搜索 GIN 索引
CREATE INDEX ix_notes_search_vector ON notes USING GIN (search_vector);

-- ---------------------------------------------------------------------------
-- 中文全文检索说明:
--   search_vector 不再由数据库触发器维护, 而是由应用层(backend)填充。
--   原因: PostgreSQL 内置分词器不支持中文分词, 应用层使用 jieba 对
--   标题/内容分词后再生成 to_tsvector('simple', 分词结果), 写入此列。
--   查询时同样用 jieba 对关键词分词后生成 plainto_tsquery 进行匹配。
--   因此本方案无需安装 zhparser / pg_jieba 等 PostgreSQL 扩展。
-- ---------------------------------------------------------------------------
