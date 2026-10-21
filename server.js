// Prototype backend: keeps your API key private and builds the tutor's system prompt.
require("dotenv").config();
const express = require("express");
const path = require("path");

const app = express();
app.use(express.json({ limit: "100kb" }));
app.get("/", (req, res) => res.sendFile(path.join(__dirname, "index.html")));
app.get("/style.css", (req, res) => res.sendFile(path.join(__dirname, "style.css")));
app.get("/app.js", (req, res) => res.sendFile(path.join(__dirname, "app.js")));

const API_KEY = process.env.GEMINI_API_KEY;
const MODEL = process.env.GEMINI_MODEL || "gemini-3.8-flash";
const PORT = process.env.PORT || 3000;

// ---- Step 2: the tutor's personality and teaching style -------------------
function buildSystemPrompt(p) {
  return `You are PythonBuddy, a friendly, patient Python tutor for beginners. Teach practical Python fundamentals with small, runnable examples.
Learner: ${p.name}. Self-reported level: ${p.level}. Focus topic: ${p.topic}. Difficulty: ${p.difficulty}.

RULES
- Explain simply, introduce one idea at a time, and use small Python code examples.
- Ask the learner questions often. Give a hint before the solution; reveal the full solution only after they have tried or clearly given up.
- Encourage them to try again. Give constructive feedback.
- Keep replies under 150 words. Use fenced code blocks for multi-line Python and backticks for inline code; do not use tables.
- Stay focused on beginner Python. If the question is unrelated, politely steer back to the selected Python topic.
- Correct spelling mistakes silently.
- Never claim to run code. Explain the expected result by reasoning through it.
- If asked for a direct answer, give a hint and the first step instead, then offer the solution if they are still stuck.

DIFFICULTY
- Beginner: familiar examples, short snippets, explain each new symbol, and give plenty of hints.
- Intermediate: combine concepts in short programs and give fewer hints.
- Advanced: offer multi-step coding challenges and edge cases, with minimal hints.

MODES (follow the latest [MODE: ...] note in the conversation)
- Learn: explain the selected Python concept with a small code example, then check understanding with ONE question.
- Practice: give ONE Python question or small coding task at a time and wait for the answer.
- Quiz: ask 5 Python questions, one at a time, no hints until the end, then give a score.
- Doubt: answer the learner's question clearly.

EVALUATING ANSWERS
When the learner answers a question you asked: say Correct / Almost / Incorrect, explain why, show a corrected snippet when useful, add a hint or encouragement, then (in Practice/Quiz) ask the next question.

TRACKING (Step 8)
After evaluating an answer, end your reply with exactly one tag such as [[RESULT:correct|python variables]] or [[RESULT:incorrect|python loops]] (short lower-case skill name). Use it once per evaluated answer and never otherwise. Never mention the tag.`;
}

// ---- Chat endpoint --------------------------------------------------------
app.post("/api/chat", async (req, res) => {
  if (!API_KEY) return res.status(500).json({ error: "Missing GEMINI_API_KEY in .env" });

  const { messages, profile } = req.body || {};
  if (!Array.isArray(messages) || !messages.length || !profile) {
    return res.status(400).json({ error: "Bad request" });
  }

  // Keep only valid, recent messages (cheap protection against huge requests)
  const safe = messages
    .filter((m) => (m.role === "user" || m.role === "assistant") && typeof m.content === "string")
    .slice(-12)
    .map((m) => ({ role: m.role, content: m.content.slice(0, 1200) }));

  const clean = (v, n = 40) => String(v || "").slice(0, n);
  const p = {
    name: clean(profile.name) || "Learner",
    level: clean(profile.level),
    topic: clean(profile.topic),
    difficulty: clean(profile.difficulty),
  };

  try {
    const startedAt = performance.now();
    const response = await fetch(
      "https://generativelanguage.googleapis.com/v1beta/interactions",
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-goog-api-key": API_KEY,
        },
        body: JSON.stringify({
          model: MODEL,
          system_instruction: buildSystemPrompt(p),
          input: safe
            .map((message) => `${message.role === "assistant" ? "Tutor" : "Learner"}: ${message.content}`)
            .join("\n\n"),
          generation_config: { max_output_tokens: 500, thinking_level: "low" },
        }),
      },
    );
    const data = await response.json();
    console.info(`Gemini request completed in ${((performance.now() - startedAt) / 1000).toFixed(2)} seconds with status ${response.status}`);
    if (!response.ok) {
      console.error("API error:", data);
      return res.status(502).json({ error: data?.error?.message || "AI request failed" });
    }
    const text = (data.steps || [])
      .filter((step) => step.type === "model_output")
      .flatMap((step) => step.content || [])
      .filter((part) => part.type === "text" && typeof part.text === "string")
      .map((part) => part.text)
      .join("\n");
    if (!text) return res.status(502).json({ error: "Gemini returned no text response" });
    res.json({ text });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Server error. Is your internet working?" });
  }
});

app.listen(PORT, () => console.log(`PythonBuddy running at http://localhost:${PORT}`));
