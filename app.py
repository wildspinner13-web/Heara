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

DATABASE = "database.db"


# =========================================================
# DATABASE
# =========================================================

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

def get_pexels_videos(
    query,
    page=1,
    per_page=20
):

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

        with urllib.request.urlopen(
            req,
            timeout=20
        ) as response:

            data = json.loads(
                response.read().decode("utf-8")
            )

        videos = []

        for video in data.get("videos", []):

            files = video.get(
                "video_files",
                []
            )

            if not files:
                continue

            selected_file = None

            # Prefer HD MP4
            for file in files:

                if (
                    file.get("file_type") == "video/mp4"
                    and file.get("width", 0) >= 720
                ):
                    selected_file = file
                    break

            # Fallback to any MP4
            if selected_file is None:

                for file in files:

                    if file.get(
                        "file_type"
                    ) == "video/mp4":

                        selected_file = file
                        break

            if selected_file is None:
                continue

            videos.append({

                "id": video.get("id"),

                "url": selected_file.get(
                    "link"
                ),

                "thumbnail": video.get(
                    "image"
                ),

                "duration": video.get(
                    "duration",
                    0
                ),

                "width": selected_file.get(
                    "width",
                    0
                ),

                "height": selected_file.get(
                    "height",
                    0
                ),

                "user": video.get(
                    "user",
                    {}
                ).get(
                    "name",
                    "Pexels"
                )

            })

        return videos

    except urllib.error.HTTPError as e:

        print(
            "Pexels HTTP error:",
            e.code
        )

        return []

    except urllib.error.URLError as e:

        print(
            "Pexels connection error:",
            e
        )

        return []

    except Exception as e:

        print(
            "Pexels error:",
            e
        )

        return []


# =========================================================
# USER HELPERS
# =========================================================

def current_user():

    user_id = session.get("user_id")

    if not user_id:
        return None

    conn = get_db()

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    return user


def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            return redirect("/login")

        return function(
            *args,
            **kwargs
        )

    return wrapper


# =========================================================
# MAIN WEBSITE DESIGN
# =========================================================

def page(title, body):

    user = current_user()

    username = (
        user["username"]
        if user
        else None
    )

    if username:

        account_links = f"""
            <span class="welcome">
                Hi, {username}
            </span>

            <a href="/logout">
                Logout
            </a>
        """

    else:

        account_links = """
            <a href="/login">
                Login
            </a>

            <a href="/register">
                Register
            </a>
        """

    return f"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,
             initial-scale=1.0"
>

<title>{title} - Heara</title>


<style>

* {{
    box-sizing: border-box;
}}

html,
body {{
    margin: 0;
    padding: 0;

    min-height: 100%;

    font-family:
        Arial,
        Helvetica,
        sans-serif;

    color: white;
}}

body {{

    background:
        linear-gradient(
            rgba(0,0,0,.48),
            rgba(0,0,0,.65)
        ),
        url("/static/images/heara-hero.png");

    background-size: cover;

    background-position: center;

    background-attachment: fixed;

    background-repeat: no-repeat;

    background-color: #0f0f0f;
}}


/* NAVIGATION */

nav {{

    position: sticky;

    top: 0;

    z-index: 1000;

    background:
        rgba(10,10,20,.78);

    backdrop-filter:
        blur(15px);

    padding: 16px;

    display: flex;

    align-items: center;

    gap: 18px;

    border-bottom:
        1px solid
        rgba(255,255,255,.12);

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

    color: #bbb;

}}


/* CONTAINER */

.container {{

    width:
        min(1100px, 94%);

    margin: auto;

    padding: 30px 0;

}}


/* HERO */

.hero {{

    text-align: center;

    padding: 80px 20px;

}}

.hero h1 {{

    font-size: 55px;

    margin-bottom: 10px;

}}

.hero span {{

    color: #ff4f81;

}}

.hero p {{

    color: #ddd;

    font-size: 18px;

}}


/* BUTTON */

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


/* CARDS */

.card,
.post {{

    background:
        rgba(20,20,25,.82);

    backdrop-filter:
        blur(12px);

    border:
        1px solid
        rgba(255,255,255,.08);

    border-radius: 15px;

    padding: 20px;

    margin-bottom: 20px;

}}


/* FORMS */

