import mysql.connector
import logging
import os

DATABASE_NAME = 'musicapp.db'

# 获取当前文件所在的目录，用于构建数据库文件的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, DATABASE_NAME)

# --- MySQL Configuration ---
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'musicdown_db',
    'password': 'Your_PASSWORD',
    'database': 'musicdown_db',
    'charset': 'utf8mb4' # Recommended for full Unicode support
}

# Configure logging for this module
logger = logging.getLogger(__name__)

def get_db_connection():
    """Establishes a connection to the MySQL database."""
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        # logger.debug("MySQL connection established.")
        return conn
    except mysql.connector.Error as err:
        logger.error(f"Error connecting to MySQL: {err}")
        # In a real app, you might want to raise this or handle it more gracefully
        raise  # Re-raise the exception if connection fails

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        logger.info("Table 'users' checked/created.")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS playlists (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            name VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        logger.info("Table 'playlists' checked/created.")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS playlist_songs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            playlist_id INT NOT NULL,
            song_api_index VARCHAR(255) NOT NULL, -- Can be non-integer from some APIs
            song_query TEXT NOT NULL,
            title VARCHAR(255) NOT NULL,
            singer VARCHAR(255),
            cover TEXT, -- URL, can be long
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
            UNIQUE KEY unique_song_in_playlist (playlist_id, song_api_index, song_query(255)) 
            -- Added (255) for song_query in unique key for TEXT type indexing limit
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        # Note on UNIQUE KEY for song_query: MySQL has limitations on indexing full TEXT columns.
        # A prefix length (e.g., 255) is often used for TEXT/BLOB columns in unique keys.
        # If song_query can be very long and identical up to 255 chars but different afterwards,
        # this could theoretically allow "duplicates" if only differentiated by the part beyond 255 chars.
        # For most practical purposes with song titles/queries, this should be fine.
        logger.info("Table 'playlist_songs' checked/created.")

        conn.commit()
        logger.info("Database tables initialized/verified successfully.")
    except mysql.connector.Error as err:
        logger.error(f"Error initializing database: {err}")
        if conn:
            conn.rollback() # Rollback any changes if an error occurs
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            # logger.debug("MySQL connection closed after init_db.")

# --- User Functions ---
def get_user_by_username(username):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True) # dictionary=True to get rows as dicts
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        return user
    except mysql.connector.Error as err:
        logger.error(f"Error fetching user by username '{username}': {err}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def get_user_by_id(user_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        return user
    except mysql.connector.Error as err:
        logger.error(f"Error fetching user by ID '{user_id}': {err}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def create_user(username):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username) VALUES (%s)", (username,))
        conn.commit()
        user_id = cursor.lastrowid # Get the ID of the newly inserted user
        if user_id:
            logger.info(f"User '{username}' created with ID {user_id}.")
            return {'id': user_id, 'username': username} # Return a dict similar to fetchone()
        else: # Should not happen if insert was successful without error
            logger.error(f"User '{username}' creation reported success but no lastrowid.")
            return None
    except mysql.connector.Error as err:
        if err.errno == 1062: # Error number for duplicate entry
            logger.warning(f"Attempted to create duplicate user '{username}'.")
            return get_user_by_username(username) # Return existing user
        logger.error(f"Error creating user '{username}': {err}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# --- Playlist Functions ---
def create_playlist(user_id, name):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO playlists (user_id, name) VALUES (%s, %s)", (user_id, name))
        conn.commit()
        playlist_id = cursor.lastrowid
        logger.info(f"Playlist '{name}' created for user_id {user_id} with playlist_id {playlist_id}.")
        return playlist_id
    except mysql.connector.Error as err:
        logger.error(f"Error creating playlist '{name}' for user_id {user_id}: {err}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def get_playlists_by_user_id(user_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM playlists WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
        playlists = cursor.fetchall()
        return playlists
    except mysql.connector.Error as err:
        logger.error(f"Error fetching playlists for user_id {user_id}: {err}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def get_playlist_by_id(playlist_id, user_id=None):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if user_id:
            cursor.execute("SELECT * FROM playlists WHERE id = %s AND user_id = %s", (playlist_id, user_id))
        else:
            cursor.execute("SELECT * FROM playlists WHERE id = %s", (playlist_id,))
        playlist = cursor.fetchone()
        return playlist
    except mysql.connector.Error as err:
        logger.error(f"Error fetching playlist ID {playlist_id}: {err}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def delete_playlist_by_id(playlist_id, user_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # First, verify ownership
        cursor.execute("SELECT user_id FROM playlists WHERE id = %s", (playlist_id,))
        playlist = cursor.fetchone()
        if not playlist or playlist[0] != user_id:
            logger.warning(f"User {user_id} attempted to delete playlist {playlist_id} without ownership.")
            return False
        
        # CASCADE delete should handle playlist_songs, but good to be aware
        cursor.execute("DELETE FROM playlists WHERE id = %s AND user_id = %s", (playlist_id, user_id))
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Playlist ID {playlist_id} deleted by user_id {user_id}.")
            return True
        logger.warning(f"Playlist ID {playlist_id} not found or not owned by user_id {user_id} during delete.")
        return False
    except mysql.connector.Error as err:
        logger.error(f"Error deleting playlist ID {playlist_id} by user_id {user_id}: {err}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# --- Playlist Song Functions ---
def add_song_to_playlist(playlist_id, song_api_index, song_query, title, singer, cover):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Check if song already exists (optional, as UNIQUE constraint handles it)
        # cursor.execute(
        #     "SELECT id FROM playlist_songs WHERE playlist_id = %s AND song_api_index = %s AND song_query = %s",
        #     (playlist_id, song_api_index, song_query)
        # )
        # existing_song = cursor.fetchone()
        # if existing_song:
        #     logger.info(f"Song '{title}' (API Index: {song_api_index}) already in playlist ID {playlist_id}.")
        #     return True, f"歌曲 '{title}' 已存在于歌单中。"

        cursor.execute("""
            INSERT INTO playlist_songs (playlist_id, song_api_index, song_query, title, singer, cover)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (playlist_id, song_api_index, song_query, title, singer, cover))
        conn.commit()
        logger.info(f"Song '{title}' (API Index: {song_api_index}) added to playlist ID {playlist_id}.")
        return True, f"歌曲 '{title}' 已成功添加到歌单。"
    except mysql.connector.Error as err:
        if err.errno == 1062: # Duplicate entry
            logger.warning(f"Song '{title}' (Query: {song_query}, API Index: {song_api_index}) already exists in playlist ID {playlist_id} due to UNIQUE constraint.")
            # Fetch the existing song details if needed, or just inform
            return True, f"歌曲 '{title}' 已存在于歌单中。"
        logger.error(f"Error adding song to playlist ID {playlist_id}: {err}")
        if conn:
            conn.rollback()
        return False, f"添加歌曲 '{title}' 到歌单时发生数据库错误。"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def remove_song_from_playlist(playlist_song_id, user_id):
    """Removes a song from a playlist. playlist_song_id is the ID from playlist_songs table."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verify ownership: check if the playlist_song_id belongs to a playlist owned by user_id
        # This is a bit more complex as it involves a join or subquery.
        cursor.execute("""
            SELECT ps.id 
            FROM playlist_songs ps
            JOIN playlists p ON ps.playlist_id = p.id
            WHERE ps.id = %s AND p.user_id = %s
        """, (playlist_song_id, user_id))
        song_to_delete = cursor.fetchone()

        if not song_to_delete:
            logger.warning(f"User {user_id} attempted to remove song (playlist_song_id: {playlist_song_id}) not found or not owned.")
            return False

        cursor.execute("DELETE FROM playlist_songs WHERE id = %s", (playlist_song_id,))
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Song (playlist_song_id: {playlist_song_id}) removed from playlist by user {user_id}.")
            return True
        # This case should ideally be caught by the check above
        logger.warning(f"Song (playlist_song_id: {playlist_song_id}) not found during delete for user {user_id}, though ownership check passed (should not happen).")
        return False
    except mysql.connector.Error as err:
        logger.error(f"Error removing song (playlist_song_id: {playlist_song_id}) from playlist by user {user_id}: {err}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def get_songs_in_playlist(playlist_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM playlist_songs 
            WHERE playlist_id = %s 
            ORDER BY added_at ASC 
        """, (playlist_id,)) # Changed to ASC to play in order added
        songs = cursor.fetchall()
        return songs
    except mysql.connector.Error as err:
        logger.error(f"Error fetching songs for playlist ID {playlist_id}: {err}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logger.info("Running database.py directly for testing...")
    
    # Test connection (implicitly tested by init_db)
    # init_db() # This will attempt to create tables

    # Example: Create a user
    # new_user = create_user("test_mysql_user")
    # if new_user:
    #     logger.info(f"Test user created/retrieved: {new_user}")
    #     # Example: Create a playlist for this user
    #     playlist_id = create_playlist(new_user['id'], "My Test MySQL Playlist")
    #     if playlist_id:
    #         logger.info(f"Test playlist created with ID: {playlist_id}")
            
    #         # Example: Add songs to playlist
    #         add_song_to_playlist(playlist_id, "api_idx_123", "test query", "Test Song 1", "Test Singer", "http://example.com/cover1.jpg")
    #         add_song_to_playlist(playlist_id, "api_idx_456", "another query", "Test Song 2", "Another Singer", "http://example.com/cover2.jpg")
            
    #         # Example: Get songs from playlist
    #         songs = get_songs_in_playlist(playlist_id)
    #         logger.info(f"Songs in playlist {playlist_id}: {songs}")

    # else:
    #     logger.error("Failed to create/retrieve test user.")
    logger.info("Finished database.py direct test run.") 