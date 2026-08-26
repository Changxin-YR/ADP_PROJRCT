SET NAMES utf8mb4;

INSERT INTO cost_entries (
  organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,
  cost_nature,source_type,source_ref,source_detail_json,target_type,target_id,created_by,confirmed_by,confirmed_at
)
SELECT d.organization_id,d.farm_id,COALESCE(p.area_id,d.area_id,w.area_id),c.id,
  -g.quantity_delta*COALESCE(NULLIF(g.unit_cost,0),l.unit_cost,0),DATE(g.happened_at),DATE(g.happened_at),DATE(g.happened_at),'confirmed',
  c.default_nature,'warehouse_ledger',d.code,
  JSON_OBJECT(
    'inventory_ledger_id',g.id,'warehouse_document_id',d.id,'document_code',d.code,'material_id',g.material_id,'inventory_lot_id',g.inventory_lot_id,
    'purchase_order_id',(SELECT receipt.purchase_order_id FROM warehouse_documents receipt
      WHERE receipt.inventory_lot_id=g.inventory_lot_id AND receipt.document_type='receipt'
        AND receipt.status='verified' AND receipt.purchase_order_id IS NOT NULL ORDER BY receipt.id LIMIT 1)
  ),
  CASE WHEN g.batch_id IS NOT NULL THEN 'batch' WHEN g.pond_id IS NOT NULL THEN 'pond' ELSE NULL END,
  COALESCE(g.batch_id,g.pond_id),g.posted_by,g.posted_by,g.created_at
FROM inventory_ledger g
JOIN warehouse_documents d ON d.id=g.source_id
JOIN warehouses w ON w.id=g.warehouse_id
JOIN materials m ON m.id=g.material_id
JOIN inventory_lots l ON l.id=g.inventory_lot_id
LEFT JOIN ponds p ON p.id=g.pond_id
JOIN cost_categories c ON c.code=CASE
  WHEN LOWER(COALESCE(m.category,'')) LIKE '%feed%' OR m.category LIKE '%饲料%' OR m.name LIKE '%饲料%' THEN 'feed'
  WHEN LOWER(COALESCE(m.category,'')) REGEXP 'health|medicine|drug|disinfect' OR m.category REGEXP '动保|药|消毒' OR m.name REGEXP '动保|药|消毒' THEN 'health'
  ELSE 'other' END
WHERE d.status='verified' AND d.document_type IN ('issue','return')
  AND g.source_type IN ('issue','return','correction')
  AND NOT EXISTS (
    SELECT 1 FROM cost_entries ce
    WHERE ce.source_type='warehouse_ledger'
      AND CAST(JSON_UNQUOTE(JSON_EXTRACT(ce.source_detail_json,'$.inventory_ledger_id')) AS UNSIGNED)=g.id
  );

DROP TRIGGER IF EXISTS inventory_ledger_post_cost;
DELIMITER $$
CREATE TRIGGER inventory_ledger_post_cost AFTER INSERT ON inventory_ledger FOR EACH ROW
BEGIN
  DECLARE v_document_type VARCHAR(32);
  DECLARE v_organization_id BIGINT UNSIGNED;
  DECLARE v_farm_id BIGINT UNSIGNED;
  DECLARE v_area_id BIGINT UNSIGNED;
  DECLARE v_category_id BIGINT UNSIGNED;
  DECLARE v_cost_nature VARCHAR(16);
  DECLARE v_category_code VARCHAR(64);
  DECLARE v_document_code VARCHAR(64);
  DECLARE v_purchase_order_id BIGINT UNSIGNED;

  IF NEW.source_type IN ('issue','return','correction') THEN
    SELECT d.document_type,d.organization_id,d.farm_id,COALESCE(p.area_id,d.area_id,w.area_id),d.code,
      CASE
        WHEN LOWER(COALESCE(m.category,'')) LIKE '%feed%' OR m.category LIKE '%饲料%' OR m.name LIKE '%饲料%' THEN 'feed'
        WHEN LOWER(COALESCE(m.category,'')) REGEXP 'health|medicine|drug|disinfect' OR m.category REGEXP '动保|药|消毒' OR m.name REGEXP '动保|药|消毒' THEN 'health'
        ELSE 'other' END
    INTO v_document_type,v_organization_id,v_farm_id,v_area_id,v_document_code,v_category_code
    FROM warehouse_documents d
    JOIN warehouses w ON w.id=NEW.warehouse_id
    JOIN materials m ON m.id=NEW.material_id
    LEFT JOIN ponds p ON p.id=NEW.pond_id
    WHERE d.id=NEW.source_id;

    IF v_document_type IN ('issue','return') THEN
      SELECT id,default_nature INTO v_category_id,v_cost_nature
      FROM cost_categories WHERE code=v_category_code AND status='active';
      SELECT receipt.purchase_order_id INTO v_purchase_order_id
      FROM warehouse_documents receipt
      WHERE receipt.inventory_lot_id=NEW.inventory_lot_id AND receipt.document_type='receipt'
        AND receipt.status='verified' AND receipt.purchase_order_id IS NOT NULL
      ORDER BY receipt.id LIMIT 1;
      INSERT INTO cost_entries (
        organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,
        cost_nature,source_type,source_ref,source_detail_json,target_type,target_id,created_by,confirmed_by,confirmed_at
      ) VALUES (
        v_organization_id,v_farm_id,v_area_id,v_category_id,-NEW.quantity_delta*NEW.unit_cost,
        DATE(NEW.happened_at),DATE(NEW.happened_at),DATE(NEW.happened_at),'confirmed',v_cost_nature,
        'warehouse_ledger',v_document_code,
        JSON_OBJECT('inventory_ledger_id',NEW.id,'warehouse_document_id',NEW.source_id,'document_code',v_document_code,'material_id',NEW.material_id,
          'inventory_lot_id',NEW.inventory_lot_id,'purchase_order_id',v_purchase_order_id),
        CASE WHEN NEW.batch_id IS NOT NULL THEN 'batch' WHEN NEW.pond_id IS NOT NULL THEN 'pond' ELSE NULL END,
        COALESCE(NEW.batch_id,NEW.pond_id),NEW.posted_by,NEW.posted_by,CURRENT_TIMESTAMP
      );
    END IF;
  END IF;
END$$
DELIMITER ;
