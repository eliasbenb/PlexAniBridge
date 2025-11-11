(function () {
    "use strict";

    const SALT_ROUNDS = 12;
    const READY_DATA_FLAG = "htpasswdReady";

    const resolveBcrypt = () => {
        if (window.bcrypt) {
            return window.bcrypt;
        }
        if (window.dcodeIO && window.dcodeIO.bcrypt) {
            return window.dcodeIO.bcrypt;
        }
        return null;
    };

    // Apache's htpasswd expects $2y$ prefixes even though bcrypt.js outputs $2a$/$2b$.
    const transformApachePrefix = (hash) => {
        if (hash.startsWith("$2a$") || hash.startsWith("$2b$")) {
            return "$2y$" + hash.slice(4);
        }
        return hash;
    };

    const generateHash = (bcrypt, password) =>
        new Promise((resolve, reject) => {
            bcrypt.genSalt(SALT_ROUNDS, (saltErr, salt) => {
                if (saltErr) {
                    reject(saltErr);
                    return;
                }
                bcrypt.hash(password, salt, (hashErr, encoded) => {
                    if (hashErr) {
                        reject(hashErr);
                        return;
                    }
                    resolve(transformApachePrefix(encoded));
                });
            });
        });

    const initGenerator = (root, bcrypt) => {
        if (root.dataset[READY_DATA_FLAG] === "true") {
            return;
        }
        root.dataset[READY_DATA_FLAG] = "true";

        const form = root.querySelector("form");
        const usernameInput = root.querySelector("[data-htpasswd-username]");
        const passwordInput = root.querySelector("[data-htpasswd-password]");
        const output = root.querySelector("[data-htpasswd-output]");
        const copyButton = root.querySelector("[data-htpasswd-copy]");
        const feedback = root.querySelector("[data-htpasswd-feedback]");
        const submitButton = form
            ? form.querySelector("button[type=submit]")
            : null;

        if (
            !form ||
            !usernameInput ||
            !passwordInput ||
            !output ||
            !copyButton
        ) {
            console.warn(
                "htpasswd generator is missing required elements",
                root,
            );
            return;
        }

        const setFeedback = (message, isError = false) => {
            if (!feedback) {
                return;
            }
            if (!message) {
                feedback.textContent = "";
                delete feedback.dataset.state;
                return;
            }
            feedback.textContent = message;
            feedback.dataset.state = isError ? "error" : "success";
        };

        const toggleWorking = (working) => {
            const controls = [
                usernameInput,
                passwordInput,
                submitButton,
                copyButton,
            ].filter(Boolean);
            controls.forEach((control) => {
                control.disabled = working;
                if (working) {
                    control.setAttribute("aria-busy", "true");
                } else {
                    control.removeAttribute("aria-busy");
                }
            });
        };

        copyButton.disabled = true;

        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const username = usernameInput.value.trim();
            const password = passwordInput.value;
            setFeedback("");
            output.value = "";
            copyButton.disabled = true;

            if (!username || !password) {
                setFeedback("Username and password are required.", true);
                return;
            }

            toggleWorking(true);
            try {
                const hash = await generateHash(bcrypt, password);
                output.value = `${username}:${hash}`;
                copyButton.disabled = false;
                setFeedback("Generated bcrypt htpasswd entry.");
                output.focus();
                output.select();
            } catch (error) {
                console.error("Failed to generate htpasswd entry", error);
                setFeedback(
                    "Failed to generate entry. Please try again.",
                    true,
                );
            } finally {
                toggleWorking(false);
                copyButton.disabled = output.value.trim().length === 0;
            }
        });

        copyButton.addEventListener("click", async (event) => {
            event.preventDefault();
            const value = output.value.trim();
            if (!value) {
                setFeedback("No entry to copy yet.", true);
                return;
            }

            const copyToClipboard = async () => {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    await navigator.clipboard.writeText(value);
                    return true;
                }
                output.focus();
                output.select();
                const successful = document.execCommand
                    ? document.execCommand("copy")
                    : false;
                return successful;
            };

            try {
                const success = await copyToClipboard();
                setFeedback(
                    success ? "Copied to clipboard." : "Copy failed.",
                    !success,
                );
            } catch (error) {
                console.error("Clipboard copy failed", error);
                setFeedback("Copy failed.", true);
            }
        });
    };

    const bootstrap = () => {
        const bcrypt = resolveBcrypt();
        if (!bcrypt) {
            console.warn(
                "bcrypt.js is not available; htpasswd generator disabled.",
            );
            return;
        }

        document
            .querySelectorAll("[data-htpasswd-generator]")
            .forEach((root) => {
                initGenerator(root, bcrypt);
            });
    };

    if (window.document$ && window.document$.subscribe) {
        window.document$.subscribe(() => bootstrap());
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bootstrap);
    } else {
        bootstrap();
    }
})();
