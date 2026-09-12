from flask import Flask, request, redirect, url_for, session, jsonify, render_template_string, abort
import sqlite3
import os
import secrets
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("HEARA_SECRET", secrets.token_hex(32))

DB = os.path.join(os.path.dirname(__file__), "heara.db")
LIVE_FOLLOWERS = 250


# ============================================================
# DATABASE
# ============================================================

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    cur = con.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        bio TEXT DEFAULT '',
        avatar TEXT DEFAULT '',
        followers INTEGER DEFAULT 0,
        following INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        caption TEXT DEFAULT '',
        media_url TEXT DEFAULT '',
        media_type TEXT DEFAULT 'text',
        likes INTEGER DEFAULT 0,
        views INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        post_id INTEGER NOT NULL,
        UNIQUE(user_id, post_id)
    );

    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        seen INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS live_rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_code TEXT UNIQUE NOT NULL,
        user_id INTEGER NOT NULL,
        title TEXT DEFAULT 'Heara Live',
        active INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    con.commit()
    con.close()


init_db()


# ============================================================
# AUTH
# ============================================================

def current_user():
    if "user_id" not in session:
        return None

    con = db()
    user = con.execute(
        "SELECT * FROM users WHERE id=?",
        (session["user_id"],)
    ).fetchone()
    con.close()
    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


# ============================================================
# DESIGN
# ============================================================

PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{{ title }} • Heara</title>

<style>
* {
    box-sizing:border-box;
    margin:0;
    padding:0;
}

body {
    font-family:Arial,Helvetica,sans-serif;
    background:#070612;
    color:#fff;
    min-height:100vh;
}

a {
    color:inherit;
    text-decoration:none;
}

button,
input,
textarea {
    font:inherit;
}

button {
    cursor:pointer;
}

.nav {
    height:68px;
    position:fixed;
    top:0;
    left:0;
    right:0;
    z-index:100;
    display:flex;
    align-items:center;
    justify-content:space-between;
    padding:0 28px;
    background:rgba(7,6,18,.88);
    backdrop-filter:blur(18px);
    border-bottom:1px solid rgba(255,255,255,.08);
}

