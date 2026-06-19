-- ============================================================================
-- 智能笔记 (AI Note) — 007: AI 对话会话表增加 note_id
-- 说明: 笔记编辑页的 AI 助手侧边栏需要让 AI 知道当前在处理哪篇笔记。
--       给会话表加一个可空的 note_id,绑定时该会话即"笔记上下文会话";
--       为空则是普通自由对话(与 AI 对话页一致)。关联在应用层校验(无 FK)。
-- ============================================================================

-- 表在限定 schema(= .env 中 DB_SCHEMA) 内, 不使用 public。
-- 运行方式: psql -v schema=<DB_SCHEMA> -f migration/007_ai_chat_session_note_id.sql
-- CREATE SCHEMA IF NOT EXISTS :"schema";
-- SET search_path TO :"schema";

ALTER TABLE ai_chat_sessions ADD COLUMN IF NOT EXISTS note_id BIGINT NULL;

COMMENT ON COLUMN ai_chat_sessions.note_id IS '绑定的笔记ID(可空;笔记AI助手会话用,应用层校验,无FK)';

-- 按笔记筛选会话(笔记AI助手侧边栏加载某笔记的最近会话)。
CREATE INDEX IF NOT EXISTS ix_ai_chat_sessions_note ON ai_chat_sessions (note_id, is_deleted);
