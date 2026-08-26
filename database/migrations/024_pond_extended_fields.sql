SET NAMES utf8mb4;

-- BUG-007 塘口扩展字段：增氧机数量 / 投苗规格 / 目前规格 / 存塘数量与数据来源。
ALTER TABLE ponds
  ADD COLUMN aerator_count INT NOT NULL DEFAULT 0 AFTER pond_status,
  ADD COLUMN stocking_spec VARCHAR(40) NULL AFTER aerator_count,
  ADD COLUMN current_spec VARCHAR(40) NULL AFTER stocking_spec,
  ADD COLUMN stock_quantity DECIMAL(18,3) NULL AFTER current_spec,
  ADD COLUMN stock_quantity_source ENUM('estimated','manual','measured','sampled','corrected') NOT NULL DEFAULT 'manual' AFTER stock_quantity;
