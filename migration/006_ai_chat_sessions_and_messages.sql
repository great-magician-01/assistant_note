-- ============================================================================
-- 智能笔记 (AI Note) — 006: AI 对话会话与消息表
-- 说明: 服务端管理对话会话, 每轮 user/assistant/tool 消息都落库, 含工具调用记录。
--       会话在首条消息时快照 config/model/api_format, 避免后续改配置影响进行中对话。
--       session_id/user_id/config_id/model_id 关联在应用层校验(无 FK)。
-- ============================================================================

-- 表在限定 schema(= .env 中 DB_SCHEMA) 内, 不使用 public。
-- 运行方式: psql -v schema=<DB_SCHEMA> -f migration/006_ai_chat_sessions_and_messages.sql
-- CREATE SCHEMA IF NOT EXISTS :"schema";
-- SET search_path TO :"schema";

-- ---------------------------------------------------------------------------
-- 对话会话表
-- ---------------------------------------------------------------------------
CREATE TABLE ai_chat_sessions (
    session_id      BIGINT          NOT NULL,
    user_id         BIGINT          NOT NULL,
    config_id       BIGINT          NOT NULL,
    model_id        BIGINT          NOT NULL,
    api_format      VARCHAR(20)     NOT NULL,
    session_title   VARCHAR(200)    NOT NULL DEFAULT '新对话',
    is_deleted      SMALLINT        NOT NULL DEFAULT 0,
    created_at      TIMESTAMP       NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP       NOT NULL DEFAULT now(),

    CONSTRAINT pk_ai_chat_sessions PRIMARY KEY (session_id)
);

COMMENT ON TABLE  ai_chat_sessions                IS 'AI对话会话表(服务端管理,首条消息时快照config/model)';
COMMENT ON COLUMN ai_chat_sessions.session_id     IS '会话ID(雪花ID)';
COMMENT ON COLUMN ai_chat_sessions.user_id        IS '所属用户ID(应用层校验,无FK)';
COMMENT ON COLUMN ai_chat_sessions.config_id      IS '快照:使用的AI配置ID(无FK)';
COMMENT ON COLUMN ai_chat_sessions.model_id       IS '快照:使用的模型池ID(无FK)';
COMMENT ON COLUMN ai_chat_sessions.api_format     IS '快照:接口格式(openai/anthropic)';
COMMENT ON COLUMN ai_chat_sessions.session_title  IS '会话标题(默认新对话,首条消息后自动取前30字)';
COMMENT ON COLUMN ai_chat_sessions.is_deleted     IS '是否删除(0-正常 1-已删除)';
COMMENT ON COLUMN ai_chat_sessions.created_at     IS '创建时间';
COMMENT ON COLUMN ai_chat_sessions.updated_at     IS '更新时间';

CREATE INDEX ix_ai_chat_sessions_user_created ON ai_chat_sessions (user_id, created_at DESC);
CREATE INDEX ix_ai_chat_sessions_is_deleted   ON ai_chat_sessions (is_deleted);

-- ---------------------------------------------------------------------------
-- 对话消息表: 一张表覆盖 user/assistant/tool 三种角色, 角色专属列可空
-- ---------------------------------------------------------------------------
CREATE TABLE ai_chat_messages (
    message_id        BIGINT          NOT NULL,
    session_id        BIGINT          NOT NULL,
    role              VARCHAR(20)     NOT NULL,
    content           TEXT,
    tool_calls        JSONB           NOT NULL DEFAULT '[]'::jsonb,
    tool_call_id      VARCHAR(100),
    tool_name         VARCHAR(100),
    is_error          SMALLINT        NOT NULL DEFAULT 0,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    iter_index        SMALLINT        NOT NULL DEFAULT 0,
    created_at        TIMESTAMP       NOT NULL DEFAULT now(),
    updated_at        TIMESTAMP       NOT NULL DEFAULT now(),

    CONSTRAINT pk_ai_chat_messages PRIMARY KEY (message_id)
);

COMMENT ON TABLE  ai_chat_messages                   IS 'AI对话消息表(覆盖user/assistant/tool角色,含工具调用记录)';
COMMENT ON COLUMN ai_chat_messages.message_id        IS '消息ID(雪花ID)';
COMMENT ON COLUMN ai_chat_messages.session_id        IS '所属会话ID(应用层校验,无FK)';
COMMENT ON COLUMN ai_chat_messages.role              IS '角色(user/assistant/tool)';
COMMENT ON COLUMN ai_chat_messages.content           IS '文本内容(user/assistant正文;tool为结果文本)';
COMMENT ON COLUMN ai_chat_messages.tool_calls        IS 'assistant请求工具:[{id,name,arguments{}}]';
COMMENT ON COLUMN ai_chat_messages.tool_call_id      IS 'role=tool:对应的tool_call id';
COMMENT ON COLUMN ai_chat_messages.tool_name         IS 'role=tool:工具名';
COMMENT ON COLUMN ai_chat_messages.is_error          IS 'role=tool:工具执行是否出错(0-否 1-是)';
COMMENT ON COLUMN ai_chat_messages.prompt_tokens     IS 'assistant行:输入token(该轮)';
COMMENT ON COLUMN ai_chat_messages.completion_tokens IS 'assistant行:输出token(该轮)';
COMMENT ON COLUMN ai_chat_messages.iter_index        IS '该消息属于第几次模型调用(0=首条user,1..N=模型轮次)';
COMMENT ON COLUMN ai_chat_messages.created_at        IS '创建时间';
COMMENT ON COLUMN ai_chat_messages.updated_at        IS '更新时间';

CREATE INDEX ix_ai_chat_messages_session_created ON ai_chat_messages (session_id, created_at);
CREATE INDEX ix_ai_chat_messages_session_iter    ON ai_chat_messages (session_id, iter_index);
