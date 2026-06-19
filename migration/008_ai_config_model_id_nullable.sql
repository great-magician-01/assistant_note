-- ============================================================================
-- 智能笔记 (AI Note) — 008: ai_configs.model_id 改为可空
-- 说明: 默认配置初始化时模型池可能为空，先用空模型占位，等后续用户添加模型再绑定。
-- ============================================================================

ALTER TABLE ai_configs ALTER COLUMN model_id DROP NOT NULL;

COMMENT ON COLUMN ai_configs.model_id IS '引用模型池ID(NULL=未绑定模型,应用层校验,无FK)';
