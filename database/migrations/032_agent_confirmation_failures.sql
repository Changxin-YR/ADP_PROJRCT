ALTER TABLE agent_confirmations
  MODIFY status ENUM('pending','confirmed','failed','cancelled','expired') NOT NULL DEFAULT 'pending';
