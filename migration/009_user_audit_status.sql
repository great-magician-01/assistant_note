-- ============================================================================
-- 智能笔记 (AI Note) — 009: users.audit_status 注册审核制
-- 说明: 注册改为审核制, 新增 audit_status 列(0=待审核 1=已通过 2=已拒绝)。
--       与 is_active(管理员事后启停) 正交, 登录同时校验两者。
-- 表在限定 schema(= .env 中 DB_SCHEMA) 内, 不使用 public。
-- 运行方式: psql -v schema=<DB_SCHEMA> -f migration/009_user_audit_status.sql
-- SET search_path TO :"schema";
-- ============================================================================

-- ---------------------------------------------------------------------------
-- users: 增加 audit_status 列
-- ---------------------------------------------------------------------------
ALTER TABLE users ADD COLUMN IF NOT EXISTS audit_status SMALLINT NOT NULL DEFAULT 0;

COMMENT ON COLUMN users.audit_status IS '审核状态(0=待审核 1=已通过 2=已拒绝)';

-- 回填历史用户为已通过(他们注册时审核制尚未生效, 视为已通过)
UPDATE users SET audit_status = 1 WHERE audit_status = 0;

CREATE INDEX IF NOT EXISTS ix_users_audit_status ON users (audit_status);
