from flask import Flask, render_template, request, redirect, session
import sqlite3
import os
import urllib.request
import urllib.error
import urllib.parse

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "heara-development-key")

DATABASE = "database.db"

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
    "Lifestyle": "lifestyle people fashion daily life",
    "Motivation": "motivation success people inspirational",
    "Entertainment": "entertainment actor performer people"
}


def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = get_db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            UNIQUE(user_id, post_id)
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS follows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            follower_id INTEGER NOT NULL,
            following_id INTEGER NOT NULL,
            UNIQUE(follower_id, following_id)
        )
    """)

    connection.commit()
    connection.close()


def get_pexels_videos(query, page=1, per_page=20):
    api_key = os.environ.get("PEXELS_API_KEY")

    if not api_key:
        return []

    encoded_query = urllib.parse.quote(query)

    url = (
        "https://api.pexels.com/v1/videos/search"
        f"?query={encoded_query}"
        f"&page={page}"
        f"&per_page={per_page}"
        "&orientation=portrait"
    )

    request_object = urllib.request.Request(
        url,
        headers={
            "Authorization": api_key
        }
    )

    try:
        with urllib.request.urlopen(request_object, timeout=15) as response:
            data = response.read().decode("utf-8")

        import json
        data = json.loads(data)

        videos = []

        for video in data.get("videos", []):
            files = video.get("video_files", [])

            portrait_file = None

            for video_file in files:
                width = video_file.get("width") or 0
                height = video_file.get("height") or 0

                if height > width:
                    portrait_file = video_file
                    break

            if not portrait_file and files:
                portrait_file = files[0]

            if not portrait_file:
                continue

            user = video.get("user", {})

            videos.append({
                "id": video.get("id"),
                "url": portrait_file.get("link"),
                "thumbnail": video.get("image"),
                "width": portrait_file.get("width"),
                "height": portrait_file.get("height"),
                "duration": video.get("duration"),
                "creator": user.get("name", "Pexels Creator"),
                "creator_url": user.get("url", ""),
                "source_url": video.get("url", "")
            })

        return videos

    except urllib.error.HTTPError as error:
        print("Pexels HTTP error:", error.code)
        return []

    except urllib.error.URLError as error:
        print("Pexels connection error:", error)
        return []

    except Exception as error:
        print("Pexels error:", error)
        return []


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]

        if not username or not email or not password:
            return "Please complete all fields."

        try:
            connection = get_db()

            connection.execute(
                """
                INSERT INTO users (username, email, password)
                VALUES (?, ?, ?)
                """,
                (username, email, password)
            )

            connection.commit()
            connection.close()

            return redirect("/login")

        except sqlite3.IntegrityError:
            return "Username or email already exists."

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        connection = get_db()

        user = connection.execute(
            """
            SELECT id, username
            FROM users
            WHERE username = ? AND password = ?
            """,
            (username, password)
        ).fetchone()

        connection.close()

        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect("/home")

        return "Incorrect username or password."

    return render_template("login.html")


@app.route("/home")
def user_home():
    if "user_id" not in session:
        return redirect("/login")

    connection = get_db()

    posts = connection.execute("""
        SELECT
            posts.id,
            posts.user_id,
            posts.content,
            posts.created_at,
            users.username,
            COUNT(DISTINCT likes.id) AS like_count
        FROM posts
        JOIN users ON posts.user_id = users.id
        LEFT JOIN likes ON posts.id = likes.post_id
        GROUP BY posts.id
        ORDER BY posts.id DESC
    """).fetchall()

    comments = connection.execute("""
        SELECT
            comments.post_id,
            comments.content,
            comments.created_at,
            users.username
        FROM comments
        JOIN users ON comments.user_id = users.id
        ORDER BY comments.id ASC
    """).fetchall()

    users = connection.execute("""
        SELECT id, username
        FROM users
        WHERE id != ?
        ORDER BY username
    """, (session["user_id"],)).fetchall()

    following = connection.execute("""
        SELECT following_id
        FROM follows
        WHERE follower_id = ?
    """, (session["user_id"],)).fetchall()

    following_ids = [row["following_id"] for row in following]

    connection.close()

    return render_template(
        "home.html",
        username=session["username"],
        posts=posts,
        comments=comments,
        users=users,
        following_ids=following_ids
    )


@app.route("/create-post", methods=["POST"])
def create_post():
    if "user_id" not in session:
        return redirect("/login")

    content = request.form["content"].strip()

    if content:
        connection = get_db()

        connection.execute(
            """
            INSERT INTO posts (user_id, content)
            VALUES (?, ?)
            """,
            (session["user_id"], content)
        )

        connection.commit()
        connection.close()

    return redirect("/home")


@app.route("/like/<int:post_id>", methods=["POST"])
def like_post(post_id):
    if "user_id" not in session:
        return redirect("/login")

    connection = get_db()

    existing = connection.execute(
        """
        SELECT id
        FROM likes
        WHERE user_id = ? AND post_id = ?
        """,
        (session["user_id"], post_id)
    ).fetchone()

    if existing:
        connection.execute(
            "DELETE FROM likes WHERE id = ?",
            (existing["id"],)
        )
    else:
        connection.execute(
            """
            INSERT INTO likes (user_id, post_id)
            VALUES (?, ?)
            """,
            (session["user_id"], post_id)
        )

    connection.commit()
    connection.close()

    return redirect("/home")


@app.route("/comment/<int:post_id>", methods=["POST"])
def comment(post_id):
    if "user_id" not in session:
        return redirect("/login")

    content = request.form["content"].strip()

    if content:
        connection = get_db()

        connection.execute(
            """
            INSERT INTO comments
            (user_id, post_id, content)
            VALUES (?, ?, ?)
            """,
            (session["user_id"], post_id, content)
        )

        connection.commit()
        connection.close()

    return redirect("/home")


@app.route("/follow/<int:user_id>", methods=["POST"])
def follow(user_id):
    if "user_id" not in session:
        return redirect("/login")

    if user_id == session["user_id"]:
        return redirect("/home")

    connection = get_db()

    existing = connection.execute(
        """
        SELECT id
        FROM follows
        WHERE follower_id = ? AND following_id = ?
        """,
        (session["user_id"], user_id)
    ).fetchone()

    if existing:
        connection.execute(
            "DELETE FROM follows WHERE id = ?",
            (existing["id"],)
        )
    else:
        connection.execute(
            """
            INSERT INTO follows (follower_id, following_id)
            VALUES (?, ?)
            """,
            (session["user_id"], user_id)
        )

    connection.commit()
    connection.close()

    return redirect("/home")


@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect("/login")

    connection = get_db()

    user = connection.execute(
        """
        SELECT id, username, email
        FROM users
        WHERE id = ?
        """,
        (session["user_id"],)
    ).fetchone()

    post_count = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM posts
        WHERE user_id = ?
        """,
        (session["user_id"],)
    ).fetchone()["count"]

    follower_count = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM follows
        WHERE following_id = ?
        """,
        (session["user_id"],)
    ).fetchone()["count"]

    following_count = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM follows
        WHERE follower_id = ?
        """,
        (session["user_id"],)
    ).fetchone()["count"]

    connection.close()

    return render_template(
        "profile.html",
        user=user,
        post_count=post_count,
        follower_count=follower_count,
        following_count=following_count
    )


