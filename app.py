from flask import (
    Flask, request, redirect, url_for, session,
    jsonify, render_template_string, flash
)
import sqlite3
import os
import time
import secrets
from functools import wraps
from datetime import datetime

# ============================================================
# HEARA
# All-in-one social platform MVP
#
# Features:
# - Accounts
# - Profiles
# - FYP
# - Video posts
# - Text posts
# - Likes
# - Comments
# - Shares
# - Following
# - Inbox / direct messages
# - Notifications
# - Live rooms
# - 250 follower live eligibility
# - Creator dashboard
# - Monetization framework
# - Search
# - Trending
#
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "heara-development-secret-change-this"
)

DATABASE = os.environ.get("DATABASE_PATH", "heara.db")

LIVE_FOLLOWER_REQUIREMENT = 250


# ============================================================
# DATABASE
# ============================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    db = get_db()

    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        display_name TEXT,
        bio TEXT DEFAULT '',
        avatar TEXT DEFAULT '',
        followers INTEGER DEFAULT 0,
        following INTEGER DEFAULT 0,
        verified INTEGER DEFAULT 0,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        post_type TEXT DEFAULT 'video',
        video_url TEXT DEFAULT '',
        image_url TEXT DEFAULT '',
        text TEXT DEFAULT '',
        caption TEXT DEFAULT '',
        category TEXT DEFAULT 'General',
        views INTEGER DEFAULT 0,
        likes INTEGER DEFAULT 0,
        comments INTEGER DEFAULT 0,
        shares INTEGER DEFAULT 0,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        post_id INTEGER NOT NULL,
        UNIQUE(user_id, post_id)
    );

    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        post_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS follows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        follower_id INTEGER NOT NULL,
        following_id INTEGER NOT NULL,
        UNIQUE(follower_id, following_id)
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        read INTEGER DEFAULT 0,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        actor_id INTEGER,
        notification_type TEXT,
        message TEXT,
        read INTEGER DEFAULT 0,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS live_rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT,
        room_code TEXT UNIQUE,
        active INTEGER DEFAULT 1,
        viewers INTEGER DEFAULT 0,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS live_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_code TEXT NOT NULL,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER,
        signal_type TEXT,
        signal TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS earnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount REAL DEFAULT 0,
        source TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reporter_id INTEGER NOT NULL,
        post_id INTEGER,
        reported_user_id INTEGER,
        reason TEXT,
        created_at TEXT
    );
    """)

    db.commit()
    db.close()


init_db()


# ============================================================
# HELPERS
# ============================================================

def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    db.close()

    return user


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def notify(user_id, actor_id, notification_type, message):
    db = get_db()

    db.execute("""
        INSERT INTO notifications
        (user_id, actor_id, notification_type, message, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        user_id,
        actor_id,
        notification_type,
        message,
        now()
    ))

    db.commit()
    db.close()


def get_user(user_id):
    db = get_db()

    user = db.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    db.close()

    return user


# ============================================================
# BASE DESIGN
# ============================================================

BASE_CSS = """

* {
    box-sizing: border-box;
}

html, body {
    margin: 0;
    padding: 0;
    background: #05050a;
    color: white;
    font-family: Arial, Helvetica, sans-serif;
}

body {
    min-height: 100vh;
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
    min-height: 100vh;
    background:
        radial-gradient(circle at 20% 10%, rgba(91, 45, 170, .25), transparent 30%),
        radial-gradient(circle at 80% 20%, rgba(0, 160, 255, .12), transparent 30%),
        #05050a;
}

.nav {
    position: fixed;
    z-index: 1000;
    top: 0;
    left: 0;
    right: 0;
    height: 64px;
    background: rgba(5,5,10,.88);
    backdrop-filter: blur(15px);
    border-bottom: 1px solid rgba(255,255,255,.08);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 22px;
}

.logo {
    font-size: 25px;
    font-weight: 900;
    letter-spacing: -1px;
    background: linear-gradient(90deg,#fff,#a970ff,#56c8ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.navlinks {
    display: flex;
    gap: 18px;
    align-items: center;
}

.navlinks a {
    color: #ddd;
    font-size: 14px;
}

.navlinks a:hover {
    color: white;
}

.page {
    padding-top: 80px;
    max-width: 1100px;
    margin: auto;
    padding-left: 18px;
    padding-right: 18px;
}

.card {
    background: rgba(20,20,30,.75);
    border: 1px solid rgba(255,255,255,.08);
    border-radius: 18px;
    padding: 20px;
    margin-bottom: 18px;
}

.btn {
    border: 0;
    border-radius: 12px;
    padding: 11px 17px;
    background: linear-gradient(135deg,#7d35ff,#a85dff);
    color: white;
    font-weight: bold;
}

.btn.secondary {
    background: #20202c;
}

.btn.danger {
    background: #d92752;
}

input,
textarea,
select {
    width: 100%;
    padding: 13px;
    background: #11111a;
    color: white;
    border: 1px solid #292938;
    border-radius: 12px;
    margin-bottom: 12px;
}

textarea {
    min-height: 100px;
    resize: vertical;
}

.avatar {
    width: 45px;
    height: 45px;
    border-radius: 50%;
    background: linear-gradient(135deg,#6b2cff,#22b8ff);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: bold;
}

.muted {
    color: #999;
}

.stats {
    display: flex;
    gap: 25px;
    margin: 15px 0;
}

.stat strong {
    display: block;
    font-size: 20px;
}

.post {
    margin-bottom: 20px;
}

.post-head {
    display: flex;
    gap: 12px;
    align-items: center;
    margin-bottom: 12px;
}

.post-video {
    width: 100%;
    max-height: 650px;
    object-fit: contain;
    background: black;
    border-radius: 16px;
}

.post-actions {
    display: flex;
    gap: 12px;
    padding: 12px 0;
}

.action {
    background: #15151f;
    border: 0;
    color: white;
    padding: 9px 14px;
    border-radius: 10px;
}

.grid {
    display: grid;
    grid-template-columns: repeat(3,1fr);
    gap: 12px;
}

.grid-item {
    background: #101018;
    border-radius: 14px;
    overflow: hidden;
    aspect-ratio: 9/14;
}

.grid-item video {
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.message {
    padding: 12px;
    margin: 8px 0;
    border-radius: 14px;
    max-width: 75%;
}

.message.mine {
    margin-left: auto;
    background: #7038db;
}

.message.theirs {
    background: #191924;
}

.live-badge {
    color: white;
    background: #e6244f;
    border-radius: 7px;
    padding: 5px 8px;
    font-size: 11px;
    font-weight: bold;
}

@media(max-width:700px) {

    .nav {
        padding: 0 12px;
    }

    .navlinks {
        gap: 10px;
    }

    .navlinks a:nth-child(n+5) {
        display: none;
    }

    .page {
        padding-left: 10px;
        padding-right: 10px;
    }

    .grid {
        grid-template-columns: repeat(2,1fr);
    }
}

"""


