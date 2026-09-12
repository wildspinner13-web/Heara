from flask import Flask, request, redirect, session, jsonify
import sqlite3
import os
import urllib.request
import urllib.error
import urllib.parse
import json
from functools import wraps

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "heara-development-key"
)

# =========================================================
# DATABASE
# =========================================================

DATABASE = "database.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            UNIQUE(user_id, post_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS follows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            follower_id INTEGER NOT NULL,
            following_id INTEGER NOT NULL,
            UNIQUE(follower_id, following_id)
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================================================
# VIDEO CATEGORIES
# =========================================================

VIDEO_CATEGORIES = {
    "For You": "funny people comedy entertainment",
    "Comedy": "funny comedy humor people laughing",
    "Dance": "dance dancing people performance",
    "Music": "music singer musician performance",
    "Sports": "sports football basketball athletic",
    "Africa": "Africa African people culture",
    "Nigeria": "Nigeria Nigerian people Lagos",
    "Food": "food cooking restaurant street food",
    "Animals": "funny animals pets dogs cats",
    "Travel": "travel adventure vacation people",
    "Fitness": "fitness workout exercise people",
    "Lifestyle": "lifestyle people fashion daily life"
}


# =========================================================
# PEXELS VIDEO API
# =========================================================

def get_pexels_videos(query, page=1, per_page=20):

    api_key = os.environ.get("PEXELS_API_KEY")

    if not api_key:
        print("PEXELS_API_KEY is missing")
        return []

    url = (
        "https://api.pexels.com/videos/search?"
        + urllib.parse.urlencode({
            "query": query,
            "page": page,
            "per_page": per_page
        })
    )

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": api_key,
            "User-Agent": "Heara/1.0"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))

        videos = []

        for video in data.get("videos", []):

            files = video.get("video_files", [])

            if not files:
                continue

            # Prefer HD MP4
            selected_file = None

            for file in files:
                if (
                    file.get("file_type") == "video/mp4"
                    and file.get("width", 0) >= 720
                ):
                    selected_file = file
                    break

            if selected_file is None:
                for file in files:
                    if file.get("file_type") == "video/mp4":
                        selected_file = file
                        break

            if selected_file is None:
                continue

            videos.append({
                "id": video.get("id"),
                "url": selected_file.get("link"),
                "thumbnail": video.get("image"),
                "duration": video.get("duration", 0),
                "width": selected_file.get("width", 0),
                "height": selected_file.get("height", 0),
                "user": video.get("user", {}).get("name", "Pexels")
            })

        return videos

    except urllib.error.HTTPError as e:
        print("Pexels HTTP error:", e.code)
        return []

    except urllib.error.URLError as e:
        print("Pexels connection error:", e)
        return []

    except Exception as e:
        print("Pexels error:", e)
        return []


# =========================================================
# HELPERS
# =========================================================

def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    conn = get_db()

    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    conn.close()

    return user


def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            return redirect("/login")

        return function(*args, **kwargs)

    return wrapper


def page(title, body):

    user = current_user()

    username = user["username"] if user else None

    nav = """
        <nav>
            <a href="/">Home</a>
            <a href="/videos">Videos</a>
    """

    if username:
        nav += f"""
            <span class="welcome">Hi, {username}</span>
            <a href="/logout">Logout</a>
        """
    else:
        nav += """
            <a href="/login">Login</a>
            <a href="/register">Register</a>
        """

    nav += "</nav>"

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>{title} - Heara</title>

<style>

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    font-family: Arial, sans-serif;
    background: #0f0f0f;
    color: white;
}}

nav {{
    position: sticky;
    top: 0;
    z-index: 100;
    background: #181818;
    padding: 16px;
    display: flex;
    align-items: center;
    gap: 18px;
    border-bottom: 1px solid #292929;
}}

nav a {{
    color: white;
    text-decoration: none;
    font-weight: bold;
}}

nav a:hover {{
    color: #ff4f81;
}}

.welcome {{
    margin-left: auto;
    color: #aaa;
}}

.container {{
    width: min(1100px, 94%);
    margin: auto;
    padding: 30px 0;
}}

.hero {{
    text-align: center;
    padding: 60px 20px;
}}

.hero h1 {{
    font-size: 55px;
    margin-bottom: 10px;
}}

.hero span {{
    color: #ff4f81;
}}

.hero p {{
    color: #bbb;
    font-size: 18px;
}}