@app.route("/videos")
def videos():
    if "user_id" not in session:
        return redirect("/login")

    category = request.args.get("category", "For You")
    search_query = request.args.get("q", "").strip()

    if search_query:
        query = search_query
    else:
        query = VIDEO_CATEGORIES.get(
            category,
            VIDEO_CATEGORIES["For You"]
        )

    video_list = get_pexels_videos(query)

    return render_template(
        "videos.html",
        videos=video_list,
        categories=VIDEO_CATEGORIES.keys(),
        current_category=category,
        search_query=search_query
    )


@app.route("/discover")
def discover():
    if "user_id" not in session:
        return redirect("/login")

    connection = get_db()

    users = connection.execute("""
        SELECT id, username
        FROM users
        WHERE id != ?
        ORDER BY username
    """, (session["user_id"],)).fetchall()

    connection.close()

    return render_template(
        "home.html",
        username=session["username"],
        posts=[],
        comments=[],
        users=users,
        following_ids=[]
    )


@app.route("/messages")
def messages():
    if "user_id" not in session:
        return redirect("/login")

    return "Messaging system coming soon."


@app.route("/notifications")
def notifications():
    if "user_id" not in session:
        return redirect("/login")

    return "Notifications system coming soon."


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# IMPORTANT FOR RENDER:
# Initialize the database when Gunicorn starts the application.
init_db()


if __name__ == "__main__":
    app.run(debug=True)
