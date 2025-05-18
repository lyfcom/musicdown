# 聚合音乐平台 (Music Aggregator Web App)

一个基于 Flask 的 Web 应用程序，允许用户搜索来自多个来源的音乐、在线播放、下载 MP3 文件、管理播放列表以及查看播放历史。

## 主要功能

- **音乐搜索**: 搜索歌曲和艺术家。
- **在线播放**: 
    - 内建 HTML5 播放器，支持自定义控件和歌词同步。
    - 支持多种播放模式：普通播放、单曲循环、列表循环（搜索结果或歌单）、随机播放（搜索结果或歌单）。
    - 支持在当前播放列表（搜索结果或歌单）中进行上一首/下一首切换。
- **歌曲下载**: 下载 MP3 格式的歌曲，并嵌入元数据（如封面、标题、歌手）。
- **播放列表管理**: 
    - 用户可以创建自己的歌单，并向歌单中添加或移除歌曲。
    - 支持将整个歌单作为播放列表进行播放（包括"播放全部"功能）。
- **播放历史**: 自动记录用户播放过的歌曲。
- **最近搜索**: 保存用户最近的搜索词条，方便快速再次搜索。
- **用户系统**: 基于用户名的简单登录系统（无密码），数据与用户关联。
- **主题切换**: 支持多种 DaisyUI 主题，并持久化用户选择。
- **响应式设计**: 界面适配桌面和移动设备。
- **免责声明**: 用户首次访问时需同意免责声明方可使用。
- **自动清理**: 自动清理旧的已下载音乐文件（默认7天前），节约服务器空间。

## 技术栈

- **后端**: Python, Flask
- **数据库**: MySQL (之前是 SQLite)
- **数据库驱动**: mysql-connector-python
- **前端**: HTML, JavaScript
- **CSS框架**: DaisyUI, TailwindCSS
- **音乐处理**: mutagen (用于 MP3 元数据)
- **API请求**: requests

## 项目结构

```
musicdown/
├── __pycache__/                  # Python 缓存文件
├── static/                       # 静态资源
│   ├── css/custom.css            # 自定义 CSS 样式
│   ├── downloads/                # 用户下载的音乐文件
│   ├── images/                   # UI 图片 (如默认封面)
│   └── temp/                     # 临时文件 (如下载的封面)
├── templates/                    # HTML 模板
│   ├── layout.html               # 基础布局模板
│   ├── index.html                # 首页和搜索结果页
│   ├── song_player.html          # 歌曲播放页
│   ├── history.html              # 播放历史页
│   ├── my_playlists.html         # 用户歌单列表页
│   ├── playlist_detail.html      # 特定歌单详情页
│   └── login.html                # 登录页
├── app.py                        # Flask 主应用文件 (路由、视图函数)
├── database.py                   # 数据库初始化和操作函数 (MySQL 版本)
├── music_api_handler.py          # 处理音乐 API 交互、歌曲下载和元数据处理
├── requirements.txt              # Python 依赖包
└── README.md                     # 本文档
```
(注意: `musicapp.db` 文件已移除，因为数据库现在是 MySQL。)

## 安装与运行

1.  **先决条件**:
    *   **Python 3.x**
    *   **MySQL 服务器**: 确保您的系统上已安装并正在运行 MySQL 服务器。
    *   **Git** (可选, 用于克隆仓库)

2.  **克隆仓库** (如果项目在版本控制中):
    ```bash
    git clone <repository_url>
    cd musicdown
    ```

3.  **创建并激活虚拟环境**:
    -   Windows:
        ```bash
        python -m venv venv
        .\venv\Scripts\activate
        ```
    -   macOS/Linux:
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```

4.  **配置数据库**:
    *   **创建数据库**: 在您的 MySQL 服务器中创建一个数据库。例如，名为 `musicdown_db`。
        ```sql
        CREATE DATABASE IF NOT EXISTS musicdown_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
        ```
    *   **创建用户并授权 (推荐)**: 创建一个专用的 MySQL 用户，并授予其对上述数据库的权限。例如：
        ```sql
        CREATE USER 'musicdown_user'@'localhost' IDENTIFIED BY 'your_strong_password';
        GRANT ALL PRIVILEGES ON musicdown_db.* TO 'musicdown_user'@'localhost';
        FLUSH PRIVILEGES;
        ```
        (请将 `'your_strong_password'` 替换为您选择的强密码。)
    *   **更新 `database.py`**: 打开 `musicdown/database.py` 文件，修改 `MYSQL_CONFIG` 字典中的数据库连接信息，以匹配您的 MySQL 设置：
        ```python
        MYSQL_CONFIG = {
            'host': 'localhost',  # MySQL 服务器地址
            'user': 'musicdown_user', # 您创建的 MySQL 用户名
            'password': 'your_strong_password', # 您的 MySQL 用户密码
            'database': 'musicdown_db', # 您创建的数据库名
            'charset': 'utf8mb4'
        }
        ```
        *(在之前的步骤中，我们使用了您提供的特定凭据。这里作为通用指南说明。)*

5.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```
    (这将安装 Flask, requests, mutagen, 和 `mysql-connector-python` 等。)

6.  **运行应用与初始化数据库**:
    当您首次运行应用时，`database.init_db()` 函数会被调用，它会自动在您配置的 MySQL 数据库中创建所需的表。
    `app.py` 中 `if __name__ == '__main__':` 块内默认使用 `app.run(debug=True, host='0.0.0.0', port=5001)`。
    可以直接运行:
    ```bash
    python app.py
    ```
    或者使用 Flask CLI (如果 Flask 已正确安装并配置):
    ```bash
    flask run --host=0.0.0.0 --port=5001 
    ```
    (注意: 如果使用 `flask run`，它可能默认使用 5000 端口，除非通过环境变量或参数指定。直接运行 `python app.py` 会使用代码中指定的 5001 端口。)
    **监控应用启动时的日志输出，确保数据库表成功创建，并且没有连接错误。**

