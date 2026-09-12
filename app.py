import os
import sqlite3
import secrets
import hashlib
import mimetypes
from functools import wraps
from urllib.parse import quote

import requests
from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    render_template_string,
    send_from_directory,
)

# ============================================================
# HEARA
# Single-file social platform
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get("HEARA_SECRET_KEY", "heara-change-this-secret")

DATABASE = os.environ.get("HEARA_DB", "heara.db")
UPLOAD_FOLDER = os.path.join("static", "uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Pexels key is read from Render Environment Variables.
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "").strip()

LIVE_FOLLOWERS = 250
MAX_UPLOAD_MB = 100

ALLOWED_VIDEO = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
}

ALLOWED_IMAGE = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


# ============================================================
# DATABASE
# ============================================================

def db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def column_exists(connection, table, column):
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def add_column_if_missing(connection, table, column, definition):
    if not column_exists(connection, table, column):
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def init_db():
    connection = db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            avatar_url TEXT DEFAULT '',
            followers INTEGER DEFAULT 0,
            following INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            content TEXT DEFAULT '',
            media_url TEXT DEFAULT '',
            media_type TEXT DEFAULT '',
            source TEXT DEFAULT 'user',
            source_url TEXT DEFAULT '',
            creator_name TEXT DEFAULT '',
            creator_url TEXT DEFAULT '',
            caption TEXT DEFAULT '',
            views INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, post_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            comment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS follows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            follower_id INTEGER NOT NULL,
            following_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(follower_id, following_id),
            FOREIGN KEY(follower_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(following_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(receiver_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            actor_id INTEGER,
            notification_type TEXT NOT NULL,
            post_id INTEGER,
            text TEXT DEFAULT '',
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(actor_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE SET NULL
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS live_rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            room_code TEXT UNIQUE NOT NULL,
            title TEXT DEFAULT 'Live on Heara',
            is_live INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Upgrade older Heara databases safely.
    add_column_if_missing(connection, "users", "display_name", "TEXT DEFAULT ''")
    add_column_if_missing(connection, "users", "bio", "TEXT DEFAULT ''")
    add_column_if_missing(connection, "users", "avatar_url", "TEXT DEFAULT ''")
    add_column_if_missing(connection, "users", "followers", "INTEGER DEFAULT 0")
    add_column_if_missing(connection, "users", "following", "INTEGER DEFAULT 0")

    add_column_if_missing(connection, "posts", "source", "TEXT DEFAULT 'user'")
    add_column_if_missing(connection, "posts", "source_url", "TEXT DEFAULT ''")
    add_column_if_missing(connection, "posts", "creator_name", "TEXT DEFAULT ''")
    add_column_if_missing(connection, "posts", "creator_url", "TEXT DEFAULT ''")
    add_column_if_missing(connection, "posts", "caption", "TEXT DEFAULT ''")
    add_column_if_missing(connection, "posts", "views", "INTEGER DEFAULT 0")

    connection.commit()
    connection.close()


init_db()


# ============================================================
# HELPERS
# ============================================================

def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    connection = db()
    user = connection.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    connection.close()

    return user


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return function(*args, **kwargs)

    return wrapper


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def make_room_code():
    return secrets.token_urlsafe(8)


def safe_filename(filename):
    filename = os.path.basename(filename)
    filename = filename.replace(" ", "_")

    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    filename = "".join(c for c in filename if c in allowed)

    if not filename:
        filename = "upload"

    return filename


def save_upload(file):
    if not file or not file.filename:
        return None, None, "No file selected."

    file.seek(0, 2)
    size = file.tell()
    file.seek(0)

    if size > MAX_UPLOAD_MB * 1024 * 1024:
        return None, None, f"File is too large. Maximum is {MAX_UPLOAD_MB} MB."

    content_type = (file.mimetype or "").lower()

    if content_type in ALLOWED_VIDEO:
        media_type = "video"
    elif content_type in ALLOWED_IMAGE:
        media_type = "image"
    else:
        return None, None, "That file type is not supported."

    extension = os.path.splitext(file.filename)[1].lower()

    if not extension:
        extension = mimetypes.guess_extension(content_type) or ""

    filename = (
        secrets.token_hex(12)
        + extension
    )

    path = os.path.join(UPLOAD_FOLDER, filename)

    file.save(path)

    return (
        "/static/uploads/" + filename,
        media_type,
        None,
    )


def post_counts(connection, post_id, user_id=None):
    likes = connection.execute(
        "SELECT COUNT(*) AS c FROM likes WHERE post_id = ?",
        (post_id,)
    ).fetchone()["c"]

    comments = connection.execute(
        "SELECT COUNT(*) AS c FROM comments WHERE post_id = ?",
        (post_id,)
    ).fetchone()["c"]

    liked = False

    if user_id:
        liked = connection.execute(
            """
            SELECT 1 FROM likes
            WHERE post_id = ? AND user_id = ?
            """,
            (post_id, user_id)
        ).fetchone() is not None

    return likes, comments, liked


def enrich_post(row, user_id=None, connection=None):
    own_connection = False

    if connection is None:
        connection = db()
        own_connection = True

    likes, comments, liked = post_counts(
        connection,
        row["id"],
        user_id
    )

    data = dict(row)
    data["likes"] = likes
    data["comments"] = comments
    data["liked"] = liked

    if own_connection:
        connection.close()

    return data


def pexels_request(endpoint, params):
    if not PEXELS_API_KEY:
        return None, "Pexels API key is not configured."

    try:
        response = requests.get(
            "https://api.pexels.com/v1/" + endpoint,
            headers={
                "Authorization": PEXELS_API_KEY
            },
            params=params,
            timeout=15
        )

        if response.status_code != 200:
            return None, (
                f"Pexels returned HTTP {response.status_code}."
            )

        return response.json(), None

    except requests.RequestException as error:
        return None, str(error)


def choose_video_file(video):
    files = video.get("video_files") or []

    if not files:
        return None

    # Prefer portrait files.
    portrait = [
        item for item in files
        if item.get("height", 0) > item.get("width", 0)
    ]

    candidates = portrait or files

    # Prefer a reasonable HD/Full-HD file.
    candidates = sorted(
        candidates,
        key=lambda item: (
            abs((item.get("height") or 720) - 1280),
            abs((item.get("width") or 720) - 720)
        )
    )

    return candidates[0].get("link")


def get_pexels_videos(page=1, query=None):
    queries = [
        "trending",
        "people",
        "music",
        "fashion",
        "travel",
        "nature",
        "sports",
        "city",
        "lifestyle",
        "technology"
    ]

    if not query:
        query = queries[(page - 1) % len(queries)]

    data, error = pexels_request(
        "videos/search",
        {
            "query": query,
            "orientation": "portrait",
            "size": "medium",
            "page": page,
            "per_page": 12
        }
    )

    if error:
        return [], error

    videos = []

    for video in data.get("videos", []):
        link = choose_video_file(video)

        if not link:
            continue

        user = video.get("user") or {}

        videos.append({
            "id": "pexels-" + str(video.get("id")),
            "video_id": video.get("id"),
            "media_url": link,
            "thumbnail": video.get("image", ""),
            "duration": video.get("duration", 0),
            "creator_name": user.get("name", "Pexels Creator"),
            "creator_url": user.get("url", "https://www.pexels.com/")
            ,
            "source_url": video.get(
                "url",
                "https://www.pexels.com/videos/"
            ),
            "source": "pexels",
            "caption": "Discover on Heara"
        })

    return videos, None


# ============================================================
# SHARED PAGE DESIGN
# ============================================================

BASE_STYLE = """
<style>
* {
    box-sizing: border-box;
}

html, body {
    margin: 0;
    padding: 0;
    font-family: Inter, Arial, sans-serif;
    background:
        radial-gradient(circle at 15% 10%, rgba(104, 71, 255, .22), transparent 30%),
        radial-gradient(circle at 85% 20%, rgba(0, 220, 255, .13), transparent 28%),
        #070817;
    color: #fff;
    min-height: 100%;
}

body {
    overflow-x: hidden;
}

a {
    color: inherit;
    text-decoration: none;
}

button,
input,
textarea,
select {
    font: inherit;
}

button {
    cursor: pointer;
}

.nav {
    position: sticky;
    top: 0;
    z-index: 1000;
    height: 66px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 22px;
    background: rgba(7, 8, 23, .86);
    backdrop-filter: blur(18px);
    border-bottom: 1px solid rgba(255,255,255,.08);
}

.logo {
    font-size: 25px;
    font-weight: 900;
    letter-spacing: -.8px;
}

.logo span {
    background: linear-gradient(90deg, #9d6cff, #29e6ff);
    -webkit-background-clip: text;
    color: transparent;
}

.navlinks {
    display: flex;
    gap: 8px;
    align-items: center;
}

.navlinks a {
    padding: 10px 13px;
    border-radius: 12px;
    color: #bfc4db;
}

.navlinks a:hover {
    background: rgba(255,255,255,.07);
    color: white;
}

.container {
    width: min(1100px, calc(100% - 30px));
    margin: 30px auto;
}

.card {
    background: rgba(20, 22, 48, .75);
    border: 1px solid rgba(255,255,255,.09);
    border-radius: 22px;
    padding: 20px;
    box-shadow: 0 20px 70px rgba(0,0,0,.25);
}

.btn {
    border: 0;
    border-radius: 13px;
    padding: 11px 17px;
    color: white;
    background: linear-gradient(135deg, #7555ff, #3f9cff);
    font-weight: 800;
}

.btn.secondary {
    background: rgba(255,255,255,.09);
}

.btn.danger {
    background: #d93861;
}

input,
textarea,
select {
    width: 100%;
    background: rgba(0,0,0,.25);
    border: 1px solid rgba(255,255,255,.1);
    color: white;
    padding: 13px;
    border-radius: 13px;
    outline: none;
}

textarea {
    min-height: 120px;
    resize: vertical;
}

.form-group {
    margin-bottom: 15px;
}

.muted {
    color: #aeb3ca;
}

.error {
    background: rgba(255, 55, 90, .12);
    border: 1px solid rgba(255, 55, 90, .3);
    padding: 13px;
    border-radius: 12px;
    margin-bottom: 15px;
}

.success {
    background: rgba(50, 220, 150, .12);
    border: 1px solid rgba(50, 220, 150, .3);
    padding: 13px;
    border-radius: 12px;
}

.grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 18px;
}

.avatar {
    width: 46px;
    height: 46px;
    border-radius: 50%;
    object-fit: cover;
    background: linear-gradient(135deg, #7354ff, #25d8ff);
}

.post-media {
    width: 100%;
    max-height: 650px;
    object-fit: cover;
    border-radius: 17px;
    background: #000;
}

.post-actions {
    display: flex;
    gap: 8px;
    margin-top: 12px;
    flex-wrap: wrap;
}

.action-btn {
    background: rgba(255,255,255,.07);
    border: 1px solid rgba(255,255,255,.07);
    color: white;
    padding: 9px 13px;
    border-radius: 12px;
}

.action-btn.active {
    background: rgba(255,70,120,.2);
}

.footer {
    text-align: center;
    padding: 40px 20px;
    color: #858ba7;
}

@media(max-width: 700px) {
    .nav {
        padding: 0 12px;
    }

    .navlinks {
        gap: 2px;
    }

    .navlinks a {
        font-size: 12px;
        padding: 8px;
    }

    .container {
        width: calc(100% - 18px);
        margin: 18px auto;
    }
}
</style>
"""


def render_page(title, content):
    user = current_user()

    nav = f"""
    <nav class="nav">
        <a class="logo" href="{url_for('home')}">
            <span>Heara</span>
        </a>

        <div class="navlinks">
            <a href="{url_for('fyp')}">FYP</a>
            <a href="{url_for('home')}">Home</a>
            <a href="{url_for('create')}">＋ Post</a>
            <a href="{url_for('live')}">🔴 Live</a>
            {"<a href='" + url_for("inbox") + "'>💬</a>" if user else ""}
            {"<a href='" + url_for("notifications") + "'>🔔</a>" if user else ""}
            {
                "<a href='" + url_for("profile", username=user["username"]) + "'>Profile</a>"
                if user else
                "<a href='" + url_for("login") + "'>Login</a>"
            }
        </div>
    </nav>
    """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0"
        >
        <title>{title} — Heara</title>
        {BASE_STYLE}
    </head>
    <body>
        {nav}
        {content}
        <div class="footer">
            <strong>Heara</strong> · Your world. Your voice.
        </div>
    </body>
    </html>
    """


# ============================================================
# LANDING PAGE
# ============================================================

@app.route("/")
def home():
    user = current_user()

    connection = db()

    posts = connection.execute("""
        SELECT
            posts.*,
            users.username,
            users.display_name,
            users.avatar_url
        FROM posts
        LEFT JOIN users ON users.id = posts.user_id
        WHERE posts.source = 'user'
        ORDER BY posts.id DESC
        LIMIT 20
    """).fetchall()

    connection.close()

    cards = ""

    for post in posts:
        media = ""

        if post["media_type"] == "video":
            media = f"""
            <video
                class="post-media"
                src="{post["media_url"]}"
                controls
                playsinline
                preload="metadata">
            </video>
            """
        elif post["media_type"] == "image":
            media = f"""
            <img
                class="post-media"
                src="{post["media_url"]}"
                alt="Heara post">
            """

        author = post["display_name"] or post["username"] or "Heara user"

        cards += f"""
        <article class="card">
            <div style="display:flex;gap:12px;align-items:center;margin-bottom:13px;">
                <div>
                    <strong>{author}</strong><br>
                    <span class="muted">@{post["username"] or "heara"}</span>
                </div>
            </div>

            {media}

            <p>{post["caption"] or post["content"]}</p>

            <div class="post-actions">
                <button
                    class="action-btn"
                    onclick="shareHeara('{request.host_url}post/{post["id"]}')">
                    ↗ Share
                </button>
            </div>
        </article>
        """

    if not cards:
        cards = """
        <div class="card">
            <h2>Welcome to Heara 👋</h2>
            <p class="muted">
                Your social world starts here.
                Open FYP to discover videos.
            </p>
        </div>
        """

    content = f"""
    <main class="container">

        <section style="
            min-height:420px;
            display:grid;
            grid-template-columns:1fr 1fr;
            gap:30px;
            align-items:center;
        ">
            <div>
                <p class="muted">THE SOCIAL WORLD FOR YOU</p>

                <h1 style="
                    font-size:clamp(48px,8vw,88px);
                    line-height:.92;
                    margin:10px 0;
                ">
                    Hear<br>
                    <span style="
                        background:linear-gradient(90deg,#9d6cff,#29e6ff);
                        -webkit-background-clip:text;
                        color:transparent;
                    ">a.</span>
                </h1>

                <p class="muted" style="font-size:18px;max-width:550px;">
                    Discover videos, share your voice, connect with people,
                    message your friends and go live.
                </p>

                <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:22px;">
                    <a class="btn" href="{url_for('fyp')}">
                        Explore FYP
                    </a>
                    {
                        f"<a class='btn secondary' href='{url_for('create')}'>Create</a>"
                        if user else
                        f"<a class='btn secondary' href='{url_for('register')}'>Join Heara</a>"
                    }
                </div>
            </div>

            <div style="text-align:center;">
                <img
                    src="{url_for('static', filename='images/heara-hero.png')}"
                    alt="Heara"
                    style="
                        width:min(100%,480px);
                        max-height:430px;
                        object-fit:contain;
                        filter:drop-shadow(0 25px 70px rgba(95,70,255,.35));
                    "
                    onerror="this.style.display='none';"
                >
            </div>
        </section>

        <h2>Latest on Heara</h2>

        <section class="grid">
            {cards}
        </section>

    </main>

    <script>
    async function shareHeara(url) {{
        if (navigator.share) {{
            try {{
                await navigator.share({{
                    title: "Heara",
                    text: "Check this out on Heara",
                    url: url
                }});
                return;
            }} catch (e) {{}}
        }}

        try {{
            await navigator.clipboard.writeText(url);
            alert("Heara link copied!");
        }} catch (e) {{
            prompt("Copy this Heara link:", url);
        }}
    }}
    </script>
    """

    return render_page("Home", content)


# ============================================================
# FYP — PEXELS
# ============================================================

@app.route("/fyp")
@app.route("/videos")
def fyp():
    page = max(1, request.args.get("page", 1, type=int))
    query = request.args.get("q", "").strip() or None

    videos, error = get_pexels_videos(page, query)

    user = current_user()

    video_html = ""

    for index, video in enumerate(videos):
        share_url = request.host_url.rstrip("/") + "/pexels/" + str(
            video["video_id"]
        )

        video_html += f"""
        <section class="fyp-slide" data-index="{index}">
            <video
                class="fyp-video"
                src="{video["media_url"]}"
                poster="{video["thumbnail"]}"
                playsinline
                loop
                preload="metadata"
                data-video-id="{video["video_id"]}">
            </video>

            <div class="fyp-gradient"></div>

            <div class="fyp-info">
                <div class="fyp-creator">
                    <strong>@{video["creator_name"]}</strong>
                </div>

                <p>{video["caption"]}</p>

                <a
                    href="{video["source_url"]}"
                    target="_blank"
                    rel="noopener"
                    class="pexels-credit">
                    Video by {video["creator_name"]} on Pexels
                </a>
            </div>

            <div class="fyp-actions">
                <button
                    class="fyp-action"
                    onclick="toggleLikeVisual(this)">
                    ❤️
                    <span>Like</span>
                </button>

                <button
                    class="fyp-action"
                    onclick="openCommentBox(this)">
                    💬
                    <span>Comment</span>
                </button>

                <button
                    class="fyp-action"
                    onclick="shareHeara('{share_url}')">
                    ↗️
                    <span>Share</span>
                </button>

                <button
                    class="fyp-action sound-button"
                    onclick="toggleSound(this)">
                    🔇
                    <span>Sound</span>
                </button>

                <button
                    class="fyp-action"
                    onclick="this.closest('.fyp-slide').querySelector('video').requestFullscreen()">
                    ⛶
                    <span>Full</span>
                </button>
            </div>

            <div class="comment-box">
                <input
                    placeholder="Write a comment..."
                    onkeydown="
                        if(event.key==='Enter') {{
                            this.value='';
                            this.blur();
                        }}
                    "
                >
            </div>
        </section>
        """

    if not video_html:
        if error:
            video_html = f"""
            <section class="fyp-error">
                <h2>FYP couldn't load right now.</h2>
                <p>{error}</p>
                <button class="btn" onclick="location.reload()">
                    Try again
                </button>
            </section>
            """
        else:
            video_html = """
            <section class="fyp-error">
                <h2>No videos found.</h2>
                <button class="btn" onclick="location.reload()">
                    Refresh
                </button>
            </section>
            """

    content = f"""
    <style>
    body {
        overflow:hidden;
    }

    .fyp-wrap {
        position:fixed;
        top:66px;
        left:0;
        right:0;
        bottom:0;
        background:#000;
    }

    .fyp-feed {
        height:100%;
        overflow-y:auto;
        scroll-snap-type:y mandatory;
        scrollbar-width:none;
        overscroll-behavior-y:contain;
    }

    .fyp-feed::-webkit-scrollbar {
        display:none;
    }

    .fyp-slide {
        position:relative;
        height:100%;
        min-height:100%;
        scroll-snap-align:start;
        scroll-snap-stop:always;
        background:#000;
        overflow:hidden;
    }

    .fyp-video {
        position:absolute;
        inset:0;
        width:100%;
        height:100%;
        object-fit:cover;
        background:#000;
    }

    .fyp-gradient {
        position:absolute;
        inset:0;
        pointer-events:none;
        background:
            linear-gradient(
                to top,
                rgba(0,0,0,.86),
                transparent 35%,
                rgba(0,0,0,.08)
            );
    }

    .fyp-info {
        position:absolute;
        left:25px;
        bottom:30px;
        width:min(65%,600px);
        z-index:5;
        text-shadow:0 2px 12px #000;
    }

    .fyp-info p {
        margin:9px 0;
        font-size:17px;
    }

    .pexels-credit {
        color:#fff;
        text-decoration:underline;
        font-size:12px;
        opacity:.85;
    }

    .fyp-actions {
        position:absolute;
        right:22px;
        bottom:28px;
        z-index:10;
        display:flex;
        flex-direction:column;
        gap:11px;
        align-items:center;
    }

    .fyp-action {
        border:0;
        color:white;
        background:rgba(0,0,0,.48);
        backdrop-filter:blur(10px);
        width:62px;
        min-height:58px;
        border-radius:18px;
        display:flex;
        flex-direction:column;
        justify-content:center;
        align-items:center;
        gap:3px;
        font-size:20px;
    }

    .fyp-action span {
        font-size:9px;
        color:#ddd;
    }

    .fyp-action:hover {
        background:rgba(117,85,255,.65);
    }

    .comment-box {
        display:none;
        position:absolute;
        bottom:110px;
        left:20px;
        right:100px;
        z-index:20;
    }

    .comment-box input {
        background:rgba(10,10,20,.92);
    }

    .fyp-error {
        height:100%;
        display:flex;
        flex-direction:column;
        justify-content:center;
        align-items:center;
        text-align:center;
        padding:30px;
        background:
            radial-gradient(circle,#241c58,#05050c 65%);
    }

    @media(max-width:700px) {
        .fyp-wrap {
            top:58px;
        }

        .fyp-info {
            left:14px;
            bottom:20px;
            width:70%;
        }

        .fyp-actions {
            right:9px;
            bottom:18px;
        }

        .fyp-action {
            width:53px;
            min-height:52px;
            border-radius:15px;
        }
    }
    </style>

    <div class="fyp-wrap">
        <div class="fyp-feed" id="fypFeed">
            {video_html}
        </div>
    </div>

    <script>
    const feed = document.getElementById("fypFeed");

    function toggleLikeVisual(button) {{
        button.classList.toggle("liked");
        button.firstChild.textContent =
            button.classList.contains("liked") ? "❤️" : "🤍";
    }}

    function openCommentBox(button) {{
        const slide = button.closest(".fyp-slide");
        const box = slide.querySelector(".comment-box");

        box.style.display =
            box.style.display === "block" ? "none" : "block";

        if (box.style.display === "block") {{
            box.querySelector("input").focus();
        }}
    }}

    function toggleSound(button) {{
        const slide = button.closest(".fyp-slide");
        const video = slide.querySelector("video");

        video.muted = !video.muted;

        button.firstChild.textContent =
            video.muted ? "🔇" : "🔊";
    }}

    async function shareHeara(url) {{
        if (navigator.share) {{
            try {{
                await navigator.share({{
                    title: "Heara",
                    text: "Check this video on Heara",
                    url: url
                }});
                return;
            }} catch (e) {{}}
        }}

        try {{
            await navigator.clipboard.writeText(url);
            alert("Heara link copied!");
        }} catch (e) {{
            prompt("Copy this Heara link:", url);
        }}
    }}

    function playVisibleVideos() {{
        const videos = document.querySelectorAll(".fyp-video");

        videos.forEach(video => {{
            if (video.closest(".fyp-slide").classList.contains("visible")) {{
                video.play().catch(() => {{}});
            }} else {{
                video.pause();
            }}
        }});
    }}

    const observer = new IntersectionObserver(
        entries => {{
            entries.forEach(entry => {{
                const slide = entry.target;
                const video = slide.querySelector("video");

                if (entry.isIntersecting && entry.intersectionRatio > .65) {{
                    slide.classList.add("visible");

                    // Browsers normally require autoplay to be muted.
                    video.muted = true;
                    video.play().catch(() => {{}});
                }} else {{
                    slide.classList.remove("visible");
                    video.pause();
                }}
            }});
        }},
        {{
            root: feed,
            threshold: [0, .65, 1]
        }}
    );

    document.querySelectorAll(".fyp-slide").forEach(slide => {{
        observer.observe(slide);
    }});

    // Keyboard support.
    document.addEventListener("keydown", event => {{
        if (event.key === "ArrowDown") {{
            feed.scrollBy({{
                top: window.innerHeight,
                behavior:"smooth"
            }});
        }}

        if (event.key === "ArrowUp") {{
            feed.scrollBy({{
                top: -window.innerHeight,
                behavior:"smooth"
            }});
        }}
    }});

    // Mouse wheel support.
    let wheelLock = false;

    feed.addEventListener("wheel", event => {{
        if (wheelLock) return;

        wheelLock = true;

        feed.scrollBy({{
            top: event.deltaY > 0
                ? window.innerHeight
                : -window.innerHeight,
            behavior:"smooth"
        }});

        setTimeout(() => wheelLock = false, 650);
    }}, {{passive:true}});

    // Load another Pexels page near the end.
    feed.addEventListener("scroll", () => {{
        if (
            feed.scrollTop + feed.clientHeight
            >= feed.scrollHeight - feed.clientHeight * 1.5
        ) {{
            const currentPage = {page};

            if (!window.hearaLoadingMore) {{
                window.hearaLoadingMore = true;

                const query = {json.dumps(query or "")};

                const next =
                    "/fyp?page=" +
                    (currentPage + 1) +
                    (query ? "&q=" + encodeURIComponent(query) : "");

                fetch(next)
                    .then(response => response.text())
                    .then(html => {{
                        // The server-rendered next page is intentionally
                        // not injected directly because that would duplicate
                        // the complete document.
                        //
                        // Instead, navigate when the current batch is nearly
                        // finished.
                        window.hearaLoadingMore = false;
                    }})
                    .catch(() => {{
                        window.hearaLoadingMore = false;
                    }});
            }}
        }}
    }});

    // First video.
    setTimeout(() => {{
        const first = document.querySelector(".fyp-slide");

        if (first) {{
            first.classList.add("visible");

            const video = first.querySelector("video");
            video.muted = true;
            video.play().catch(() => {{}});
        }}
    }}, 250);
    </script>
    """

    return render_page("For You", content)


# ============================================================
# CREATE / POST
# ============================================================

@app.route("/create", methods=["GET", "POST"])
@login_required
def create():
    user = current_user()
    error = ""

    if request.method == "POST":
        caption = request.form.get("caption", "").strip()
        content = request.form.get("content", "").strip()
        post_type = request.form.get("post_type", "text")

        media_url = ""
        media_type = ""

        uploaded = request.files.get("media")

        if uploaded and uploaded.filename:
            media_url, media_type, upload_error = save_upload(uploaded)

            if upload_error:
                error = upload_error

        elif post_type == "text":
            media_type = ""

        else:
            error = "Please choose a photo or video."

        if not error and not caption and not content and not media_url:
            error = "Your post is empty."

        if not error:
            connection = db()

            connection.execute("""
                INSERT INTO posts (
                    user_id,
                    content,
                    media_url,
                    media_type,
                    source,
                    caption
                )
                VALUES (?, ?, ?, ?, 'user', ?)
            """, (
                user["id"],
                content,
                media_url,
                media_type,
                caption
            ))

            connection.commit()
            connection.close()

            return redirect(url_for("home"))

    content = f"""
    <main class="container">

        <div class="card" style="max-width:750px;margin:auto;">

            <h1>Create on Heara</h1>

            <p class="muted">
                Record something, choose a video/photo from your device,
                or simply write a post.
            </p>

            {"<div class='error'>" + error + "</div>" if error else ""}

            <form
                method="POST"
                enctype="multipart/form-data"
                id="postForm">

                <div class="form-group">
                    <label><strong>What are you posting?</strong></label>

                    <select name="post_type" id="postType">
                        <option value="text">📝 Text</option>
                        <option value="video">🎥 Video</option>
                        <option value="image">📷 Photo</option>
                    </select>
                </div>

                <div
                    class="form-group"
                    id="mediaArea"
                    style="display:none;">

                    <label><strong>Choose media</strong></label>

                    <input
                        type="file"
                        name="media"
                        id="mediaInput"
                        accept="video/*,image/*">

                    <div style="display:flex;gap:10px;margin-top:12px;flex-wrap:wrap;">

                        <button
                            type="button"
                            class="btn"
                            onclick="startCamera()">
                            📹 Camera
                        </button>

                        <button
                            type="button"
                            class="btn secondary"
                            onclick="stopCamera()">
                            Stop camera
                        </button>
                    </div>

                    <video
                        id="cameraPreview"
                        autoplay
                        playsinline
                        muted
                        style="
                            display:none;
                            width:100%;
                            margin-top:15px;
                            border-radius:18px;
                            background:#000;
                        ">
                    </video>

                    <button
                        type="button"
                        class="btn"
                        id="recordButton"
                        onclick="toggleRecording()"
                        style="display:none;margin-top:10px;">
                        🔴 Start recording
                    </button>

                    <video
                        id="recordedPreview"
                        controls
                        playsinline
                        style="
                            display:none;
                            width:100%;
                            margin-top:15px;
                            border-radius:18px;
                            background:#000;
                        ">
                    </video>
                </div>

                <div class="form-group">
                    <label><strong>Caption</strong></label>

                    <textarea
                        name="caption"
                        placeholder="Say something about your post..."></textarea>
                </div>

                <div class="form-group" id="textArea">
                    <label><strong>Text post</strong></label>

                    <textarea
                        name="content"
                        placeholder="What's happening?"></textarea>
                </div>

                <button class="btn" type="submit">
                    Publish to Heara
                </button>

            </form>
        </div>

    </main>

    <script>
    let cameraStream = null;
    let recorder = null;
    let recordedChunks = [];

    const postType = document.getElementById("postType");
    const mediaArea = document.getElementById("mediaArea");
    const textArea = document.getElementById("textArea");
    const mediaInput = document.getElementById("mediaInput");

    postType.addEventListener("change", () => {{
        const type = postType.value;

        mediaArea.style.display =
            type === "video" || type === "image"
                ? "block"
                : "none";

        textArea.style.display =
            type === "text" ? "block" : "block";

        if (type === "video") {{
            mediaInput.accept = "video/*";
        }} else if (type === "image") {{
            mediaInput.accept = "image/*";
        }}
    }});

    async function startCamera() {{
        try {{
            cameraStream = await navigator.mediaDevices.getUserMedia({{
                video:true,
                audio:true
            }});

            const preview =
                document.getElementById("cameraPreview");

            preview.srcObject = cameraStream;
            preview.style.display = "block";

            document.getElementById("recordButton")
                .style.display = "inline-block";

        }} catch (error) {{
            alert(
                "Camera permission was not granted or your browser does not support camera access."
            );
        }}
    }}

    function stopCamera() {{
        if (cameraStream) {{
            cameraStream.getTracks().forEach(track => track.stop());
            cameraStream = null;
        }}

        document.getElementById("cameraPreview")
            .style.display = "none";

        document.getElementById("recordButton")
            .style.display = "none";
    }}

    function toggleRecording() {{
        const button =
            document.getElementById("recordButton");

        if (recorder && recorder.state === "recording") {{
            recorder.stop();
            button.textContent = "🔴 Start recording";
            return;
        }}

        if (!cameraStream) {{
            alert("Start the camera first.");
            return;
        }}

        recordedChunks = [];

        let options = {{}};

        if (MediaRecorder.isTypeSupported("video/webm;codecs=vp9,opus")) {{
            options.mimeType = "video/webm;codecs=vp9,opus";
        }} else if (MediaRecorder.isTypeSupported("video/webm")) {{
            options.mimeType = "video/webm";
        }}

        recorder = new MediaRecorder(
            cameraStream,
            options
        );

        recorder.ondataavailable = event => {{
            if (event.data.size > 0) {{
                recordedChunks.push(event.data);
            }}
        }};

        recorder.onstop = () => {{
            const blob = new Blob(
                recordedChunks,
                {{type: recorder.mimeType || "video/webm"}}
            );

            const file = new File(
                [blob],
                "heara-camera.webm",
                {{type: blob.type}}
            );

            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);

            mediaInput.files = dataTransfer.files;

            const preview =
                document.getElementById("recordedPreview");

            preview.src = URL.createObjectURL(blob);
            preview.style.display = "block";
        }};

        recorder.start();

        button.textContent = "⏹ Stop recording";
    }}

    document.getElementById("mediaInput")
        .addEventListener("change", event => {{
            const file = event.target.files[0];

            if (!file) return;

            const preview =
                document.getElementById("recordedPreview");

            if (file.type.startsWith("video/")) {{
                preview.src = URL.createObjectURL(file);
                preview.style.display = "block";
            }}
        }});
    </script>
    """

    return render_page("Create", content)


# ============================================================
# POST DETAILS
# ============================================================

@app.route("/post/<int:post_id>")
def post_detail(post_id):
    connection = db()

    post = connection.execute("""
        SELECT
            posts.*,
            users.username,
            users.display_name,
            users.avatar_url
        FROM posts
        LEFT JOIN users ON users.id = posts.user_id
        WHERE posts.id = ?
    """, (post_id,)).fetchone()

    if not post:
        connection.close()
        return "Post not found", 404

    user = current_user()

    comments = connection.execute("""
        SELECT
            comments.*,
            users.username,
            users.display_name
        FROM comments
        JOIN users ON users.id = comments.user_id
        WHERE comments.post_id = ?
        ORDER BY comments.id ASC
    """, (post_id,)).fetchall()

    likes, comment_count, liked = post_counts(
        connection,
        post_id,
        user["id"] if user else None
    )

    connection.close()

    media = ""

    if post["media_type"] == "video":
        media = f"""
        <video
            class="post-media"
            src="{post["media_url"]}"
            controls
            playsinline>
        </video>
        """

    elif post["media_type"] == "image":
        media = f"""
        <img
            class="post-media"
            src="{post["media_url"]}"
            alt="Heara post">
        """

    comment_html = ""

    for comment in comments:
        name = comment["display_name"] or comment["username"]

        comment_html += f"""
        <div style="
            padding:12px 0;
            border-bottom:1px solid rgba(255,255,255,.06);
        ">
            <strong>@{name}</strong>
            <div class="muted">{comment["comment"]}</div>
        </div>
        """

    user_actions = ""

    if user:
        user_actions = f"""
        <form method="POST" action="{url_for('comment', post_id=post_id)}">
            <div style="display:flex;gap:8px;">
                <input
                    name="comment"
                    placeholder="Write a comment..."
                    required>
                <button class="btn">Send</button>
            </div>
        </form>
        """

    content = f"""
    <main class="container">
        <div class="card" style="max-width:750px;margin:auto;">

            <h2>
                {post["display_name"] or post["username"] or "Heara creator"}
            </h2>

            {media}

            <p>{post["caption"] or post["content"]}</p>

            <div class="post-actions">

                {
                    f'''
                    <form method="POST" action="{url_for("like", post_id=post_id)}">
                        <button class="action-btn">
                            {"❤️" if liked else "🤍"} {likes}
                        </button>
                    </form>
                    '''
                    if user else
                    f"<span class='muted'>❤️ {likes}</span>"
                }

                <button
                    class="action-btn"
                    onclick="shareHeara(location.href)">
                    ↗ Share
                </button>
            </div>

            <hr style="border-color:rgba(255,255,255,.08);margin:25px 0;">

            <h3>Comments · {comment_count}</h3>

            {comment_html or "<p class='muted'>No comments yet.</p>"}

            {user_actions}

        </div>
    </main>

    <script>
    async function shareHeara(url) {{
        if (navigator.share) {{
            try {{
                await navigator.share({{
                    title:"Heara",
                    text:"Check this out on Heara",
                    url:url
                }});
                return;
            }} catch(e) {{}}
        }}

        try {{
            await navigator.clipboard.writeText(url);
            alert("Heara link copied!");
        }} catch(e) {{
            prompt("Copy this link:", url);
        }}
    }}
    </script>
    """

    return render_page("Post", content)


# ============================================================
# LIKE
# ============================================================

@app.route("/like/<int:post_id>", methods=["POST"])
@login_required
def like(post_id):
    user = current_user()

    connection = db()

    existing = connection.execute("""
        SELECT id
        FROM likes
        WHERE user_id = ? AND post_id = ?
    """, (user["id"], post_id)).fetchone()

    if existing:
        connection.execute(
            "DELETE FROM likes WHERE id = ?",
            (existing["id"],)
        )
    else:
        connection.execute("""
            INSERT OR IGNORE INTO likes(user_id, post_id)
            VALUES (?, ?)
        """, (user["id"], post_id))

    connection.commit()
    connection.close()

    return redirect(
        request.referrer or url_for("post_detail", post_id=post_id)
    )


# ============================================================
# COMMENTS
# ============================================================

@app.route("/comment/<int:post_id>", methods=["POST"])
@login_required
def comment(post_id):
    user = current_user()

    text = request.form.get("comment", "").strip()

    if text:
        connection = db()

        connection.execute("""
            INSERT INTO comments(user_id, post_id, comment)
            VALUES (?, ?, ?)
        """, (user["id"], post_id, text))

        connection.commit()
        connection.close()

    return redirect(
        request.referrer or url_for("post_detail", post_id=post_id)
    )


# ============================================================
# PROFILE
# ============================================================

@app.route("/profile/<username>")
def profile(username):
    connection = db()

    profile_user = connection.execute(
        "SELECT * FROM users WHERE username = ?",
        (username,)
    ).fetchone()

    if not profile_user:
        connection.close()
        return "User not found", 404

    posts = connection.execute("""
        SELECT *
        FROM posts
        WHERE user_id = ?
        ORDER BY id DESC
    """, (profile_user["id"],)).fetchall()

    me = current_user()

    is_following = False

    if me:
        is_following = connection.execute("""
            SELECT 1
            FROM follows
            WHERE follower_id = ?
              AND following_id = ?
        """, (me["id"], profile_user["id"])).fetchone() is not None

    connection.close()

    media_cards = ""

    for post in posts:
        media = ""

        if post["media_type"] == "video":
            media = f"""
            <video
                class="post-media"
                src="{post["media_url"]}"
                controls
                playsinline>
            </video>
            """

        elif post["media_type"] == "image":
            media = f"""
            <img class="post-media" src="{post["media_url"]}">
            """

        media_cards += f"""
        <article class="card">
            {media}
            <p>{post["caption"] or post["content"]}</p>

            <a class="btn secondary"
               href="{url_for('post_detail', post_id=post["id"])}">
                Open post
            </a>
        </article>
        """

    follow_button = ""

    if me and me["id"] != profile_user["id"]:
        follow_button = f"""
        <form method="POST"
              action="{url_for(
                  "unfollow" if is_following else "follow",
                  user_id=profile_user["id"]
              )}">
            <button class="btn">
                {"Following ✓" if is_following else "Follow"}
            </button>
        </form>
        """

    content = f"""
    <main class="container">

        <section class="card">

            <div style="
                display:flex;
                align-items:center;
                gap:18px;
                flex-wrap:wrap;
            ">

                <div
                    style="
                        width:90px;
                        height:90px;
                        border-radius:50%;
                        background:linear-gradient(135deg,#7655ff,#2de3ff);
                        display:flex;
                        align-items:center;
                        justify-content:center;
                        font-size:32px;
                        font-weight:900;
                    ">
                    {(profile_user["username"][:1] or "H").upper()}
                </div>

                <div style="flex:1;">
                    <h1 style="margin:0;">
                        {profile_user["display_name"] or profile_user["username"]}
                    </h1>

                    <p class="muted">
                        @{profile_user["username"]}
                    </p>

                    <p>{profile_user["bio"]}</p>

                    <p class="muted">
                        {profile_user["followers"]} followers
                        · {profile_user["following"]} following
                    </p>
                </div>

                {follow_button}

            </div>
        </section>

        <h2>Posts</h2>

        <section class="grid">
            {media_cards or "<div class='card'><p class='muted'>No posts yet.</p></div>"}
        </section>

    </main>
    """

    return render_page(
        "@" + profile_user["username"],
        content
    )


# ============================================================
# FOLLOW
# ============================================================

@app.route("/follow/<int:user_id>", methods=["POST"])
@login_required
def follow(user_id):
    me = current_user()

    if me["id"] == user_id:
        return redirect(request.referrer or url_for("home"))

    connection = db()

    existing = connection.execute("""
        SELECT id FROM follows
        WHERE follower_id = ?
          AND following_id = ?
    """, (me["id"], user_id)).fetchone()

    if not existing:
        connection.execute("""
            INSERT INTO follows(follower_id, following_id)
            VALUES (?, ?)
        """, (me["id"], user_id))

        connection.execute("""
            UPDATE users
            SET followers = followers + 1
            WHERE id = ?
        """, (user_id,))

        connection.execute("""
            UPDATE users
            SET following = following + 1
            WHERE id = ?
        """, (me["id"],))

        connection.execute("""
            INSERT INTO notifications(
                user_id,
                actor_id,
                notification_type,
                text
            )
            VALUES (?, ?, 'follow', ?)
        """, (
            user_id,
            me["id"],
            f"@{me['username']} followed you."
        ))

    connection.commit()
    connection.close()

    return redirect(request.referrer or url_for("home"))


@app.route("/unfollow/<int:user_id>", methods=["POST"])
@login_required
def unfollow(user_id):
    me = current_user()

    connection = db()

    existing = connection.execute("""
        SELECT id FROM follows
        WHERE follower_id = ?
          AND following_id = ?
    """, (me["id"], user_id)).fetchone()

    if existing:
        connection.execute(
            "DELETE FROM follows WHERE id = ?",
            (existing["id"],)
        )

        connection.execute("""
            UPDATE users
            SET followers = MAX(followers - 1, 0)
            WHERE id = ?
        """, (user_id,))

        connection.execute("""
            UPDATE users
            SET following = MAX(following - 1, 0)
            WHERE id = ?
        """, (me["id"],))

    connection.commit()
    connection.close()

    return redirect(request.referrer or url_for("home"))


# ============================================================
# AUTH
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    error = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "").strip()
        display_name = request.form.get("display_name", "").strip()

        if len(username) < 3:
            error = "Username must be at least 3 characters."

        elif len(password) < 4:
            error = "Password must be at least 4 characters."

        else:
            connection = db()

            try:
                cursor = connection.execute("""
                    INSERT INTO users(
                        username,
                        password,
                        display_name
                    )
                    VALUES (?, ?, ?)
                """, (
                    username,
                    hash_password(password),
                    display_name or username
                ))

                connection.commit()

                session["user_id"] = cursor.lastrowid

                connection.close()

                return redirect(url_for("home"))

            except sqlite3.IntegrityError:
                connection.close()
                error = "That username already exists."

    content = f"""
    <main class="container">
        <div class="card" style="max-width:500px;margin:auto;">
            <h1>Join Heara</h1>

            {"<div class='error'>" + error + "</div>" if error else ""}

            <form method="POST">

                <div class="form-group">
                    <input
                        name="display_name"
                        placeholder="Display name">
                </div>

                <div class="form-group">
                    <input
                        name="username"
                        placeholder="Username"
                        required>
                </div>

                <div class="form-group">
                    <input
                        type="password"
                        name="password"
                        placeholder="Password"
                        required>
                </div>

                <button class="btn">
                    Create account
                </button>

            </form>

            <p class="muted">
                Already have an account?
                <a href="{url_for('login')}">Log in</a>
            </p>
        </div>
    </main>
    """

    return render_page("Register", content)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "").strip()

        connection = db()

        user = connection.execute("""
            SELECT *
            FROM users
            WHERE username = ?
              AND password = ?
        """, (
            username,
            hash_password(password)
        )).fetchone()

        connection.close()

        if user:
            session["user_id"] = user["id"]
            return redirect(url_for("home"))

        error = "Incorrect username or password."

    content = f"""
    <main class="container">
        <div class="card" style="max-width:500px;margin:auto;">
            <h1>Log in</h1>

            {"<div class='error'>" + error + "</div>" if error else ""}

            <form method="POST">

                <div class="form-group">
                    <input
                        name="username"
                        placeholder="Username"
                        required>
                </div>

                <div class="form-group">
                    <input
                        type="password"
                        name="password"
                        placeholder="Password"
                        required>
                </div>

                <button class="btn">
                    Log in
                </button>

            </form>

            <p class="muted">
                New to Heara?
                <a href="{url_for('register')}">Create an account</a>
            </p>
        </div>
    </main>
    """

    return render_page("Login", content)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ============================================================
# INBOX
# ============================================================

@app.route("/inbox")
@login_required
def inbox():
    me = current_user()

    connection = db()

    people = connection.execute("""
        SELECT DISTINCT
            users.id,
            users.username,
            users.display_name
        FROM users
        JOIN messages
        ON (
            users.id = messages.sender_id
            OR users.id = messages.receiver_id
        )
        WHERE users.id != ?
        ORDER BY messages.id DESC
    """, (me["id"],)).fetchall()

    connection.close()

    rows = ""

    for person in people:
        rows += f"""
        <a
            href="{url_for('messages', user_id=person["id"])}"
            class="card"
            style="display:block;">
            <strong>
                {person["display_name"] or person["username"]}
            </strong>
            <div class="muted">
                @{person["username"]}
            </div>
        </a>
        """

    content = f"""
    <main class="container">
        <h1>Messages</h1>

        <div class="grid">
            {rows or "<div class='card'><p class='muted'>No conversations yet.</p></div>"}
        </div>
    </main>
    """

    return render_page("Messages", content)


@app.route("/messages/<int:user_id>", methods=["GET", "POST"])
@login_required
def messages(user_id):
    me = current_user()

    connection = db()

    person = connection.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    if not person:
        connection.close()
        return "User not found", 404

    if request.method == "POST":
        message = request.form.get("message", "").strip()

        if message:
            connection.execute("""
                INSERT INTO messages(
                    sender_id,
                    receiver_id,
                    message
                )
                VALUES (?, ?, ?)
            """, (
                me["id"],
                user_id,
                message
            ))

            connection.execute("""
                INSERT INTO notifications(
                    user_id,
                    actor_id,
                    notification_type,
                    text
                )
                VALUES (?, ?, 'message', ?)
            """, (
                user_id,
                me["id"],
                f"@{me['username']} sent you a message."
            ))

            connection.commit()

    messages_list = connection.execute("""
        SELECT *
        FROM messages
        WHERE
            (sender_id = ? AND receiver_id = ?)
            OR
            (sender_id = ? AND receiver_id = ?)
        ORDER BY id ASC
    """, (
        me["id"],
        user_id,
        user_id,
        me["id"]
    )).fetchall()

    connection.close()

    message_html = ""

    for item in messages_list:
        mine = item["sender_id"] == me["id"]

        message_html += f"""
        <div style="
            display:flex;
            justify-content:{'flex-end' if mine else 'flex-start'};
            margin:8px 0;
        ">
            <div style="
                max-width:75%;
                padding:11px 14px;
                border-radius:16px;
                background:{'linear-gradient(135deg,#7355ff,#3f9cff)' if mine else 'rgba(255,255,255,.08)'};
            ">
                {item["message"]}
            </div>
        </div>
        """

    content = f"""
    <main class="container">

        <div class="card" style="max-width:700px;margin:auto;">

            <h2>
                {person["display_name"] or person["username"]}
            </h2>

            <div style="
                height:450px;
                overflow-y:auto;
                padding:10px;
                background:rgba(0,0,0,.15);
                border-radius:15px;
            ">
                {message_html or "<p class='muted'>Start the conversation.</p>"}
            </div>

            <form method="POST" style="margin-top:12px;">
                <div style="display:flex;gap:8px;">
                    <input
                        name="message"
                        placeholder="Type a message..."
                        required>
                    <button class="btn">Send</button>
                </div>
            </form>

        </div>

    </main>
    """

    return render_page("Chat", content)


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route("/notifications")
@login_required
def notifications():
    user = current_user()

    connection = db()

    rows = connection.execute("""
        SELECT
            notifications.*,
            users.username,
            users.display_name
        FROM notifications
        LEFT JOIN users
        ON users.id = notifications.actor_id
        WHERE notifications.user_id = ?
        ORDER BY notifications.id DESC
        LIMIT 100
    """, (user["id"],)).fetchall()

    connection.execute("""
        UPDATE notifications
        SET is_read = 1
        WHERE user_id = ?
    """, (user["id"],))

    connection.commit()
    connection.close()

    html = ""

    for row in rows:
        html += f"""
        <div class="card">
            {row["text"] or "You have a new notification."}
        </div>
        """

    content = f"""
    <main class="container">

        <h1>Notifications</h1>

        <div style="
            display:grid;
            gap:10px;
            max-width:700px;
            margin:auto;
        ">
            {html or "<div class='card'><p class='muted'>No notifications yet.</p></div>"}
        </div>

    </main>
    """

    return render_page("Notifications", content)


# ============================================================
# SEARCH
# ============================================================

@app.route("/search")
def search():
    query = request.args.get("q", "").strip()

    users = []

    if query:
        connection = db()

        users = connection.execute("""
            SELECT *
            FROM users
            WHERE username LIKE ?
               OR display_name LIKE ?
            ORDER BY followers DESC
            LIMIT 30
        """, (
            "%" + query + "%",
            "%" + query + "%"
        )).fetchall()

        connection.close()

    results = ""

    for user in users:
        results += f"""
        <a
            class="card"
            href="{url_for('profile', username=user["username"])}">
            <strong>
                {user["display_name"] or user["username"]}
            </strong>
            <div class="muted">
                @{user["username"]}
            </div>
        </a>
        """

    content = f"""
    <main class="container">

        <div class="card">
            <h1>Search Heara</h1>

            <form method="GET">
                <div style="display:flex;gap:8px;">
                    <input
                        name="q"
                        value="{query}"
                        placeholder="Search creators..."
                        required>
                    <button class="btn">Search</button>
                </div>
            </form>
        </div>

        <div class="grid" style="margin-top:20px;">
            {results or "<div class='card'><p class='muted'>Search for a creator.</p></div>"}
        </div>

    </main>
    """

    return render_page("Search", content)


# ============================================================
# LIVE
# ============================================================

@app.route("/live")
def live():
    connection = db()

    rooms = connection.execute("""
        SELECT
            live_rooms.*,
            users.username,
            users.display_name,
            users.followers
        FROM live_rooms
        JOIN users
        ON users.id = live_rooms.owner_id
        WHERE live_rooms.is_live = 1
        ORDER BY live_rooms.id DESC
    """).fetchall()

    connection.close()

    cards = ""

    for room in rooms:
        cards += f"""
        <a
            class="card"
            href="{url_for(
                'live_room',
                room_code=room["room_code"]
            )}">
            <div style="font-size:30px;">🔴</div>
            <h3>
                {room["title"]}
            </h3>
            <p class="muted">
                @{room["username"]}
            </p>
            <span class="btn">
                Watch Live
            </span>
        </a>
        """

    content = f"""
    <main class="container">

        <div class="card">
            <h1>🔴 Heara Live</h1>

            <p class="muted">
                Creators with at least {LIVE_FOLLOWERS} followers
                can start a live broadcast.
            </p>

            {
                f"<a class='btn' href='{url_for('go_live')}'>Go Live</a>"
                if current_user()
                else
                f"<a class='btn' href='{url_for('login')}'>Log in to go live</a>"
            }
        </div>

        <h2>Live now</h2>

        <div class="grid">
            {cards or "<div class='card'><p class='muted'>Nobody is live right now.</p></div>"}
        </div>

    </main>
    """

    return render_page("Live", content)


@app.route("/go-live", methods=["GET", "POST"])
@login_required
def go_live():
    user = current_user()

    if user["followers"] < LIVE_FOLLOWERS:
        content = f"""
        <main class="container">
            <div class="card" style="max-width:650px;margin:auto;text-align:center;">
                <h1>🔒 Live isn't unlocked yet</h1>
                <p>
                    You need at least
                    <strong>{LIVE_FOLLOWERS} followers</strong>
                    to go live.
                </p>
                <p class="muted">
                    Keep creating and growing your Heara community.
                </p>
            </div>
        </main>
        """

        return render_page("Live", content)

    if request.method == "POST":
        title = request.form.get(
            "title",
            "Live on Heara"
        ).strip()

        room_code = make_room_code()

        connection = db()

        connection.execute("""
            INSERT INTO live_rooms(
                owner_id,
                room_code,
                title,
                is_live
            )
            VALUES (?, ?, ?, 1)
        """, (
            user["id"],
            room_code,
            title or "Live on Heara"
        ))

        connection.commit()
        connection.close()

        return redirect(
            url_for("live_room", room_code=room_code)
        )

    content = f"""
    <main class="container">

        <div class="card" style="max-width:650px;margin:auto;">

            <h1>Go Live 🔴</h1>

            <p class="muted">
                Your camera and microphone will be requested
                by the browser.
            </p>

            <form method="POST">

                <div class="form-group">
                    <input
                        name="title"
                        value="Live on Heara"
                        placeholder="Live title">
                </div>

                <button class="btn">
                    Start Live
                </button>

            </form>

        </div>

    </main>
    """

    return render_page("Go Live", content)


@app.route("/live/<room_code>")
def live_room(room_code):
    connection = db()

    room = connection.execute("""
        SELECT
            live_rooms.*,
            users.username,
            users.display_name,
            users.followers
        FROM live_rooms
        JOIN users
        ON users.id = live_rooms.owner_id
        WHERE room_code = ?
    """, (room_code,)).fetchone()

    connection.close()

    if not room:
        return "Live room not found", 404

    user = current_user()

    owner = (
        user is not None
        and user["id"] == room["owner_id"]
    )

    content = f"""
    <main class="container">

        <div class="card">

            <h1>
                🔴 {room["title"]}
            </h1>

            <p class="muted">
                @{room["username"]}
            </p>

            <div style="
                position:relative;
                background:#000;
                border-radius:20px;
                overflow:hidden;
                min-height:450px;
                display:flex;
                align-items:center;
                justify-content:center;
            ">

                <video
                    id="livePreview"
                    autoplay
                    playsinline
                    muted
                    style="
                        width:100%;
                        max-height:650px;
                        object-fit:cover;
                    ">
                </video>

                <div
                    id="viewerMessage"
                    style="
                        position:absolute;
                        inset:0;
                        display:flex;
                        align-items:center;
                        justify-content:center;
                        text-align:center;
                        padding:30px;
                    ">
                    {
                        "Starting camera..."
                        if owner
                        else
                        "🔴 This live room is active.<br><br>"
                        "The broadcaster's camera stream requires "
                        "a real-time streaming server/WebRTC media layer "
                        "for internet-wide viewers."
                    }
                </div>

            </div>

            {
                f'''
                <div style="display:flex;gap:10px;margin-top:15px;">
                    <button class="btn" onclick="startLiveCamera()">
                        🎥 Start camera
                    </button>

                    <form method="POST"
                          action="{url_for('end_live', room_code=room_code)}">
                        <button class="btn danger">
                            End Live
                        </button>
                    </form>
                </div>
                '''
                if owner else
                ""
            }

        </div>

    </main>

    <script>
    async function startLiveCamera() {{
        try {{
            const stream =
                await navigator.mediaDevices.getUserMedia({{
                    video:true,
                    audio:true
                }});

            const video =
                document.getElementById("livePreview");

            video.srcObject = stream;

            document.getElementById("viewerMessage")
                .style.display = "none";

        }} catch(error) {{
            alert(
                "Camera/microphone permission was not granted."
            );
        }}
    }}
    </script>
    """

    return render_page("Live", content)


@app.route("/live/<room_code>/end", methods=["POST"])
@login_required
def end_live(room_code):
    user = current_user()

    connection = db()

    connection.execute("""
        UPDATE live_rooms
        SET is_live = 0,
            ended_at = CURRENT_TIMESTAMP
        WHERE room_code = ?
          AND owner_id = ?
    """, (
        room_code,
        user["id"]
    ))

    connection.commit()
    connection.close()

    return redirect(url_for("live"))


# ============================================================
# PEXELS SHARE ROUTE
# ============================================================

@app.route("/pexels/<int:video_id>")
def pexels_shared(video_id):
    """
    Shareable Heara landing page for a Pexels video.
    """

    data, error = pexels_request(
        f"videos/videos/{video_id}",
        {}
    )

    if error or not data:
        return redirect(url_for("fyp"))

    link = choose_video_file(data)

    if not link:
        return redirect(url_for("fyp"))

    user = data.get("user") or {}

    content = f"""
    <main class="container">

        <div class="card" style="max-width:700px;margin:auto;">

            <video
                src="{link}"
                poster="{data.get("image", "")}"
                controls
                autoplay
                playsinline
                class="post-media">
            </video>

            <h2>
                Discover this video on Heara
            </h2>

            <p>
                Video by
                <strong>{user.get("name", "Pexels creator")}</strong>
                on Pexels.
            </p>

            <a
                class="btn"
                href="{url_for('fyp')}">
                Open Heara FYP
            </a>

        </div>

    </main>
    """

    return render_page("Shared Video", content)


# ============================================================
# API
# ============================================================

@app.route("/api/me")
def api_me():
    user = current_user()

    if not user:
        return jsonify({
            "logged_in": False
        })

    return jsonify({
        "logged_in": True,
        "user": dict(user)
    })


@app.route("/api/fyp")
def api_fyp():
    page = max(
        1,
        request.args.get("page", 1, type=int)
    )

    query = request.args.get("q", "").strip() or None

    videos, error = get_pexels_videos(
        page,
        query
    )

    return jsonify({
        "ok": not bool(error),
        "error": error,
        "page": page,
        "videos": videos
    })


@app.route("/api/view/<int:post_id>", methods=["POST"])
def api_view(post_id):
    connection = db()

    connection.execute("""
        UPDATE posts
        SET views = COALESCE(views, 0) + 1
        WHERE id = ?
    """, (post_id,))

    connection.commit()

    row = connection.execute(
        "SELECT views FROM posts WHERE id = ?",
        (post_id,)
    ).fetchone()

    connection.close()

    return jsonify({
        "ok": True,
        "views": row["views"] if row else 0
    })


@app.route("/health")
def health():
    try:
        connection = db()

        connection.execute(
            "SELECT 1"
        ).fetchone()

        connection.close()

        pexels_status = bool(PEXELS_API_KEY)

        return jsonify({
            "status": "ok",
            "service": "Heara",
            "database": "ok",
            "pexels_key_configured": pexels_status
        })

    except Exception as error:
        return jsonify({
            "status": "error",
            "service": "Heara",
            "error": str(error)
        }), 500


# ============================================================
# ERRORS
# ============================================================

@app.errorhandler(404)
def not_found(error):
    content = """
    <main class="container">
        <div class="card" style="text-align:center;">
            <h1>404</h1>
            <p class="muted">
                That Heara page doesn't exist.
            </p>
            <a class="btn" href="/">Go home</a>
        </div>
    </main>
    """

    return render_page("Not Found", content), 404


@app.errorhandler(500)
def server_error(error):
    content = """
    <main class="container">
        <div class="card" style="text-align:center;">
            <h1>Something went wrong.</h1>

            <p class="muted">
                Heara encountered a server error.
            </p>

            <a class="btn" href="/">
                Try again
            </a>
        </div>
    </main>
    """

    return render_page("Error", content), 500


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