.button {{
    display: inline-block;
    background: #ff4f81;
    color: white;
    padding: 12px 22px;
    border-radius: 25px;
    text-decoration: none;
    margin: 8px;
    border: none;
    cursor: pointer;
}}

.card {{
    background: #191919;
    border-radius: 15px;
    padding: 20px;
    margin-bottom: 20px;
}}

input, textarea {{
    width: 100%;
    padding: 13px;
    margin: 8px 0 15px;
    border-radius: 8px;
    border: 1px solid #333;
    background: #111;
    color: white;
}}

textarea {{
    min-height: 100px;
}}

.category {{
    display: inline-block;
    background: #252525;
    color: white;
    text-decoration: none;
    padding: 10px 15px;
    border-radius: 20px;
    margin: 5px;
}}

.category:hover {{
    background: #ff4f81;
}}

.video-grid {{
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(280px, 1fr));
    gap: 20px;
}}

.video-card {{
    background: #191919;
    border-radius: 15px;
    overflow: hidden;
}}

.video-card video {{
    width: 100%;
    display: block;
    background: black;
    max-height: 500px;
}}

.video-info {{
    padding: 15px;
}}

.post {{
    background: #191919;
    padding: 20px;
    border-radius: 15px;
    margin-bottom: 20px;
}}

.small {{
    color: #888;
    font-size: 13px;
}}

.error {{
    background: #5b1b1b;
    padding: 15px;
    border-radius: 8px;
    margin-bottom: 15px;
}}

.success {{
    background: #174d2a;
    padding: 15px;
    border-radius: 8px;
    margin-bottom: 15px;
}}

footer {{
    text-align: center;
    padding: 40px;
    color: #777;
}}

</style>

</head>

<body>

{nav}

<div class="container">

{body}

</div>

<footer>
Heara © 2026
</footer>

