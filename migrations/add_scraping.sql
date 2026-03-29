-- migrations/add_scraping.sql

-- 添加刮削相关字段
ALTER TABLE files ADD COLUMN scrape_status TEXT DEFAULT 'pending';
ALTER TABLE files ADD COLUMN last_scrape_at TEXT;

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_files_scrape_status ON files(scrape_status);

-- 迁移现有状态: processed -> organized
UPDATE files SET status = 'organized' WHERE status = 'processed';

-- 验证迁移
SELECT 'Migration completed' as status,
       (SELECT COUNT(*) FROM files WHERE status = 'organized') as organized_count,
       (SELECT COUNT(*) FROM files WHERE scrape_status = 'pending') as pending_count;
