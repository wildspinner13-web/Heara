document.addEventListener("DOMContentLoaded", function () {

    /*
        HEARA LANDING PAGE
        -------------------
        Mouse movement gives the hero image
        and floating cards a subtle 3D effect.
    */

    const visual = document.querySelector(".hero-visual");
    const image = document.querySelector(".hero-image");

    if (visual && image) {

        visual.addEventListener("mousemove", function (event) {

            const rect = visual.getBoundingClientRect();

            const x = event.clientX - rect.left;
            const y = event.clientY - rect.top;

            const centerX = rect.width / 2;
            const centerY = rect.height / 2;

            const rotateY = (x - centerX) / 45;
            const rotateX = (centerY - y) / 45;

            image.style.transform =
                `perspective(1200px)
                 rotateX(${rotateX}deg)
                 rotateY(${rotateY}deg)
                 scale(1.02)`;

        });

        visual.addEventListener("mouseleave", function () {

            image.style.transform =
                "perspective(1200px) rotateY(-7deg) rotateX(3deg)";

        });
    }


    /*
        Smooth scroll for Explore Heara
    */

    document.querySelectorAll('a[href^="#"]').forEach(function (link) {

        link.addEventListener("click", function (event) {

            const targetId = this.getAttribute("href");

            if (targetId === "#") {
                return;
            }

            const target = document.querySelector(targetId);

            if (target) {

                event.preventDefault();

                target.scrollIntoView({
                    behavior: "smooth"
                });

            }

        });

    });


    /*
        Button press animation
    */

    const buttons = document.querySelectorAll(".primary-button");

    buttons.forEach(function (button) {

        button.addEventListener("mousedown", function () {
            button.style.transform = "scale(.96)";
        });

        button.addEventListener("mouseup", function () {
            button.style.transform = "";
        });

        button.addEventListener("mouseleave", function () {
            button.style.transform = "";
        });

    });

});