</body>
</html>
"""


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():

    conn = get_db()

    posts = conn.execute("""
        SELECT
            posts.id,
            posts.content,
            posts.created_at,
            users.username,
            COUNT(likes.id) AS like_count
        FROM posts
        JOIN users
            ON posts.user_id = users.id
        LEFT JOIN likes
            ON posts.id = likes.post_id
        GROUP BY posts.id
        ORDER BY posts.created_at DESC
        LIMIT 30
    """).fetchall()

    conn.close()

    post_html = ""

    for post in posts:

        post_html += f"""
        <div class="post">

            <strong>@{post["username"]}</strong>

            <p>{post["content"]}</p>

            <div class="small">
                {post["like_count"]} likes
                · {post["created_at"]}
            </div>

            <br>

            <a class="button"
               href="/like/{post["id"]}">
               Like
            </a>

            <a class="button"
               href="/post/{post["id"]}">
               View
            </a>

        </div>
        """

    if not post_html:
        post_html = """
        <div class="card">
            <h2>No posts yet</h2>
            <p>Be the first person to post on Heara.</p>
        </div>
        """

    body = f"""

    <section class="hero">

        <h1>Welcome to <span>Heara</span></h1>

        <p>
            Discover videos, share your thoughts,
            follow people and enjoy the community.
        </p>

        <a class="button" href="/videos">
            Watch Videos
        </a>

        <a class="button" href="/register">
            Join Heara
        </a>

    </section>

    <div class="card">

        <h2>Create a Post</h2>

        <form method="POST" action="/post">

            <textarea
                name="content"
                placeholder="What's on your mind?"
                required>
            </textarea>

            <button class="button" type="submit">
                Post
            </button>

        </form>

    </div>

    <h2>Latest Posts</h2>

    {post_html}

    """

    return page("Home", body)


# =========================================================
# VIDEOS
# =========================================================

@app.route("/videos")
def videos():

    category = request.args.get(
        "category",
        "For You"
    )

    if category not in VIDEO_CATEGORIES:
        category = "For You"

    query = VIDEO_CATEGORIES[category]

    videos = get_pexels_videos(
        query=query,
        page=1,
        per_page=20
    )

    categories_html = ""

    for name in VIDEO_CATEGORIES:

        categories_html += f"""
        <a class="category"
           href="/videos?category={urllib.parse.quote(name)}">
           {name}
        </a>
        """

    video_html = ""

    for video in videos:

        video_html += f"""
        <div class="video-card">

            <video
                controls
                playsinline
                preload="metadata"
                poster="{video["thumbnail"]}">

                <source
                    src="{video["url"]}"
                    type="video/mp4">

                Your browser does not support video.
            </video>

            <div class="video-info">

                <strong>{category}</strong>

                <p class="small">
                    Video by {video["user"]}
                </p>

            </div>

        </div>
        """

    if not video_html:

        video_html = """
        <div class="card">

            <h2>No videos available right now.</h2>

            <p>
                Make sure your PEXELS_API_KEY is configured
                in Render Environment Variables.
            </p>

        </div>
        """

    body = f"""

    <h1>Heara Videos</h1>

    <p>
        Discover videos from different categories.
    </p>

    <div>
        {categories_html}
    </div>

    <br>

    <h2>{category}</h2>

    <div class="video-grid">
        {video_html}
    </div>

    """

    return page("Videos", body)


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    error = ""

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not username or not password:

            error = "Please enter a username and password."

        elif len(username) < 3:

            error = "Username must be at least 3 characters."

        elif len(password) < 4:

            error = "Password must be at least 4 characters."

        else:

            conn = get_db()

            try:

                cursor = conn.execute(
                    """
                    INSERT INTO users
                    (username, password)
                    VALUES (?, ?)
                    """,
                    (username, password)
                )

                conn.commit()

                session["user_id"] = cursor.lastrowid

                conn.close()

                return redirect("/")

            except sqlite3.IntegrityError:

                conn.close()

                error = "That username already exists."

    body = f"""

    <div class="card">

        <h1>Create your Heara account</h1>

        {f'<div class="error">{error}</div>' if error else ''}

        <form method="POST">

            <label>Username</label>

            <input
                type="text"
                name="username"
                required>

            <label>Password</label>

            <input
                type="password"
                name="password"
                required>

            <button class="button" type="submit">
                Register
            </button>

        </form>

    </div>

    """

    return page("Register", body)


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    error = ""

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        conn = get_db()

        user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
            AND password = ?
            """,
            (username, password)
        ).fetchone()

        conn.close()

        if user:

            session["user_id"] = user["id"]

            return redirect("/")

        error = "Incorrect username or password."

    body = f"""

    <div class="card">

        <h1>Login</h1>

        {f'<div class="error">{error}</div>' if error else ''}

        <form method="POST">

            <label>Username</label>

            <input
                type="text"
                name="username"
                required>

            <label>Password</label>

            <input
                type="password"
                name="password"
                required>

            <button class="button" type="submit">
                Login
            </button>

        </form>

        <p>
            Don't have an account?
            <a href="/register">Register</a>
        </p>

    </div>

    """

    return page("Login", body)


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# =========================================================
# CREATE POST
# =========================================================

@app.route("/post", methods=["POST"])
@login_required
def create_post():

    content = request.form.get(
        "content",
        ""
    ).strip()

    if content:

        conn = get_db()

        conn.execute(
            """
            INSERT INTO posts
            (user_id, content)
            VALUES (?, ?)
            """,
            (
                session["user_id"],
                content
            )
        )

        conn.commit()
        conn.close()

    return redirect("/")


# =========================================================
# LIKE POST
# =========================================================

@app.route("/like/<int:post_id>")
@login_required
def like_post(post_id):

    conn = get_db()

    existing = conn.execute(
        """
        SELECT *
        FROM likes
        WHERE user_id = ?
        AND post_id = ?
        """,
        (
            session["user_id"],
            post_id
        )
    ).fetchone()

    if existing:

        conn.execute(
            """
            DELETE FROM likes
            WHERE user_id = ?
            AND post_id = ?
            """,
            (
                session["user_id"],
                post_id
            )
        )

    else:

        conn.execute(
            """
            INSERT OR IGNORE INTO likes
            (user_id, post_id)
            VALUES (?, ?)
            """,
            (
                session["user_id"],
                post_id
            )
        )

    conn.commit()
    conn.close()

    return redirect(request.referrer or "/")


# =========================================================
# VIEW POST
# =========================================================