input,
textarea {{

    width: 100%;

    padding: 13px;

    margin: 8px 0 15px;

    border-radius: 8px;

    border:
        1px solid #333;

    background:
        rgba(0,0,0,.65);

    color: white;

}}

textarea {{

    min-height: 100px;

}}


/* CATEGORY */

.category {{

    display: inline-block;

    background:
        rgba(37,37,37,.85);

    color: white;

    text-decoration: none;

    padding: 10px 15px;

    border-radius: 20px;

    margin: 5px;

}}

.category:hover {{

    background: #ff4f81;

}}


/* TEXT */

.small {{

    color: #aaa;

    font-size: 13px;

}}

.error {{

    background: #5b1b1b;

    padding: 15px;

    border-radius: 8px;

}}

.success {{

    background: #174d2a;

    padding: 15px;

    border-radius: 8px;

}}

footer {{

    text-align: center;

    padding: 40px;

    color: #aaa;

}}

</style>

</head>


<body>

<nav>

    <a href="/">
        Home
    </a>

    <a href="/videos">
        Videos
    </a>

    {account_links}

</nav>


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
# HOME
# =========================================================

@app.route("/")
def home():

    conn = get_db()

    posts = conn.execute(
        """
        SELECT
            posts.id,
            posts.content,
            posts.created_at,
            users.username,
            COUNT(likes.id)
            AS like_count

        FROM posts

        JOIN users
        ON posts.user_id = users.id

        LEFT JOIN likes
        ON posts.id = likes.post_id

        GROUP BY posts.id

        ORDER BY posts.created_at DESC

        LIMIT 30
        """
    ).fetchall()

    conn.close()

    post_html = ""

    for post in posts:

        post_html += f"""
        <div class="post">

            <strong>
                @{post["username"]}
            </strong>

            <p>
                {post["content"]}
            </p>

            <div class="small">

                {post["like_count"]}
                likes

                ·

                {post["created_at"]}

            </div>

            <br>

            <a
                class="button"
                href="/like/{post["id"]}"
            >
                Like
            </a>

            <a
                class="button"
                href="/post/{post["id"]}"
            >
                View
            </a>

        </div>
        """

    if not post_html:

        post_html = """
        <div class="card">

            <h2>
                No posts yet
            </h2>

            <p>
                Be the first person
                to post on Heara.
            </p>

        </div>
        """

    body = f"""

    <section class="hero">

        <h1>
            Welcome to
            <span>Heara</span>
        </h1>

        <p>
            Discover videos,
            share your thoughts,
            follow people and enjoy
            the community.
        </p>

        <a
            class="button"
            href="/videos"
        >
            Watch Videos
        </a>

        <a
            class="button"
            href="/register"
        >
            Join Heara
        </a>

    </section>


    <div class="card">

        <h2>
            Create a Post
        </h2>

        <form
            method="POST"
            action="/post"
        >

            <textarea
                name="content"
                placeholder="What's on your mind?"
                required
            ></textarea>

            <button
                class="button"
                type="submit"
            >
                Post
            </button>

        </form>

    </div>


    <h2>
        Latest Posts
    </h2>

    {post_html}

    """

    return page(
        "Home",
        body
    )


# =========================================================
# TIKTOK-STYLE VIDEOS
# =========================================================

