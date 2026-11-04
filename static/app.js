const $ = s => document.querySelector(s);
const preview = $("#preview");
let user = null, project = null, captions = [], mode = "login";
let activeCaptionRef = null;
let selectedKeywordIndex = 0;

const STOP_WORDS_SET = new Set([
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "to", "of", "in", "on", "for",
    "with", "that", "this", "it", "i", "you", "we", "they", "he", "she", "my", "your", "our", "their",
    "at", "as", "be", "do", "does", "did", "have", "has", "had", "will", "would", "can", "could",
    "should", "so", "if", "by", "from", "up", "about", "into", "over", "after", "not", "no", "yes",
    "just", "now", "then", "there", "here", "what", "who", "whom", "how", "when", "where", "why",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "than", "too",
    "very", "me", "him", "her", "us", "them", "its", "mine", "yours", "his", "hers", "ours", "theirs",
    "don't", "dont", "gonna", "wanna", "gotta", "yeah", "ok", "okay", "oh"
]);

async function request(url, body, method = "POST") {
    const options = { method };
    if (body) options.body = body;
    const r = await fetch(url, options);
    const d = await r.json().catch(() => ({ detail: "Unexpected response" }));
    if (!r.ok) throw Error(d.detail || "Request failed");
    return d;
}

function auth(kind = "login") {
    mode = kind;
    $("#auth").showModal();
    $("#name-row").hidden = kind === "login";
    $("#auth-submit").textContent = kind === "login" ? "Sign in" : "Create account";
    document.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("active", b.dataset.mode === kind));
}

async function refresh() {
    try {
        const d = await request("/api/auth/me", null, "GET");
        user = d.user;
    } catch {
        user = null;
    }
    $("#profile").hidden = !user;
    $("#sign-in").hidden = !!user;
    $("#create-account").hidden = !!user;
    if ($("#nav-sign-in")) $("#nav-sign-in").hidden = !!user;
    if ($("#nav-create-account")) $("#nav-create-account").hidden = !!user;
    $("#upload-form").hidden = !user;
    const gate = $("#auth-gate");
    if (gate) gate.style.display = user ? "none" : "flex";
    if (user) {
        $("#profile-name").textContent = user.name;
        $("#verified-by").textContent = user.verified_by || "Email code";
        $("#login-state").hidden = true;
    } else {
        $("#login-state").hidden = false;
        $("#login-state").textContent = "Sign in to save";
    }
}

function buildBoxes() {
    const box = $("#code-boxes");
    box.innerHTML = "";
    for (let i = 0; i < 6; i++) {
        const input = document.createElement("input");
        input.maxLength = 1;
        input.inputMode = "numeric";
        input.oninput = () => input.value && box.children[i + 1]?.focus();
        input.onpaste = e => {
            e.preventDefault();
            [...e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6)].forEach((x, n) => {
                if (box.children[n]) box.children[n].value = x;
            });
            box.children[Math.min(5, box.children.length - 1)]?.focus();
        };
        box.append(input);
    }
}

function active() {
    const t = preview.currentTime;
    if (!captions || captions.length === 0) return null;

    // 1. Exact match with smooth 0.15s boundary padding
    let c = captions.find(x => t >= Number(x.start) - 0.15 && t <= Number(x.end) + 0.15);
    if (c) return c;

    if (preview.paused) {
        // 2. When paused, viewers pause right after hearing a word or phrase.
        // Keep the most recent caption visible within 2.5s after it ends
        const recent = captions.filter(x => Number(x.end) <= t && (t - Number(x.end)) <= 2.5);
        if (recent.length > 0) {
            return recent[recent.length - 1];
        }
        // 3. Or if paused just before a caption begins (within 0.8s)
        const upcoming = captions.find(x => Number(x.start) >= t && (Number(x.start) - t) <= 0.8);
        if (upcoming) return upcoming;
    }
    return null;
}

