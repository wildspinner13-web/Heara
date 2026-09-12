import os
import re
import json
import sqlite3
import secrets
import hashlib
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from functools import wraps

from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    send_from_directory,
    abort,
)

# ============================================================
# HEARA
# Single-file Flask application
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "heara.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

app.secret_key = os.environ.get(
    "HEARA_SECRET_KEY",
    "heara-development-secret-change-me"
)

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "").strip()

LIVE_FOLLOWERS = 250
MAX_UPLOAD_MB = 100


# ============================================================
# DATABASE
# ============================================================

def db():
    connection = sqlite3.connect(str(DB_PATH))
    connection.row_factory = sqlite3.Row
    return connection


def column_exists(connection, table, column):
    rows = connection.execute(
        "PRAGMA table_info(" + table + ")"
    ).fetchall()

    return any(row["name"] == column for row in rows)


def add_column_if_missing(connection, table, column, definition):
    if not column_exists(connection, table, column):
        connection.execute(
            "ALTER TABLE " + table +
            " ADD COLUMN " + column +
            " " + definition
        )


def init_db():
    connection = db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            bio TEXT DEFAULT '',
            avatar TEXT DEFAULT '',
            followers INTEGER DEFAULT 0,
            following INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            content TEXT DEFAULT '',
            media_url TEXT DEFAULT '',
            media_type TEXT DEFAULT '',
            source TEXT DEFAULT 'local',
            source_id TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            photographer TEXT DEFAULT '',
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            post_id INTEGER,
            UNIQUE(user_id, post_id)
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS follows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            follower_id INTEGER,
            following_id INTEGER,
            UNIQUE(follower_id, following_id)
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            post_id INTEGER,
            text TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            receiver_id INTEGER,
            text TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            seen INTEGER DEFAULT 0
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            seen INTEGER DEFAULT 0
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS live_rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT DEFAULT 'Live on Heara',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Safe migrations for older Heara databases.
    add_column_if_missing(connection, "users", "bio", "TEXT DEFAULT ''")
    add_column_if_missing(connection, "users", "avatar", "TEXT DEFAULT ''")
    add_column_if_missing(connection, "users", "followers", "INTEGER DEFAULT 0")
    add_column_if_missing(connection, "users", "following", "INTEGER DEFAULT 0")

    add_column_if_missing(connection, "posts", "media_url", "TEXT DEFAULT ''")
    add_column_if_missing(connection, "posts", "media_type", "TEXT DEFAULT ''")
    add_column_if_missing(connection, "posts", "source", "TEXT DEFAULT 'local'")
    add_column_if_missing(connection, "posts", "source_id", "TEXT DEFAULT ''")
    add_column_if_missing(connection, "posts", "source_url", "TEXT DEFAULT ''")
    add_column_if_missing(connection, "posts", "photographer", "TEXT DEFAULT ''")
    add_column_if_missing(connection, "posts", "likes", "INTEGER DEFAULT 0")
    add_column_if_missing(connection, "posts", "comments", "INTEGER DEFAULT 0")

    connection.commit()
    connection.close()


init_db()


# ============================================================
# HELPERS
# ============================================================

def hash_password(password):
    return hashlib.sha256(
        password.encode("utf-8")
    ).hexdigest()


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
        if not current_user():
            return redirect(url_for("login"))
        return function(*args, **kwargs)

    return wrapper


def clean_username(username):
    username = username.strip()

    username = re.sub(
        r"[^A-Za-z0-9_.-]",
        "",
        username
    )

    return username[:30]


def safe_filename(filename):
    filename = os.path.basename(filename)
    filename = re.sub(
        r"[^A-Za-z0-9_.-]",
        "_",
        filename
    )

    return filename


def is_video(filename):
    extension = Path(filename).suffix.lower()

    return extension in {
        ".mp4",
        ".webm",
        ".mov",
        ".m4v",
        ".avi",
        ".mkv",
    }


def is_image(filename):
    extension = Path(filename).suffix.lower()

    return extension in {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
    }


# ============================================================
# PEXELS
# Uses Python's built-in urllib.
# No requests package required.
# ============================================================

