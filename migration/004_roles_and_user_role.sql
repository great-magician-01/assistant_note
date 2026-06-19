-- ============================================================================
-- 智能笔记 (AI Note) — 004: 角色表 + users.role_id
-- 说明: roles 为系统级查找表, 用固定 ID 种子(1=普通用户, 2=管理员)。
--       users.role_id 引用 roles(应用层校验, 无 FK)。
-- ============================================================================

-- 表在限定 schema(= .env 中 DB_SCHEMA) 内, 不使用 public。
-- 运行方式: psql -v schema=<DB_SCHEMA> -f migration/004_roles_and_user_role.sql
-- SET search_path TO :"schema";

-- ---------------------------------------------------------------------------
-- 角色表
-- ---------------------------------------------------------------------------
CREATE TABLE roles (
    role_id         BIGINT          NOT NULL,
    role_code       VARCHAR(20)     NOT NULL,
    role_name       VARCHAR(50)     NOT NULL,
    remark          VARCHAR(200),
    created_at      TIMESTAMP       NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP       NOT NULL DEFAULT now(),

    CONSTRAINT pk_roles PRIMARY KEY (role_id),
    CONSTRAINT uq_roles_code UNIQUE (role_code)
);

COMMENT ON TABLE  roles            IS '角色表(系统级, 固定ID种子)';
COMMENT ON COLUMN roles.role_id    IS '角色ID(1=普通用户 2=管理员)';
COMMENT ON COLUMN roles.role_code  IS '角色编码(user/admin)';
COMMENT ON COLUMN roles.role_name  IS '角色名称';
COMMENT ON COLUMN roles.remark     IS '备注';
COMMENT ON COLUMN roles.created_at IS '创建时间';
COMMENT ON COLUMN roles.updated_at IS '更新时间';

-- 种子数据: 固定 ID, 供应用层常量直接引用
INSERT INTO roles (role_id, role_code, role_name, remark) VALUES
    (1, 'user',  '普通用户', '默认角色'),
    (2, 'admin', '管理员',   '可管理 AI 配置等系统资源')
ON CONFLICT (role_id) DO UPDATE SET
    role_code = EXCLUDED.role_code,
    role_name = EXCLUDED.role_name;

-- ---------------------------------------------------------------------------
-- users: 增加 role_id 列
-- ---------------------------------------------------------------------------
ALTER TABLE users ADD COLUMN role_id BIGINT;

COMMENT ON COLUMN users.role_id IS '角色ID(引用roles, 默认1=普通用户)';

-- 回填历史用户为普通用户, 再加 NOT NULL + 默认值
UPDATE users SET role_id = 1 WHERE role_id IS NULL;

ALTER TABLE users ALTER COLUMN role_id SET DEFAULT 1;
ALTER TABLE users ALTER COLUMN role_id SET NOT NULL;

CREATE INDEX ix_users_role_id ON users (role_id);
