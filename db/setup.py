"""
数据库初始化脚本 - 创建数据库和表
"""
import sys, os, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

def setup():
    logger.info("麒麟投研 - MySQL 数据库初始化")
    logger.info("=" * 40)
    if not config.MYSQL_PASSWORD or config.MYSQL_PASSWORD == "your_mysql_password_here":
        logger.error("请先编辑 .env 文件，填入 MYSQL_PASSWORD")
        logger.error("    示例: MYSQL_PASSWORD=your_root_password")
        return False
    import pymysql
    try:
        conn = pymysql.connect(
            host=config.MYSQL_HOST, port=config.MYSQL_PORT,
            user=config.MYSQL_USER, password=config.MYSQL_PASSWORD,
            charset="utf8mb4",
        )
        with conn.cursor() as cur:
            cur.execute(
                "CREATE DATABASE IF NOT EXISTS `" + config.MYSQL_DATABASE + "` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            logger.info("数据库 %s 已就绪", config.MYSQL_DATABASE)
        conn.close()
    except Exception as e:
        logger.error("连接 MySQL 失败: %s", e)
        return False
    from core.database import Database
    Database.create_tables()
    logger.info("所有数据表已创建")
    logger.info("MySQL 持久化就绪！")
    return True


if __name__ == "__main__":
    setup()
