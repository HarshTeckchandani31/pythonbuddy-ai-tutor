// AlgebraBuddy frontend. Talks to the backend at /api/chat.
const $ = (id) => document.getElementById(id);

let profile = {};          // Step 5: learner info
let mode = "Learn";        // Step 4: current learning mode
let history = [];          // full conversation sent to the AI each time
let stats = { attempted: 0, correct: 0, skills: {} };  // Step 8: session-only tracking
let busy = false;

// Quick-reply chips and the first message for each mode
const CHIPS = {
  Learn: ["Explain it to me", "Show another example"],
  Practice: ["Give me a question", "Give me a hint", "I’m stuck – show the first step"],
  Quiz: ["Start the quiz", "Next question"],
  Doubt: ["What is a variable?", "Why do we subtract on both sides?"],
};
const KICKOFF = {
  Learn: "[MODE: Learn] Please teach me the topic.",
  Practice: "[MODE: Practice] Give me my first practice question.",
  Quiz: "[MODE: Quiz] Start a 5-question quiz.",
  Doubt: "[MODE: Doubt] I have a doubt. Invite me to ask it.",
};

function addBubble(cls, text) {
  const d = document.createElement("div");
  d.className = "m " + cls;
  d.textContent = text;           // textContent = safe from HTML injection
  $("chat").appendChild(d);
  $("chat").scrollTop = $("chat").scrollHeight;
  return d;
}

// Remove the hidden tracking tag before showing the reply
const stripTag = (t) => t.replace(/\[\[RESULT:[^\]]*\]\]?/g, "").trim();

// Step 8: read [[RESULT:correct|skill]] tags and update the learner profile
function trackResults(text) {
  const re = /\[\[RESULT:(correct|incorrect)\|([^\]]*)\]\]/g;
  let m;
  while ((m = re.exec(text))) {
    const skill = m[2].trim() || profile.topic.toLowerCase();
    stats.skills[skill] = stats.skills[skill] || { a: 0, c: 0 };
    stats.attempted++; stats.skills[skill].a++;
    if (m[1] === "correct") { stats.correct++; stats.skills[skill].c++; }
  }
  renderProgress();
}

function renderProgress() {
  $("sc").textContent = `${stats.correct}/${stats.attempted}`;
  const accuracy = stats.attempted ? Math.round((100 * stats.correct) / stats.attempted) : 0;
  $("pb").style.width = accuracy + "%";
  $("pb").parentElement.setAttribute("aria-valuenow", String(accuracy));
  $("rate").textContent = stats.attempted ? String(accuracy) : "--";
  $("attempted-count").textContent = `${stats.attempted} ${stats.attempted === 1 ? "attempt" : "attempts"}`;
  const strong = [], weak = [];
  for (const [k, v] of Object.entries(stats.skills)) (v.c / v.a >= 0.7 ? strong : weak).push(k);
  fillList("strong", strong);
  fillList("weak", weak);
  $("next-topic").textContent = weak.length
    ? `A little more practice with ${weak[0]} will help it stick.`
    : strong.length
      ? `Keep building on ${strong[0]} with a new challenge.`
      : "Your next step will take shape as you learn.";
}
function fillList(id, items) {
  const ul = $(id);
  ul.innerHTML = "";
  (items.length ? items : ["Not enough data yet"]).forEach((x) => {
    const li = document.createElement("li");
    li.textContent = x;
    ul.appendChild(li);
  });
}

// Send a message to the backend and show the reply
async function ask(userText, shownText) {
  if (busy) return;
  busy = true; $("send").disabled = true; $("end").disabled = true; $("err").textContent = "";
  if (shownText) addBubble("u", shownText);
  history.push({ role: "user", content: userText });
  const bubble = addBubble("a", "Thinking…");

  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history, profile }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Request failed");
    history.push({ role: "assistant", content: data.text });
    bubble.textContent = stripTag(data.text);
    trackResults(data.text);
  } catch (e) {
    bubble.remove();
    history.pop();                // let the learner retry
    $("err").textContent = e.message;
  }
  busy = false; $("send").disabled = false; $("end").disabled = false;
  $("chat").scrollTop = $("chat").scrollHeight;
}

function renderChips() {
  $("chips").innerHTML = "";
  CHIPS[mode].forEach((t) => {
    const b = document.createElement("button");
    b.textContent = t;
    b.onclick = () => ask(`[MODE: ${mode}] ${t}`, t);
    $("chips").appendChild(b);
  });
}

function setMode(m, first) {
  mode = m;
  [...$("tabs").children].forEach((b) => {
    const active = b.dataset.m === m;
    b.classList.toggle("on", active);
    b.setAttribute("aria-selected", String(active));
  });
  $("mode-label").textContent = `${m.toUpperCase()} MODE`;
  renderChips();
  if (!first) addBubble("s", `Switched to ${m} mode`);
  ask(KICKOFF[m]);
}

$("tabs").onclick = (e) => {
  const b = e.target.closest("button");
  if (b && !busy && b.dataset.m !== mode) setMode(b.dataset.m, false);
};

function submit() {
  const v = $("in").value.trim();
  if (!v || busy) return;
  $("in").value = "";
  ask(`[MODE: ${mode}] ${v}`, v);
}
$("send").onclick = submit;
$("in").onkeydown = (e) => { if (e.key === "Enter") submit(); };

// Step 9: end-of-session report and recommendation
$("end").onclick = () => {
  if (busy) return;
  const skills = Object.entries(stats.skills).map(([k, v]) => `${k}: ${v.c}/${v.a}`).join("; ") || "none recorded";
  addBubble("s", "Session summary");
  ask(
    `[SESSION END] Write my session report in plain text with these parts: "Today’s Performance" ` +
    `(questions attempted: ${stats.attempted}, correct: ${stats.correct}), "Strengths", "Needs improvement", ` +
    `and "Recommended next lesson" (one specific lesson title). Per-skill results: ${skills}. ` +
    `Be encouraging and brief. Do not add a RESULT tag.`
  );
};

// Start button
$("go").onclick = () => {
  profile = {
    name: $("nm").value.trim() || "Learner",
    level: $("lv").value,
    topic: $("tp").value,
    difficulty: $("df").value,
  };
  $("setup").classList.add("hide");
  $("app").classList.remove("hide");
  $("who").textContent = profile.name;
  $("avatar").textContent = profile.name.charAt(0).toUpperCase();
  $("lesson-title").textContent = `Let's work on ${profile.topic.toLowerCase()}.`;
  $("lesson-meta").textContent = `${profile.level} · ${profile.difficulty} practice`;
  renderProgress();
  setMode("Learn", true);
};