def pexels_request(endpoint, params=None):
    if not PEXELS_API_KEY:
        return None

    base = "https://api.pexels.com/v1/"
    url = base + endpoint

    if params:
        clean_params = {}

        for key, value in params.items():
            if value is not None:
                clean_params[key] = value

        query_string = urllib.parse.urlencode(clean_params)

        if query_string:
            url += "?" + query_string

    request_object = urllib.request.Request(
        url,
        headers={
            "Authorization": PEXELS_API_KEY,
            "User-Agent": "Heara/1.0",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(
            request_object,
            timeout=15
        ) as response:

            raw = response.read().decode("utf-8")

            return json.loads(raw)

    except Exception as error:
        print("Pexels error:", error)
        return None


def pexels_videos(page=1, per_page=12):
    data = pexels_request(
        "videos/search",
        {
            "query": "people lifestyle",
            "orientation": "portrait",
            "size": "medium",
            "page": page,
            "per_page": per_page,
        },
    )

    if not data:
        return []

    result = []

    for video in data.get("videos", []):
        files = video.get("video_files", [])

        if not files:
            continue

        selected = None

        # Prefer portrait / reasonably sized files.
        for item in files:
            width = item.get("width") or 0
            height = item.get("height") or 0

            if height >= width:
                selected = item
                break

        if selected is None:
            selected = files[0]

        result.append({
            "id": video.get("id"),
            "url": selected.get("link"),
            "width": selected.get("width"),
            "height": selected.get("height"),
            "duration": video.get("duration", 0),
            "image": video.get("image", ""),
            "photographer": video.get(
                "user",
                {}
            ).get(
                "name",
                "Pexels creator"
            ),
            "pexels_url": video.get(
                "url",
                "https://www.pexels.com/"
            ),
        })

    return result


# ============================================================
# COMMON HTML
# ============================================================

BASE_CSS = """
* {
    box-sizing: border-box;
}

html,
body {
    margin: 0;
    padding: 0;
    min-height: 100%;
    background: #070b18;
    color: #ffffff;
    font-family: Inter, Arial, sans-serif;
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

.heara-bg {
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: -1;
    background:
        radial-gradient(circle at 15% 15%, rgba(111, 75, 255, .20), transparent 28%),
        radial-gradient(circle at 85% 20%, rgba(0, 212, 255, .12), transparent 30%),
        radial-gradient(circle at 50% 90%, rgba(168, 53, 255, .12), transparent 30%),
        #070b18;
}

.nav {
    height: 70px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 28px;
    position: sticky;
    top: 0;
    z-index: 100;
    background: rgba(7, 11, 24, .82);
    backdrop-filter: blur(18px);
    border-bottom: 1px solid rgba(255,255,255,.08);
}

.logo {
    font-size: 27px;
    font-weight: 900;
    letter-spacing: -1px;
}

.logo span {
    color: #8d6bff;
}

.nav-links {
    display: flex;
    gap: 10px;
    align-items: center;
}

.nav-links a,
.nav-btn {
    padding: 10px 14px;
    border-radius: 12px;
    color: #dce2ff;
    background: transparent;
    border: 0;
}

.nav-links a:hover,
.nav-btn:hover {
    background: rgba(255,255,255,.08);
}

.container {
    width: min(1180px, calc(100% - 32px));
    margin: 0 auto;
}

.card {
    background: rgba(15, 21, 42, .76);
    border: 1px solid rgba(255,255,255,.08);
    border-radius: 22px;
    box-shadow: 0 20px 70px rgba(0,0,0,.28);
    backdrop-filter: blur(16px);
}

.btn {
    border: 0;
    border-radius: 13px;
    padding: 11px 17px;
    color: white;
    background: linear-gradient(135deg, #7557ff, #a34cff);
    font-weight: 700;
}

.btn:hover {
    transform: translateY(-1px);
    filter: brightness(1.08);
}

.btn.secondary {
    background: rgba(255,255,255,.08);
}

.btn.danger {
    background: #e5484d;
}

input,
textarea {
    width: 100%;
    border: 1px solid rgba(255,255,255,.10);
    background: rgba(0,0,0,.25);
    color: white;
    padding: 13px 15px;
    border-radius: 13px;
    outline: none;
}

input:focus,
textarea:focus {
    border-color: #8266ff;
}

textarea {
    min-height: 110px;
    resize: vertical;
}

.page-title {
    font-size: 34px;
    margin: 30px 0 20px;
}

.muted {
    color: #9da6c7;
}

.empty {
    padding: 40px;
    text-align: center;
    color: #9da6c7;
}

.post-card {
    padding: 20px;
    margin-bottom: 18px;
}

.post-head {
    display: flex;
    align-items: center;
    gap: 12px;
}

.avatar {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    object-fit: cover;
    background: linear-gradient(135deg,#765cff,#00c8ff);
    display: grid;
    place-items: center;
    font-weight: 900;
}

.post-content {
    margin: 16px 0;
    line-height: 1.6;
    white-space: pre-wrap;
}

.post-media {
    width: 100%;
    max-height: 650px;
    border-radius: 17px;
    object-fit: contain;
    background: #000;
}

.post-actions {
    display: flex;
    gap: 10px;
    margin-top: 14px;
    flex-wrap: wrap;
}

.action-btn {
    border: 0;
    background: rgba(255,255,255,.07);
    color: #dce2ff;
    border-radius: 12px;
    padding: 9px 13px;
}

.hero {
    min-height: calc(100vh - 70px);
    display: grid;
    grid-template-columns: 1fr 1fr;
    align-items: center;
    gap: 40px;
    padding: 50px 0;
}

.hero h1 {
    font-size: clamp(48px, 7vw, 92px);
    line-height: .95;
    margin: 0 0 24px;
}

.hero h1 span {
    color: #8567ff;
}

.hero p {
    font-size: 19px;
    color: #aab2d0;
    line-height: 1.7;
}

.hero-image {
    width: 100%;
    max-width: 570px;
    margin-left: auto;
    display: block;
    animation: floatImage 5s ease-in-out infinite;
}

@keyframes floatImage {
    0%,100% { transform: translateY(0); }
    50% { transform: translateY(-13px); }
}

.auth-wrap {
    width: min(460px, calc(100% - 32px));
    margin: 70px auto;
}

.auth-card {
    padding: 30px;
}

.auth-card h1 {
    margin-top: 0;
}

.form-row {
    margin-bottom: 16px;
}

.form-row label {
    display: block;
    margin-bottom: 7px;
    color: #b9c1dc;
}

.feed-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 330px;
    gap: 22px;
    align-items: start;
}

.sidebar {
    padding: 20px;
    position: sticky;
    top: 90px;
}

.profile-card {
    padding: 30px;
    margin-top: 30px;
}

.profile-top {
    display: flex;
    align-items: center;
    gap: 20px;
}

.profile-avatar {
    width: 90px;
    height: 90px;
    border-radius: 50%;
    object-fit: cover;
    background: linear-gradient(135deg,#765cff,#00c8ff);
}

.stats {
    display: flex;
    gap: 25px;
    margin-top: 20px;
}

.stat strong {
    display: block;
    font-size: 22px;
}

.create-card {
    padding: 20px;
    margin: 25px 0;
}

.create-buttons {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 13px;
}

.hidden {
    display: none !important;
}

/* ============================================================
   FYP
   ============================================================ */

.fyp-page {
    height: calc(100vh - 70px);
    overflow: hidden;
    background: #000;
}

.fyp-wrap {
    height: 100%;
    overflow-y: auto;
    scroll-snap-type: y mandatory;
    scrollbar-width: none;
}

.fyp-wrap::-webkit-scrollbar {
    display: none;
}

.fyp-card {
    height: calc(100vh - 70px);
    min-height: 620px;
    position: relative;
    scroll-snap-align: start;
    scroll-snap-stop: always;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #000;
}

.fyp-video {
    height: 100%;
    width: min(100%, 650px);
    object-fit: cover;
    background: #000;
}

.fyp-overlay {
    position: absolute;
    inset: 0;
    pointer-events: none;
    background:
        linear-gradient(to top, rgba(0,0,0,.78), transparent 35%),
        linear-gradient(to bottom, rgba(0,0,0,.35), transparent 25%);
}

.fyp-info {
    position: absolute;
    left: 25px;
    bottom: 28px;
    width: min(70%, 550px);
    z-index: 3;
}

.fyp-info h3 {
    margin: 0 0 8px;
}

.fyp-info p {
    color: #d5d9e8;
    margin: 5px 0;
}

.fyp-actions {
    position: absolute;
    right: 25px;
    bottom: 35px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    z-index: 5;
}

.fyp-action {
    width: 52px;
    height: 52px;
    border-radius: 50%;
    border: 1px solid rgba(255,255,255,.16);
    background: rgba(0,0,0,.52);
    color: white;
    font-size: 20px;
    display: grid;
    place-items: center;
}

.fyp-top {
    position: fixed;
    top: 82px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 20;
    background: rgba(0,0,0,.5);
    border: 1px solid rgba(255,255,255,.12);
    padding: 9px 17px;
    border-radius: 20px;
    backdrop-filter: blur(10px);
}

.fyp-loading {
    height: 100%;
    display: grid;
    place-items: center;
    color: #aaa;
    font-size: 18px;
}

.source-credit {
    font-size: 12px;
    color: #aeb4c9;
}

@media (max-width: 800px) {
    .nav {
        padding: 0 15px;
    }

    .nav-links a:nth-child(3),
    .nav-links a:nth-child(4) {
        display: none;
    }

    .hero {
        grid-template-columns: 1fr;
        text-align: center;
    }

    .hero-image {
        margin: auto;
    }

    .feed-grid {
        grid-template-columns: 1fr;
    }

    .sidebar {
        position: static;
    }

    .fyp-card,
    .fyp-page {
        height: calc(100vh - 60px);
        min-height: 520px;
    }

    .fyp-info {
        width: 72%;
        left: 15px;
    }

    .fyp-actions {
        right: 13px;
    }
}
"""


def page(title, body, extra_css="", extra_js=""):
    # IMPORTANT:
    # This function deliberately does NOT use an f-string.
    # This prevents CSS braces from causing Python syntax errors.

    user = current_user()

    if user:
        auth_links = """
        <a href="/videos">FYP</a>
        <a href="/create">Create</a>
        <a href="/live">Live</a>
        <a href="/inbox">Inbox</a>
        <a href="/profile/{username}">Profile</a>
        <a href="/logout">Logout</a>
        """.replace(
            "{username}",
            urllib.parse.quote(user["username"])
        )
    else:
        auth_links = """
        <a href="/login">Login</a>
        <a href="/register" class="btn">Join Heara</a>
        """

    template = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{TITLE} — Heara</title>
<style>
{CSS}
{EXTRA_CSS}
</style>
</head>

<body>

<div class="heara-bg"></div>

<nav class="nav">
    <a href="/" class="logo">He<span>a</span>ra</a>

    <div class="nav-links">
        <a href="/">Home</a>
        {AUTH_LINKS}
    </div>
</nav>

{BODY}

<script>
{JS}
</script>

</body>
</html>
"""

    return (
        template
        .replace("{TITLE}", str(title))
        .replace("{CSS}", BASE_CSS)
        .replace("{EXTRA_CSS}", extra_css)
        .replace("{AUTH_LINKS}", auth_links)
        .replace("{BODY}", body)
        .replace("{JS}", extra_js)
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():
    if current_user():
        return feed()

    hero_image = url_for(
        "static",
        filename="images/heara-hero.png"
    )

    body = """
    <main class="container hero">

        <section>
            <h1>Welcome to <span>Heara.</span></h1>

            <p>
                A new social world for videos, conversations,
                creators, communities and live moments.
            </p>

            <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:25px;">
                <a href="/register" class="btn">
                    Create account
                </a>

                <a href="/login" class="btn secondary">
                    Login
                </a>

                <a href="/videos" class="btn secondary">
                    Explore FYP
                </a>
            </div>
        </section>

        <section>
            <img
                src="__HERO_IMAGE__"
                class="hero-image"
                alt="Heara"
            >
        </section>

    </main>
    """.replace(
        "__HERO_IMAGE__",
        hero_image
    )

    return page("Home", body)


# ============================================================
# FEED
# ============================================================

@app.route("/feed")
def feed():
    user = current_user()

    if not user:
        return redirect(url_for("login"))

    connection = db()

    posts = connection.execute("""
        SELECT
            posts.*,
            users.username,
            users.avatar
        FROM posts
        LEFT JOIN users
        ON users.id = posts.user_id
        ORDER BY posts.id DESC
        LIMIT 50
    """).fetchall()

    connection.close()

    post_html = ""

    for post in posts:
        media_html = ""

        if post["media_url"]:
            if post["media_type"] == "video":
                media_html = """
                <video
                    class="post-media"
                    src="__URL__"
                    controls
                    playsinline
                ></video>
                """.replace(
                    "__URL__",
                    post["media_url"]
                )

            elif post["media_type"] == "image":
                media_html = """
                <img
                    class="post-media"
                    src="__URL__"
                    alt="Heara post"
                >
                """.replace(
                    "__URL__",
                    post["media_url"]
                )

        username = post["username"] or "Heara user"

        post_html += """
        <article class="card post-card">

            <div class="post-head">
                <div class="avatar">
                    __INITIAL__
                </div>

                <div>
                    <strong>__USERNAME__</strong>
                    <div class="muted">
                        @__USERNAME__
                    </div>
                </div>
            </div>

            <div class="post-content">__CONTENT__</div>

            __MEDIA__

            <div class="post-actions">

                <button
                    class="action-btn"
                    onclick="likePost(__ID__, this)"
                >
                    ❤️ __LIKES__
                </button>

                <a
                    class="action-btn"
                    href="/post/__ID__"
                >
                    💬 __COMMENTS__
                </a>

                <button
                    class="action-btn"
                    onclick="sharePost(__ID__, '__SHARE_TEXT__')"
                >
                    🔗 Share
                </button>

            </div>

        </article>
        """.replace(
            "__INITIAL__",
            username[:1].upper()
        ).replace(
            "__USERNAME__",
            username
        ).replace(
            "__CONTENT__",
            post["content"] or ""
        ).replace(
            "__MEDIA__",
            media_html
        ).replace(
            "__ID__",
            str(post["id"])
        ).replace(
            "__LIKES__",
            str(post["likes"] or 0)
        ).replace(
            "__COMMENTS__",
            str(post["comments"] or 0)
        ).replace(
            "__SHARE_TEXT__",
            username.replace("'", "")
        )

    if not post_html:
        post_html = """
        <div class="card empty">
            <h2>Your Heara feed is waiting.</h2>
            <p>
                Create the first post or explore the FYP.
            </p>
        </div>
        """

    body = """
    <main class="container">

        <div class="page-title">
            Home
        </div>

        <div class="feed-grid">

            <section>

                <div class="card create-card">
                    <h3>What's happening?</h3>

                    <form method="POST" action="/post">
                        <textarea
                            name="content"
                            placeholder="Share something with Heara..."
                        ></textarea>

                        <div class="create-buttons">
                            <button class="btn" type="submit">
                                Post
                            </button>

                            <a href="/create" class="btn secondary">
                                🎥 Create video
                            </a>
                        </div>
                    </form>
                </div>

                __POSTS__

            </section>

            <aside class="card sidebar">

                <h3>Welcome to Heara</h3>

                <p class="muted">
                    Discover videos, meet creators,
                    chat with people and go live.
                </p>

                <a
                    href="/videos"
                    class="btn"
                    style="display:block;text-align:center;margin-top:15px;"
                >
                    Open FYP
                </a>

            </aside>

        </div>

    </main>
    """.replace(
        "__POSTS__",
        post_html
    )

    js = """
    async function likePost(id, button) {
        try {
            const response = await fetch("/like/" + id, {
                method: "POST"
            });

            const data = await response.json();

            if (data.ok) {
                button.innerText = "❤️ " + data.likes;
            }
        } catch (error) {
            console.log(error);
        }
    }

    async function sharePost(id, text) {
        const link =
            window.location.origin +
            "/post/" +
            id;

        if (navigator.share) {
            try {
                await navigator.share({
                    title: "Heara",
                    text: text,
                    url: link
                });
                return;
            } catch (error) {}
        }

        try {
            await navigator.clipboard.writeText(link);
            alert("Heara link copied.");
        } catch (error) {
            prompt("Copy this Heara link:", link);
        }
    }
    """

    return page("Home", body, extra_js=js)


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        username = clean_username(
            request.form.get("username", "")
        )

        password = request.form.get(
            "password",
            ""
        )

        if len(username) < 3:
            return page(
                "Register",
                """
                <div class="auth-wrap">
                    <div class="card auth-card">
                        <h1>Choose a longer username.</h1>
                        <a href="/register" class="btn">Go back</a>
                    </div>
                </div>
                """
            )

        if len(password) < 4:
            return page(
                "Register",
                """
                <div class="auth-wrap">
                    <div class="card auth-card">
                        <h1>Password is too short.</h1>
                        <a href="/register" class="btn">Go back</a>
                    </div>
                </div>
                """
            )

        connection = db()

        try:
            cursor = connection.execute(
                """
                INSERT INTO users
                (username, password)
                VALUES (?, ?)
                """,
                (
                    username,
                    hash_password(password)
                )
            )

            connection.commit()

            user_id = cursor.lastrowid

        except sqlite3.IntegrityError:
            connection.close()

            return page(
                "Register",
                """
                <div class="auth-wrap">
                    <div class="card auth-card">
                        <h1>Username already exists.</h1>
                        <a href="/register" class="btn">
                            Try another
                        </a>
                    </div>
                </div>
                """
            )

        connection.close()

        session["user_id"] = user_id

        return redirect(url_for("home"))

    body = """
    <div class="auth-wrap">

        <div class="card auth-card">

            <h1>Create your Heara account</h1>

            <p class="muted">
                Join the community.
            </p>

            <form method="POST">

                <div class="form-row">
                    <label>Username</label>
                    <input
                        name="username"
                        required
                        autocomplete="username"
                        placeholder="Choose a username"
                    >
                </div>

                <div class="form-row">
                    <label>Password</label>
                    <input
                        type="password"
                        name="password"
                        required
                        autocomplete="new-password"
                        placeholder="Create a password"
                    >
                </div>

                <button class="btn" type="submit">
                    Create account
                </button>

            </form>

            <p class="muted" style="margin-top:20px;">
                Already have an account?
                <a href="/login" style="color:#9b83ff;">
                    Login
                </a>
            </p>

        </div>

    </div>
    """

    return page("Register", body)


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":

        username = clean_username(
            request.form.get("username", "")
        )

        password = request.form.get(
            "password",
            ""
        )

        connection = db()

        user = connection.execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
            AND password = ?
            """,
            (
                username,
                hash_password(password)
            )
        ).fetchone()

        connection.close()

        if user:
            session["user_id"] = user["id"]

            return redirect(
                request.args.get(
                    "next",
                    url_for("home")
                )
            )

        error = "Incorrect username or password."

    body = """
    <div class="auth-wrap">

        <div class="card auth-card">

            <h1>Welcome back</h1>

            <p class="muted">
                Login to Heara.
            </p>

            __ERROR__

            <form method="POST">

                <div class="form-row">
                    <label>Username</label>
                    <input
                        name="username"
                        required
                        autocomplete="username"
                    >
                </div>

                <div class="form-row">
                    <label>Password</label>
                    <input
                        type="password"
                        name="password"
                        required
                        autocomplete="current-password"
                    >
                </div>

                <button class="btn" type="submit">
                    Login
                </button>

            </form>

            <p class="muted" style="margin-top:20px;">
                Don't have an account?
                <a href="/register" style="color:#9b83ff;">
                    Create one
                </a>
            </p>

        </div>

    </div>
    """.replace(
        "__ERROR__",
        (
            '<p style="color:#ff7777;">' +
            error +
            "</p>"
        ) if error else ""
    )

    return page("Login", body)


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ============================================================
# CREATE / UPLOAD / CAMERA
# ============================================================

@app.route("/create")
@login_required
def create():
    body = """
    <main class="container">

        <div class="page-title">
            Create
        </div>

        <div class="card create-card">

            <h2>Make something for Heara</h2>

            <p class="muted">
                Record directly with your camera or choose
                a video/image from your device.
            </p>

            <form
                id="uploadForm"
                method="POST"
                action="/upload"
                enctype="multipart/form-data"
            >

                <div style="margin-top:20px;">

                    <input
                        id="mediaInput"
                        type="file"
                        name="media"
                        accept="video/*,image/*"
                        class="hidden"
                    >

                    <button
                        type="button"
                        class="btn"
                        onclick="chooseFile()"
                    >
                        📁 Choose from device
                    </button>

                    <button
                        type="button"
                        class="btn secondary"
                        onclick="startCamera()"
                    >
                        📷 Camera
                    </button>

                </div>

                <div
                    id="cameraBox"
                    class="hidden"
                    style="margin-top:20px;"
                >

                    <video
                        id="cameraPreview"
                        autoplay
                        muted
                        playsinline
                        class="post-media"
                    ></video>

                    <div class="create-buttons">

                        <button
                            type="button"
                            class="btn"
                            id="recordButton"
                            onclick="toggleRecording()"
                        >
                            🔴 Start recording
                        </button>

                        <button
                            type="button"
                            class="btn secondary"
                            onclick="stopCamera()"
                        >
                            Stop camera
                        </button>

                    </div>

                    <p
                        id="recordStatus"
                        class="muted"
                    ></p>

                </div>

                <div
                    id="selectedFile"
                    class="muted"
                    style="margin-top:15px;"
                ></div>

                <div style="margin-top:20px;">

                    <textarea
                        name="content"
                        placeholder="Write a caption..."
                    ></textarea>

                </div>

                <button
                    class="btn"
                    type="submit"
                    style="margin-top:15px;"
                >
                    Publish to Heara
                </button>

            </form>

        </div>

    </main>
    """

    js = """
    let cameraStream = null;
    let recorder = null;
    let recordedChunks = [];
    let isRecording = false;

    function chooseFile() {
        document.getElementById("mediaInput").click();
    }

    document.getElementById("mediaInput").addEventListener(
        "change",
        function() {
            if (this.files.length) {
                document.getElementById("selectedFile").innerText =
                    "Selected: " + this.files[0].name;
            }
        }
    );

    async function startCamera() {

        try {

            cameraStream =
                await navigator.mediaDevices.getUserMedia({
                    video: true,
                    audio: true
                });

            const video =
                document.getElementById("cameraPreview");

            video.srcObject = cameraStream;

            document.getElementById("cameraBox")
                .classList.remove("hidden");

        } catch (error) {

            alert(
                "Camera access was blocked. Please allow camera and microphone access in your browser."
            );

            console.log(error);
        }
    }

    function stopCamera() {

        if (cameraStream) {

            cameraStream.getTracks().forEach(
                track => track.stop()
            );

            cameraStream = null;
        }

        document.getElementById("cameraBox")
            .classList.add("hidden");
    }

    function toggleRecording() {

        if (!cameraStream) {
            alert("Start the camera first.");
            return;
        }

        if (isRecording) {
            recorder.stop();
            return;
        }

        recordedChunks = [];

        let mimeType = "";

        if (
            MediaRecorder.isTypeSupported(
                "video/webm;codecs=vp9,opus"
            )
        ) {
            mimeType =
                "video/webm;codecs=vp9,opus";
        } else if (
            MediaRecorder.isTypeSupported(
                "video/webm"
            )
        ) {
            mimeType = "video/webm";
        }

        try {

            recorder = new MediaRecorder(
                cameraStream,
                mimeType
                    ? { mimeType: mimeType }
                    : undefined
            );

        } catch (error) {

            alert("Your browser cannot record video here.");
            return;
        }

        recorder.ondataavailable = function(event) {

            if (event.data.size > 0) {
                recordedChunks.push(event.data);
            }
        };

        recorder.onstop = function() {

            const blob = new Blob(
                recordedChunks,
                {
                    type:
                        recorder.mimeType ||
                        "video/webm"
                }
            );

            const file = new File(
                [blob],
                "heara-recording.webm",
                {
                    type:
                        blob.type ||
                        "video/webm"
                }
            );

            const dataTransfer = new DataTransfer();

            dataTransfer.items.add(file);

            document.getElementById(
                "mediaInput"
            ).files = dataTransfer.files;

            document.getElementById(
                "selectedFile"
            ).innerText =
                "Recorded video ready to publish.";

            document.getElementById(
                "recordStatus"
            ).innerText =
                "Recording finished. Click Publish to Heara.";

            document.getElementById(
                "recordButton"
            ).innerText =
                "🔴 Start recording";

            isRecording = false;
        };

        recorder.start();

        isRecording = true;

        document.getElementById(
            "recordButton"
        ).innerText =
            "⏹ Stop recording";

        document.getElementById(
            "recordStatus"
        ).innerText =
            "Recording...";
    }
    """

    return page("Create", body, extra_js=js)


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    user = current_user()

    file = request.files.get("media")
    content = request.form.get("content", "").strip()

    if not file or not file.filename:
        if content:
            connection = db()

            connection.execute(
                """
                INSERT INTO posts
                (user_id, content, media_type, source)
                VALUES (?, ?, ?, ?)
                """,
                (
                    user["id"],
                    content,
                    "text",
                    "local"
                )
            )

            connection.commit()
            connection.close()

            return redirect(url_for("home"))

        return redirect(url_for("create"))

    filename = safe_filename(file.filename)

    if not is_video(filename) and not is_image(filename):
        return page(
            "Upload",
            """
            <div class="auth-wrap">
                <div class="card auth-card">
                    <h1>Unsupported file</h1>
                    <p class="muted">
                        Please choose an image or video.
                    </p>
                    <a href="/create" class="btn">
                        Back to Create
                    </a>
                </div>
            </div>
            """
        )

    unique_name = (
        secrets.token_hex(12) +
        "_" +
        filename
    )

    target = UPLOAD_DIR / unique_name

    file.save(str(target))

    media_type = "video" if is_video(filename) else "image"

    media_url = (
        "/static/uploads/" +
        urllib.parse.quote(unique_name)
    )

    connection = db()

    connection.execute(
        """
        INSERT INTO posts
        (
            user_id,
            content,
            media_url,
            media_type,
            source
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user["id"],
            content,
            media_url,
            media_type,
            "local"
        )
    )

    connection.commit()
    connection.close()

    return redirect(url_for("home"))


# ============================================================
# SIMPLE TEXT POST
# ============================================================

@app.route("/post", methods=["POST"])
@login_required
def create_text_post():
    user = current_user()

    content = request.form.get(
        "content",
        ""
    ).strip()

    if not content:
        return redirect(url_for("home"))

    connection = db()

    connection.execute(
        """
        INSERT INTO posts
        (
            user_id,
            content,
            media_type,
            source
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            user["id"],
            content,
            "text",
            "local"
        )
    )

    connection.commit()
    connection.close()

    return redirect(url_for("home"))


# ============================================================
# FYP
# ============================================================

@app.route("/videos")
@login_required
def videos():
    return fyp()


@app.route("/fyp")
@login_required
def fyp():
    videos_data = pexels_videos(
        page=1,
        per_page=15
    )

    cards = ""

    for video in videos_data:

        video_id = str(video.get("id", ""))

        video_url = video.get("url", "")
        poster = video.get("image", "")
        photographer = video.get(
            "photographer",
            "Pexels creator"
        )

        pexels_url = video.get(
            "pexels_url",
            "https://www.pexels.com/"
        )

        video_json = json.dumps({
            "id": video_id,
            "url": video_url,
            "poster": poster,
            "photographer": photographer,
            "pexels_url": pexels_url,
        }).replace(
            "</",
            "<\\/"
        )

        cards += """
        <section
            class="fyp-card"
            data-video='__VIDEO_DATA__'
        >

            <video
                class="fyp-video"
                playsinline
                loop
                muted
                preload="metadata"
                poster="__POSTER__"
            >
                <source
                    src="__VIDEO_URL__"
                    type="video/mp4"
                >
            </video>

            <div class="fyp-overlay"></div>

            <div class="fyp-info">

                <h3>
                    Discover on Heara
                </h3>

                <p>
                    Watch. Share. Create.
                </p>

                <div class="source-credit">
                    Video by __PHOTOGRAPHER__
                    · Pexels
                </div>

            </div>

            <div class="fyp-actions">

                <button
                    class="fyp-action"
                    onclick="toggleSound(this)"
                    title="Sound"
                >
                    🔇
                </button>

                <button
                    class="fyp-action"
                    onclick="shareVideo(this)"
                    title="Share"
                >
                    ↗
                </button>

                <a
                    class="fyp-action"
                    href="/create"
                    title="Create"
                >
                    ＋
                </a>

            </div>

        </section>
        """.replace(
            "__VIDEO_DATA__",
            video_json.replace(
                "'",
                "&#39;"
            )
        ).replace(
            "__POSTER__",
            poster
        ).replace(
            "__VIDEO_URL__",
            video_url
        ).replace(
            "__PHOTOGRAPHER__",
            photographer
        )

    if not cards:
        cards = """
        <div class="fyp-loading">
            <div>
                <h2>Heara FYP</h2>
                <p>
                    Pexels videos are temporarily unavailable.
                </p>
                <p>
                    Check that your PEXELS_API_KEY is still
                    present in Render Environment Variables.
                </p>
            </div>
        </div>
        """

    body = """
    <div class="fyp-page">

        <div class="fyp-top">
            <strong>Heara FYP</strong>
        </div>

        <div
            class="fyp-wrap"
            id="fypWrap"
        >
            __CARDS__
        </div>

    </div>
    """.replace(
        "__CARDS__",
        cards
    )

    js = """
    const feed = document.getElementById("fypWrap");

    const cards =
        Array.from(
            document.querySelectorAll(".fyp-card")
        );

    let activeCard = null;

    function pauseAllExcept(video) {

        document
            .querySelectorAll(".fyp-video")
            .forEach(function(item) {

                if (item !== video) {
                    item.pause();
                }

            });
    }

    function playVideo(video) {

        if (!video) {
            return;
        }

        pauseAllExcept(video);

        const promise = video.play();

        if (promise) {
            promise.catch(function() {
                // Browser autoplay policy may block
                // sound. Video remains available muted.
            });
        }

        activeCard =
            video.closest(".fyp-card");
    }

    function toggleSound(button) {

        const card =
            button.closest(".fyp-card");

        const video =
            card.querySelector(".fyp-video");

        video.muted = !video.muted;

        button.innerText =
            video.muted
                ? "🔇"
                : "🔊";

        playVideo(video);
    }

    async function shareVideo(button) {

        const card =
            button.closest(".fyp-card");

        let data = {};

        try {
            data = JSON.parse(
                card.dataset.video
            );
        } catch (error) {
            console.log(error);
        }

        const shareUrl =
            window.location.origin +
            "/pexels/" +
            data.id;

        if (navigator.share) {

            try {

                await navigator.share({
                    title: "Heara",
                    text:
                        "Watch this video on Heara",
                    url: shareUrl
                });

                return;

            } catch (error) {}
        }

        try {

            await navigator.clipboard.writeText(
                shareUrl
            );

            alert("Heara share link copied.");

        } catch (error) {

            prompt(
                "Copy this Heara link:",
                shareUrl
            );
        }
    }

    const observer =
        new IntersectionObserver(
            function(entries) {

                entries.forEach(function(entry) {

                    const video =
                        entry.target.querySelector(
                            ".fyp-video"
                        );

                    if (!video) {
                        return;
                    }

                    if (
                        entry.isIntersecting &&
                        entry.intersectionRatio >= .65
                    ) {

                        playVideo(video);

                    } else {

                        video.pause();
                    }

                });

            },
            {
                threshold: [0, .25, .65, 1]
            }
        );

    cards.forEach(function(card) {
        observer.observe(card);
    });

    document.addEventListener(
        "keydown",
        function(event) {

            if (!activeCard) {
                activeCard = cards[0];
            }

            if (
                event.key === "ArrowDown" ||
                event.key === "PageDown"
            ) {

                event.preventDefault();

                const next =
                    activeCard.nextElementSibling;

                if (next) {

                    next.scrollIntoView({
                        behavior: "smooth"
                    });
                }
            }

            if (
                event.key === "ArrowUp" ||
                event.key === "PageUp"
            ) {

                event.preventDefault();

                const previous =
                    activeCard.previousElementSibling;

                if (previous) {

                    previous.scrollIntoView({
                        behavior: "smooth"
                    });
                }
            }

        }
    );

    let wheelLocked = false;

    feed.addEventListener(
        "wheel",
        function(event) {

            if (wheelLocked) {
                return;
            }

            if (Math.abs(event.deltaY) < 20) {
                return;
            }

            event.preventDefault();

            wheelLocked = true;

            if (!activeCard) {
                activeCard = cards[0];
            }

            const target =
                event.deltaY > 0
                    ? activeCard.nextElementSibling
                    : activeCard.previousElementSibling;

            if (target) {

                target.scrollIntoView({
                    behavior: "smooth"
                });
            }

            setTimeout(
                function() {
                    wheelLocked = false;
                },
                650
            );

        },
        {
            passive: false
        }
    );

    // Start the first video.
    window.addEventListener(
        "load",
        function() {

            const first =
                document.querySelector(
                    ".fyp-video"
                );

            if (first) {
                playVideo(first);
            }

        }
    );
    """

    return page(
        "FYP",
        body,
        extra_js=js
    )


# ============================================================
# PEXELS SHARE PAGE
# ============================================================

@app.route("/pexels/<video_id>")
@login_required
def pexels_share(video_id):

    data = pexels_request(
        "videos/videos/" + urllib.parse.quote(
            str(video_id)
        )
    )

    if not data:
        return redirect(url_for("videos"))

    files = data.get("video_files", [])

    if not files:
        return redirect(url_for("videos"))

    selected = files[0]

    for item in files:
        width = item.get("width") or 0
        height = item.get("height") or 0

        if height >= width:
            selected = item
            break

    video_url = selected.get("link", "")

    photographer = data.get(
        "user",
        {}
    ).get(
        "name",
        "Pexels creator"
    )

    pexels_url = data.get(
        "url",
        "https://www.pexels.com/"
    )

    body = """
    <main class="container">

        <div class="page-title">
            Heara Video
        </div>

        <div class="card post-card">

            <video
                class="post-media"
                controls
                autoplay
                muted
                loop
                playsinline
                src="__VIDEO_URL__"
            ></video>

            <h3>
                Video by __PHOTOGRAPHER__
            </h3>

            <p class="muted">
                Original video from Pexels.
            </p>

            <div class="post-actions">

                <button
                    class="action-btn"
                    onclick="sharePage()"
                >
                    🔗 Share
                </button>

                <a
                    class="action-btn"
                    href="__PEXELS_URL__"
                    target="_blank"
                    rel="noopener"
                >
                    View on Pexels
                </a>

                <a
                    class="action-btn"
                    href="/create"
                >
                    🎥 Create your own
                </a>

            </div>

        </div>

    </main>
    """.replace(
        "__VIDEO_URL__",
        video_url
    ).replace(
        "__PHOTOGRAPHER__",
        photographer
    ).replace(
        "__PEXELS_URL__",
        pexels_url
    )

    js = """
    async function sharePage() {

        const link =
            window.location.href;

        if (navigator.share) {

            try {

                await navigator.share({
                    title: "Heara",
                    text: "Watch this video on Heara",
                    url: link
                });

                return;

            } catch (error) {}
        }

        try {

            await navigator.clipboard.writeText(link);

            alert("Link copied.");

        } catch (error) {

            prompt(
                "Copy this link:",
                link
            );
        }
    }
    """

    return page(
        "Heara Video",
        body,
        extra_js=js
    )


# ============================================================
# LIKE
# ============================================================

@app.route("/like/<int:post_id>", methods=["POST"])
@login_required
def like(post_id):

    user = current_user()

    connection = db()

    existing = connection.execute(
        """
        SELECT id
        FROM likes
        WHERE user_id = ?
        AND post_id = ?
        """,
        (
            user["id"],
            post_id
        )
    ).fetchone()

    if existing:

        connection.execute(
            "DELETE FROM likes WHERE id = ?",
            (existing["id"],)
        )

        connection.execute(
            """
            UPDATE posts
            SET likes = MAX(0, likes - 1)
            WHERE id = ?
            """,
            (post_id,)
        )

    else:

        connection.execute(
            """
            INSERT OR IGNORE INTO likes
            (user_id, post_id)
            VALUES (?, ?)
            """,
            (
                user["id"],
                post_id
            )
        )

        connection.execute(
            """
            UPDATE posts
            SET likes = likes + 1
            WHERE id = ?
            """,
            (post_id,)
        )

    row = connection.execute(
        """
        SELECT likes
        FROM posts
        WHERE id = ?
        """,
        (post_id,)
    ).fetchone()

    connection.commit()
    connection.close()

    return jsonify({
        "ok": True,
        "likes": row["likes"] if row else 0
    })


# ============================================================
# POST DETAIL / COMMENTS
# ============================================================

@app.route("/post/<int:post_id>")
@login_required
def post_detail(post_id):

    connection = db()

    post = connection.execute(
        """
        SELECT
            posts.*,
            users.username
        FROM posts
        LEFT JOIN users
        ON users.id = posts.user_id
        WHERE posts.id = ?
        """,
        (post_id,)
    ).fetchone()

    comments = connection.execute(
        """
        SELECT
            comments.*,
            users.username
        FROM comments
        LEFT JOIN users
        ON users.id = comments.user_id
        WHERE comments.post_id = ?
        ORDER BY comments.id ASC
        """,
        (post_id,)
    ).fetchall()

    connection.close()

    if not post:
        abort(404)

    media = ""

    if post["media_type"] == "video":
        media = """
        <video
            class="post-media"
            controls
            playsinline
            src="__URL__"
        ></video>
        """.replace(
            "__URL__",
            post["media_url"]
        )

    elif post["media_type"] == "image":
        media = """
        <img
            class="post-media"
            src="__URL__"
        >
        """.replace(
            "__URL__",
            post["media_url"]
        )

    comments_html = ""

    for comment in comments:

        comments_html += """
        <div
            style="
                padding:12px 0;
                border-bottom:1px solid rgba(255,255,255,.06);
            "
        >
            <strong>__USER__</strong>
            <div class="muted">
                __TEXT__
            </div>
        </div>
        """.replace(
            "__USER__",
            comment["username"]
        ).replace(
            "__TEXT__",
            comment["text"]
        )

    if not comments_html:
        comments_html = """
        <div class="empty">
            No comments yet.
        </div>
        """

    body = """
    <main class="container">

        <div class="page-title">
            Post
        </div>

        <article class="card post-card">

            <div class="post-head">
                <div class="avatar">
                    __INITIAL__
                </div>

                <strong>
                    __USERNAME__
                </strong>
            </div>

            <div class="post-content">
                __CONTENT__
            </div>

            __MEDIA__

            <div class="post-actions">

                <button
                    class="action-btn"
                    onclick="likePost(__ID__, this)"
                >
                    ❤️ __LIKES__
                </button>

                <button
                    class="action-btn"
                    onclick="sharePost()"
                >
                    🔗 Share
                </button>

            </div>

        </article>

        <div class="card post-card">

            <h3>Comments</h3>

            <form method="POST" action="/comment">

                <input
                    type="hidden"
                    name="post_id"
                    value="__ID__"
                >

                <textarea
                    name="text"
                    placeholder="Write a comment..."
                    required
                ></textarea>

                <button
                    class="btn"
                    type="submit"
                    style="margin-top:10px;"
                >
                    Comment
                </button>

            </form>

            <div style="margin-top:20px;">
                __COMMENTS__
            </div>

        </div>

    </main>
    """.replace(
        "__INITIAL__",
        (post["username"] or "H")[:1].upper()
    ).replace(
        "__USERNAME__",
        post["username"] or "Heara user"
    ).replace(
        "__CONTENT__",
        post["content"] or ""
    ).replace(
        "__MEDIA__",
        media
    ).replace(
        "__ID__",
        str(post["id"])
    ).replace(
        "__LIKES__",
        str(post["likes"] or 0)
    ).replace(
        "__COMMENTS__",
        comments_html
    )

    js = """
    async function likePost(id, button) {

        const response =
            await fetch(
                "/like/" + id,
                {
                    method: "POST"
                }
            );

        const data =
            await response.json();

        if (data.ok) {
            button.innerText =
                "❤️ " + data.likes;
        }
    }

    async function sharePost() {

        const link =
            window.location.href;

        if (navigator.share) {

            try {

                await navigator.share({
                    title: "Heara",
                    text: "Check out this Heara post",
                    url: link
                });

                return;

            } catch (error) {}
        }

        await navigator.clipboard.writeText(link);

        alert("Link copied.");
    }
    """

    return page(
        "Post",
        body,
        extra_js=js
    )


@app.route("/comment", methods=["POST"])
@login_required
def comment():

    user = current_user()

    post_id = request.form.get(
        "post_id",
        type=int
    )

    text = request.form.get(
        "text",
        ""
    ).strip()

    if not post_id or not text:
        return redirect(url_for("home"))

    connection = db()

    connection.execute(
        """
        INSERT INTO comments
        (user_id, post_id, text)
        VALUES (?, ?, ?)
        """,
        (
            user["id"],
            post_id,
            text[:1000]
        )
    )

    connection.execute(
        """
        UPDATE posts
        SET comments = comments + 1
        WHERE id = ?
        """,
        (post_id,)
    )

    connection.commit()
    connection.close()

    return redirect(
        url_for(
            "post_detail",
            post_id=post_id
        )
    )


# ============================================================
# FOLLOW
# ============================================================

@app.route("/follow/<username>", methods=["POST"])
@login_required
def follow(username):

    user = current_user()

    connection = db()

    target = connection.execute(
        """
        SELECT *
        FROM users
        WHERE username = ?
        """,
        (username,)
    ).fetchone()

    if not target or target["id"] == user["id"]:
        connection.close()

        return jsonify({
            "ok": False
        })

    connection.execute(
        """
        INSERT OR IGNORE INTO follows
        (follower_id, following_id)
        VALUES (?, ?)
        """,
        (
            user["id"],
            target["id"]
        )
    )

    connection.execute(
        """
        UPDATE users
        SET followers =
            (
                SELECT COUNT(*)
                FROM follows
                WHERE following_id = users.id
            )
        """
    )

    connection.execute(
        """
        UPDATE users
        SET following =
            (
                SELECT COUNT(*)
                FROM follows
                WHERE follower_id = users.id
            )
        """
    )

    connection.commit()
    connection.close()

    return jsonify({
        "ok": True
    })


@app.route("/unfollow/<username>", methods=["POST"])
@login_required
def unfollow(username):

    user = current_user()

    connection = db()

    target = connection.execute(
        """
        SELECT *
        FROM users
        WHERE username = ?
        """,
        (username,)
    ).fetchone()

    if target:

        connection.execute(
            """
            DELETE FROM follows
            WHERE follower_id = ?
            AND following_id = ?
            """,
            (
                user["id"],
                target["id"]
            )
        )

        connection.execute(
            """
            UPDATE users
            SET followers =
                (
                    SELECT COUNT(*)
                    FROM follows
                    WHERE following_id = users.id
                )
            """
        )

        connection.execute(
            """
            UPDATE users
            SET following =
                (
                    SELECT COUNT(*)
                    FROM follows
                    WHERE follower_id = users.id
                )
            """
        )

        connection.commit()

    connection.close()

    return jsonify({
        "ok": True
    })


# ============================================================
# PROFILE
# ============================================================

@app.route("/profile/<username>")
@login_required
def profile(username):

    connection = db()

    user = connection.execute(
        """
        SELECT *
        FROM users
        WHERE username = ?
        """,
        (username,)
    ).fetchone()

    if not user:
        connection.close()
        abort(404)

    posts = connection.execute(
        """
        SELECT *
        FROM posts
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 30
        """,
        (user["id"],)
    ).fetchall()

    me = current_user()

    following = connection.execute(
        """
        SELECT id
        FROM follows
        WHERE follower_id = ?
        AND following_id = ?
        """,
        (
            me["id"],
            user["id"]
        )
    ).fetchone()

    connection.close()

    post_html = ""

    for post in posts:

        media = ""

        if post["media_type"] == "video":
            media = """
            <video
                class="post-media"
                controls
                playsinline
                src="__URL__"
            ></video>
            """.replace(
                "__URL__",
                post["media_url"]
            )

        elif post["media_type"] == "image":
            media = """
            <img
                class="post-media"
                src="__URL__"
            >
            """.replace(
                "__URL__",
                post["media_url"]
            )

        post_html += """
        <article class="card post-card">

            <div class="post-content">
                __CONTENT__
            </div>

            __MEDIA__

            <div class="post-actions">

                <a
                    class="action-btn"
                    href="/post/__ID__"
                >
                    💬 __COMMENTS__
                </a>

                <button
                    class="action-btn"
                    onclick="sharePost(__ID__)"
                >
                    🔗 Share
                </button>

            </div>

        </article>
        """.replace(
            "__CONTENT__",
            post["content"] or ""
        ).replace(
            "__MEDIA__",
            media
        ).replace(
            "__ID__",
            str(post["id"])
        ).replace(
            "__COMMENTS__",
            str(post["comments"] or 0)
        )

    if not post_html:
        post_html = """
        <div class="card empty">
            No posts yet.
        </div>
        """

    avatar = user["avatar"] or ""

    if avatar:
        avatar_html = """
        <img
            src="__AVATAR__"
            class="profile-avatar"
        >
        """.replace(
            "__AVATAR__",
            avatar
        )
    else:
        avatar_html = """
        <div
            class="profile-avatar"
            style="
                display:grid;
                place-items:center;
                font-size:35px;
            "
        >
            __INITIAL__
        </div>
        """.replace(
            "__INITIAL__",
            username[:1].upper()
        )

    follow_button = ""

    if user["id"] != me["id"]:

        if following:
            follow_button = """
            <button
                class="btn secondary"
                onclick="followUser(false)"
            >
                Following
            </button>
            """
        else:
            follow_button = """
            <button
                class="btn"
                onclick="followUser(true)"
            >
                Follow
            </button>
            """

    body = """
    <main class="container">

        <div class="card profile-card">

            <div class="profile-top">

                __AVATAR__

                <div>

                    <h1 style="margin:0;">
                        __USERNAME__
                    </h1>

                    <p class="muted">
                        @__USERNAME__
                    </p>

                    <p>
                        __BIO__
                    </p>

                </div>

            </div>

            <div class="stats">

                <div class="stat">
                    <strong>__FOLLOWERS__</strong>
                    <span class="muted">
                        Followers
                    </span>
                </div>

                <div class="stat">
                    <strong>__FOLLOWING__</strong>
                    <span class="muted">
                        Following
                    </span>
                </div>

            </div>

            <div class="create-buttons" style="margin-top:20px;">
                __FOLLOW_BUTTON__
            </div>

        </div>

        <div class="page-title">
            Posts
        </div>

        __POSTS__

    </main>
    """.replace(
        "__AVATAR__",
        avatar_html
    ).replace(
        "__USERNAME__",
        username
    ).replace(
        "__BIO__",
        user["bio"] or ""
    ).replace(
        "__FOLLOWERS__",
        str(user["followers"] or 0)
    ).replace(
        "__FOLLOWING__",
        str(user["following"] or 0)
    ).replace(
        "__FOLLOW_BUTTON__",
        follow_button
    ).replace(
        "__POSTS__",
        post_html
    )

    js = """
    async function followUser(value) {

        const action =
            value
                ? "/follow/__USERNAME__"
                : "/unfollow/__USERNAME__";

        const response =
            await fetch(
                action,
                {
                    method: "POST"
                }
            );

        const data =
            await response.json();

        if (data.ok) {
            window.location.reload();
        }
    }

    async function sharePost(id) {

        const link =
            window.location.origin +
            "/post/" +
            id;

        if (navigator.share) {

            try {

                await navigator.share({
                    title: "Heara",
                    text: "Check this out on Heara",
                    url: link
                });

                return;

            } catch (error) {}
        }

        await navigator.clipboard.writeText(link);

        alert("Link copied.");
    }
    """.replace(
        "__USERNAME__",
        urllib.parse.quote(username)
    )

    return page(
        username,
        body,
        extra_js=js
    )


# ============================================================
# INBOX
# ============================================================

@app.route("/inbox")
@login_required
def inbox():

    user = current_user()

    connection = db()

    people = connection.execute(
        """
        SELECT DISTINCT
            users.id,
            users.username
        FROM users
        JOIN messages
        ON
            (
                messages.sender_id = users.id
                AND messages.receiver_id = ?
            )
            OR
            (
                messages.receiver_id = users.id
                AND messages.sender_id = ?
            )
        WHERE users.id != ?
        ORDER BY users.username
        """,
        (
            user["id"],
            user["id"],
            user["id"]
        )
    ).fetchall()

    connection.close()

    people_html = ""

    for person in people:

        people_html += """
        <a
            href="/chat/__USERNAME__"
            class="card"
            style="
                display:block;
                padding:18px;
                margin-bottom:10px;
            "
        >
            <strong>@__USERNAME__</strong>
            <div class="muted">
                Open conversation
            </div>
        </a>
        """.replace(
            "__USERNAME__",
            urllib.parse.quote(person["username"])
        )

    if not people_html:
        people_html = """
        <div class="card empty">
            No conversations yet.
            Visit someone's profile to start connecting.
        </div>
        """

    body = """
    <main class="container">

        <div class="page-title">
            Inbox
        </div>

        __PEOPLE__

    </main>
    """.replace(
        "__PEOPLE__",
        people_html
    )

    return page(
        "Inbox",
        body
    )


@app.route("/chat/<username>", methods=["GET", "POST"])
@login_required
def chat(username):

    me = current_user()

    connection = db()

    other = connection.execute(
        """
        SELECT *
        FROM users
        WHERE username = ?
        """,
        (username,)
    ).fetchone()

    if not other:
        connection.close()
        abort(404)

    if request.method == "POST":

        text = request.form.get(
            "text",
            ""
        ).strip()

        if text:

            connection.execute(
                """
                INSERT INTO messages
                (
                    sender_id,
                    receiver_id,
                    text
                )
                VALUES (?, ?, ?)
                """,
                (
                    me["id"],
                    other["id"],
                    text[:2000]
                )
            )

            connection.commit()

    messages = connection.execute(
        """
        SELECT
            messages.*,
            users.username
        FROM messages
        LEFT JOIN users
        ON users.id = messages.sender_id
        WHERE
            (
                sender_id = ?
                AND receiver_id = ?
            )
            OR
            (
                sender_id = ?
                AND receiver_id = ?
            )
        ORDER BY messages.id ASC
        """,
        (
            me["id"],
            other["id"],
            other["id"],
            me["id"]
        )
    ).fetchall()

    connection.close()

    message_html = ""

    for message in messages:

        align = (
            "margin-left:auto;"
            if message["sender_id"] == me["id"]
            else "margin-right:auto;"
        )

        message_html += """
        <div
            style="
                max-width:75%;
                __ALIGN__
                margin-bottom:10px;
                padding:12px 15px;
                border-radius:15px;
                background:rgba(255,255,255,.08);
            "
        >
            __TEXT__
        </div>
        """.replace(
            "__ALIGN__",
            align
        ).replace(
            "__TEXT__",
            message["text"]
        )

    body = """
    <main class="container">

        <div class="page-title">
            Chat with @__USERNAME__
        </div>

        <div class="card post-card">

            <div
                style="
                    max-height:500px;
                    overflow-y:auto;
                "
            >
                __MESSAGES__
            </div>

            <form method="POST" style="margin-top:20px;">

                <textarea
                    name="text"
                    placeholder="Write a message..."
                    required
                    style="min-height:80px;"
                ></textarea>

                <button
                    class="btn"
                    type="submit"
                    style="margin-top:10px;"
                >
                    Send
                </button>

            </form>

        </div>

    </main>
    """.replace(
        "__USERNAME__",
        username
    ).replace(
        "__MESSAGES__",
        message_html
    )

    return page(
        "Chat",
        body
    )


# ============================================================
# LIVE
# ============================================================

@app.route("/live")
@login_required
def live():

    connection = db()

    rooms = connection.execute(
        """
        SELECT
            live_rooms.*,
            users.username,
            users.followers
        FROM live_rooms
        LEFT JOIN users
        ON users.id = live_rooms.user_id
        WHERE live_rooms.active = 1
        ORDER BY live_rooms.id DESC
        """
    ).fetchall()

    connection.close()

    room_html = ""

    for room in rooms:

        room_html += """
        <a
            href="/live-room/__ID__"
            class="card"
            style="
                display:block;
                padding:20px;
                margin-bottom:14px;
            "
        >
            <h3>
                🔴 __TITLE__
            </h3>

            <p class="muted">
                @__USERNAME__
            </p>

            <span class="btn">
                Watch live
            </span>
        </a>
        """.replace(
            "__ID__",
            str(room["id"])
        ).replace(
            "__TITLE__",
            room["title"]
        ).replace(
            "__USERNAME__",
            room["username"]
        )

    if not room_html:
        room_html = """
        <div class="card empty">
            <h2>No one is live right now.</h2>
            <p>
                You can be the first.
            </p>
        </div>
        """

    body = """
    <main class="container">

        <div class="page-title">
            Live
        </div>

        <div class="card post-card">

            <h2>Go live on Heara</h2>

            <p class="muted">
                Heara currently requires at least
                <strong>250 followers</strong>
                to start a live broadcast.
            </p>

            <a
                href="/go-live"
                class="btn"
            >
                Go Live
            </a>

        </div>

        <h2>Live now</h2>

        __ROOMS__

    </main>
    """.replace(
        "__ROOMS__",
        room_html
    )

    return page(
        "Live",
        body
    )


@app.route("/go-live")
@login_required
def go_live():

    user = current_user()

    if (user["followers"] or 0) < LIVE_FOLLOWERS:

        body = """
        <main class="container">

            <div class="card auth-card" style="margin-top:50px;">

                <h1>🔒 Live is locked</h1>

                <p class="muted">
                    You need at least
                    <strong>250 followers</strong>
                    to start a Heara live.
                </p>

                <p>
                    Your current followers:
                    <strong>__FOLLOWERS__</strong>
                </p>

                <a
                    href="/profile/__USERNAME__"
                    class="btn"
                >
                    View profile
                </a>

            </div>

        </main>
        """.replace(
            "__FOLLOWERS__",
            str(user["followers"] or 0)
        ).replace(
            "__USERNAME__",
            urllib.parse.quote(user["username"])
        )

        return page(
            "Go Live",
            body
        )

    body = """
    <main class="container">

        <div class="page-title">
            Go Live
        </div>

        <div class="card post-card">

            <h2>Start your Heara live</h2>

            <p class="muted">
                Allow camera and microphone access.
            </p>

            <video
                id="livePreview"
                autoplay
                muted
                playsinline
                class="post-media"
            ></video>

            <div class="create-buttons">

                <button
                    class="btn"
                    onclick="startLiveCamera()"
                >
                    📹 Start camera
                </button>

                <button
                    class="btn danger"
                    onclick="endLive()"
                >
                    End live
                </button>

            </div>

            <p
                id="liveStatus"
                class="muted"
                style="margin-top:15px;"
            >
                Camera is off.
            </p>

            <p class="muted">
                This page provides the camera/live interface.
                Full internet-wide broadcasting requires a
                WebRTC/media server, which is separate from Flask.
            </p>

        </div>

    </main>
    """

    js = """
    let liveStream = null;

    async function startLiveCamera() {

        try {

            liveStream =
                await navigator.mediaDevices.getUserMedia({
                    video: true,
                    audio: true
                });

            document.getElementById(
                "livePreview"
            ).srcObject = liveStream;

            document.getElementById(
                "liveStatus"
            ).innerText =
                "Camera and microphone are active.";

        } catch (error) {

            console.log(error);

            document.getElementById(
                "liveStatus"
            ).innerText =
                "Camera/microphone permission was denied.";
        }
    }

    function endLive() {

        if (liveStream) {

            liveStream.getTracks().forEach(
                track => track.stop()
            );

            liveStream = null;
        }

        document.getElementById(
            "livePreview"
        ).srcObject = null;

        document.getElementById(
            "liveStatus"
        ).innerText =
            "Live ended.";
    }
    """

    return page(
        "Go Live",
        body,
        extra_js=js
    )


@app.route("/live-room/<int:room_id>")
@login_required
def live_room(room_id):

    connection = db()

    room = connection.execute(
        """
        SELECT
            live_rooms.*,
            users.username
        FROM live_rooms
        LEFT JOIN users
        ON users.id = live_rooms.user_id
        WHERE live_rooms.id = ?
        """,
        (room_id,)
    ).fetchone()

    connection.close()

    if not room:
        abort(404)

    body = """
    <main class="container">

        <div class="page-title">
            🔴 __TITLE__
        </div>

        <div class="card post-card">

            <h2>
                @__USERNAME__ is live
            </h2>

            <div
                style="
                    aspect-ratio:16/9;
                    background:#000;
                    border-radius:18px;
                    display:grid;
                    place-items:center;
                    margin:20px 0;
                "
            >
                <div style="text-align:center;">
                    <div style="font-size:55px;">
                        🔴
                    </div>
                    <p>
                        Live room
                    </p>
                    <p class="muted">
                        Camera broadcasting infrastructure
                        can be connected here.
                    </p>
                </div>
            </div>

            <a
                href="/live"
                class="btn secondary"
            >
                Back to Live
            </a>

        </div>

    </main>
    """.replace(
        "__TITLE__",
        room["title"]
    ).replace(
        "__USERNAME__",
        room["username"]
    )

    return page(
        "Live Room",
        body
    )


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
        "id": user["id"],
        "username": user["username"],
        "followers": user["followers"],
        "following": user["following"]
    })


