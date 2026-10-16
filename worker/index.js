// 메일의 [확인하고 올리기] 버튼이 여는 승인 페이지 (Cloudflare Worker).
// GET  /p/:pr?t=토큰        → 카드 미리보기 + 버튼
// POST /p/:pr/act           → now(지금 올리기) | schedule(예약) | revise(수정 요청) | reject(반려)
// 비밀값: GH_PAT (GitHub 토큰), APPROVAL_SECRET (메일 링크 서명용)   변수: REPO

const GH = "https://api.github.com";

async function sign(secret, pr) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(String(pr)));
  return [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

function sameText(a, b) {
  if (!a || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function gh(env, path, init = {}) {
  const res = await fetch(GH + path, {
    ...init,
    headers: {
      ...(env.GH_PAT ? { Authorization: `Bearer ${env.GH_PAT}` } : {}),
      Accept: "application/vnd.github+json",
      "User-Agent": "bukjeok-approval",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`GitHub ${res.status}: ${text.slice(0, 200)}`);
  return text ? JSON.parse(text) : {};
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function page(title, body) {
  return new Response(`<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(title)}</title>
<style>
 body{margin:0;background:#111;color:#f5f5f5;font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
 main{max-width:680px;margin:auto;padding:20px 16px 60px}
 h1{font-size:22px;line-height:1.35;margin:6px 0 10px} .muted{color:#aaa;font-size:14px}
 .cards{display:flex;gap:10px;overflow-x:auto;scroll-snap-type:x mandatory;padding:8px 0 14px}
 .cards img{width:78%;max-width:420px;flex:none;border-radius:12px;scroll-snap-align:start}
 pre{white-space:pre-wrap;background:#1d1d1d;padding:14px;border-radius:12px;font-family:inherit;font-size:15px;line-height:1.6}
 .btns{display:grid;gap:10px;margin:18px 0}
 button{width:100%;font-size:18px;font-weight:800;padding:16px;border-radius:14px;border:0;cursor:pointer}
 .now{background:#C9FF3B;color:#111} .sch{background:#fff;color:#111} .rej{background:#333;color:#ddd}
 textarea{width:100%;box-sizing:border-box;min-height:80px;border-radius:12px;padding:12px;font-size:16px;border:0}
 .rev{background:#2B50FF;color:#fff;margin-top:8px} .box{background:#1d1d1d;border-radius:14px;padding:14px;margin-top:10px}
 .ok{font-size:20px;font-weight:800;color:#C9FF3B}
</style></head><body><main>${body}</main></body></html>`, { headers: { "Content-Type": "text/html; charset=utf-8" } });
}

async function loadPost(env, pr) {
  const info = await gh(env, `/repos/${env.REPO}/pulls/${pr}`);
  const files = await gh(env, `/repos/${env.REPO}/pulls/${pr}/files?per_page=100`);
  const postFile = files.map((f) => f.filename).find((f) => /^content\/[^/]+\/post\.json$/.test(f));
  if (!postFile) throw new Error("이 PR에서 게시물을 찾지 못했어요.");
  const dir = postFile.replace(/\/post\.json$/, "");
  const sha = info.head.sha;
  const raw = (p) => `https://raw.githubusercontent.com/${env.REPO}/${sha}/${dir}/${p}`;
  const post = await (await fetch(raw("post.json"))).json();
  const meta = await fetch(raw("meta.json")).then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
  return { info, dir, post, meta, raw };
}

async function view(env, pr, t) {
  const { info, post, meta, raw } = await loadPost(env, pr);
  const cards = post.slides.map((_, i) => `<img src="${raw(`cards/${String(i + 1).padStart(2, "0")}.jpg`)}" loading="lazy">`).join("");
  const when = meta.publish_at ? new Date(meta.publish_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "-";
  const state = info.merged ? "✅ 승인됨" : info.state === "closed" ? "❌ 반려됨" : "⏳ 검수 대기";
  const form = (action, label, cls, extra = "") =>
    `<form method="post" action="/p/${pr}/act"><input type="hidden" name="t" value="${esc(t)}"><input type="hidden" name="action" value="${action}">${extra}<button class="${cls}">${label}</button></form>`;
  let buttons = "";
  if (!info.merged && info.state === "open") {
    buttons = `<div class="btns">
      ${form("now", "🚀 지금 바로 올리기", "now")}
      ${form("schedule", `🗓 예약대로 올리기 (${esc(when)})`, "sch")}
    </div>
    <div class="box"><b>✏️ 고칠 점이 있나요?</b>
      ${form("revise", "수정 요청 보내기", "rev", `<textarea name="note" placeholder="예) 표지 문구를 더 세게 / 3번 카드 예시를 카페로 바꿔줘" required></textarea>`)}
      <p class="muted">Claude가 고쳐서 몇 분 뒤 새 메일로 다시 보내드려요.</p></div>
    <div class="btns">${form("reject", "반려하기 (올리지 않음)", "rej")}</div>`;
  } else if (info.merged) {
    buttons = `<div class="btns">${form("now", "🚀 지금 바로 올리기", "now")}</div><p class="muted">이미 승인됐어요. 아직 안 올라갔다면 위 버튼으로 바로 올릴 수 있어요. (이미 올라간 곳은 다시 올리지 않아요)</p>`;
  }
  return page(post.topic, `
    <p class="muted">${state} · ${esc(post.pillar)} · 예약 ${esc(when)}</p>
    <h1>${esc(post.topic)}</h1>
    <p class="muted">해결하는 고민: ${esc(post.problem)}</p>
    <div class="cards">${cards}</div>
    ${buttons}
    <h3>📝 인스타 캡션</h3><pre>${esc(post.instagram_caption)}</pre>
    <h3>🧵 스레드</h3>${post.threads.map((x) => `<pre>${esc(x)}</pre>`).join("")}`);
}

async function act(env, pr, form) {
  const action = form.get("action");
  const { info, dir, post } = await loadPost(env, pr);
  const merge = async () => {
    if (!info.merged) await gh(env, `/repos/${env.REPO}/pulls/${pr}/merge`, { method: "PUT", body: JSON.stringify({ merge_method: "squash" }) });
  };
  let msg;
  if (action === "now") {
    await merge();
    await gh(env, `/repos/${env.REPO}/actions/workflows/3-publish.yml/dispatches`, {
      method: "POST", body: JSON.stringify({ ref: "main", inputs: { only: dir } }),
    });
    msg = "🚀 발행을 시작했어요! 2~3분 뒤 인스타그램·스레드에 올라가고, 완료 메일을 보내드려요.";
  } else if (action === "schedule") {
    await merge();
    msg = "🗓 승인 완료! 예약된 시각에 자동으로 올라가요.";
  } else if (action === "revise") {
    const note = (form.get("note") || "").trim();
    if (!note) return page("수정 요청", `<p>수정할 내용을 적어주세요.</p>`);
    await gh(env, `/repos/${env.REPO}/issues/${pr}/comments`, { method: "POST", body: JSON.stringify({ body: `/수정 ${note}` }) });
    msg = "✏️ 수정 요청을 보냈어요. 고친 버전이 준비되면 새 메일로 알려드려요.";
  } else if (action === "reject") {
    await gh(env, `/repos/${env.REPO}/pulls/${pr}`, { method: "PATCH", body: JSON.stringify({ state: "closed" }) });
    msg = "❌ 반려했어요. 이 게시물은 올라가지 않아요.";
  } else {
    return new Response("알 수 없는 요청", { status: 400 });
  }
  return page("완료", `<h1>${esc(post.topic)}</h1><p class="ok">${msg}</p>`);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const m = url.pathname.match(/^\/p\/(\d+)(\/act)?$/);
    if (!m) return new Response("북적마케팅 승인 페이지", { status: 404 });
    const pr = m[1];
    try {
      const form = request.method === "POST" ? await request.formData() : null;
      const t = form ? form.get("t") : url.searchParams.get("t");
      if (!sameText(t, await sign(env.APPROVAL_SECRET, pr))) {
        return page("링크 오류", "<h1>링크가 올바르지 않아요</h1><p>메일의 버튼을 다시 눌러주세요.</p>");
      }
      if (m[2] && request.method === "POST") return await act(env, pr, form);
      return await view(env, pr, t);
    } catch (e) {
      return page("오류", `<h1>문제가 생겼어요</h1><pre>${esc(e.message)}</pre>`);
    }
  },
};