function getCaptionKeywords(c) {
    if (c.keywords && Array.isArray(c.keywords) && c.keywords.length > 0) {
        return c.keywords;
    }
    const words = (c.text || "").match(/[A-Za-z']+/g) || [];
    const keyWords = words.filter(w => !STOP_WORDS_SET.has(w.toLowerCase()) && w.length > 1);
    const seen = new Set();
    const result = [];
    for (const w of keyWords) {
        const clean = w.replace(/'s$/i, "").replace(/^'+|'+$/g, "");
        const display = clean ? clean.charAt(0).toUpperCase() + clean.slice(1) : w;
        if (seen.has(display.toLowerCase())) continue;
        seen.add(display.toLowerCase());
        result.push({
            word: display,
            term: `Meaning — ${display}`,
            meaning: `1. Word: ${display}.\n2. Context: Spoken in video dialogue.\n3. Main idea: ${c.text}.\n4. You can edit this meaning card in the timeline.`
        });
        if (result.length >= 6) break;
    }
    return result;
}

function renderKeywordChips(c, keywords) {
    const selectorEl = $("#keywords-selector");
    const chipsEl = $("#keywords-chips");
    if (!keywords || keywords.length <= 1) {
        selectorEl.hidden = true;
        chipsEl.innerHTML = "";
        return;
    }
    selectorEl.hidden = false;
    chipsEl.innerHTML = "";
    keywords.forEach((kw, idx) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `keyword-chip ${idx === selectedKeywordIndex ? "active" : ""}`;
        btn.textContent = kw.word || `Word ${idx + 1}`;
        btn.onclick = () => {
            selectedKeywordIndex = idx;
            document.querySelectorAll(".keyword-chip").forEach((b, i) => b.classList.toggle("active", i === idx));
            c.term = kw.term || `Meaning — ${kw.word}`;
            c.meaning = kw.meaning || "";
            updateCardDisplay(c);
            render();
        };
        chipsEl.appendChild(btn);
    });
}

function updateCardDisplay(c) {
    const raw = c?.term || "";
    let type = "Meaning", word = raw || "Pause on a caption";
    if (/^Proper Name\s*[—–-]\s*/i.test(raw)) {
        type = "Proper Name";
        word = raw.replace(/^Proper Name\s*[—–-]\s*/i, "");
    } else if (/^Phrasal Verb\s*[—–-]\s*/i.test(raw)) {
        type = "Phrasal Verb";
        word = raw.replace(/^Phrasal Verb\s*[—–-]\s*/i, "");
    } else if (/^Idiom\s*[—–-]\s*/i.test(raw)) {
        type = "Idiom";
        word = raw.replace(/^Idiom\s*[—–-]\s*/i, "");
    } else if (/^Acronym\s*[—–-]\s*/i.test(raw)) {
        type = "Acronym";
        word = raw.replace(/^Acronym\s*[—–-]\s*/i, "");
    } else if (/^Technical Term\s*[—–-]\s*/i.test(raw)) {
        type = "Technical Term";
        word = raw.replace(/^Technical Term\s*[—–-]\s*/i, "");
    } else if (/^Expression\s*[—–-]\s*/i.test(raw)) {
        type = "Expression";
        word = raw.replace(/^Expression\s*[—–-]\s*/i, "");
    } else if (/^Meaning\s*[—–-]\s*/i.test(raw)) {
        type = "Meaning";
        word = raw.replace(/^Meaning\s*[—–-]\s*/i, "");
    }
    const cardTypeEl = $("#card-type");
    if (cardTypeEl) {
        cardTypeEl.textContent = type;
        cardTypeEl.className = "card-badge card-badge-" + type.toLowerCase().replace(/[^a-z0-9]+/g, "-");
    }
    $("#card-word").textContent = word;
    $("#card-text").textContent = c?.meaning || "A short explanation appears here when the video is paused.";
    $("#safety-flag").hidden = !c?.inappropriate;
}

function sync() {
    const c = active();
    const sub = $("#subtitle");

    if (!c) {
        sub.hidden = true;
        sub.textContent = "";
        $("#card-word").textContent = "Pause on a caption";
        $("#card-type").textContent = "Meaning";
        $("#card-text").textContent = "A short explanation appears here when the video is paused.";
        $("#safety-flag").hidden = true;
        $("#caption-active").textContent = "Caption — active";
        $("#keywords-selector").hidden = true;
        activeCaptionRef = null;
    } else {
        // Plain subtitle text without keyword highlighting as requested
        sub.hidden = false;
        sub.textContent = c.text || "";

        if (activeCaptionRef !== c) {
            activeCaptionRef = c;
            selectedKeywordIndex = 0;
            const keywords = getCaptionKeywords(c);
            renderKeywordChips(c, keywords);
            if (keywords.length > 0 && !c.meaning) {
                c.term = keywords[0].term;
                c.meaning = keywords[0].meaning;
            }
        }

        updateCardDisplay(c);
        const idx = captions.indexOf(c);
        $("#caption-active").textContent = idx >= 0 ? `Caption ${idx + 1} active` : "Caption — active";
    }
    $("#play-state").textContent = preview.paused ? "Paused" : "Playing";
}

function render() {
    const out = $("#editor");
    const search = $("#search").value.toLowerCase();
    const review = $("#needs-review").checked;
    out.innerHTML = "";
    captions
        .filter(c => (!search || c.text.toLowerCase().includes(search)) && (!review || c.low_confidence || c.inappropriate))
        .forEach((c) => {
            const row = document.createElement("article");
            row.className = "caption";
            row.innerHTML = `<input class="start" value="${c.start}"><input class="end" value="${c.end}"><input class="text" value="${c.text.replace(/"/g, "&quot;")}"><input class="term" value="${c.term || "Meaning"}"><label>Flag <input class="flag" type="checkbox" ${c.inappropriate ? "checked" : ""}></label><button class="remove">Remove</button><textarea class="meaning" placeholder="Explanation (up to 5 lines)">${c.meaning || ""}</textarea>`;
            row.querySelector(".start").onchange = e => { c.start = Number(e.target.value); };
            row.querySelector(".end").onchange = e => { c.end = Number(e.target.value); };
            row.querySelector(".text").oninput = e => { c.text = e.target.value; sync(); };
            row.querySelector(".term").oninput = e => { c.term = e.target.value; sync(); };
            row.querySelector(".meaning").oninput = e => { c.meaning = e.target.value; sync(); };
            row.querySelector(".flag").onchange = e => { c.inappropriate = e.target.checked; sync(); };
            row.querySelector(".remove").onclick = () => {
                const idx = captions.indexOf(c);
                if (idx !== -1) {
                    captions.splice(idx, 1);
                    render();
                    sync();
                }
            };
            out.append(row);
        });
    $("#caption-count").textContent = `${captions.length} captions`;
}

function payload() {
    return new URLSearchParams({ captions_json: JSON.stringify(captions) });
}

async function downloadCompleteLearningVideo() {
    if (!user) {
        auth("login");
        return;
    }
    if (!project) {
        $("#studio-message").textContent = "Please upload a video and generate captions first.";
        return;
    }
    const btn = $("#download-complete-video");
    const originalHtml = btn ? btn.innerHTML : "";
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="btn-spinner"></span> <span>Rendering Learning Video…</span>`;
    }
    try {
        $("#studio-message").textContent = "Rendering complete learning video with sidebar explanations…";
        const d = await request(`/api/projects/${project}/export-learning-video`, payload());
        location.href = d.download_url;
        $("#studio-message").textContent = "Complete video ready! Download started.";
        showNotification("Complete video download started!");
    } catch (x) {
        $("#studio-message").textContent = x.message;
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    }
}

function showNotification(msg = "Subtitle generated successfully") {
    const pop = $("#popup-notification");
    const text = $("#popup-text");
    if (!pop) return;
    if (text) text.textContent = msg;
    pop.hidden = false;
    clearTimeout(window._popTimer);
    window._popTimer = setTimeout(() => {
        pop.hidden = true;
    }, 4500);
}

$("#popup-close")?.addEventListener("click", () => {
    const pop = $("#popup-notification");
    if (pop) pop.hidden = true;
});

buildBoxes();
refresh();

$("#sign-in").onclick = () => auth();
$("#create-account").onclick = () => auth("register");
$("#nav-sign-in")?.addEventListener("click", () => auth("login"));
$("#nav-create-account")?.addEventListener("click", () => auth("register"));
$("#hero-open-btn")?.addEventListener("click", (e) => {
    e.preventDefault();
    document.querySelector("#workspace")?.scrollIntoView({ behavior: "smooth" });
    if (!user) {
        setTimeout(() => auth("login"), 550);
    }
});
$("#close-auth").onclick = () => $("#auth").close();
$("#gate-sign-in")?.addEventListener("click", () => auth("login"));
document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => auth(b.dataset.mode));
$("#show-password").onclick = () => {
    const p = $("#password");
    p.type = p.type === "password" ? "text" : "password";
};
$("#password").oninput = e => $("#strength").style.width = `${Math.min(100, e.target.value.length * 12)}%`;

$("#email").oninput = async e => {
    if (!e.target.value.includes("@")) return;
    try {
        const d = await request(`/api/auth/check-email?email=${encodeURIComponent(e.target.value)}`, null, "GET");
        $("#email-help").textContent = d.exists ? "This email is already registered. Sign in instead." : d.domain_ok === false ? "This email domain cannot receive mail." : "";
    } catch {}
};

$("#auth-form").onsubmit = async e => {
    e.preventDefault();
    try {
        const data = new FormData(e.target);
        if (mode === "register") {
            const d = await request("/api/auth/register", data);
            if (d.needs_verification) {
                window.verifyEmail = data.get("email");
                $("#auth-form").hidden = true;
                $("#code-screen").hidden = false;
                $("#auth-message").textContent = d.message;
            }
        } else {
            await request("/api/auth/login", data);
            $("#auth").close();
            refresh();
        }
    } catch (x) {
        $("#auth-message").textContent = x.message;
        if (x.message.includes("verify")) {
            window.verifyEmail = $("#email").value;
            $("#auth-form").hidden = true;
            $("#code-screen").hidden = false;
        }
    }
};

$("#verify-code").onclick = async () => {
    try {
        await request("/api/auth/verify-email", new URLSearchParams({
            email: window.verifyEmail,
            code: [...$("#code-boxes").children].map(x => x.value).join("")
        }));
        $("#code-screen").hidden = true;
        $("#auth-form").hidden = false;
        auth();
        $("#email").value = window.verifyEmail;
        $("#auth-message").textContent = "Email verified. Please sign in.";
    } catch (x) {
        $("#auth-message").textContent = x.message;
    }
};

$("#resend").onclick = async () => {
    try {
        $("#auth-message").textContent = (await request("/api/auth/resend-code", new URLSearchParams({ email: window.verifyEmail }))).message;
    } catch (x) {
        $("#auth-message").textContent = x.message;
    }
};

$("#sign-out").onclick = async () => {
    await request("/api/auth/logout", new URLSearchParams());
    user = null;
    refresh();
};

function resetToUpload() {
    project = null;
    captions = [];
    activeCaptionRef = null;
    try {
        preview.pause();
        preview.removeAttribute("src");
        preview.load();
    } catch {}
    $("#studio-view").hidden = true;
    $("#upload-view").hidden = false;
    const form = $("#upload-form");
    if (form) form.reset();
    $("#upload-message").textContent = "";
    $("#studio-message").textContent = "";
    $("#progress-text").textContent = "";
    render();
    sync();
}

$("#new-project-btn")?.addEventListener("click", resetToUpload);

function renderSkeletons() {
    const editor = $("#editor");
    if (!editor) return;
    editor.innerHTML = `
      <div class="skeleton-card">
        <div class="skeleton-shimmer"></div>
        <div class="skeleton-line skeleton-time"></div>
        <div class="skeleton-line skeleton-text"></div>
        <div class="skeleton-line skeleton-meaning"></div>
      </div>
      <div class="skeleton-card">
        <div class="skeleton-shimmer"></div>
        <div class="skeleton-line skeleton-time"></div>
        <div class="skeleton-line skeleton-text"></div>
        <div class="skeleton-line skeleton-meaning"></div>
      </div>
      <div class="skeleton-card">
        <div class="skeleton-shimmer"></div>
        <div class="skeleton-line skeleton-time"></div>
        <div class="skeleton-line skeleton-text"></div>
        <div class="skeleton-line skeleton-meaning"></div>
      </div>
    `;
}

function uploadWithProgress(url, formData, onProgress) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", url);
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable && onProgress) {
                const pct = Math.round((e.loaded / e.total) * 100);
                const loadedMb = e.loaded / (1024 * 1024);
                const totalMb = e.total / (1024 * 1024);
                onProgress(pct, loadedMb, totalMb);
            }
        };
        xhr.onload = () => {
            try {
                const data = JSON.parse(xhr.responseText || "{}");
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(data);
                } else {
                    reject(new Error(data.detail || "Upload failed"));
                }
            } catch (err) {
                reject(new Error("Invalid server response"));
            }
        };
        xhr.onerror = () => reject(new Error("Network connection error during upload"));
        xhr.send(formData);
    });
}

async function generateCaptions() {
    if (!user) {
        auth("login");
        return;
    }
    if (!project) return;
    const genBtn = $("#generate");
    if (genBtn) genBtn.disabled = true;

    const hud = $("#processing-hud");
    const stepTitle = $("#processing-step-title");
    const stepDesc = $("#processing-step-desc");
    const step1 = $("#hud-step-1");
    const step2 = $("#hud-step-2");
    const step3 = $("#hud-step-3");

    if (hud) hud.hidden = false;
    if (step1) step1.className = "hud-step active";
    if (step2) step2.className = "hud-step";
    if (step3) step3.className = "hud-step";
    if (stepTitle) stepTitle.textContent = "Extracting dialogue audio…";
    if (stepDesc) stepDesc.textContent = "Preparing clean audio track for high-accuracy recognition.";

    renderSkeletons();

    let stepCounter = 1;
    const stepTimer = setInterval(() => {
        stepCounter++;
        if (stepCounter === 2) {
            if (step1) step1.className = "hud-step done";
            if (step2) step2.className = "hud-step active";
            if (stepTitle) stepTitle.textContent = "AI speech recognition in progress…";
            if (stepDesc) stepDesc.textContent = "Faster-Whisper neural model transcribing speech & timestamps.";
        } else if (stepCounter >= 3) {
            if (step2) step2.className = "hud-step done";
            if (step3) step3.className = "hud-step active";
            if (stepTitle) stepTitle.textContent = "Aligning contextual meanings & idioms…";
            if (stepDesc) stepDesc.textContent = "Disambiguating word senses, proper names, and phrasal verbs.";
        }
    }, 4500);

    try {
        $("#progress-text").textContent = "Transcribing dialogue and computing contextual word meanings…";
        const d = await request(`/api/projects/${project}/auto-captions`, new URLSearchParams({
            language: $("#language")?.value || "en",
            quality: "fast",
            explanation_language: "en"
        }));
        if (Array.isArray(d.captions)) {
            captions = d.captions;
        } else if (d.captions && Array.isArray(d.captions.captions)) {
            captions = d.captions.captions;
        } else if (Array.isArray(d)) {
            captions = d;
        } else {
            captions = [];
        }
        $("#progress-text").textContent = "Subtitles generated successfully.";
        render();
        sync();
        showNotification("Subtitles & contextual meanings generated successfully!");
    } catch (x) {
        $("#studio-message").textContent = x.message;
        $("#progress-text").textContent = "";
        render();
    } finally {
        clearInterval(stepTimer);
        if (hud) hud.hidden = true;
        if (genBtn) genBtn.disabled = false;
    }
}

$("#generate").onclick = generateCaptions;

$("#upload-form").onsubmit = async e => {
    e.preventDefault();
    if (!user) {
        auth("login");
        return;
    }
    const form = e.target;
    const submitBtn = form.querySelector("button[type='submit']");
    const originalText = submitBtn ? submitBtn.textContent : "Upload video →";
    const progressBox = $("#upload-progress-box");
    const progressFill = $("#upload-progress-fill");
    const progressText = $("#upload-progress-text");
    const progressMb = $("#upload-progress-mb");

    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Uploading video…";
    }
    if (progressBox) progressBox.hidden = false;
    if (progressFill) progressFill.style.width = "0%";
    if (progressText) progressText.textContent = "Uploading video… 0%";
    if (progressMb) progressMb.textContent = "";

    try {
        const formData = new FormData(form);
        const d = await uploadWithProgress("/api/projects", formData, (pct, loadedMb, totalMb) => {
            if (progressFill) progressFill.style.width = pct + "%";
            if (progressText) progressText.textContent = `Uploading video… ${pct}%`;
            if (progressMb) progressMb.textContent = `${loadedMb.toFixed(1)} / ${totalMb.toFixed(1)} MB`;
        });
        project = d.id;
        preview.src = d.video_url;
        $("#upload-view").hidden = true;
        $("#studio-view").hidden = false;
        $("#upload-message").textContent = "";
        // Automatically start generating subtitles right upon upload!
        generateCaptions();
    } catch (x) {
        $("#upload-message").textContent = x.message;
    } finally {
        if (progressBox) progressBox.hidden = true;
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }
    }
};

["timeupdate", "seeked", "play", "pause", "loadeddata", "loadedmetadata"].forEach(e => preview.addEventListener(e, sync));
if (preview.requestVideoFrameCallback) {
    const tick = () => {
        sync();
        if (!preview.paused) preview.requestVideoFrameCallback(tick);
    };
    preview.addEventListener("play", () => preview.requestVideoFrameCallback(tick));
}

$("#search").oninput = render;
$("#needs-review").onchange = render;
$("#add-caption").onclick = () => {
    captions.push({ start: 0, end: 2, text: "New subtitle", term: "Meaning", meaning: "" });
    render();
};

$("#download-complete-video").onclick = downloadCompleteLearningVideo;

$("#export").onchange = async e => {
    if (!user) {
        auth("login");
        return;
    }
    const val = e.target.value;
    if (!val) return;
    if (val === "learning") {
        await downloadCompleteLearningVideo();
        e.target.value = "";
        return;
    }
    const route = { srt: "subtitles", audio: "extract-audio", video: "burn-subtitles" }[val];
    if (!route) return;
    try {
        if (route !== "extract-audio") await request(`/api/projects/${project}/subtitles`, payload());
        const d = await request(`/api/projects/${project}/${route}`, route === "extract-audio" ? new URLSearchParams() : payload());
        location.href = d.download_url;
    } catch (x) {
        $("#studio-message").textContent = x.message;
    } finally {
        e.target.value = "";
    }
};

$("#seal").onclick = async () => {
    if (!user) {
        auth("login");
        return;
    }
    try {
        $("#studio-message").textContent = (await request(`/api/projects/${project}/seal`, new URLSearchParams({
            captions_json: JSON.stringify(captions),
            secret: $("#seal-secret").value
        }))).message;
    } catch (x) {
        $("#studio-message").textContent = x.message;
    }
};

$("#verify").onclick = async () => {
    if (!user) {
        auth("login");
        return;
    }
    try {
        $("#studio-message").textContent = (await request(`/api/projects/${project}/verify`, new URLSearchParams({
            secret: $("#seal-secret").value
        }))).message;
    } catch (x) {
        $("#studio-message").textContent = x.message;
    }
};


// ==========================================================================
// Project History Management
// ==========================================================================

let projectHistoryCache = [];

async function openHistoryModal() {
    if (!user) {
        auth("login");
        return;
    }
    const dialog = $("#history-dialog");
    if (!dialog) return;
    dialog.showModal();
    await loadProjectHistory();
}

async function loadProjectHistory() {
    const listEl = $("#history-list");
    const loadingEl = $("#history-loading");
    const emptyEl = $("#history-empty");
    const countEl = $("#history-count");

    if (loadingEl) loadingEl.hidden = false;
    if (emptyEl) emptyEl.hidden = true;
    if (listEl) listEl.innerHTML = "";

    try {
        const data = await request("/api/projects", null, "GET");
        projectHistoryCache = data.projects || [];
        renderHistoryList(projectHistoryCache);
    } catch (err) {
        if (listEl) listEl.innerHTML = `<p class="message" style="color:#f87171;text-align:center;">Failed to load project history: ${err.message}</p>`;
    } finally {
        if (loadingEl) loadingEl.hidden = true;
    }
}

function renderHistoryList(items) {
    const listEl = $("#history-list");
    const emptyEl = $("#history-empty");
    const countEl = $("#history-count");
    if (!listEl) return;

    if (countEl) countEl.textContent = `${items.length} saved`;

    if (!items || items.length === 0) {
        if (emptyEl) emptyEl.hidden = false;
        listEl.innerHTML = "";
        return;
    }
    if (emptyEl) emptyEl.hidden = true;

    listEl.innerHTML = items.map(p => {
        const dateStr = p.created_at ? new Date(p.created_at).toLocaleDateString(undefined, {
            year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
        }) : "Recent";

        const subtitleBadge = p.has_subtitles 
            ? `<span class="history-pill pill-sub">${p.caption_count || "✓"} Subtitles</span>`
            : `<span class="history-pill pill-pending">Pending STT</span>`;

        const learningBadge = p.has_learning_video
            ? `<span class="history-pill pill-mp4">✓ Learning MP4</span>`
            : "";

        const isCurrent = project === p.id;

        return `
            <div class="history-card ${isCurrent ? 'current-active-project' : ''}" data-id="${p.id}">
              <div class="history-card-main">
                <div class="history-card-title-row">
                  <h3 class="history-card-title">${escapeHtml(p.title)}</h3>
                  ${isCurrent ? '<span class="history-current-tag">● Currently Active</span>' : ''}
                </div>
                <div class="history-card-meta">
                  <span class="history-date">📅 ${dateStr}</span>
                  ${subtitleBadge}
                  ${learningBadge}
                </div>
              </div>
              <div class="history-card-actions">
                <button type="button" class="primary history-open-btn" onclick="openProject('${p.id}')">
                  ${isCurrent ? 'Viewing in Studio →' : 'Open in Studio →'}
                </button>
                <button type="button" class="quiet history-delete-btn" title="Delete project" onclick="deleteProject('${p.id}', '${escapeAttr(p.title)}')">
                  🗑️
                </button>
              </div>
            </div>
        `;
    }).join("");
}

function escapeHtml(str) {
    return (str || "Untitled video")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function escapeAttr(str) {
    return (str || "Untitled video")
        .replace(/'/g, "\\'")
        .replace(/"/g, "&quot;");
}

async function openProject(projectId) {
    try {
        const dialog = $("#history-dialog");
        if (dialog) dialog.close();

        $("#studio-message").textContent = "Loading project details…";
        const details = await request(`/api/projects/${projectId}/details`, null, "GET");

        project = details.id;
        preview.src = details.video_url;
        captions = Array.isArray(details.captions) ? details.captions : [];

        $("#upload-view").hidden = true;
        $("#studio-view").hidden = false;
        $("#upload-message").textContent = "";
        $("#studio-message").textContent = `Loaded project: ${details.title}`;

        render();
        sync();
        showNotification(`Project loaded: ${details.title}`);
    } catch (err) {
        showNotification(`Error loading project: ${err.message}`);
    }
}

async function deleteProject(projectId, title) {
    if (!confirm(`Are you sure you want to delete "${title || 'this project'}"? This action cannot be undone.`)) {
        return;
    }
    try {
        await request(`/api/projects/${projectId}`, null, "DELETE");
        showNotification(`Project "${title}" deleted.`);
        if (project === projectId) {
            resetToUpload();
        }
        await loadProjectHistory();
    } catch (err) {
        alert(`Failed to delete project: ${err.message}`);
    }
}

// History event listeners
$("#history-btn")?.addEventListener("click", openHistoryModal);
$("#history-btn-studio")?.addEventListener("click", openHistoryModal);
$("#close-history")?.addEventListener("click", () => $("#history-dialog")?.close());

$("#history-search")?.addEventListener("input", (e) => {
    const q = (e.target.value || "").trim().toLowerCase();
    if (!q) {
        renderHistoryList(projectHistoryCache);
    } else {
        const filtered = projectHistoryCache.filter(p => (p.title || "").toLowerCase().includes(q));
        renderHistoryList(filtered);
    }
});