.logo {
    font-size:28px;
    font-weight:900;
    letter-spacing:-1px;
    background:linear-gradient(90deg,#9b5cff,#ff4fd8);
    -webkit-background-clip:text;
    color:transparent;
}

.search {
    width:320px;
    background:#151326;
    border:1px solid #29243e;
    color:#fff;
    border-radius:30px;
    padding:11px 18px;
    outline:none;
}

.navlinks {
    display:flex;
    gap:20px;
    align-items:center;
}

.navlinks a {
    color:#bbb6ce;
    font-size:14px;
}

.navlinks a:hover {
    color:white;
}

.avatar {
    width:38px;
    height:38px;
    border-radius:50%;
    display:flex;
    align-items:center;
    justify-content:center;
    background:linear-gradient(135deg,#9b5cff,#ff4fd8);
    font-weight:bold;
}

.page {
    padding:92px 25px 90px;
    max-width:1250px;
    margin:auto;
}

.card {
    background:rgba(20,17,37,.86);
    border:1px solid rgba(255,255,255,.08);
    border-radius:22px;
    padding:22px;
    margin-bottom:20px;
    box-shadow:0 15px 50px rgba(0,0,0,.25);
}

.btn {
    border:0;
    border-radius:25px;
    padding:11px 20px;
    color:white;
    background:linear-gradient(135deg,#8d4dff,#ec3fc9);
    font-weight:bold;
}

.btn.secondary {
    background:#211d34;
}

.input,
textarea {
    width:100%;
    background:#0d0b18;
    color:white;
    border:1px solid #302a47;
    border-radius:14px;
    padding:13px;
    outline:none;
}

textarea {
    min-height:120px;
    resize:vertical;
}

.grid {
    display:grid;
    grid-template-columns:2fr 1fr;
    gap:22px;
}

.post {
    overflow:hidden;
}

.post-head {
    display:flex;
    align-items:center;
    gap:12px;
    margin-bottom:15px;
}

.post-user {
    font-weight:bold;
}

.post-time {
    color:#777188;
    font-size:12px;
}

.post-media {
    width:100%;
    max-height:650px;
    object-fit:cover;
    border-radius:16px;
    background:#000;
}

.post-actions {
    display:flex;
    gap:10px;
    margin-top:15px;
}

.action {
    border:0;
    background:#211d34;
    color:#ddd8e9;
    padding:9px 14px;
    border-radius:20px;
}

.action:hover {
    background:#332b4d;
}

.bottom {
    display:none;
}

.hero {
    min-height:calc(100vh - 68px);
    display:grid;
    grid-template-columns:1fr 1fr;
    align-items:center;
    gap:30px;
}

.hero h1 {
    font-size:clamp(50px,8vw,100px);
    line-height:.9;
    margin-bottom:25px;
}

.gradient {
    background:linear-gradient(90deg,#9d55ff,#ff4ed4);
    -webkit-background-clip:text;
    color:transparent;
}

.hero p {
    color:#aaa4bd;
    font-size:19px;
    line-height:1.6;
    max-width:600px;
}

.hero-img {
    width:100%;
    max-width:570px;
    margin:auto;
    filter:drop-shadow(0 30px 80px rgba(150,60,255,.35));
    animation:float 4s ease-in-out infinite;
}

@keyframes float {
    50% { transform:translateY(-14px); }
}

.auth {
    max-width:450px;
    margin:60px auto;
}

.auth h1 {
    margin-bottom:25px;
}

.auth form {
    display:grid;
    gap:14px;
}

.fyp {
    height:calc(100vh - 68px);
    margin-top:68px;
    overflow-y:auto;
    scroll-snap-type:y mandatory;
    background:#000;
}

.fyp::-webkit-scrollbar {
    display:none;
}

.fyp-item {
    height:calc(100vh - 68px);
    min-height:600px;
    scroll-snap-align:start;
    position:relative;
    display:flex;
    justify-content:center;
    align-items:center;
    background:#000;
    overflow:hidden;
}

.fyp-video {
    height:100%;
    width:100%;
    object-fit:contain;
}

.fyp-overlay {
    position:absolute;
    left:25px;
    bottom:35px;
    right:100px;
    z-index:3;
    text-shadow:0 2px 12px #000;
}

.fyp-overlay strong {
    font-size:18px;
}

.fyp-actions {
    position:absolute;
    right:20px;
    bottom:80px;
    display:flex;
    flex-direction:column;
    gap:12px;
    z-index:4;
}

.fyp-btn {
    width:52px;
    height:52px;
    border-radius:50%;
    border:1px solid rgba(255,255,255,.2);
    background:rgba(0,0,0,.55);
    color:white;
    font-size:21px;
}

.sound {
    position:absolute;
    top:25px;
    right:20px;
    z-index:5;
}

.profile-cover {
    height:220px;
    border-radius:25px;
    background:
      radial-gradient(circle at 20% 30%,#8b45ff55,transparent 30%),
      radial-gradient(circle at 80% 60%,#ff3fd855,transparent 30%),
      #151126;
}

.profile-info {
    padding:0 25px 25px;
    margin-top:-35px;
}

.profile-avatar {
    width:90px;
    height:90px;
    border-radius:50%;
    border:5px solid #070612;
    background:linear-gradient(135deg,#8b4dff,#ff45ce);
    display:flex;
    align-items:center;
    justify-content:center;
    font-size:30px;
    font-weight:bold;
}

.live-box {
    min-height:500px;
    border-radius:25px;
    display:flex;
    flex-direction:column;
    justify-content:center;
    align-items:center;
    background:
      radial-gradient(circle,#39165c,transparent 45%),
      #090711;
    text-align:center;
}

.live-video {
    width:min(900px,100%);
    max-height:650px;
    background:#000;
    border-radius:20px;
}

.comment {
    padding:10px 0;
    border-bottom:1px solid #252036;
}

.muted {
    color:#8f899f;
}

.error {
    padding:18px;
    border-radius:15px;
    background:#381525;
    color:#ff9eb5;
}

@media(max-width:850px) {

    .nav {
        padding:0 15px;
    }

    .search {
        display:none;
    }

    .navlinks {
        display:none;
    }

    .page {
        padding:85px 14px 90px;
    }

    .grid,
    .hero {
        grid-template-columns:1fr;
    }

    .hero {
        text-align:center;
        padding-top:30px;
    }

    .hero-img {
        max-width:400px;
    }

    .bottom {
        position:fixed;
        display:flex;
        bottom:0;
        left:0;
        right:0;
        height:65px;
        z-index:100;
        background:rgba(9,7,18,.94);
        backdrop-filter:blur(18px);
        border-top:1px solid rgba(255,255,255,.1);
        justify-content:space-around;
        align-items:center;
    }

    .bottom a {
        font-size:11px;
        color:#aaa4bb;
        text-align:center;
    }

    .bottom span {
        display:block;
        font-size:21px;
        margin-bottom:3px;
    }

    .fyp,
    .fyp-item {
        height:100vh;
        margin-top:0;
    }
}
</style>
</head>

<body>

<nav class="nav">
    <a href="{{ url_for('home') }}" class="logo">HEARA</a>

    <form action="{{ url_for('search') }}" method="get">
        <input class="search" name="q" placeholder="Search Heara...">
    </form>

    <div class="navlinks">
        <a href="{{ url_for('home') }}">Home</a>
        <a href="{{ url_for('fyp') }}">FYP</a>
        <a href="{{ url_for('live') }}">Live</a>
        <a href="{{ url_for('inbox') }}">Inbox</a>

        {% if user %}
        <a href="{{ url_for('profile', username=user['username']) }}">
            <div class="avatar">{{ user['username'][0].upper() }}</div>
        </a>
        {% else %}
        <a href="{{ url_for('login') }}">Login</a>
        {% endif %}
    </div>
</nav>

{% block content %}{% endblock %}

<div class="bottom">
    <a href="{{ url_for('home') }}"><span>⌂</span>Home</a>
    <a href="{{ url_for('fyp') }}"><span>▶</span>FYP</a>
    <a href="{{ url_for('create') }}"><span>＋</span>Create</a>
    <a href="{{ url_for('live') }}"><span>🔴</span>Live</a>
    <a href="{{ url_for('inbox') }}"><span>✉</span>Inbox</a>
</div>

</body>
</html>
"""


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():
    user = current_user()

    con = db()
    posts = con.execute("""
        SELECT posts.*, users.username
        FROM posts
        JOIN users ON users.id=posts.user_id
        ORDER BY posts.id DESC
        LIMIT 30
    """).fetchall()
    con.close()

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """
        <main class="page">

        {% if not user %}
        <section class="hero">

            <div>
                <div class="logo" style="font-size:20px;margin-bottom:15px">
                    THE SOCIAL WORLD, REIMAGINED.
                </div>

                <h1>
                    Welcome to<br>
                    <span class="gradient">Heara.</span>
                </h1>

                <p>
                    Share your world. Discover creators.
                    Talk, watch, connect and go live.
                    Everything social, in one place.
                </p>

                <br>

                <a class="btn" href="{{ url_for('register') }}">
                    Join Heara
                </a>

                <a class="btn secondary" href="{{ url_for('login') }}">
                    Login
                </a>
            </div>

            <div>
                <img class="hero-img"
                     src="/static/images/heara-hero.png"
                     onerror="this.style.display='none'">
            </div>

        </section>

        {% else %}

        <div class="grid">

            <section>

                <div class="card">
                    <h2>Welcome back, @{{ user['username'] }} 👋</h2>
                    <p class="muted" style="margin-top:8px">
                        What's happening on Heara?
                    </p>

                    <br>

                    <a class="btn" href="{{ url_for('create') }}">
                        ＋ Create post
                    </a>

                    <a class="btn secondary" href="{{ url_for('fyp') }}">
                        ▶ Watch FYP
                    </a>
                </div>

                {% for p in posts %}
                <article class="card post">

                    <div class="post-head">
                        <div class="avatar">{{ p['username'][0].upper() }}</div>

                        <div>
                            <div class="post-user">
                                @{{ p['username'] }}
                            </div>
                            <div class="post-time">
                                {{ p['created_at'] }}
                            </div>
                        </div>
                    </div>

                    {% if p['caption'] %}
                    <p style="margin-bottom:15px">{{ p['caption'] }}</p>
                    {% endif %}

                    {% if p['media_type'] == 'video' and p['media_url'] %}
                    <video
                        class="post-media"
                        controls
                        playsinline
                        preload="metadata"
                        src="{{ p['media_url'] }}">
                    </video>
                    {% elif p['media_type'] == 'image' and p['media_url'] %}
                    <img class="post-media" src="{{ p['media_url'] }}">
                    {% endif %}

                    <div class="post-actions">
                        <form action="{{ url_for('like', post_id=p['id']) }}" method="post">
                            <button class="action">❤️ {{ p['likes'] }}</button>
                        </form>

                        <a class="action" href="{{ url_for('post', post_id=p['id']) }}">
                            💬 Comments
                        </a>

                        <button class="action"
                                onclick="navigator.clipboard.writeText(location.origin + '/post/{{ p['id'] }}')">
                            ↗ Share
                        </button>
                    </div>

                </article>
                {% else %}

                <div class="card">
                    <h2>No posts yet.</h2>
                    <p class="muted">Be the first person to post on Heara.</p>
                </div>

                {% endfor %}

            </section>

            <aside>

                <div class="card">
                    <h3>Heara Live 🔴</h3>
                    <p class="muted" style="margin:10px 0">
                        Watch creators live.
                    </p>
                    <a class="btn" href="{{ url_for('live') }}">Open Live</a>
                </div>

                <div class="card">
                    <h3>Your Heara</h3>
                    <br>
                    <a href="{{ url_for('profile', username=user['username']) }}">
                        Profile →
                    </a>
                    <br><br>
                    <a href="{{ url_for('inbox') }}">
                        Messages →
                    </a>
                    <br><br>
                    <a href="{{ url_for('notifications') }}">
                        Notifications →
                    </a>
                    <br><br>
                    <a href="{{ url_for('creator') }}">
                        Creator Studio →
                    </a>
                </div>

            </aside>

        </div>

        {% endif %}

        </main>
        """),
        title="Home",
        user=user,
        posts=posts
    )


# ============================================================
# FYP
# ============================================================

@app.route("/fyp")
@app.route("/videos")
def fyp():

    con = db()

    videos = con.execute("""
        SELECT posts.*, users.username
        FROM posts
        JOIN users ON users.id=posts.user_id
        WHERE posts.media_type='video'
          AND posts.media_url != ''
        ORDER BY posts.id DESC
        LIMIT 100
    """).fetchall()

    con.close()

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """

        {% if not videos %}
        <div class="page">
            <div class="card" style="text-align:center">
                <h1>No videos yet</h1>
                <p class="muted" style="margin:12px">
                    Create the first video on Heara.
                </p>
                {% if user %}
                <a class="btn" href="{{ url_for('create') }}">Create video</a>
                {% endif %}
            </div>
        </div>

        {% else %}

        <main class="fyp" id="fyp">

            {% for v in videos %}

            <section class="fyp-item">

                <video
                    class="fyp-video"
                    playsinline
                    loop
                    preload="metadata"
                    src="{{ v['media_url'] }}">
                </video>

                <button class="fyp-btn sound"
                        onclick="toggleSound(this)">
                    🔇
                </button>

                <div class="fyp-overlay">
                    <strong>@{{ v['username'] }}</strong>

                    {% if v['caption'] %}
                    <p style="margin-top:10px">
                        {{ v['caption'] }}
                    </p>
                    {% endif %}
                </div>

                <div class="fyp-actions">

                    <form action="{{ url_for('like', post_id=v['id']) }}" method="post">
                        <button class="fyp-btn">❤️</button>
                    </form>

                    <a class="fyp-btn"
                       href="{{ url_for('post', post_id=v['id']) }}"
                       style="display:flex;align-items:center;justify-content:center">
                       💬
                    </a>

                    <button class="fyp-btn"
                            onclick="navigator.clipboard.writeText(location.origin + '/post/{{ v['id'] }}')">
                        ↗
                    </button>

                </div>

            </section>

            {% endfor %}

        </main>

        <script>
        const feed = document.getElementById("fyp");

        const observer = new IntersectionObserver((entries) => {

            entries.forEach(entry => {

                const video = entry.target.querySelector("video");

                if (!video) return;

                if (entry.isIntersecting) {

                    document.querySelectorAll(".fyp-video").forEach(v => {
                        if (v !== video) {
                            v.pause();
                        }
                    });

                    video.currentTime = 0;

                    /*
                     Browsers normally block autoplay with sound.
                     Therefore autoplay begins muted.
                    */
                    video.muted = true;

                    video.play().catch(() => {});

                } else {
                    video.pause();
                }

            });

        }, {threshold:0.65});

        document.querySelectorAll(".fyp-item")
            .forEach(item => observer.observe(item));


        function toggleSound(button) {

            const item = button.closest(".fyp-item");
            const video = item.querySelector("video");

            /*
             Turn sound on only after the user interacts.
            */
            video.muted = !video.muted;

            if (!video.muted) {
                video.volume = 1;
                button.textContent = "🔊";
                video.play().catch(() => {});
            } else {
                button.textContent = "🔇";
            }
        }


        /*
        Mouse wheel support.
        */
        let scrolling = false;

        feed.addEventListener("wheel", function(e) {

            if (scrolling) return;

            scrolling = true;

            const direction = e.deltaY > 0 ? 1 : -1;

            feed.scrollBy({
                top: direction * window.innerHeight,
                behavior: "smooth"
            });

            setTimeout(() => {
                scrolling = false;
            }, 700);

        });


        /*
        Keyboard support.
        */
        document.addEventListener("keydown", function(e) {

            if (e.key === "ArrowDown") {
                feed.scrollBy({
                    top: window.innerHeight,
                    behavior:"smooth"
                });
            }

            if (e.key === "ArrowUp") {
                feed.scrollBy({
                    top: -window.innerHeight,
                    behavior:"smooth"
                });
            }

        });
        </script>

        {% endif %}

        """),
        title="FYP",
        user=current_user(),
        videos=videos
    )


# ============================================================
# CREATE
# ============================================================

@app.route("/create", methods=["GET", "POST"])
@login_required
def create():

    if request.method == "POST":

        caption = request.form.get("caption", "").strip()
        media_url = request.form.get("media_url", "").strip()
        media_type = request.form.get("media_type", "text")

        con = db()

        con.execute("""
            INSERT INTO posts
            (user_id, caption, media_url, media_type)
            VALUES (?, ?, ?, ?)
        """, (
            current_user()["id"],
            caption,
            media_url,
            media_type
        ))

        con.commit()
        con.close()

        return redirect(url_for("home"))

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """

        <main class="page">

            <div class="card" style="max-width:700px;margin:auto">

                <h1>Create on Heara</h1>

                <p class="muted" style="margin:8px 0 25px">
                    Share something with the Heara community.
                </p>

                <form method="post">

                    <textarea
                        name="caption"
                        placeholder="What's on your mind?"
                    ></textarea>

                    <br><br>

                    <input
                        class="input"
                        name="media_url"
                        placeholder="Video or image URL (optional)"
                    >

                    <br><br>

                    <select class="input" name="media_type">
                        <option value="text">Text</option>
                        <option value="video">Video</option>
                        <option value="image">Image</option>
                    </select>

                    <br><br>

                    <button class="btn">
                        Publish
                    </button>

                </form>

                <br>

                <p class="muted">
                    Note: direct large-video uploading will be connected
                    to cloud storage in the production version.
                </p>

            </div>

        </main>

        """),
        title="Create",
        user=current_user()
    )


# ============================================================
# POST
# ============================================================

@app.route("/post/<int:post_id>")
def post(post_id):

    con = db()

    p = con.execute("""
        SELECT posts.*, users.username
        FROM posts
        JOIN users ON users.id=posts.user_id
        WHERE posts.id=?
    """, (post_id,)).fetchone()

    comments = con.execute("""
        SELECT comments.*, users.username
        FROM comments
        JOIN users ON users.id=comments.user_id
        WHERE post_id=?
        ORDER BY comments.id DESC
    """, (post_id,)).fetchall()

    con.close()

    if not p:
        abort(404)

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """

        <main class="page">

            <article class="card">

                <div class="post-head">
                    <div class="avatar">
                        {{ p['username'][0].upper() }}
                    </div>

                    <strong>@{{ p['username'] }}</strong>
                </div>

                {% if p['caption'] %}
                <p style="margin-bottom:18px">
                    {{ p['caption'] }}
                </p>
                {% endif %}

                {% if p['media_type']=='video' and p['media_url'] %}
                <video
                    class="post-media"
                    controls
                    playsinline
                    preload="metadata"
                    src="{{ p['media_url'] }}">
                </video>
                {% endif %}

                {% if p['media_type']=='image' and p['media_url'] %}
                <img class="post-media" src="{{ p['media_url'] }}">
                {% endif %}

            </article>

            {% if user %}

            <div class="card">

                <h3>Comment</h3>

                <form method="post"
                      action="{{ url_for('comment', post_id=p['id']) }}">

                    <br>

                    <input
                        class="input"
                        name="text"
                        placeholder="Write a comment..."
                        required
                    >

                    <br><br>

                    <button class="btn">Comment</button>

                </form>

            </div>

            {% endif %}

            <div class="card">

                <h2>Comments</h2>

                <br>

                {% for c in comments %}

                <div class="comment">
                    <strong>@{{ c['username'] }}</strong>
                    <p style="margin-top:5px">{{ c['text'] }}</p>
                </div>

                {% else %}

                <p class="muted">No comments yet.</p>

                {% endfor %}

            </div>

        </main>

        """),
        title="Post",
        user=current_user(),
        p=p,
        comments=comments
    )


@app.route("/like/<int:post_id>", methods=["POST"])
@login_required
def like(post_id):

    con = db()

    exists = con.execute("""
        SELECT id FROM likes
        WHERE user_id=? AND post_id=?
    """, (current_user()["id"], post_id)).fetchone()

    if exists:

        con.execute("""
            DELETE FROM likes
            WHERE user_id=? AND post_id=?
        """, (current_user()["id"], post_id))

        con.execute("""
            UPDATE posts
            SET likes=MAX(likes-1,0)
            WHERE id=?
        """, (post_id,))

    else:

        con.execute("""
            INSERT INTO likes(user_id,post_id)
            VALUES(?,?)
        """, (current_user()["id"], post_id))

        con.execute("""
            UPDATE posts
            SET likes=likes+1
            WHERE id=?
        """, (post_id,))

    con.commit()
    con.close()

    return redirect(request.referrer or url_for("home"))


@app.route("/comment/<int:post_id>", methods=["POST"])
@login_required
def comment(post_id):

    text = request.form.get("text", "").strip()

    if text:

        con = db()

        con.execute("""
            INSERT INTO comments(post_id,user_id,text)
            VALUES(?,?,?)
        """, (
            post_id,
            current_user()["id"],
            text
        ))

        con.commit()
        con.close()

    return redirect(request.referrer or url_for("post", post_id=post_id))


# ============================================================
# PROFILE
# ============================================================

@app.route("/profile/<username>")
def profile(username):

    con = db()

    u = con.execute(
        "SELECT * FROM users WHERE username=?",
        (username,)
    ).fetchone()

    if not u:
        con.close()
        abort(404)

    posts = con.execute("""
        SELECT * FROM posts
        WHERE user_id=?
        ORDER BY id DESC
    """, (u["id"],)).fetchall()

    con.close()

    me = current_user()

    following = False

    if me:
        con = db()
        following = con.execute("""
            SELECT id FROM follows
            WHERE follower_id=? AND following_id=?
        """, (me["id"], u["id"])).fetchone()
        con.close()

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """

        <main class="page">

            <div class="card">

                <div class="profile-cover"></div>

                <div class="profile-info">

                    <div class="profile-avatar">
                        {{ u['username'][0].upper() }}
                    </div>

                    <h1 style="margin-top:12px">
                        @{{ u['username'] }}
                    </h1>

                    <p class="muted">
                        {{ u['bio'] or 'Welcome to my Heara profile.' }}
                    </p>

                    <p style="margin-top:12px">
                        <strong>{{ u['followers'] }}</strong> followers
                        &nbsp;&nbsp;
                        <strong>{{ u['following'] }}</strong> following
                    </p>

                    {% if me and me['id'] != u['id'] %}

                    <br>

                    {% if following %}

                    <form method="post"
                          action="{{ url_for('unfollow', user_id=u['id']) }}">
                        <button class="btn secondary">
                            Following ✓
                        </button>
                    </form>

                    {% else %}

                    <form method="post"
                          action="{{ url_for('follow', user_id=u['id']) }}">
                        <button class="btn">
                            Follow
                        </button>
                    </form>

                    {% endif %}

                    {% endif %}

                </div>

            </div>

            <h2 style="margin:25px 0 15px">Posts</h2>

            {% for p in posts %}

            <article class="card">

                {% if p['caption'] %}
                <p style="margin-bottom:15px">
                    {{ p['caption'] }}
                </p>
                {% endif %}

                {% if p['media_type']=='video' and p['media_url'] %}

                <video
                    class="post-media"
                    controls
                    playsinline
                    preload="metadata"
                    src="{{ p['media_url'] }}">
                </video>

                {% elif p['media_type']=='image' and p['media_url'] %}

                <img class="post-media" src="{{ p['media_url'] }}">

                {% endif %}

            </article>

            {% else %}

            <div class="card">
                <p class="muted">No posts yet.</p>
            </div>

            {% endfor %}

        </main>

        """),
        title=username,
        user=me,
        u=u,
        posts=posts,
        following=following
    )


@app.route("/follow/<int:user_id>", methods=["POST"])
@login_required
def follow(user_id):

    me = current_user()

    if me["id"] == user_id:
        return redirect(request.referrer or url_for("home"))

    con = db()

    try:
        con.execute("""
            INSERT INTO follows(follower_id,following_id)
            VALUES(?,?)
        """, (me["id"], user_id))

        con.execute("""
            UPDATE users SET followers=followers+1
            WHERE id=?
        """, (user_id,))

        con.execute("""
            UPDATE users SET following=following+1
            WHERE id=?
        """, (me["id"],))

        con.execute("""
            INSERT INTO notifications(user_id,text)
            VALUES(?,?)
        """, (
            user_id,
            "@" + me["username"] + " started following you."
        ))

        con.commit()

    except sqlite3.IntegrityError:
        pass

    con.close()

    return redirect(request.referrer or url_for("home"))


@app.route("/unfollow/<int:user_id>", methods=["POST"])
@login_required
def unfollow(user_id):

    me = current_user()

    con = db()

    deleted = con.execute("""
        DELETE FROM follows
        WHERE follower_id=? AND following_id=?
    """, (me["id"], user_id))

    if deleted.rowcount:

        con.execute("""
            UPDATE users SET followers=MAX(followers-1,0)
            WHERE id=?
        """, (user_id,))

        con.execute("""
            UPDATE users SET following=MAX(following-1,0)
            WHERE id=?
        """, (me["id"],))

    con.commit()
    con.close()

    return redirect(request.referrer or url_for("home"))


# ============================================================
# LIVE
# ============================================================

@app.route("/live")
def live():

    con = db()

    rooms = con.execute("""
        SELECT live_rooms.*, users.username
        FROM live_rooms
        JOIN users ON users.id=live_rooms.user_id
        WHERE active=1
        ORDER BY live_rooms.id DESC
    """).fetchall()

    con.close()

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """

        <main class="page">

            <div class="card">
                <h1>🔴 Heara Live</h1>
                <p class="muted" style="margin-top:8px">
                    Watch creators who are live right now.
                </p>

                {% if user %}
                <br>
                <a class="btn" href="{{ url_for('go_live') }}">
                    Go Live
                </a>
                {% endif %}
            </div>

            {% for room in rooms %}

            <div class="card">

                <h2>@{{ room['username'] }}</h2>

                <p class="muted">
                    {{ room['title'] }}
                </p>

                <br>

                <a class="btn"
                   href="{{ url_for('live_room', room_code=room['room_code']) }}">
                    Watch Live
                </a>

            </div>

            {% else %}

            <div class="live-box">
                <h1>No one is live right now.</h1>
                <p class="muted" style="margin:12px">
                    Be the first creator to go live.
                </p>
            </div>

            {% endfor %}

        </main>

        """),
        title="Live",
        user=current_user(),
        rooms=rooms
    )


@app.route("/go-live", methods=["GET", "POST"])
@login_required
def go_live():

    user = current_user()

    if user["followers"] < LIVE_FOLLOWERS:

        return render_template_string(
            PAGE.replace("{% block content %}{% endblock %}", """

            <main class="page">

                <div class="card" style="max-width:650px;margin:auto;text-align:center">

                    <h1>🔒 Go Live</h1>

                    <p style="margin:20px 0">
                        You need <strong>{{ required }}</strong>
                        followers to go live.
                    </p>

                    <p class="muted">
                        Your current followers:
                        <strong>{{ followers }}</strong>
                    </p>

                    <br>

                    <a class="btn" href="{{ url_for('profile', username=user['username']) }}">
                        Back to profile
                    </a>

                </div>

            </main>

            """),
            title="Go Live",
            user=user,
            required=LIVE_FOLLOWERS,
            followers=user["followers"]
        )

    if request.method == "POST":

        title = request.form.get("title", "Heara Live").strip()

        code = secrets.token_urlsafe(10)

        con = db()

        con.execute("""
            INSERT INTO live_rooms(room_code,user_id,title,active)
            VALUES(?,?,?,1)
        """, (
            code,
            user["id"],
            title or "Heara Live"
        ))

        con.commit()
        con.close()

        return redirect(url_for("live_room", room_code=code))

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """

        <main class="page">

            <div class="card" style="max-width:650px;margin:auto">

                <h1>🔴 Go Live</h1>

                <p class="muted" style="margin:10px 0 25px">
                    You're eligible to go live.
                </p>

                <form method="post">

                    <input
                        class="input"
                        name="title"
                        placeholder="Live title"
                        value="Heara Live"
                        required
                    >

                    <br><br>

                    <button class="btn">
                        Start Live
                    </button>

                </form>

            </div>

        </main>

        """),
        title="Go Live",
        user=user
    )


@app.route("/live/<room_code>")
def live_room(room_code):

    con = db()

    room = con.execute("""
        SELECT live_rooms.*, users.username
        FROM live_rooms
        JOIN users ON users.id=live_rooms.user_id
        WHERE room_code=? AND active=1
    """, (room_code,)).fetchone()

    con.close()

    if not room:
        return redirect(url_for("live"))

    user = current_user()

    is_owner = bool(
        user and user["id"] == room["user_id"]
    )

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """

        <main class="page">

            <div class="live-box">

                <video
                    id="camera"
                    class="live-video"
                    autoplay
                    muted
                    playsinline
                    style="display:{{ 'block' if is_owner else 'none' }}">
                </video>

                {% if not is_owner %}

                <div>
                    <h1>🔴 {{ room['title'] }}</h1>

                    <p class="muted" style="margin-top:10px">
                        @{{ room['username'] }} is live.
                    </p>

                    <br>

                    <p>
                        Live room connected.
                    </p>
                </div>

                {% endif %}

            </div>

            {% if is_owner %}

            <div class="card" style="text-align:center">

                <h2>You are live 🔴</h2>

                <p class="muted" style="margin:10px">
                    Allow camera and microphone access when your browser asks.
                </p>

                <br>

                <button class="btn" onclick="startCamera()">
                    Enable Camera & Mic
                </button>

                <form method="post"
                      action="{{ url_for('end_live', room_code=room['room_code']) }}"
                      style="display:inline">

                    <button class="btn secondary">
                        End Live
                    </button>

                </form>

            </div>

            <script>

            async function startCamera() {

                const video = document.getElementById("camera");

                try {

                    const stream =
                        await navigator.mediaDevices.getUserMedia({
                            video:true,
                            audio:true
                        });

                    video.srcObject = stream;

                } catch(error) {

                    alert(
                        "Camera or microphone permission was denied. " +
                        "Please allow camera and microphone access in your browser."
                    );

                }

            }

            </script>

            {% endif %}

        </main>

        """),
        title="Live",
        user=user,
        room=room,
        is_owner=is_owner
    )


@app.route("/live/<room_code>/end", methods=["POST"])
@login_required
def end_live(room_code):

    con = db()

    con.execute("""
        UPDATE live_rooms
        SET active=0
        WHERE room_code=? AND user_id=?
    """, (room_code, current_user()["id"]))

    con.commit()
    con.close()

    return redirect(url_for("live"))


# ============================================================
# INBOX
# ============================================================

@app.route("/inbox")
@login_required
def inbox():

    me = current_user()

    con = db()

    users = con.execute("""
        SELECT DISTINCT users.*
        FROM users
        JOIN messages
        ON users.id=messages.sender_id
        OR users.id=messages.receiver_id
        WHERE users.id != ?
        ORDER BY messages.id DESC
    """, (me["id"],)).fetchall()

    con.close()

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """

        <main class="page">

            <div class="card">

                <h1>✉ Inbox</h1>

                <br>

                {% for u in users %}

                <a href="{{ url_for('messages', user_id=u['id']) }}"
                   style="display:block;padding:18px;border-bottom:1px solid #28223a">

                    <strong>@{{ u['username'] }}</strong>

                    <p class="muted">
                        Open conversation →
                    </p>

                </a>

                {% else %}

                <p class="muted">
                    No conversations yet.
                </p>

                {% endfor %}

            </div>

        </main>

        """),
        title="Inbox",
        user=me,
        users=users
    )


@app.route("/messages/<int:user_id>", methods=["GET", "POST"])
@login_required
def messages(user_id):

    me = current_user()

    con = db()

    other = con.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if not other:
        con.close()
        abort(404)

    if request.method == "POST":

        text = request.form.get("text", "").strip()

        if text:

            con.execute("""
                INSERT INTO messages(sender_id,receiver_id,text)
                VALUES(?,?,?)
            """, (
                me["id"],
                user_id,
                text
            ))

            con.execute("""
                INSERT INTO notifications(user_id,text)
                VALUES(?,?)
            """, (
                user_id,
                "New message from @" + me["username"]
            ))

            con.commit()

    messages_list = con.execute("""
        SELECT messages.*, users.username
        FROM messages
        JOIN users ON users.id=messages.sender_id
        WHERE
        (sender_id=? AND receiver_id=?)
        OR
        (sender_id=? AND receiver_id=?)
        ORDER BY messages.id ASC
    """, (
        me["id"], user_id,
        user_id, me["id"]
    )).fetchall()

    con.close()

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """

        <main class="page">

            <div class="card">

                <h1>Chat with @{{ other['username'] }}</h1>

                <div style="margin-top:25px">

                    {% for m in messages_list %}

                    <div style="
                        padding:12px;
                        margin:8px 0;
                        border-radius:15px;
                        background:{{ '#47257a' if m['sender_id']==user['id'] else '#211d34' }};
                        max-width:75%;
                        margin-left:{{ 'auto' if m['sender_id']==user['id'] else '0' }};
                    ">

                        {{ m['text'] }}

                    </div>

                    {% endfor %}

                </div>

                <form method="post" style="display:flex;gap:10px;margin-top:20px">

                    <input
                        class="input"
                        name="text"
                        placeholder="Write a message..."
                        required
                    >

                    <button class="btn">Send</button>

                </form>

            </div>

        </main>

        """),
        title="Messages",
        user=me,
        other=other,
        messages_list=messages_list
    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route("/notifications")
@login_required
def notifications():

    con = db()

    notes = con.execute("""
        SELECT * FROM notifications
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 50
    """, (current_user()["id"],)).fetchall()

    con.execute("""
        UPDATE notifications
        SET seen=1
        WHERE user_id=?
    """, (current_user()["id"],))

    con.commit()
    con.close()

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """

        <main class="page">

            <div class="card">

                <h1>🔔 Notifications</h1>

                <br>

                {% for n in notes %}

                <div style="
                    padding:16px;
                    border-bottom:1px solid #28223a
                ">
                    {{ n['text'] }}
                </div>

                {% else %}

                <p class="muted">
                    Nothing new.
                </p>

                {% endfor %}

            </div>

        </main>

        """),
        title="Notifications",
        user=current_user(),
        notes=notes
    )


# ============================================================
# SEARCH
# ============================================================

@app.route("/search")
def search():

    q = request.args.get("q", "").strip()

    con = db()

    users = []

    if q:
        users = con.execute("""
            SELECT * FROM users
            WHERE username LIKE ?
            LIMIT 30
        """, ("%" + q + "%",)).fetchall()

    con.close()

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """

        <main class="page">

            <div class="card">

                <h1>Search Heara</h1>

                <form style="margin-top:20px">

                    <input
                        class="input"
                        name="q"
                        value="{{ q }}"
                        placeholder="Search usernames..."
                    >

                    <br><br>

                    <button class="btn">Search</button>

                </form>

            </div>

            {% for u in users %}

            <div class="card">

                <h2>@{{ u['username'] }}</h2>

                <p class="muted">{{ u['followers'] }} followers</p>

                <br>

                <a class="btn"
                   href="{{ url_for('profile', username=u['username']) }}">
                    View profile
                </a>

            </div>

            {% endfor %}

        </main>

        """),
        title="Search",
        user=current_user(),
        users=users,
        q=q
    )


# ============================================================
# CREATOR
# ============================================================

@app.route("/creator")
@login_required
def creator():

    user = current_user()

    con = db()

    posts = con.execute("""
        SELECT COUNT(*) AS total
        FROM posts
        WHERE user_id=?
    """, (user["id"],)).fetchone()["total"]

    likes = con.execute("""
        SELECT COALESCE(SUM(likes),0) AS total
        FROM posts
        WHERE user_id=?
    """, (user["id"],)).fetchone()["total"]

    views = con.execute("""
        SELECT COALESCE(SUM(views),0) AS total
        FROM posts
        WHERE user_id=?
    """, (user["id"],)).fetchone()["total"]

    con.close()

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """

        <main class="page">

            <h1>Creator Studio</h1>

            <p class="muted" style="margin:8px 0 25px">
                Your Heara creator dashboard.
            </p>

            <div class="grid">

                <div class="card">
                    <h2>{{ posts }}</h2>
                    <p class="muted">Posts</p>
                </div>

                <div class="card">
                    <h2>{{ likes }}</h2>
                    <p class="muted">Likes</p>
                </div>

                <div class="card">
                    <h2>{{ views }}</h2>
                    <p class="muted">Views</p>
                </div>

                <div class="card">
                    <h2>₦0</h2>
                    <p class="muted">Creator earnings</p>
                </div>

            </div>

            <div class="card">

                <h2>Go Live</h2>

                <p class="muted" style="margin:10px 0 20px">
                    Live access requires {{ required }} followers.
                </p>

                <a class="btn" href="{{ url_for('go_live') }}">
                    Check Live Access
                </a>

            </div>

        </main>

        """),
        title="Creator Studio",
        user=user,
        posts=posts,
        likes=likes,
        views=views,
        required=LIVE_FOLLOWERS
    )


# ============================================================
# AUTH PAGES
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        if len(username) < 3 or len(password) < 4:
            return "Username must be at least 3 characters and password 4 characters."

        con = db()

        try:

            cur = con.execute("""
                INSERT INTO users(username,password)
                VALUES(?,?)
            """, (username, password))

            con.commit()

            session["user_id"] = cur.lastrowid

            con.close()

            return redirect(url_for("home"))

        except sqlite3.IntegrityError:

            con.close()

            return "That username is already taken."

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """

        <main class="page">

            <div class="auth card">

                <h1>Join Heara</h1>

                <form method="post">

                    <input
                        class="input"
                        name="username"
                        placeholder="Username"
                        required
                    >

                    <input
                        class="input"
                        type="password"
                        name="password"
                        placeholder="Password"
                        required
                    >

                    <button class="btn">
                        Create account
                    </button>

                </form>

                <p class="muted" style="margin-top:20px">
                    Already have an account?
                    <a href="{{ url_for('login') }}">
                        Login
                    </a>
                </p>

            </div>

        </main>

        """),
        title="Register",
        user=None
    )


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        con = db()

        user = con.execute("""
            SELECT * FROM users
            WHERE username=? AND password=?
        """, (username, password)).fetchone()

        con.close()

        if user:

            session["user_id"] = user["id"]

            return redirect(url_for("home"))

        return "Incorrect username or password."

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """

        <main class="page">

            <div class="auth card">

                <h1>Welcome back</h1>

                <form method="post">

                    <input
                        class="input"
                        name="username"
                        placeholder="Username"
                        required
                    >

                    <input
                        class="input"
                        type="password"
                        name="password"
                        placeholder="Password"
                        required
                    >

                    <button class="btn">
                        Login
                    </button>

                </form>

                <p class="muted" style="margin-top:20px">
                    Don't have an account?
                    <a href="{{ url_for('register') }}">
                        Create one
                    </a>
                </p>

            </div>

        </main>

        """),
        title="Login",
        user=None
    )


@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# ============================================================
# API
# ============================================================

@app.route("/api/me")
def api_me():

    user = current_user()

    if not user:
        return jsonify({
            "logged_in":False
        })

    return jsonify({
        "logged_in":True,
        "id":user["id"],
        "username":user["username"],
        "followers":user["followers"]
    })


@app.route("/api/fyp")
def api_fyp():

    con = db()

    videos = con.execute("""
        SELECT posts.id,
               posts.caption,
               posts.media_url,
               posts.likes,
               posts.views,
               users.username
        FROM posts
        JOIN users ON users.id=posts.user_id
        WHERE posts.media_type='video'
          AND posts.media_url != ''
        ORDER BY posts.id DESC
        LIMIT 100
    """).fetchall()

    con.close()

    return jsonify([dict(v) for v in videos])


@app.route("/api/view/<int:post_id>", methods=["POST"])
def api_view(post_id):

    con = db()

    con.execute("""
        UPDATE posts
        SET views=views+1
        WHERE id=?
    """, (post_id,))

    con.commit()
    con.close()

    return jsonify({"ok":True})


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    try:

        con = db()
        con.execute("SELECT 1")
        con.close()

        return jsonify({
            "status":"ok",
            "service":"Heara"
        })

    except Exception as e:

        return jsonify({
            "status":"error",
            "error":str(e)
        }), 500


# ============================================================
# ERROR PAGES
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """

        <main class="page">

            <div class="card" style="text-align:center">

                <h1 style="font-size:80px">404</h1>

                <p class="muted">
                    This Heara page doesn't exist.
                </p>

                <br>

                <a class="btn" href="{{ url_for('home') }}">
                    Go Home
                </a>

            </div>

        </main>

        """),
        title="Not Found",
        user=current_user()
    ), 404


@app.errorhandler(500)
def server_error(error):

    return render_template_string(
        PAGE.replace("{% block content %}{% endblock %}", """

        <main class="page">

            <div class="card">

                <h1>Heara had a problem.</h1>

                <p class="muted" style="margin-top:12px">
                    The server encountered an error.
                    Please try again.
                </p>

                <br>

                <a class="btn" href="{{ url_for('home') }}">
                    Return Home
                </a>

            </div>

        </main>

        """),
        title="Server Error",
        user=current_user()
    ), 500


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
