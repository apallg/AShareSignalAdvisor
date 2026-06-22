-- Apallg投研 A股量化平台 - 数据库初始化脚本
-- 用法: mysql -u root -p < setup.sql
-- 或: mysql -u root -p -e "source setup.sql"

CREATE DATABASE IF NOT EXISTS `qilin_stock`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `qilin_stock`;

-- 持仓表
CREATE TABLE IF NOT EXISTS `holdings` (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(10) NOT NULL,
  name VARCHAR(50) NOT NULL,
  shares INT NOT NULL DEFAULT 0,
  cost_price DECIMAL(12,2) NOT NULL DEFAULT 0,
  buy_date DATE,
  alerts_enabled TINYINT(1) DEFAULT 1,
  risk_threshold INT DEFAULT 7,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 风控告警表
CREATE TABLE IF NOT EXISTS `risk_alerts` (
  id INT AUTO_INCREMENT PRIMARY KEY,
  stock_code VARCHAR(10) NOT NULL,
  stock_name VARCHAR(50) NOT NULL,
  risk_level VARCHAR(10) NOT NULL,
  risk_score INT NOT NULL,
  risk_detail TEXT,
  suggestion TEXT,
  notified TINYINT(1) DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_created (created_at),
  INDEX idx_stock (stock_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 设置表
CREATE TABLE IF NOT EXISTS `settings` (
  id INT AUTO_INCREMENT PRIMARY KEY,
  setting_key VARCHAR(100) NOT NULL UNIQUE,
  setting_value TEXT,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 分析历史表
CREATE TABLE IF NOT EXISTS `analysis_history` (
  id INT AUTO_INCREMENT PRIMARY KEY,
  stock_code VARCHAR(10),
  stock_name VARCHAR(50),
  analysis_type VARCHAR(50),
  analysis_result LONGTEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_type_created (analysis_type, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 日K线行情表
CREATE TABLE IF NOT EXISTS `daily_quotes` (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(10) NOT NULL,
  trade_date DATE NOT NULL,
  open DECIMAL(10,2),
  high DECIMAL(10,2),
  low DECIMAL(10,2),
  close DECIMAL(10,2),
  volume BIGINT,
  amount DECIMAL(16,2),
  amplitude DECIMAL(10,2),
  pct_chg DECIMAL(10,2),
  turnover DECIMAL(10,2),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_code_date (code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 通用数据缓存表
CREATE TABLE IF NOT EXISTS `data_cache` (
  cache_key VARCHAR(255) NOT NULL PRIMARY KEY,
  data_blob LONGBLOB NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  expires_at DATETIME,
  INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 情绪日度汇总表
CREATE TABLE IF NOT EXISTS `sentiment_daily` (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(10) NOT NULL,
  trade_date DATE NOT NULL,
  avg_score DECIMAL(10,4),
  pos_ratio DECIMAL(10,4),
  neg_ratio DECIMAL(10,4),
  news_count INT DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_code_date (code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 原始新闻表
CREATE TABLE IF NOT EXISTS `raw_news` (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(10) NOT NULL,
  title VARCHAR(500) NOT NULL,
  url VARCHAR(500),
  date VARCHAR(20),
  source VARCHAR(50),
  hash VARCHAR(12),
  collected_at DATETIME,
  INDEX idx_code_date (code, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 股票板块关联表
CREATE TABLE IF NOT EXISTS `stock_sectors` (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(10) NOT NULL,
  sector_name VARCHAR(100) NOT NULL,
  UNIQUE KEY uk_code_sector (code, sector_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 回测结果表
CREATE TABLE IF NOT EXISTS `backtest_results` (
  id VARCHAR(64) PRIMARY KEY,
  strategy_name VARCHAR(100),
  stock_code VARCHAR(10),
  params JSON,
  metrics JSON,
  trades LONGTEXT,
  equity_curve LONGTEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 选股扫描结果表
CREATE TABLE IF NOT EXISTS `scan_results` (
  id INT AUTO_INCREMENT PRIMARY KEY,
  stock_code VARCHAR(10),
  stock_name VARCHAR(50),
  price DECIMAL(12,2),
  pct_chg DECIMAL(10,2),
  ai_risk_score INT,
  risk_level VARCHAR(10),
  reason TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 委托记录表
CREATE TABLE IF NOT EXISTS `orders` (
  id VARCHAR(32) PRIMARY KEY,
  symbol VARCHAR(10) NOT NULL,
  name VARCHAR(50) NOT NULL,
  side VARCHAR(5) NOT NULL,
  quantity INT NOT NULL DEFAULT 0,
  price_type VARCHAR(10) NOT NULL DEFAULT 'market',
  price DECIMAL(12,3) NOT NULL DEFAULT 0,
  filled_qty INT DEFAULT 0,
  filled_price DECIMAL(12,3) DEFAULT 0,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_symbol (symbol),
  INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 成交记录表
CREATE TABLE IF NOT EXISTS `trades` (
  id VARCHAR(32) PRIMARY KEY,
  order_id VARCHAR(32) NOT NULL,
  symbol VARCHAR(10) NOT NULL,
  name VARCHAR(50) NOT NULL,
  side VARCHAR(5) NOT NULL,
  price DECIMAL(12,3) NOT NULL,
  quantity INT NOT NULL,
  amount DECIMAL(16,2) NOT NULL,
  commission DECIMAL(10,2) DEFAULT 0,
  stamp_duty DECIMAL(10,2) DEFAULT 0,
  trade_time DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_symbol (symbol),
  INDEX idx_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 账户资金表
CREATE TABLE IF NOT EXISTS `accounts` (
  id VARCHAR(32) PRIMARY KEY,
  cash DECIMAL(16,2) NOT NULL DEFAULT 0,
  frozen DECIMAL(16,2) NOT NULL DEFAULT 0,
  market_value DECIMAL(16,2) NOT NULL DEFAULT 0,
  total_assets DECIMAL(16,2) NOT NULL DEFAULT 0,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
