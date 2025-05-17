import sqlite3
import logging
import os

DATABASE_NAME = 'musicapp.db'

# 获取当前文件所在的目录，用于构建数据库文件的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, DATABASE_NAME)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_db_connection():
    """建立并返回数据库连接，开启行工厂模式以便按列名访问数据。"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row # 允许按列名访问数据
    return conn

def init_db():
    """初始化数据库，创建表结构（如果表不存在）。"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    logging.info("Users table checked/created.")

    # 歌单表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')
    logging.info("Playlists table checked/created.")

    # 歌单歌曲关联表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS playlist_songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER NOT NULL,
            song_api_index TEXT NOT NULL, 
            song_query TEXT NOT NULL,     
            title TEXT NOT NULL,
            singer TEXT,
            cover TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (playlist_id) REFERENCES playlists (id) ON DELETE CASCADE,
            UNIQUE(playlist_id, song_api_index, song_query) -- 确保同一歌单内歌曲的唯一性，基于API索引和原始查询
        )
    ''')
    logging.info("Playlist_songs table checked/created.")

    conn.commit()
    conn.close()
    logging.info("Database initialized successfully.")

# --- User Functions ---
def get_user_by_username(username):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return user

def get_user_by_id(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return user

def create_user(username):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (username) VALUES (?)', (username,))
        conn.commit()
        user_id = cursor.lastrowid
        logging.info(f"User '{username}' created with ID: {user_id}")
        return get_user_by_id(user_id)
    except sqlite3.IntegrityError:
        logging.warning(f"Attempted to create user '{username}' but username already exists.")
        return None # 用户名已存在
    finally:
        conn.close()

# --- Playlist Functions ---
def create_playlist(user_id, name):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO playlists (user_id, name) VALUES (?, ?)', (user_id, name))
        conn.commit()
        playlist_id = cursor.lastrowid
        logging.info(f"Playlist '{name}' created for user_id {user_id} with ID: {playlist_id}")
        return playlist_id
    except sqlite3.Error as e:
        logging.error(f"Error creating playlist for user {user_id}: {e}")
        return None
    finally:
        conn.close()

def get_playlists_by_user_id(user_id):
    conn = get_db_connection()
    playlists = conn.execute('SELECT * FROM playlists WHERE user_id = ? ORDER BY created_at DESC', (user_id,)).fetchall()
    conn.close()
    return playlists

def get_playlist_by_id(playlist_id, user_id=None):
    """获取特定歌单。如果提供了 user_id，则验证歌单是否属于该用户。"""
    conn = get_db_connection()
    query = 'SELECT * FROM playlists WHERE id = ?'
    params = (playlist_id,)
    if user_id:
        query += ' AND user_id = ?'
        params = (playlist_id, user_id)
    
    playlist = conn.execute(query, params).fetchone()
    conn.close()
    return playlist

def delete_playlist_by_id(playlist_id, user_id):
    """删除歌单，同时会通过 ON DELETE CASCADE 删除关联的 playlist_songs。"""
    conn = get_db_connection()
    try:
        # 首先确认歌单属于该用户
        playlist = get_playlist_by_id(playlist_id, user_id)
        if not playlist:
            logging.warning(f"Attempt to delete non-existent or unauthorized playlist ID {playlist_id} by user ID {user_id}.")
            return False
        
        cursor = conn.cursor()
        cursor.execute('DELETE FROM playlists WHERE id = ? AND user_id = ?', (playlist_id, user_id))
        conn.commit()
        deleted_count = cursor.rowcount
        if deleted_count > 0:
            logging.info(f"Playlist ID {playlist_id} deleted successfully by user ID {user_id}.")
            return True
        else:
            # 此情况理论上不应发生，因为前面已经验证了歌单所有权
            logging.warning(f"Playlist ID {playlist_id} not found or not owned by user ID {user_id} during delete operation.")
            return False
    except sqlite3.Error as e:
        logging.error(f"Error deleting playlist ID {playlist_id} for user {user_id}: {e}")
        return False
    finally:
        conn.close()

# --- Playlist Song Functions ---
def add_song_to_playlist(playlist_id, song_api_index, song_query, title, singer, cover):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO playlist_songs (playlist_id, song_api_index, song_query, title, singer, cover)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (playlist_id, song_api_index, song_query, title, singer, cover))
        conn.commit()
        logging.info(f"Song '{title}' (API Index: {song_api_index}) added to playlist ID {playlist_id}.")
        return True, f"歌曲 '{title}' 已成功添加到歌单。"
    except sqlite3.IntegrityError: # Handles UNIQUE constraint violation
        logging.warning(f"Song '{title}' (API Index: {song_api_index}) already exists in playlist ID {playlist_id}.")
        return True, f"歌曲 '{title}' 已存在于歌单中。" # Consider this a "success" in terms of user action, but inform about duplication
    except sqlite3.Error as e:
        logging.error(f"Error adding song to playlist ID {playlist_id}: {e}")
        return False, f"添加歌曲 '{title}' 到歌单时发生数据库错误。"
    finally:
        conn.close()

def remove_song_from_playlist(playlist_song_id, user_id):
    """从歌单移除歌曲，通过 playlist_song_id，并验证用户权限。"""
    conn = get_db_connection()
    try:
        # 验证用户是否有权删除此 playlist_song_id (通过其所属的 playlist_id)
        song_to_delete = conn.execute('''
            SELECT ps.id FROM playlist_songs ps
            JOIN playlists p ON ps.playlist_id = p.id
            WHERE ps.id = ? AND p.user_id = ?
        ''', (playlist_song_id, user_id)).fetchone()

        if not song_to_delete:
            logging.warning(f"Attempt to remove non-existent or unauthorized playlist_song ID {playlist_song_id} by user ID {user_id}.")
            return False

        cursor = conn.cursor()
        cursor.execute('DELETE FROM playlist_songs WHERE id = ?', (playlist_song_id,))
        conn.commit()
        if cursor.rowcount > 0:
            logging.info(f"Song with playlist_song_id {playlist_song_id} removed successfully by user ID {user_id}.")
            return True
        return False # Should not happen if song_to_delete was found
    except sqlite3.Error as e:
        logging.error(f"Error removing song with playlist_song_id {playlist_song_id}: {e}")
        return False
    finally:
        conn.close()

def get_songs_in_playlist(playlist_id):
    conn = get_db_connection()
    songs = conn.execute('''
        SELECT * FROM playlist_songs 
        WHERE playlist_id = ? 
        ORDER BY added_at DESC
    ''', (playlist_id,)).fetchall()
    conn.close()
    return songs

if __name__ == '__main__':
    logging.info("Initializing database from script...")
    init_db() 