@app.route("/videos")
def videos():

    category = request.args.get(
        "category",
        "For You"
    )

    if category not in VIDEO_CATEGORIES:
        category = "For You"

    videos = get_pexels_videos(
        VIDEO_CATEGORIES[category],
        page=1,
        per_page=20
    )

    categories_html = ""

    for name in VIDEO_CATEGORIES:

        active = (
            "active"
            if name == category
            else ""
        )

        categories_html += f"""
        <a
            class="video-category {active}"
            href="/videos?category={urllib.parse.quote(name)}"
        >
            {name}
        </a>
        """

    video_html = ""

    for index, video in enumerate(videos):

        video_html += f"""

        <section
            class="video-slide"
            data-index="{index}"
        >

            <video
                class="feed-video"
                playsinline
                muted
                loop
                preload="metadata"
                poster="{video["thumbnail"]}"
            >

                <source
                    src="{video["url"]}"
                    type="video/mp4"
                >

            </video>


            <div class="video-shade"></div>


            <div class="video-info">

                <div class="video-tag">
                    {category}
                </div>

                <h2>
                    @{video["user"]}
                </h2>

                <p>
                    Discover more videos
                    on Heara.
                </p>

            </div>


            <div class="video-buttons">

                <button
                    class="round-button"
                    onclick="likeVideo(this)"
                >
                    <span>♥</span>
                    <small>Like</small>
                </button>


                <button
                    class="round-button"
                    onclick="shareVideo()"
                >
                    <span>↗</span>
                    <small>Share</small>
                </button>

            </div>


            <div class="video-counter">

                {index + 1}
                /
                {len(videos)}

            </div>

        </section>

        """

    if not video_html:

        video_html = """

        <section class="empty-videos">

            <h1>
                No videos available
            </h1>

            <p>
                Make sure your
                PEXELS_API_KEY is configured
                in Render Environment Variables.
            </p>

        </section>

        """

    return f"""

<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,
             initial-scale=1.0,
             maximum-scale=1.0,
             user-scalable=no"
>

<title>
    Videos - Heara
</title>


<style>

* {{
    box-sizing: border-box;
}}


html,
body {{

    margin: 0;
    padding: 0;

    width: 100%;
    height: 100%;

    overflow: hidden;

    background: #000;

    color: white;

    font-family:
        Arial,
        Helvetica,
        sans-serif;

}}


/* =====================================================
   FULL SCREEN FEED
===================================================== */

.video-feed {{

    position: fixed;

    inset: 0;

    width: 100vw;

    height: 100vh;

    overflow-y: auto;

    overflow-x: hidden;

    scroll-snap-type:
        y mandatory;

    scroll-behavior:
        smooth;

    scrollbar-width: none;

    overscroll-behavior-y:
        contain;

    -webkit-overflow-scrolling:
        touch;

}}

.video-feed::-webkit-scrollbar {{

    display: none;

}}


/* =====================================================
   EACH VIDEO
===================================================== */

.video-slide {{

    position: relative;

    width: 100vw;

    height: 100vh;

    min-height: 100vh;

    overflow: hidden;

    scroll-snap-align:
        start;

    scroll-snap-stop:
        always;

    background: #000;

}}


/* =====================================================
   VIDEO ITSELF
===================================================== */

.feed-video {{

    position: absolute;

    inset: 0;

    width: 100%;

    height: 100%;

    object-fit: contain;

    background: #000;

    z-index: 1;

}}


/* =====================================================
   BACKGROUND IMAGE
===================================================== */

.video-slide::before {{

    content: "";

    position: absolute;

    inset: 0;

    background-image:
        url("/static/images/heara-hero.png");

    background-size:
        cover;

    background-position:
        center;

    opacity: .08;

    filter:
        blur(4px);

    transform:
        scale(1.08);

    z-index: 0;

}}


/* =====================================================
   VIDEO GRADIENT
===================================================== */

.video-shade {{

    position: absolute;

    inset: 0;

    z-index: 2;

    pointer-events: none;

    background:

        linear-gradient(
            to bottom,
            rgba(0,0,0,.70),
            transparent 22%,
            transparent 58%,
            rgba(0,0,0,.85)
        );

}}


/* =====================================================
   TOP BAR
===================================================== */

.video-top {{

    position: fixed;

    top: 0;

    left: 0;

    width: 100%;

    height: 65px;

    z-index: 100;

    display: flex;

    align-items: center;

    justify-content:
        space-between;

    padding:
        0 20px;

}}


.logo {{

    color: white;

    font-size: 25px;

    font-weight: 900;

    text-decoration: none;

    text-shadow:
        0 2px 8px black;

}}

.logo span {{

    color: #ff4f81;

}}


.home {{

    color: white;

    text-decoration: none;

    background:
        rgba(0,0,0,.50);

    padding:
        9px 17px;

    border-radius: 25px;

    backdrop-filter:
        blur(12px);

}}


/* =====================================================
   CATEGORY BAR
===================================================== */

.video-categories {{

    position: fixed;

    top: 65px;

    left: 0;

    width: 100%;

    z-index: 100;

    display: flex;

    gap: 8px;

    padding:
        8px 14px;

    overflow-x: auto;

    scrollbar-width: none;

}}

.video-categories::-webkit-scrollbar {{
    display: none;
}}


.video-category {{

    flex-shrink: 0;

    color: white;

    text-decoration: none;

    font-size: 13px;

    padding:
        8px 14px;

    border-radius: 22px;

    background:
        rgba(0,0,0,.48);

    border:
        1px solid
        rgba(255,255,255,.16);

    backdrop-filter:
        blur(12px);

}}


.video-category.active {{

    background:
        #ff4f81;

    border-color:
        #ff4f81;

}}


/* =====================================================
   VIDEO INFORMATION
===================================================== */

.video-info {{

    position: absolute;

    left: 22px;

    bottom: 40px;

    z-index: 10;

    max-width: 65%;

    text-shadow:
        0 2px 8px black;

}}


.video-info h2 {{

    margin:
        8px 0;

    font-size:
        21px;

}}


.video-info p {{

    margin: 0;

    color:
        rgba(255,255,255,.85);

    font-size:
        14px;

}}


.video-tag {{

    display:
        inline-block;

    padding:
        6px 12px;

    border-radius:
        20px;

    background:
        rgba(255,79,129,.9);

    font-size:
        12px;

}}


/* =====================================================
   RIGHT BUTTONS
===================================================== */

.video-buttons {{

    position: absolute;

    right: 18px;

    bottom: 75px;

    z-index: 20;

    display: flex;

    flex-direction: column;

    gap: 18px;

}}


.round-button {{

    width: 58px;

    height: 58px;

    border: none;

    border-radius: 50%;

    color: white;

    background:
        rgba(0,0,0,.50);

    backdrop-filter:
        blur(12px);

    cursor: pointer;

    display: flex;

    flex-direction: column;

    align-items: center;

    justify-content: center;

}}


.round-button span {{

    font-size: 22px;

}}


.round-button small {{

    font-size: 9px;

}}


.round-button:hover {{

    background:
        rgba(255,79,129,.8);

    transform:
        scale(1.08);

}}


/* =====================================================
   COUNTER
===================================================== */

.video-counter {{

    position: absolute;

    right: 20px;

    bottom: 25px;

    z-index: 20;

    color:
        rgba(255,255,255,.65);

    font-size: 12px;

}}


/* =====================================================
   EMPTY
===================================================== */

.empty-videos {{

    height: 100vh;

    display: flex;

    flex-direction: column;

    justify-content: center;

    align-items: center;

    text-align: center;

    padding: 30px;

}}


/* =====================================================
   MOBILE
===================================================== */

@media (max-width: 600px) {{

    .video-info {{

        left: 15px;

        bottom: 35px;

        max-width: 72%;

    }}

    .video-buttons {{

        right: 10px;

        bottom: 70px;

    }}

    .round-button {{

        width: 52px;

        height: 52px;

    }}

}}


</style>

</head>


<body>


<!-- TOP BAR -->

<div class="video-top">

    <a
        class="logo"
        href="/"
    >
        He<span>a</span>ra
    </a>


    <a
        class="home"
        href="/"
    >
        Home
    </a>

</div>


<!-- CATEGORIES -->

<div class="video-categories">

    {categories_html}

</div>


<!-- FEED -->

<main
    class="video-feed"
    id="videoFeed"
>

    {video_html}

</main>


<script>

/* =====================================================
   GET ALL VIDEOS
===================================================== */

const videos =
    document.querySelectorAll(
        ".feed-video"
    );


/* =====================================================
   PLAY ONLY THE VIDEO ON SCREEN
===================================================== */

const observer =
    new IntersectionObserver(

        function(entries) {{

            entries.forEach(
                function(entry) {{

                    const video =
                        entry.target;


                    if (
                        entry.isIntersecting
                        &&
                        entry.intersectionRatio >= .65
                    ) {{

                        videos.forEach(
                            function(other) {{

                                if (
                                    other !== video
                                ) {{

                                    other.pause();

                                }}

                            }}
                        );


                        video.play()
                            .catch(
                                function() {{

                                    console.log(
                                        "Video waiting for interaction"
                                    );

                                }}
                            );

                    }}

                    else {{

                        video.pause();

                    }}

                }}
            );

        }},

        {{
            threshold: .65
        }}

    );


videos.forEach(
    function(video) {{

        observer.observe(
            video
        );

    }}
);


/* =====================================================
   START FIRST VIDEO
===================================================== */

if (videos.length > 0) {{

    videos[0]
        .play()
        .catch(
            function() {{}}
        );

}}


/* =====================================================
   LIKE
===================================================== */

function likeVideo(button) {{

    const heart =
        button.querySelector(
            "span"
        );


    if (
        heart.style.color ===
        "rgb(255, 79, 129)"
    ) {{

        heart.style.color =
            "white";

    }}

    else {{

        heart.style.color =
            "rgb(255, 79, 129)";

    }}

}}


/* =====================================================
   SHARE
===================================================== */

function shareVideo() {{

    if (
        navigator.share
    ) {{

        navigator.share({{

            title:
                "Heara",

            text:
                "Check out this video on Heara.",

            url:
                window.location.href

        }});

    }}

    else if (
        navigator.clipboard
    ) {{

        navigator.clipboard
            .writeText(
                window.location.href
            );

        alert(
            "Video link copied!"
        );

    }}

}}


/* =====================================================
   DESKTOP MOUSE WHEEL
===================================================== */

let wheelLocked = false;


document
    .getElementById(
        "videoFeed"
    )
    .addEventListener(
        "wheel",
        function(event) {{

            if (wheelLocked) {{

                event.preventDefault();

                return;

            }}


            if (
                Math.abs(
                    event.deltaY
                ) < 20
            ) {{

                return;

            }}


            event.preventDefault();

            wheelLocked = true;


            const slides =
                document.querySelectorAll(
                    ".video-slide"
                );


            const current =
                Math.round(
                    this.scrollTop /
                    window.innerHeight
                );


            let next =
                current;


            if (
                event.deltaY > 0
            ) {{

                next =
                    Math.min(
                        current + 1,
                        slides.length - 1
                    );

            }}

            else {{

                next =
                    Math.max(
                        current - 1,
                        0
                    );

            }}


            if (
                slides[next]
            ) {{

                slides[next]
                    .scrollIntoView({{
                        behavior:
                            "smooth"
                    }});

            }}


            setTimeout(
                function() {{

                    wheelLocked =
                        false;

                }},
                700
            );

        }},
        {{
            passive: false
        }}
    );


/* =====================================================
   KEYBOARD CONTROLS
===================================================== */

document.addEventListener(
    "keydown",
    function(event) {{

        const slides =
            document.querySelectorAll(
                ".video-slide"
            );


        const current =
            Math.round(
                document.getElementById(
                    "videoFeed"
                ).scrollTop /
                window.innerHeight
            );


        if (
            event.key ===
            "ArrowDown"
        ) {{

            const next =
                Math.min(
                    current + 1,
                    slides.length - 1
                );

            slides[next]
                .scrollIntoView({{
                    behavior:
                        "smooth"
                }});

        }}


        if (
            event.key ===
            "ArrowUp"
        ) {{

            const previous =
                Math.max(
                    current - 1,
                    0
                );

            slides[previous]
                .scrollIntoView({{
                    behavior:
                        "smooth"
                }});

        }}

    }}
);

</script>


</body>

</html>

"""


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
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

            error = (
                "Please enter a "
                "username and password."
            )

        elif len(username) < 3:

            error = (
                "Username must be "
                "at least 3 characters."
            )

        elif len(password) < 4:

            error = (
                "Password must be "
                "at least 4 characters."
            )

        else:

            conn = get_db()

            try:

                cursor = conn.execute(
                    """
                    INSERT INTO users
                    (username, password)
                    VALUES (?, ?)
                    """,
                    (
                        username,
                        password
                    )
                )

                conn.commit()

                session["user_id"] = (
                    cursor.lastrowid
                )

                conn.close()

                return redirect("/")

            except sqlite3.IntegrityError:

                conn.close()

                error = (
                    "That username "
                    "already exists."
                )


    body = f"""

    <div class="card">

        <h1>
            Create your Heara account
        </h1>

        {
            f'<div class="error">{error}</div>'
            if error
            else ''
        }

        <form method="POST">

            <label>
                Username
            </label>

            <input
                type="text"
                name="username"
                required
            >

            <label>
                Password
            </label>

            <input
                type="password"
                name="password"
                required
            >

            <button
                class="button"
                type="submit"
            >
                Register
            </button>

        </form>

    </div>

    """

    return page(
        "Register",
        body
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
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
            (
                username,
                password
            )
        ).fetchone()

        conn.close()

        if user:

            session["user_id"] = (
                user["id"]
            )

            return redirect("/")

        error = (
            "Incorrect username "
            "or password."
        )


    body = f"""

    <div class="card">

        <h1>
            Login
        </h1>

        {
            f'<div class="error">{error}</div>'
            if error
            else ''
        }

        <form method="POST">

            <label>
                Username
            </label>

            <input
                type="text"
                name="username"
                required
            >

            <label>
                Password
            </label>

            <input
                type="password"
                name="password"
                required
            >

            <button
                class="button"
                type="submit"
            >
                Login
            </button>

        </form>

        <p>
            Don't have an account?

            <a href="/register">
                Register
            </a>
        </p>

    </div>

    """

    return page(
        "Login",
        body
    )


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