def render_page(title, body, extra_script=""):
    user = current_user()

    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1.0">
<title>{{ title }} — Heara</title>

<style>
{{ css|safe }}
</style>
</head>

<body>

<div class="heara-bg">

<nav class="nav">

<a href="{{ url_for('home') }}" class="logo">
HEARA
</a>

<div class="navlinks">

<a href="{{ url_for('fyp') }}">FYP</a>
<a href="{{ url_for('home') }}">Home</a>
<a href="{{ url_for('videos') }}">Videos</a>
<a href="{{ url_for('live') }}">🔴 Live</a>

{% if user %}
<a href="{{ url_for('inbox') }}">✉️ Inbox</a>
<a href="{{ url_for('profile', username=user['username']) }}">
Profile
</a>
<a href="{{ url_for('logout') }}">Logout</a>
{% else %}
<a href="{{ url_for('login') }}">Login</a>
<a href="{{ url_for('register') }}">Join</a>
{% endif %}

</div>

</nav>

<div class="page">

{{ body|safe }}

</div>

</div>

<script>
{{ script|safe }}
</script>

</body>
</html>
""",
        title=title,
        body=body,
        css=BASE_CSS,
        script=extra_script
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    db = get_db()

    posts = db.execute("""
        SELECT posts.*, users.username, users.display_name
        FROM posts
        JOIN users ON users.id = posts.user_id
        ORDER BY posts.id DESC
        LIMIT 30
    """).fetchall()

    db.close()

    post_html = ""

    for post in posts:

        media = ""

        if post["video_url"]:
            media = f"""
            <video class="post-video"
                   controls
                   playsinline
                   src="{post['video_url']}">
            </video>
            """

        post_html += f"""
        <div class="card post">

            <div class="post-head">

                <div class="avatar">
                    {post["username"][:1].upper()}
                </div>

                <div>
                    <a href="/profile/{post["username"]}">
                        <strong>
                            {post["display_name"] or post["username"]}
                        </strong>
                    </a>

                    <div class="muted">
                        @{post["username"]}
                    </div>
                </div>

            </div>

            {media}

            <p>
                {post["caption"] or post["text"]}
            </p>

            <div class="post-actions">

                <form method="POST"
                      action="/like/{post['id']}">
                    <button class="action">
                        ❤️ {post["likes"]}
                    </button>
                </form>

                <a class="action"
                   href="/post/{post['id']}">
                   💬 {post["comments"]}
                </a>

                <button class="action"
                        onclick="sharePost('{request.host_url}post/{post["id"]}')">
                    🔁 Share
                </button>

            </div>

        </div>
        """

    if not post_html:
        post_html = """
        <div class="card">
            <h2>Welcome to Heara 🌍</h2>
            <p class="muted">
                Be one of the first people to create something here.
            </p>
            <a class="btn" href="/post">
                Create your first post
            </a>
        </div>
        """

    body = f"""
    <h1>Heara</h1>

    <div class="card">
        <h2>What's happening?</h2>

        <a class="btn" href="/post">
            ＋ Create post
        </a>

        <a class="btn secondary"
           href="/fyp">
            ▶ Open FYP
        </a>
    </div>

    {post_html}
    """

    script = """
    function sharePost(url) {
        if (navigator.share) {
            navigator.share({
                title: 'Heara',
                url: url
            });
        } else {
            navigator.clipboard.writeText(url);
            alert('Link copied!');
        }
    }
    """

    return render_page("Home", body, script)


# ============================================================
# FYP
# ============================================================

@app.route("/fyp")
def fyp():

    db = get_db()

    posts = db.execute("""
        SELECT posts.*, users.username, users.display_name
        FROM posts
        JOIN users ON users.id = posts.user_id
        WHERE posts.post_type = 'video'
        ORDER BY posts.views DESC, posts.likes DESC, posts.id DESC
        LIMIT 100
    """).fetchall()

    db.close()

    slides = ""

    for post in posts:

        if not post["video_url"]:
            continue

        slides += f"""
        <section class="fyp-slide">

            <video
                class="fyp-video"
                src="{post['video_url']}"
                loop
                muted
                playsinline
                preload="metadata">
            </video>

            <div class="fyp-gradient"></div>

            <div class="fyp-info">

                <a href="/profile/{post['username']}">
                    <strong>
                        @{post['username']}
                    </strong>
                </a>

                <p>
                    {post["caption"] or ""}
                </p>

                <small>
                    ❤️ {post["likes"]}
                    &nbsp;
                    👁️ {post["views"]}
                </small>

            </div>

            <div class="fyp-actions">

                <form method="POST"
                      action="/like/{post['id']}">

                    <button>❤️</button>

                </form>

                <a href="/post/{post['id']}">
                    💬
                </a>

                <button onclick="sharePost('{request.host_url}post/{post["id"]}')">
                    🔁
                </button>

                <a href="/profile/{post['username']}">
                    👤
                </a>

            </div>

        </section>
        """

    if not slides:
        slides = """
        <section class="fyp-empty">
            <h1>Your FYP is waiting.</h1>
            <p>
                Upload the first videos to Heara.
            </p>
            <a class="btn" href="/post">
                Upload video
            </a>
        </section>
        """

    body = f"""
    <div class="fyp-header">
        <strong>For You</strong>
        <span>Following</span>
        <span>Trending</span>
    </div>

    <div class="fyp-feed">
        {slides}
    </div>
    """

    script = """
    const slides =
        document.querySelectorAll(".fyp-slide");

    const observer =
        new IntersectionObserver((entries) => {

            entries.forEach(entry => {

                const video =
                    entry.target.querySelector("video");

                if (!video) return;

                if (entry.isIntersecting) {

                    video.play().catch(() => {});

                    fetch(
                        "/api/view/" +
                        entry.target.dataset.post
                    ).catch(() => {});

                } else {

                    video.pause();

                }

            });

        }, {
            threshold: 0.65
        });

    slides.forEach(slide => {

        const video =
            slide.querySelector("video");

        if (video) {

            observer.observe(slide);

            slide.addEventListener("click", () => {

                if (video.paused)
                    video.play();
                else
                    video.pause();

            });

        }

    });

    function sharePost(url) {

        if (navigator.share) {

            navigator.share({
                title: "Heara",
                url: url
            });

        } else {

            navigator.clipboard.writeText(url);

            alert("Link copied!");

        }

    }
    """

    # Add the styling specifically for FYP.
    script += """

    """

    body = f"""
    <style>

    body {
        overflow: hidden;
    }

    .page {
        padding: 0;
        max-width: none;
    }

    .nav {
        background: linear-gradient(
            rgba(0,0,0,.7),
            transparent
        );
        border: 0;
    }

    .fyp-feed {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;

        overflow-y: auto;

        scroll-snap-type: y mandatory;

        background: #000;
    }

    .fyp-slide {
        position: relative;

        width: 100%;
        height: 100vh;

        scroll-snap-align: start;

        background: #000;

        display: flex;
        justify-content: center;
        align-items: center;
    }

    .fyp-video {
        width: 100%;
        height: 100%;

        object-fit: contain;

        background: #000;
    }

    .fyp-gradient {
        position: absolute;
        inset: 0;

        pointer-events: none;

        background:
            linear-gradient(
                transparent 45%,
                rgba(0,0,0,.75)
            );
    }

    .fyp-info {
        position: absolute;
        bottom: 50px;
        left: 20px;

        max-width: 70%;
    }

    .fyp-info strong {
        font-size: 18px;
    }

    .fyp-actions {
        position: absolute;

        right: 20px;
        bottom: 80px;

        display: flex;
        flex-direction: column;
        gap: 18px;
    }

    .fyp-actions button,
    .fyp-actions a {
        border: 0;
        background: rgba(0,0,0,.5);

        color: white;

        width: 52px;
        height: 52px;

        border-radius: 50%;

        display: flex;
        align-items: center;
        justify-content: center;

        font-size: 23px;
    }

    .fyp-header {
        position: fixed;
        top: 20px;
        left: 50%;

        transform: translateX(-50%);

        z-index: 1100;

        display: flex;
        gap: 20px;
    }

    .fyp-empty {
        height: 100vh;

        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
    }

    </style>
    {slides}
    """

    return render_page("For You", body, script)


# ============================================================
# VIDEOS
# ============================================================

@app.route("/videos")
def videos():
    return redirect(url_for("fyp"))


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "").strip()
        display_name = request.form.get("display_name", "").strip()

        if not username or not password:
            return "Username and password are required."

        db = get_db()

        try:

            cur = db.execute("""
                INSERT INTO users
                (username, password, display_name, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                username,
                password,
                display_name or username,
                now()
            ))

            db.commit()

            session["user_id"] = cur.lastrowid

        except sqlite3.IntegrityError:

            db.close()

            return "Username already exists."

        db.close()

        return redirect(url_for("home"))

    body = """
    <div class="card">

        <h1>Join Heara 🌍</h1>

        <form method="POST">

            <input
                name="display_name"
                placeholder="Display name">

            <input
                name="username"
                placeholder="Username"
                required>

            <input
                type="password"
                name="password"
                placeholder="Password"
                required>

            <button class="btn">
                Create Heara account
            </button>

        </form>

    </div>
    """

    return render_page("Register", body)


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "")
        password = request.form.get("password", "")

        db = get_db()

        user = db.execute("""
            SELECT *
            FROM users
            WHERE username = ?
            AND password = ?
        """, (
            username.lower(),
            password
        )).fetchone()

        db.close()

        if not user:
            return "Incorrect username or password."

        session["user_id"] = user["id"]

        return redirect(url_for("home"))

    body = """
    <div class="card">

        <h1>Welcome back</h1>

        <form method="POST">

            <input
                name="username"
                placeholder="Username"
                required>

            <input
                type="password"
                name="password"
                placeholder="Password"
                required>

            <button class="btn">
                Login
            </button>

        </form>

    </div>
    """

    return render_page("Login", body)


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# ============================================================
# CREATE POST
# ============================================================

