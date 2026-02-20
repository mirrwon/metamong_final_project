-- Metamong MySQL schema (MySQL 8.0+)
-- Design notes:
-- 1) Plant master/catalog data stays in Redis (see redisinsight_plants_v7.txt).
-- 2) Large binaries stay in S3. This schema stores only object keys/URLs.
-- 3) `saved_recos` keeps legacy columns used by current backend code.
-- 4) Relaxed column strictness: more nullable/text-friendly columns and no FK hard-fail.

SET NAMES utf8mb4;
SET time_zone = '+00:00';

CREATE DATABASE IF NOT EXISTS metamong
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE metamong;

CREATE TABLE IF NOT EXISTS users (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_num VARCHAR(64) NULL,
  username VARCHAR(255) NOT NULL,
  password_hash VARCHAR(255) NULL,
  name VARCHAR(255) NULL,
  birth_date VARCHAR(32) NULL,
  phone VARCHAR(64) NULL,
  email VARCHAR(512) NULL,
  gender VARCHAR(64) NULL,
  zipcode VARCHAR(64) NULL,
  address1 TEXT NULL,
  address2 TEXT NULL,
  provider VARCHAR(64) NULL DEFAULT 'local',
  oauth_sub VARCHAR(512) NULL,
  profile_image_s3_key TEXT NULL,
  profile_image_url TEXT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_username (username),
  KEY idx_users_user_num (user_num),
  KEY idx_users_provider_sub (provider, oauth_sub),
  KEY idx_users_email (email(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS diary_entries (
  id VARCHAR(128) NOT NULL,
  user_id BIGINT UNSIGNED NULL,
  title TEXT NULL,
  content LONGTEXT NULL,
  image_s3_key TEXT NULL,
  image_url TEXT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_diary_user_updated (user_id, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS plant_instances (
  id VARCHAR(128) NOT NULL,
  user_id BIGINT UNSIGNED NULL,
  name VARCHAR(255) NULL,
  source_plant_id VARCHAR(128) NULL COMMENT 'Redis plant id/key (example: plant:127)',
  source_plant_name TEXT NULL,
  created_by VARCHAR(64) NULL,
  cover_s3_key TEXT NULL,
  cover_url TEXT NULL,
  room_image_s3_key TEXT NULL,
  room_image_url TEXT NULL,
  room_image_pixel_s3_key TEXT NULL,
  room_image_pixel_url TEXT NULL,
  character_name VARCHAR(120) NULL,
  character_image_url TEXT NULL,
  personality VARCHAR(255) NULL,
  extra LONGTEXT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_plant_instances_user (user_id),
  KEY idx_plant_instances_user_created (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS plant_logs (
  id VARCHAR(128) NOT NULL,
  user_id BIGINT UNSIGNED NULL,
  plant_id VARCHAR(128) NULL,
  log_type VARCHAR(64) NULL,
  log_date VARCHAR(32) NULL,
  log_time VARCHAR(32) NULL,
  title TEXT NULL,
  detail LONGTEXT NULL,
  image_s3_key TEXT NULL,
  image_url TEXT NULL,
  source_plant_id VARCHAR(128) NULL,
  source_plant_name TEXT NULL,
  plant_image_url TEXT NULL,
  plant_character_name VARCHAR(120) NULL,
  plant_personality VARCHAR(255) NULL,
  room_image_url TEXT NULL,
  room_image_pixel_url TEXT NULL,
  meta LONGTEXT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_plant_logs_user_date (user_id, log_date, log_time),
  KEY idx_plant_logs_plant (plant_id),
  KEY idx_plant_logs_type (log_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Backward-compatible table used by current backend/app/api/chat_db.py
CREATE TABLE IF NOT EXISTS saved_recos (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NULL,
  client_key VARCHAR(255) NOT NULL,
  image_path TEXT NULL,
  image_s3_key TEXT NULL,
  result_json LONGTEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_saved_recos_client_created (client_key, created_at),
  KEY idx_saved_recos_user_created (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
