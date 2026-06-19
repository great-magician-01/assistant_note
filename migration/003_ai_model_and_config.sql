-- ============================================================================
-- 智能笔记 (AI Note) — 003: AI 模型池 + 模型实际配置表
-- 说明: 这两张表为全局共享(无 user_id), 任何已登录用户可管理。
--       api_key 明文存储; 关联关系在应用层校验(无 FK)。
-- ============================================================================

-- 表在限定 schema(= .env 中 DB_SCHEMA) 内, 不使用 public。
-- schema 不存在时自动创建。运行方式: psql -v schema=<DB_SCHEMA> -f migration/003_ai_model_and_config.sql
-- CREATE SCHEMA IF NOT EXISTS :"schema";
-- SET search_path TO :"schema";

-- ---------------------------------------------------------------------------
-- 模型池表: 维护可用的模型接入信息
-- ---------------------------------------------------------------------------
CREATE TABLE ai_models (
    model_id        BIGINT          NOT NULL,
    name            VARCHAR(100)    NOT NULL,
    api_format      VARCHAR(20)     NOT NULL,
    base_url        VARCHAR(500)    NOT NULL,
    api_key         VARCHAR(500)    NOT NULL,
    model           VARCHAR(100)    NOT NULL,
    is_multimodal   SMALLINT        NOT NULL DEFAULT 0,
    max_tokens      INTEGER         NOT NULL DEFAULT 4096,
    remark          VARCHAR(500),
    extra_config    JSONB           NOT NULL DEFAULT '{}'::jsonb,
    is_active       SMALLINT        NOT NULL DEFAULT 1,
    is_deleted      SMALLINT        NOT NULL DEFAULT 0,
    created_at      TIMESTAMP       NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP       NOT NULL DEFAULT now(),

    CONSTRAINT pk_ai_models PRIMARY KEY (model_id)
);

COMMENT ON TABLE  ai_models                IS 'AI模型池表(全局共享)';
COMMENT ON COLUMN ai_models.model_id       IS '模型ID(雪花ID)';
COMMENT ON COLUMN ai_models.name           IS '友好显示名';
COMMENT ON COLUMN ai_models.api_format     IS '接口格式(openai/anthropic)';
COMMENT ON COLUMN ai_models.base_url       IS 'API基址';
COMMENT ON COLUMN ai_models.api_key        IS '密钥(明文)';
COMMENT ON COLUMN ai_models.model          IS '实际模型ID(传给API的字符串)';
COMMENT ON COLUMN ai_models.is_multimodal  IS '是否多模态(0-否 1-是)';
COMMENT ON COLUMN ai_models.max_tokens     IS '单次最大输出token';
COMMENT ON COLUMN ai_models.remark         IS '备注';
COMMENT ON COLUMN ai_models.extra_config   IS '额外参数(自定义请求头等)';
COMMENT ON COLUMN ai_models.is_active      IS '是否启用(0-禁用 1-启用)';
COMMENT ON COLUMN ai_models.is_deleted     IS '是否删除(0-正常 1-已删除)';
COMMENT ON COLUMN ai_models.created_at     IS '创建时间';
COMMENT ON COLUMN ai_models.updated_at     IS '更新时间';

CREATE INDEX ix_ai_models_is_deleted ON ai_models (is_deleted);

-- ---------------------------------------------------------------------------
-- 模型实际配置表: 从模型池选一个模型, 叠加运行参数
-- ---------------------------------------------------------------------------
CREATE TABLE ai_configs (
    config_id       BIGINT          NOT NULL,
    config_name     VARCHAR(100)    NOT NULL,
    model_id        BIGINT          NOT NULL,
    system_prompt   TEXT,
    tools           JSONB           NOT NULL DEFAULT '[]'::jsonb,
    json_output     SMALLINT        NOT NULL DEFAULT 0,
    temperature     NUMERIC(3,2),
    top_p           NUMERIC(3,2),
    max_tokens      INTEGER,
    is_default      SMALLINT        NOT NULL DEFAULT 0,
    is_active       SMALLINT        NOT NULL DEFAULT 1,
    is_deleted      SMALLINT        NOT NULL DEFAULT 0,
    created_at      TIMESTAMP       NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP       NOT NULL DEFAULT now(),

    CONSTRAINT pk_ai_configs PRIMARY KEY (config_id)
);

COMMENT ON TABLE  ai_configs                IS 'AI模型实际配置表(全局共享)';
COMMENT ON COLUMN ai_configs.config_id      IS '配置ID(雪花ID)';
COMMENT ON COLUMN ai_configs.config_name    IS '配置名';
COMMENT ON COLUMN ai_configs.model_id       IS '引用模型池ID(应用层校验,无FK)';
COMMENT ON COLUMN ai_configs.system_prompt  IS '系统提示词';
COMMENT ON COLUMN ai_configs.tools          IS '可用工具名数组';
COMMENT ON COLUMN ai_configs.json_output    IS '是否强制JSON输出(0-否 1-是)';
COMMENT ON COLUMN ai_configs.temperature    IS '温度(0-2)';
COMMENT ON COLUMN ai_configs.top_p          IS 'nucleus sampling';
COMMENT ON COLUMN ai_configs.max_tokens     IS '覆盖模型池max_tokens(NULL=用模型池值)';
COMMENT ON COLUMN ai_configs.is_default     IS '是否默认配置(0-否 1-是)';
COMMENT ON COLUMN ai_configs.is_active      IS '是否启用(0-禁用 1-启用)';
COMMENT ON COLUMN ai_configs.is_deleted     IS '是否删除(0-正常 1-已删除)';
COMMENT ON COLUMN ai_configs.created_at     IS '创建时间';
COMMENT ON COLUMN ai_configs.updated_at     IS '更新时间';

-- 按模型查配置
CREATE INDEX ix_ai_configs_model_id ON ai_configs (model_id);
-- 全局最多一个默认配置(仅约束未删除的默认行)
CREATE UNIQUE INDEX uq_ai_configs_default
    ON ai_configs (is_default)
    WHERE is_default = 1 AND is_deleted = 0;