@app.route("/post", methods=["GET", "POST"])
@login_required
def create_post():

    user = current_user()

    if request.method == "POST":

        post_type = request.form.get("post_type", "video")
        video_url = request.form.get("video_url", "").strip()
        image_url = request.form.get("image_url", "").strip()
        caption = request.form.get("caption", "").strip()
        text = request.form.get("text", "").strip()
        category = request.form.get("category", "General")

        db = get_db()

        db.execute("""
            INSERT INTO posts
            (
                user_id,
                post_type,
                video_url,
                image_url,
                text,
                caption,
                category,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user["id"],
            post_type,
            video_url,
            image_url,
            text,
            caption,
            category,
            now()
        ))

        db.commit()
        db.close()

        return redirect(url_for("home"))

    body = """
    <div class="card">

        <h1>Create on Heara</h1>

        <form method="POST">

            <label>Post type</label>

            <select name="post_type">

                <option value="video">
                    Video
                </option>

                <option value="text">
                    Text
                </option>

                <option value="image">
                    Image
                </option>

            </select>

            <label>Video URL</label>

            <input
                name="video_url"
                placeholder="Paste video URL">

            <label>Image URL</label>

            <input
                name="image_url"
                placeholder="Optional image URL">

            <label>Caption</label>

            <textarea
                name="caption"
                placeholder="Write a caption..."></textarea>

            <label>Text post</label>

            <textarea
                name="text"
                placeholder="Write something..."></textarea>

            <label>Category</label>

            <select name="category">

                <option>General</option>
                <option>Music</option>
                <option>Comedy</option>
                <option>Gaming</option>
                <option>Sports</option>
                <option>Education</option>
                <option>Technology</option>
                <option>Fashion</option>
                <option>Lifestyle</option>
                <option>Movies</option>

            </select>

            <button class="btn">
                Publish
            </button>

        </form>

        <p class="muted">
            Direct file uploading will be connected
            to cloud storage in the next infrastructure stage.
        </p>

    </div>
    """

    return render_page("Create", body)


# ============================================================
# LIKE
# ============================================================

@app.route("/like/<int:post_id>", methods=["POST"])
@login_required
def like_post(post_id):

    user = current_user()

    db = get_db()

    existing = db.execute("""
        SELECT id
        FROM likes
        WHERE user_id = ?
        AND post_id = ?
    """, (
        user["id"],
        post_id
    )).fetchone()

    post = db.execute("""
        SELECT *
        FROM posts
        WHERE id = ?
    """, (post_id,)).fetchone()

    if not post:
        db.close()
        return redirect(url_for("home"))

    if existing:

        db.execute("""
            DELETE FROM likes
            WHERE id = ?
        """, (existing["id"],))

        db.execute("""
            UPDATE posts
            SET likes = MAX(likes - 1, 0)
            WHERE id = ?
        """, (post_id,))

    else:

        db.execute("""
            INSERT INTO likes
            (user_id, post_id)
            VALUES (?, ?)
        """, (
            user["id"],
            post_id
        ))

        db.execute("""
            UPDATE posts
            SET likes = likes + 1
            WHERE id = ?
        """, (post_id,))

        if post["user_id"] != user["id"]:

            notify(
                post["user_id"],
                user["id"],
                "like",
                f"@{user['username']} liked your post."
            )

    db.commit()
    db.close()

    return redirect(request.referrer or url_for("home"))


# ============================================================
# VIEW COUNT
# ============================================================

@app.route("/api/view/<int:post_id>")
def view_post(post_id):

    db = get_db()

    db.execute("""
        UPDATE posts
        SET views = views + 1
        WHERE id = ?
    """, (post_id,))

    db.commit()
    db.close()

    return jsonify({
        "success": True
    })


# ============================================================
# SINGLE POST
# ============================================================

@app.route("/post/<int:post_id>")
def view_post_page(post_id):

    db = get_db()

    post = db.execute("""
        SELECT posts.*, users.username, users.display_name
        FROM posts
        JOIN users
        ON users.id = posts.user_id
        WHERE posts.id = ?
    """, (post_id,)).fetchone()

    comments = db.execute("""
        SELECT comments.*, users.username
        FROM comments
        JOIN users
        ON users.id = comments.user_id
        WHERE comments.post_id = ?
        ORDER BY comments.id ASC
    """, (post_id,)).fetchall()

    db.close()

    if not post:
        return "Post not found."

    media = ""

    if post["video_url"]:

        media = f"""
        <video
            class="post-video"
            controls
            autoplay
            playsinline
            src="{post['video_url']}">
        </video>
        """

    comments_html = ""

    for comment in comments:

        comments_html += f"""
        <div class="card">

            <strong>
                @{comment["username"]}
            </strong>

            <p>
                {comment["text"]}
            </p>

        </div>
        """

    comment_form = ""

    if current_user():

        comment_form = f"""
        <form method="POST"
              action="/comment/{post_id}">

            <textarea
                name="text"
                placeholder="Write a comment..."
                required></textarea>

            <button class="btn">
                Comment
            </button>

        </form>
        """

    body = f"""
    <div class="card">

        <h2>
            @{post["username"]}
        </h2>

        {media}

        <p>
            {post["caption"] or post["text"]}
        </p>

        <p class="muted">
            ❤️ {post["likes"]}
            · 👁️ {post["views"]}
        </p>

    </div>

    <div class="card">

        <h2>Comments</h2>

        {comment_form}

    </div>

    {comments_html}
    """

    return render_page(
        "Post",
        body
    )


# ============================================================
# COMMENTS
# ============================================================

@app.route("/comment/<int:post_id>", methods=["POST"])
@login_required
def comment(post_id):

    user = current_user()

    text = request.form.get("text", "").strip()

    if text:

        db = get_db()

        db.execute("""
            INSERT INTO comments
            (user_id, post_id, text, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            user["id"],
            post_id,
            text,
            now()
        ))

        db.execute("""
            UPDATE posts
            SET comments = comments + 1
            WHERE id = ?
        """, (post_id,))

        post = db.execute("""
            SELECT user_id
            FROM posts
            WHERE id = ?
        """, (post_id,)).fetchone()

        db.commit()
        db.close()

        if post and post["user_id"] != user["id"]:

            notify(
                post["user_id"],
                user["id"],
                "comment",
                f"@{user['username']} commented on your post."
            )

    return redirect(
        url_for(
            "view_post_page",
            post_id=post_id
        )
    )