@app.route("/api/fyp")
@login_required
def api_fyp():

    page_number = request.args.get(
        "page",
        1,
        type=int
    )

    if page_number < 1:
        page_number = 1

    videos_data = pexels_videos(
        page=page_number,
        per_page=15
    )

    return jsonify({
        "ok": True,
        "videos": videos_data
    })


@app.route("/api/view", methods=["POST"])
def api_view():

    return jsonify({
        "ok": True
    })


@app.route("/health")
def health():

    return jsonify({
        "status": "ok",
        "service": "Heara",
        "pexels_configured": bool(
            PEXELS_API_KEY
        )
    })


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    body = """
    <main class="container">

        <div class="card auth-card" style="margin-top:60px;">

            <h1>404</h1>

            <p class="muted">
                That Heara page does not exist.
            </p>

            <a
                href="/"
                class="btn"
            >
                Back home
            </a>

        </div>

    </main>
    """

    return page(
        "Not Found",
        body
    ), 404


@app.errorhandler(500)
def server_error(error):

    body = """
    <main class="container">

        <div class="card auth-card" style="margin-top:60px;">

            <h1>Something went wrong.</h1>

            <p class="muted">
                Heara encountered a server error.
            </p>

            <a
                href="/"
                class="btn"
            >
                Back home
            </a>

        </div>

    </main>
    """

    return page(
        "Error",
        body
    ), 500


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
