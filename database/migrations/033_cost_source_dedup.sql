SET NAMES utf8mb4;

-- 成本来源防重复归集（A1）结构准备。
-- 1) source_type 允许集合：003 迁移把 cost_entries.source_type 定义为 VARCHAR(64)，本身即可容纳
--    manual_feed_offset / manual_feed_direct 两个“财务明示口径”来源；若某处历史库/分支库把该列
--    改成了 ENUM，这里把两个新值并入既有枚举，保证新旧库允许集合一致（幂等：已包含则跳过）。
-- 2) 为“同一基地/塘口或批次、期间重叠、已由库存自动归集”的重复检查提供支撑索引。
DROP PROCEDURE IF EXISTS adp_migration_033_cost_source_dedup;
DELIMITER $$
CREATE PROCEDURE adp_migration_033_cost_source_dedup()
BEGIN
  DECLARE v_source_type_type VARCHAR(1024) DEFAULT NULL;

  SET v_source_type_type = (
    SELECT COLUMN_TYPE FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cost_entries' AND COLUMN_NAME='source_type'
      AND DATA_TYPE='enum'
    LIMIT 1
  );

  IF v_source_type_type IS NOT NULL AND LOCATE('manual_feed_offset', v_source_type_type)=0 THEN
    SET @adp_cost_source_type_ddl = CONCAT(
      'ALTER TABLE cost_entries MODIFY COLUMN source_type ',
      LEFT(v_source_type_type, CHAR_LENGTH(v_source_type_type)-1),
      ",'manual_feed_offset','manual_feed_direct') NOT NULL"
    );
    PREPARE adp_cost_source_type_stmt FROM @adp_cost_source_type_ddl;
    EXECUTE adp_cost_source_type_stmt;
    DEALLOCATE PREPARE adp_cost_source_type_stmt;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cost_entries' AND INDEX_NAME='idx_cost_entries_target_period'
  ) THEN
    ALTER TABLE cost_entries
      ADD KEY idx_cost_entries_target_period (target_type,target_id,period_start,period_end,source_type,status);
  END IF;
END$$
DELIMITER ;
CALL adp_migration_033_cost_source_dedup();
DROP PROCEDURE adp_migration_033_cost_source_dedup;
