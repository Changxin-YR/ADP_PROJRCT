SET NAMES utf8mb4;

DROP TRIGGER IF EXISTS record_revisions_no_update;
DROP TRIGGER IF EXISTS record_revisions_no_delete;

DELIMITER $$
CREATE TRIGGER record_revisions_no_update BEFORE UPDATE ON record_revisions FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='record revisions are append-only'$$
CREATE TRIGGER record_revisions_no_delete BEFORE DELETE ON record_revisions FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='record revisions are append-only'$$
DELIMITER ;