@app.route(
    "/post",
    methods=["POST"]
)
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

@app.route(
    "/like/<int:post_id>"
)
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
            INSERT OR IGNORE
            INTO likes
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

    return redirect(
        request.referrer or "/"
    )


# =========================================================
# VIEW POST
# =========================================================

@app.route(
    "/post/<int:post_id>"
)
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

                <h1>
                    Post not found
                </h1>

                <a
                    class="button"
                    href="/"
                >
                    Go Home
                </a>

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
        ON comments.user_id =
           users.id

        WHERE comments.post_id = ?

        ORDER BY
            comments.created_at ASC
        """,
        (post_id,)
    ).fetchall()

    conn.close()

    comments_html = ""

    for comment in comments:

        comments_html += f"""

        <div class="card">

            <strong>
                @{comment["username"]}
            </strong>

            <p>
                {comment["content"]}
            </p>

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

        <strong>
            @{post["username"]}
        </strong>

        <p>
            {post["content"]}
        </p>

        <div class="small">
            {post["created_at"]}
        </div>

        <br>

        <a
            class="button"
            href="/like/{post["id"]}"
        >
            Like
        </a>

    </div>


    <h2>
        Comments
    </h2>

    {comments_html}

    """

    if session.get("user_id"):

        body += f"""

        <div class="card">

            <h3>
                Add a comment
            </h3>

            <form
                method="POST"
                action="/comment/{post_id}"
            >

                <textarea
                    name="content"
                    required
                    placeholder="Write a comment..."
                ></textarea>

                <button
                    class="button"
                    type="submit"
                >
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