@app.route("/post/<int:post_id>")
def view_post(post_id):

    conn = get_db()

    post = conn.execute(
        """
        SELECT
            posts.*,
            users.username
        FROM posts
        JOIN users
            ON posts.user_id = users.id
        WHERE posts.id = ?
        """,
        (post_id,)
    ).fetchone()

    if not post:

        conn.close()

        return page(
            "Not Found",
            """
            <div class="card">
                <h1>Post not found</h1>
                <a class="button" href="/">Go Home</a>
            </div>
            """
        ), 404

    comments = conn.execute(
        """
        SELECT
            comments.*,
            users.username
        FROM comments
        JOIN users
            ON comments.user_id = users.id
        WHERE comments.post_id = ?
        ORDER BY comments.created_at ASC
        """,
        (post_id,)
    ).fetchall()

    conn.close()

    comments_html = ""

    for comment in comments:

        comments_html += f"""
        <div class="card">

            <strong>@{comment["username"]}</strong>

            <p>{comment["content"]}</p>

            <div class="small">
                {comment["created_at"]}
            </div>

        </div>
        """

    if not comments_html:

        comments_html = """
        <p class="small">
            No comments yet.
        </p>
        """

    body = f"""

    <div class="post">

        <strong>@{post["username"]}</strong>

        <p>{post["content"]}</p>

        <div class="small">
            {post["created_at"]}
        </div>

        <br>

        <a class="button"
           href="/like/{post["id"]}">
           Like
        </a>

    </div>

    <h2>Comments</h2>

    {comments_html}

    """

    if session.get("user_id"):

        body += f"""

        <div class="card">

            <h3>Add a comment</h3>

            <form method="POST"
                  action="/comment/{post_id}">

                <textarea
                    name="content"
                    required
                    placeholder="Write a comment...">
                </textarea>

                <button
                    class="button"
                    type="submit">
                    Comment
                </button>

            </form>

        </div>

        """

    else:

        body += """

        <div class="card">

            <a href="/login">
                Login to comment
            </a>

        </div>

        """

    return page(
        "Post",
        body
    )


# =========================================================
# COMMENTS
# =========================================================

@app.route("/comment/<int:post_id>", methods=["POST"])
@login_required
def add_comment(post_id):

    content = request.form.get(
        "content",
        ""
    ).strip()

    if content:

        conn = get_db()

        conn.execute(
            """
            INSERT INTO comments
            (user_id, post_id, content)
            VALUES (?, ?, ?)
            """,
            (
                session["user_id"],
                post_id,
                content
            )
        )

        conn.commit()
        conn.close()

    return redirect(
        f"/post/{post_id}"
    )


# =========================================================
# FOLLOW USER
# =========================================================

@app.route("/follow/<int:user_id>")
@login_required
def follow_user(user_id):

    if user_id == session["user_id"]:
        return redirect("/")

    conn = get_db()

    conn.execute(
        """
        INSERT OR IGNORE INTO follows
        (follower_id, following_id)
        VALUES (?, ?)
        """,
        (
            session["user_id"],
            user_id
        )
    )

    conn.commit()
    conn.close()

    return redirect(request.referrer or "/")


# =========================================================
# UNFOLLOW USER
# =========================================================

@app.route("/unfollow/<int:user_id>")
@login_required
def unfollow_user(user_id):

    conn = get_db()

    conn.execute(
        """
        DELETE FROM follows
        WHERE follower_id = ?
        AND following_id = ?
        """,
        (
            session["user_id"],
            user_id
        )
    )

    conn.commit()
    conn.close()

    return redirect(request.referrer or "/")


# =========================================================
# API: CURRENT USER
# =========================================================

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
        "username": user["username"]
    })


# =========================================================
# API: VIDEOS
# =========================================================

@app.route("/api/videos")
def api_videos():

    category = request.args.get(
        "category",
        "For You"
    )

    if category not in VIDEO_CATEGORIES:
        category = "For You"

    videos = get_pexels_videos(
        VIDEO_CATEGORIES[category]
    )

    return jsonify({
        "category": category,
        "videos": videos
    })


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    return jsonify({
        "status": "ok",
        "service": "Heara",
        "message": "Heara is running"
    })


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(404)
def not_found(error):

    return page(
        "Not Found",
        """
        <div class="card">

            <h1>Page not found</h1>

            <p>
                The page you requested does not exist.
            </p>

            <a class="button" href="/">
                Go Home
            </a>

        </div>
        """
    ), 404


@app.errorhandler(500)
def server_error(error):

    return page(
        "Server Error",
        """
        <div class="card">

            <h1>Something went wrong</h1>

            <p>
                Heara encountered a server error.
                Please try again.
            </p>

            <a class="button" href="/">
                Go Home
            </a>

        </div>
        """
    ), 500


# =========================================================
# LOCAL DEVELOPMENT
# =========================================================

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