# ============================================================
# PROFILE
# ============================================================

@app.route("/profile/<username>")
def profile(username):

    db = get_db()

    user = db.execute("""
        SELECT *
        FROM users
        WHERE username = ?
    """, (username.lower(),)).fetchone()

    if not user:

        db.close()

        return "User not found."

    posts = db.execute("""
        SELECT *
        FROM posts
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user["id"],)).fetchall()

    viewer = current_user()

    following = False

    if viewer:

        row = db.execute("""
            SELECT id
            FROM follows
            WHERE follower_id = ?
            AND following_id = ?
        """, (
            viewer["id"],
            user["id"]
        )).fetchone()

        following = bool(row)

    db.close()

    follow_button = ""

    if viewer and viewer["id"] != user["id"]:

        if following:

            follow_button = """
            <form method="POST"
                  action="/unfollow/{0}">
                <button class="btn secondary">
                    Following
                </button>
            </form>
            """.format(user["id"])

        else:

            follow_button = """
            <form method="POST"
                  action="/follow/{0}">
                <button class="btn">
                    Follow
                </button>
            </form>
            """.format(user["id"])

    grid = ""

    for post in posts:

        if post["video_url"]:

            grid += f"""
            <a href="/post/{post['id']}">
                <div class="grid-item">

                    <video
                        muted
                        playsinline
                        src="{post['video_url']}">
                    </video>

                </div>
            </a>
            """

    live_status = ""

    db = get_db()

    active_live = db.execute("""
        SELECT *
        FROM live_rooms
        WHERE user_id = ?
        AND active = 1
        ORDER BY id DESC
        LIMIT 1
    """, (user["id"],)).fetchone()

    db.close()

    if active_live:

        live_status = f"""
        <a class="btn danger"
           href="/live/{active_live['room_code']}">
           🔴 LIVE NOW
        </a>
        """

    body = f"""
    <div class="card">

        <div class="avatar"
             style="width:90px;height:90px;font-size:35px;">
            {user["username"][:1].upper()}
        </div>

        <h1>
            {user["display_name"] or user["username"]}
        </h1>

        <p class="muted">
            @{user["username"]}
        </p>

        <p>
            {user["bio"] or "Welcome to my Heara profile."}
        </p>

        <div class="stats">

            <div class="stat">
                <strong>{user["followers"]}</strong>
                Followers
            </div>

            <div class="stat">
                <strong>{user["following"]}</strong>
                Following
            </div>

        </div>

        <div style="display:flex;gap:10px;">
            {follow_button}
            {live_status}
        </div>

    </div>

    <div class="card">

        <h2>Posts</h2>

        <div class="grid">
            {grid}
        </div>

    </div>
    """

    return render_page(
        user["username"],
        body
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

    db = get_db()

    existing = db.execute("""
        SELECT id
        FROM follows
        WHERE follower_id = ?
        AND following_id = ?
    """, (
        me["id"],
        user_id
    )).fetchone()

    if not existing:

        db.execute("""
            INSERT INTO follows
            (follower_id, following_id)
            VALUES (?, ?)
        """, (
            me["id"],
            user_id
        ))

        db.execute("""
            UPDATE users
            SET following = following + 1
            WHERE id = ?
        """, (me["id"],))

        db.execute("""
            UPDATE users
            SET followers = followers + 1
            WHERE id = ?
        """, (user_id,))

        db.commit()

        notify(
            user_id,
            me["id"],
            "follow",
            f"@{me['username']} followed you."
        )

    db.close()

    return redirect(request.referrer or url_for("home"))


# ============================================================
# UNFOLLOW
# ============================================================

@app.route("/unfollow/<int:user_id>", methods=["POST"])
@login_required
def unfollow(user_id):

    me = current_user()

    db = get_db()

    existing = db.execute("""
        SELECT id
        FROM follows
        WHERE follower_id = ?
        AND following_id = ?
    """, (
        me["id"],
        user_id
    )).fetchone()

    if existing:

        db.execute("""
            DELETE FROM follows
            WHERE id = ?
        """, (existing["id"],))

        db.execute("""
            UPDATE users
            SET following = MAX(following - 1, 0)
            WHERE id = ?
        """, (me["id"],))

        db.execute("""
            UPDATE users
            SET followers = MAX(followers - 1, 0)
            WHERE id = ?
        """, (user_id,))

        db.commit()

    db.close()

    return redirect(request.referrer or url_for("home"))


# ============================================================
# INBOX
# ============================================================

@app.route("/inbox")
@login_required
def inbox():

    user = current_user()

    db = get_db()

    conversations = db.execute("""
        SELECT
            u.id,
            u.username,
            u.display_name,
            MAX(m.created_at) AS latest
        FROM messages m
        JOIN users u
        ON (
            u.id = m.sender_id
            OR u.id = m.receiver_id
        )
        WHERE
            (m.sender_id = ? OR m.receiver_id = ?)
            AND u.id != ?
        GROUP BY u.id
        ORDER BY latest DESC
    """, (
        user["id"],
        user["id"],
        user["id"]
    )).fetchall()

    db.close()

    html = """
    <div class="card">

        <h1>✉️ Inbox</h1>

        <p class="muted">
            Your private Heara messages.
        </p>

    """

    for person in conversations:

        html += f"""
        <div class="card">

            <a href="/messages/{person['id']}">

                <div style="display:flex;gap:12px;align-items:center;">

                    <div class="avatar">
                        {person["username"][:1].upper()}
                    </div>

                    <div>

                        <strong>
                            {person["display_name"] or person["username"]}
                        </strong>

                        <div class="muted">
                            @{person["username"]}
                        </div>

                    </div>

                </div>

            </a>

        </div>
        """

    html += """
    </div>

    <div class="card">

        <h2>Message someone</h2>

        <form method="GET"
              action="/messages/search">

            <input
                name="username"
                placeholder="@username">

            <button class="btn">
                Find user
            </button>

        </form>

    </div>
    """

    return render_page(
        "Inbox",
        html
    )


# ============================================================
# SEARCH MESSAGE USER
# ============================================================

@app.route("/messages/search")
@login_required
def message_search():

    username = request.args.get(
        "username",
        ""
    ).strip().lower()

    db = get_db()

    person = db.execute("""
        SELECT *
        FROM users
        WHERE username = ?
    """, (username,)).fetchone()

    db.close()

    if not person:
        return "User not found."

    return redirect(
        url_for(
            "messages",
            user_id=person["id"]
        )
    )


# ============================================================
# PRIVATE MESSAGES
# ============================================================

@app.route("/messages/<int:user_id>", methods=["GET", "POST"])
@login_required
def messages(user_id):

    me = current_user()

    other = get_user(user_id)

    if not other:
        return "User not found."

    db = get_db()

    if request.method == "POST":

        text = request.form.get(
            "text",
            ""
        ).strip()

        if text:

            db.execute("""
                INSERT INTO messages
                (
                    sender_id,
                    receiver_id,
                    text,
                    created_at
                )
                VALUES (?, ?, ?, ?)
            """, (
                me["id"],
                user_id,
                text,
                now()
            ))

            db.commit()

            notify(
                user_id,
                me["id"],
                "message",
                f"@{me['username']} sent you a message."
            )

    chat = db.execute("""
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

    db.execute("""
        UPDATE messages
        SET read = 1
        WHERE sender_id = ?
        AND receiver_id = ?
    """, (
        user_id,
        me["id"]
    ))

    db.commit()
    db.close()

    messages_html = ""

    for message in chat:

        cls = (
            "mine"
            if message["sender_id"] == me["id"]
            else "theirs"
        )

        messages_html += f"""
        <div class="message {cls}">
            {message["text"]}
        </div>
        """

    body = f"""
    <div class="card">

        <h2>
            Chat with @{other["username"]}
        </h2>

        <div>
            {messages_html}
        </div>

        <form method="POST">

            <textarea
                name="text"
                placeholder="Write a message..."
                required></textarea>

            <button class="btn">
                Send
            </button>

        </form>

    </div>
    """

    return render_page(
        "Messages",
        body
    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route("/notifications")
@login_required
def notifications():

    user = current_user()

    db = get_db()

    rows = db.execute("""
        SELECT notifications.*, users.username
        FROM notifications
        LEFT JOIN users
        ON users.id = notifications.actor_id
        WHERE notifications.user_id = ?
        ORDER BY notifications.id DESC
        LIMIT 100
    """, (user["id"],)).fetchall()

    db.execute("""
        UPDATE notifications
        SET read = 1
        WHERE user_id = ?
    """, (user["id"],))

    db.commit()
    db.close()

    html = """
    <div class="card">

        <h1>🔔 Notifications</h1>
    """

    for row in rows:

        html += f"""
        <div class="card">
            {row["message"]}
            <div class="muted">
                {row["created_at"]}
            </div>
        </div>
        """

    if not rows:

        html += """
        <p class="muted">
            No notifications yet.
        </p>
        """

    html += "</div>"

    return render_page(
        "Notifications",
        html
    )


# ============================================================
# LIVE
# ============================================================

@app.route("/live")
def live():

    db = get_db()

    rooms = db.execute("""
        SELECT live_rooms.*, users.username, users.display_name
        FROM live_rooms
        JOIN users
        ON users.id = live_rooms.user_id
        WHERE live_rooms.active = 1
        ORDER BY live_rooms.id DESC
    """).fetchall()

    db.close()

    cards = ""

    for room in rooms:

        cards += f"""
        <div class="card">

            <span class="live-badge">
                LIVE
            </span>

            <h2>
                {room["title"] or "Live on Heara"}
            </h2>

            <p>
                @{room["username"]}
            </p>

            <p class="muted">
                👁️ {room["viewers"]} viewers
            </p>

            <a class="btn"
               href="/live/{room['room_code']}">
                Watch Live
            </a>

        </div>
        """

    if not cards:

        cards = """
        <div class="card">

            <h2>No one is live right now.</h2>

            <p class="muted">
                Be the first.
            </p>

        </div>
        """

    body = f"""
    <h1>🔴 Heara LIVE</h1>

    {cards}
    """

    return render_page(
        "Live",
        body
    )


# ============================================================
# START LIVE
# ============================================================

@app.route("/go-live", methods=["GET", "POST"])
@login_required
def go_live():

    user = current_user()

    if user["followers"] < LIVE_FOLLOWER_REQUIREMENT:

        body = f"""
        <div class="card">

            <h1>🔴 Go Live</h1>

            <h2>
                {user["followers"]} / {LIVE_FOLLOWER_REQUIREMENT}
                followers
            </h2>

            <p>
                Heara LIVE becomes available when
                you reach {LIVE_FOLLOWER_REQUIREMENT}
                followers.
            </p>

            <p class="muted">
                Keep creating and building your community.
            </p>

        </div>
        """

        return render_page(
            "Go Live",
            body
        )

    if request.method == "POST":

        title = request.form.get(
            "title",
            "Live on Heara"
        ).strip()

        room_code = secrets.token_urlsafe(10)

        db = get_db()

        db.execute("""
            UPDATE live_rooms
            SET active = 0
            WHERE user_id = ?
        """, (user["id"],))

        db.execute("""
            INSERT INTO live_rooms
            (
                user_id,
                title,
                room_code,
                active,
                created_at
            )
            VALUES (?, ?, ?, 1, ?)
        """, (
            user["id"],
            title,
            room_code,
            now()
        ))

        db.commit()
        db.close()

        return redirect(
            url_for(
                "live_room",
                room_code=room_code
            )
        )

    body = """
    <div class="card">

        <h1>🔴 Go Live</h1>

        <p>
            Your followers are ready.
        </p>

        <form method="POST">

            <input
                name="title"
                placeholder="What are you going live about?"
                required>

            <button class="btn">
                Start Live
            </button>

        </form>

    </div>
    """

    return render_page(
        "Go Live",
        body
    )


# ============================================================
# LIVE ROOM
# ============================================================

@app.route("/live/<room_code>")
def live_room(room_code):

    db = get_db()

    room = db.execute("""
        SELECT live_rooms.*, users.username, users.display_name
        FROM live_rooms
        JOIN users
        ON users.id = live_rooms.user_id
        WHERE room_code = ?
    """, (room_code,)).fetchone()

    db.close()

    if not room:
        return "Live room not found."

    viewer = current_user()

    is_owner = (
        viewer and
        viewer["id"] == room["user_id"]
    )

    body = f"""
    <style>

    .live-room {
        max-width: 1000px;
        margin: auto;
    }

    .live-screen {
        width: 100%;
        aspect-ratio: 16/9;
        background: #000;
        border-radius: 20px;
        overflow: hidden;
        position: relative;
    }

    #localVideo,
    #remoteVideo {
        width: 100%;
        height: 100%;
        object-fit: cover;
        background: #000;
    }

    #remoteVideo {
        display: none;
    }

    .live-controls {
        display: flex;
        gap: 10px;
        margin-top: 15px;
        flex-wrap: wrap;
    }

    </style>

    <div class="live-room">

        <div class="card">

            <span class="live-badge">
                🔴 LIVE
            </span>

            <h1>
                {room["title"]}
            </h1>

            <p>
                @{room["username"]}
            </p>

        </div>

        <div class="live-screen">

            <video
                id="localVideo"
                autoplay
                muted
                playsinline>
            </video>

            <video
                id="remoteVideo"
                autoplay
                playsinline>
            </video>

        </div>

        <div class="live-controls">
    """

    if is_owner:

        body += """
            <button class="btn"
                    onclick="startCamera()">
                🎥 Start Camera
            </button>

            <button class="btn danger"
                    onclick="stopLive()">
                End Live
            </button>
        """

    else:

        body += """
            <button class="btn"
                    onclick="watchLive()">
                ▶ Watch Live
            </button>
        """

    body += f"""
        </div>

        <div class="card">

            <h2>Live chat</h2>

            <p class="muted">
                Live chat will connect to the Heara
                messaging system.
            </p>

        </div>

    </div>
    """

    script = f"""

    const roomCode = "{room_code}";

    let localStream = null;

    async function startCamera() {{

        try {{

            localStream =
                await navigator.mediaDevices.getUserMedia({{
                    video: true,
                    audio: true
                }});

            document.getElementById(
                "localVideo"
            ).srcObject = localStream;

        }} catch(error) {{

            alert(
                "Camera or microphone permission was denied."
            );

        }}

    }}

    async function watchLive() {{

        const video =
            document.getElementById(
                "remoteVideo"
            );

        video.style.display = "block";

        alert(
            "Heara live connection is ready for WebRTC signalling."
        );

    }}

    async function stopLive() {{

        if (localStream) {{

            localStream
                .getTracks()
                .forEach(track => track.stop());

        }}

        await fetch(
            "/api/live/end/{room_code}",
            {{
                method: "POST"
            }}
        );

        window.location.href =
            "/live";

    }}

    """

    return render_page(
        "Live",
        body,
        script
    )


# ============================================================
# END LIVE
# ============================================================

@app.route("/api/live/end/<room_code>", methods=["POST"])
@login_required
def end_live(room_code):

    user = current_user()

    db = get_db()

    db.execute("""
        UPDATE live_rooms
        SET active = 0
        WHERE room_code = ?
        AND user_id = ?
    """, (
        room_code,
        user["id"]
    ))

    db.commit()
    db.close()

    return jsonify({
        "success": True
    })


# ============================================================
# LIVE SIGNALING
# ============================================================

@app.route("/api/live/signal", methods=["POST"])
@login_required
def live_signal():

    user = current_user()

    data = request.get_json(
        silent=True
    ) or {}

    room_code = data.get("room_code")
    signal_type = data.get("signal_type")
    signal = data.get("signal")

    if not room_code or not signal_type:
        return jsonify({
            "success": False
        }), 400

    db = get_db()

    db.execute("""
        INSERT INTO live_signals
        (
            room_code,
            sender_id,
            receiver_id,
            signal_type,
            signal,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        room_code,
        user["id"],
        data.get("receiver_id"),
        signal_type,
        signal,
        now()
    ))

    db.commit()
    db.close()

    return jsonify({
        "success": True
    })


@app.route("/api/live/signals/<room_code>")
@login_required
def get_live_signals(room_code):

    user = current_user()

    db = get_db()

    rows = db.execute("""
        SELECT *
        FROM live_signals
        WHERE room_code = ?
        AND sender_id != ?
        ORDER BY id ASC
    """, (
        room_code,
        user["id"]
    )).fetchall()

    db.close()

    return jsonify([
        {
            "id": row["id"],
            "sender_id": row["sender_id"],
            "signal_type": row["signal_type"],
            "signal": row["signal"]
        }
        for row in rows
    ])


# ============================================================
# CREATOR DASHBOARD
# ============================================================

@app.route("/creator")
@login_required
def creator_dashboard():

    user = current_user()

    db = get_db()

    posts = db.execute("""
        SELECT
            COUNT(*) AS posts,
            COALESCE(SUM(views),0) AS views,
            COALESCE(SUM(likes),0) AS likes,
            COALESCE(SUM(comments),0) AS comments,
            COALESCE(SUM(shares),0) AS shares
        FROM posts
        WHERE user_id = ?
    """, (user["id"],)).fetchone()

    earnings = db.execute("""
        SELECT
            COALESCE(SUM(amount),0) AS total
        FROM earnings
        WHERE user_id = ?
    """, (user["id"],)).fetchone()

    db.close()

    live_status = (
        "Unlocked"
        if user["followers"] >= LIVE_FOLLOWER_REQUIREMENT
        else
        f"{LIVE_FOLLOWER_REQUIREMENT - user['followers']} followers needed"
    )

    body = f"""
    <div class="card">

        <h1>Creator Dashboard</h1>

        <div class="stats">

            <div class="stat">
                <strong>{posts["posts"]}</strong>
                Posts
            </div>

            <div class="stat">
                <strong>{posts["views"]}</strong>
                Views
            </div>

            <div class="stat">
                <strong>{posts["likes"]}</strong>
                Likes
            </div>

            <div class="stat">
                <strong>{posts["comments"]}</strong>
                Comments
            </div>

        </div>

    </div>

    <div class="card">

        <h2>🔴 LIVE</h2>

        <p>
            {live_status}
        </p>

        <a class="btn"
           href="/go-live">
            Go Live
        </a>

    </div>

    <div class="card">

        <h2>💰 Monetization</h2>

        <h1>
            ${earnings["total"]:.2f}
        </h1>

        <p class="muted">
            Creator earnings
        </p>

        <p>
            Monetization infrastructure is prepared
            for creator payouts.
        </p>

    </div>
    """

    return render_page(
        "Creator Dashboard",
        body
    )


# ============================================================
# SEARCH
# ============================================================

@app.route("/search")
def search():

    q = request.args.get(
        "q",
        ""
    ).strip()

    db = get_db()

    users = db.execute("""
        SELECT *
        FROM users
        WHERE username LIKE ?
        OR display_name LIKE ?
        ORDER BY followers DESC
        LIMIT 50
    """, (
        "%" + q + "%",
        "%" + q + "%"
    )).fetchall()

    posts = db.execute("""
        SELECT *
        FROM posts
        WHERE caption LIKE ?
        OR text LIKE ?
        OR category LIKE ?
        ORDER BY views DESC
        LIMIT 50
    """, (
        "%" + q + "%",
        "%" + q + "%",
        "%" + q + "%"
    )).fetchall()

    db.close()

    users_html = ""

    for user in users:

        users_html += f"""
        <div class="card">

            <a href="/profile/{user['username']}">

                <div style="display:flex;gap:12px;align-items:center;">

                    <div class="avatar">
                        {user["username"][:1].upper()}
                    </div>

                    <div>

                        <strong>
                            {user["display_name"] or user["username"]}
                        </strong>

                        <div class="muted">
                            @{user["username"]}
                            · {user["followers"]} followers
                        </div>

                    </div>

                </div>

            </a>

        </div>
        """

    body = f"""
    <div class="card">

        <h1>Search Heara</h1>

        <form method="GET">

            <input
                name="q"
                value="{q}"
                placeholder="Search people, posts, topics...">

            <button class="btn">
                Search
            </button>

        </form>

    </div>

    <h2>People</h2>

    {users_html}

    <h2>Posts</h2>
    """

    return render_page(
        "Search",
        body
    )


# ============================================================
# API — CURRENT USER
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
        "display_name": user["display_name"],
        "followers": user["followers"],
        "following": user["following"],
        "can_live":
            user["followers"] >= LIVE_FOLLOWER_REQUIREMENT
    })


# ============================================================
# API — FYP
# ============================================================

@app.route("/api/fyp")
def api_fyp():

    db = get_db()

    rows = db.execute("""
        SELECT
            posts.*,
            users.username,
            users.display_name
        FROM posts
        JOIN users
        ON users.id = posts.user_id
        WHERE posts.post_type = 'video'
        ORDER BY posts.views DESC,
                 posts.likes DESC,
                 posts.id DESC
        LIMIT 100
    """).fetchall()

    db.close()

    return jsonify([
        {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "video_url": row["video_url"],
            "caption": row["caption"],
            "category": row["category"],
            "views": row["views"],
            "likes": row["likes"],
            "comments": row["comments"]
        }
        for row in rows
    ])


# ============================================================
# TRENDING
# ============================================================

@app.route("/trending")
def trending():

    db = get_db()

    posts = db.execute("""
        SELECT
            posts.*,
            users.username
        FROM posts
        JOIN users
        ON users.id = posts.user_id
        ORDER BY
            (likes * 5)
            +
            (comments * 4)
            +
            (shares * 6)
            +
            views DESC
        LIMIT 50
    """).fetchall()

    db.close()

    html = """
    <h1>🔥 Trending</h1>
    """

    for post in posts:

        html += f"""
        <div class="card">

            <a href="/post/{post['id']}">

                <h3>
                    @{post["username"]}
                </h3>

                <p>
                    {post["caption"] or post["text"]}
                </p>

                <p class="muted">
                    👁️ {post["views"]}
                    · ❤️ {post["likes"]}
                    · 💬 {post["comments"]}
                </p>

            </a>

        </div>
        """

    return render_page(
        "Trending",
        html
    )


# ============================================================
# REPORT
# ============================================================

@app.route("/report/<int:post_id>", methods=["POST"])
@login_required
def report(post_id):

    user = current_user()

    reason = request.form.get(
        "reason",
        "Other"
    )

    db = get_db()

    db.execute("""
        INSERT INTO reports
        (
            reporter_id,
            post_id,
            reason,
            created_at
        )
        VALUES (?, ?, ?, ?)
    """, (
        user["id"],
        post_id,
        reason,
        now()
    ))

    db.commit()
    db.close()

    return jsonify({
        "success": True,
        "message": "Report received."
    })


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return jsonify({
        "status": "online",
        "platform": "Heara",
        "version": "1.0",
        "features": [
            "FYP",
            "Video posts",
            "Text posts",
            "Profiles",
            "Followers",
            "Likes",
            "Comments",
            "Shares",
            "Inbox",
            "Messaging",
            "Notifications",
            "Live rooms",
            "Creator dashboard",
            "Monetization framework"
        ]
    })


# ============================================================
# 404
# ============================================================

@app.errorhandler(404)
def not_found(error):

    body = """
    <div class="card">

        <h1>404</h1>

        <h2>Page not found</h2>

        <a class="btn" href="/">
            Go home
        </a>

    </div>
    """

    return render_page(
        "404",
        body
    ), 404


# ============================================================
# 500
# ============================================================

@app.errorhandler(500)
def server_error(error):

    body = """
    <div class="card">

        <h1>Something went wrong.</h1>

        <p>
            Heara encountered a server error.
        </p>

        <a class="btn" href="/">
            Return home
        </a>

    </div>
    """

    return render_page(
        "Error",
        body
    ), 500


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