@app.route(
    "/comment/<int:post_id>",
    methods=["POST"]
)
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
# FOLLOW
# =========================================================

@app.route(
    "/follow/<int:user_id>"
)
@login_required
def follow_user(user_id):

    if user_id == session["user_id"]:
        return redirect("/")

    conn = get_db()

    conn.execute(
        """
        INSERT OR IGNORE
        INTO follows
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

    return redirect(
        request.referrer or "/"
    )


# =========================================================
# UNFOLLOW
# =========================================================

@app.route(
    "/unfollow/<int:user_id>"
)
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

    return redirect(
        request.referrer or "/"
    )


# =========================================================
# API CURRENT USER
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

        "id":
            user["id"],

        "username":
            user["username"]

    })


# =========================================================
# API VIDEOS
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

        "category":
            category,

        "videos":
            videos

    })


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    return jsonify({

        "status":
            "ok",

        "service":
            "Heara",

        "message":
            "Heara is running"

    })


# =========================================================
# 404
# =========================================================

@app.errorhandler(404)
def not_found(error):

    return page(
        "Not Found",
        """
        <div class="card">

            <h1>
                Page not found
            </h1>

            <p>
                The page you requested
                does not exist.
            </p>

            <a
                class="button"
                href="/"
            >
                Go Home
            </a>

        </div>
        """
    ), 404


# =========================================================
# 500
# =========================================================

@app.errorhandler(500)
def server_error(error):

    return page(
        "Server Error",
        """
        <div class="card">

            <h1>
                Something went wrong
            </h1>

            <p>
                Heara encountered
                a server error.
            </p>

            <a
                class="button"
                href="/"
            >
                Go Home
            </a>

        </div>
        """
    ), 500


# =========================================================
# START
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