7.  **访问应用**:
    在浏览器中打开 `http://localhost:5001` (或您配置的主机和端口)。

## 关键模块和功能说明

### `app.py`
-   **Flask应用实例**: 初始化 Flask 应用，配置密钥、静态文件夹路径等。
-   **路由定义**: 使用 `@app.route()` 装饰器定义各个页面的 URL 和处理函数。
    -   `/`: 首页。
    -   `/search`: 处理音乐搜索请求。
    -   `/song/<query>/<song_api_index>`: 歌曲播放页面。此路由现在能够智能处理播放来源：
        -   如果通过 URL 参数指定了 `source=playlist` 和 `playlist_id`，则会将对应歌单作为播放列表。
        -   否则，默认使用 `query` 参数进行搜索，并将搜索结果作为播放列表。
        -   为播放器提供上一首/下一首导航所需的数据，适配不同来源。
    -   `/download/<query>/<song_api_index>`: 处理歌曲下载请求。
    -   `/history`, `/clear_history`: 播放历史相关。
    -   `/login`, `/logout`: 用户登录和登出。
    -   `/my_playlists`, `/playlist/create`, `/playlist/<id>`, `/playlist/delete/<id>`: 用户歌单管理。
    -   `/playlist/<playlist_id>/add_song`, `/playlist/<playlist_id>/remove_song/<song_id>`: 向歌单添加/移除歌曲。
-   **会话管理**: 使用 Flask `session` 存储用户信息、播放历史、最近搜索。
-   **数据库交互**: 调用 `database.py` 中的函数进行数据存取 (MySQL)。
-   **API交互**: 调用 `music_api_handler.py` 中的函数获取音乐数据。
-   **辅助函数**: 如 `@login_required` 装饰器保护需要登录的路由。
-   **上下文处理器**: 使用 `@app.context_processor` 向所有模板注入全局变量（例如 `current_year`）。
-   **自动清理**: 应用启动时调用 `cleanup_old_files` 函数清理 `static/downloads` 和 `static/temp` 目录中的旧文件。

### `music_api_handler.py`
此模块封装了与外部音乐源（尽管当前是模拟的或单一来源）的交互逻辑以及歌曲文件的处理。
-   `search_music(query)`: 根据查询词搜索音乐，返回歌曲列表。
-   `get_song_details(query, song_api_index)`: 获取特定歌曲的详细信息，包括播放链接、封面、歌词。
-   `download_song_assets_for_web(song_details, static_folder_path)`: 下载歌曲的音频文件和封面图片到服务器的 `static` 文件夹内，并嵌入MP3元数据。返回处理后的文件相对路径。
-   `parse_lrc_line(line)`: 解析 LRC 歌词行，提取时间戳和歌词文本。
-   `sanitize_filename(filename)`: 清理文件名，移除非法字符。
-   `clean_song_title(title)`: 清理歌曲标题中可能存在的无关字符。
-   `embed_mp3_metadata(mp3_path, title, artist, album, cover_image_path)`: 将元数据和封面嵌入到 MP3 文件中。

### `database.py`
负责所有与 MySQL 数据库相关的操作。
-   `init_db()`: 初始化数据库，连接到 MySQL 并创建 `users`, `playlists`, `playlist_songs` 表（如果它们不存在）。
-   `get_db_connection()`: 获取 MySQL 数据库连接。
-   **用户管理函数**:
    -   `create_user(username)`: 创建新用户。
    -   `get_user_by_username(username)`: 通过用户名获取用户信息。
    -   `get_user_by_id(user_id)`: 通过用户ID获取用户信息。
-   **歌单管理函数**:
    -   `create_playlist(user_id, name)`: 为用户创建新歌单。
    -   `get_playlists_by_user_id(user_id)`: 获取用户的所有歌单。
    -   `get_playlist_by_id(playlist_id, user_id=None)`: 获取特定歌单信息，可选用户ID验证所有权。
    -   `delete_playlist_by_id(playlist_id, user_id)`: 删除用户歌单（同时通过外键级联删除关联歌曲）。
-   **歌单歌曲管理函数**:
    -   `add_song_to_playlist(playlist_id, song_api_index, song_query, title, singer, cover)`: 向歌单添加歌曲，处理重复。返回 `(True/False, "消息")`。
    -   `remove_song_from_playlist(playlist_song_id, user_id)`: 从歌单移除歌曲，验证用户权限。
    -   `get_songs_in_playlist(playlist_id)`: 获取特定歌单中的所有歌曲 (按添加顺序升序排列)。

## 未来可改进方向

- **增强用户认证**: 实现基于密码的安全认证，密码哈希存储。
- **多音乐源支持**: 集成更多第三方音乐平台的 API。
- **API密钥管理**: 如果第三方 API 需要，安全地管理 API 密钥。
- **异步任务**: 对于下载等耗时操作，可以考虑使用 Celery 等进行异步处理，避免阻塞主应用。
- **测试**: 编写单元测试和集成测试，确保代码质量和功能稳定性。
- **错误处理和日志**: 进一步完善全局错误处理和更详细的日志记录。
- **前端组件化**: 如果项目规模扩大，可以考虑使用 Vue.js 或 React 等前端框架。
- **国际化与本地化**: 支持多语言界面。
- **配置管理**: 将数据库凭据等敏感信息从代码中分离到环境变量或配置文件。

### `templates/playlist_detail.html`
-   显示特定歌单的详细信息和歌曲列表。
-   提供"播放全部"按钮，允许用户将当前歌单加载到播放器进行播放。
-   允许用户从歌单中移除歌曲。 