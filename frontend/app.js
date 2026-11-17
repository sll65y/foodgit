import { $, escape, loginView, plannerView, planOutput, catalogView, profileView, recordsView, logForm, dishForm, recipeRow } from "./views.js";

const main = $("#content");
const dialog = $("#dialog");
const state = {
  user: null, token: sessionStorage.getItem("shixu-token"),
  pages: { catalog: 1, records: 1, plans: 1 },
  filter: { q: "", meal: "" },
  ingredients: [], catalog: [], plan: null, today: "",
  draft: { message: "", vegetarian: false, exclude: [] },
};
let revision = 0;
let toastTimer;

function notice(message) {
  $("#toast").textContent = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("#toast").textContent = ""; }, 4500);
}

async function api(path, {method = "GET", data} = {}) {
  const headers = state.token ? {Authorization: "Bearer " + state.token} : {};
  if (data !== undefined && !(data instanceof File)) headers["Content-Type"] = "application/json";
  const response = await fetch("/api" + path, {
    method, headers,
    body: data === undefined || data instanceof File ? data : JSON.stringify(data),
    cache: "no-store",
  });
  if (response.status === 204) return;
  const json = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login") {
      clearSession();
      showLogin();
    }
    const detail = json.detail;
    const message = typeof detail === "string" ? detail :
      (Array.isArray(detail) ? "请检查表单项：" + detail.map(d => d.loc.slice(1).join(".")).join("、") : "操作失败，请重试。");
    throw new Error(message);
  }
  return json;
}

function route() {
  const page = location.hash.slice(1);
  return ["planner", "catalog", "records", "profile"].includes(page) ? page : "planner";
}

function clearSession() {
  sessionStorage.removeItem("shixu-token");
  Object.assign(state, { user: null, token: null, profile: null, targets: null, ingredients: [], catalog: [], plan: null,
    pages: { catalog: 1, records: 1, plans: 1 }, filter: { q: "", meal: "" },
    draft: { message: "", vegetarian: false, exclude: [] },
  });
  if (dialog.open) dialog.close();
}

function showLogin() {
  ++revision;
  $("#navigation").hidden = true;
  $("#account").textContent = "";
  main.innerHTML = loginView();
}

function renderTop(page) {
  $("#navigation").hidden = false;
  [...$("#navigation").querySelectorAll("a")].forEach((a) => {
    if (a.hash === "#" + page) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  $("#account").innerHTML = `<span class="avatar" title="${escape(state.profile.display_name)}">${escape(state.profile.display_name[0])}</span>
    ${state.user.role === "admin" ? '<span class="badge">管理员</span>' : ""}
    <button class="button plain" data-action="logout">退出</button>`;
}

async function loadProfile() {
  [state.profile, state.targets] = await Promise.all([api("/profile"), api("/targets")]);
}

async function initUser() {
  const [, ingredients, health] = await Promise.all([loadProfile(), api("/ingredients"), api("/health")]);
  state.ingredients = ingredients;
  state.today = health.date;
}

async function login(username, password) {
  const result = await api("/auth/login", {method: "POST", data: {username, password}});
  state.token = result.token;
  state.user = result.user;
  sessionStorage.setItem("shixu-token", state.token);
  try {
    await initUser();
  } catch (error) {
    clearSession();
    throw error;
  }
  await render();
}

async function render() {
  if (!state.user) { showLogin(); return; }
  const current = ++revision;
  const page = route();
  renderTop(page);
  main.innerHTML = '<p class="loading" role="status">正在读取数据…</p>';
  try {
    let html;
    if (page === "planner") html = plannerView(state);
    if (page === "profile") html = profileView(state);
    if (page === "catalog") {
      const query = new URLSearchParams({ page: state.pages.catalog, size: 6, q: state.filter.q });
      if (state.filter.meal) query.set("meal", state.filter.meal);
      const data = await api("/dishes?" + query);
      if (current !== revision) return;
      state.catalog = data.items;
      html = catalogView(state, data);
    }
    if (page === "records") {
      const [records, stats, plans] = await Promise.all([
        api("/records?page=" + state.pages.records), api("/stats"), api("/plans?page=" + state.pages.plans),
      ]);
      if (current !== revision) return;
      if (records.page > 1 && !records.items.length) { state.pages.records--; return render(); }
      state.today = stats.days.at(-1).date;
      html = recordsView(records, stats, plans);
    }
    if (current === revision) main.innerHTML = html;
  } catch (error) {
    if (current === revision) main.innerHTML = `<section class="card"><p class="error">${escape(error.message)}</p>
      <button class="button" data-action="reload">重试</button></section>`;
  }
}

function openDialog(title, html) {
  dialog.innerHTML = `<div class="sectionhead"><h2 id="dialog-title">${escape(title)}</h2>
    <button class="button plain" data-action="close" aria-label="关闭">×</button></div>${html}`;
  dialog.showModal();
}

function recordMeal(dish) {
  if (dish) openDialog("记下一餐", logForm(dish, state.today));
}

function draft(form) {
  const data = new FormData(form);
  state.draft = { message: data.get("message"), vegetarian: data.has("vegetarian"), exclude: data.getAll("exclude").map(Number) };
}

document.addEventListener("input", (e) => {
  if (e.target.form?.id === "plan") draft(e.target.form);
  if (e.target.name === "exclude") {
    const box = e.target.closest("details");
    const count = box.querySelectorAll("input:checked").length;
    $("[data-count]", box).textContent = count ? `· ${count} 项` : "";
  }
});

document.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const errorLine = $(".error", form);
  const submit = $("[type=submit]", form);
  if (submit?.disabled) return;
  const original = submit?.innerHTML;
  if (errorLine) errorLine.textContent = "";
  if (submit) { submit.disabled = true; submit.textContent = "处理中…"; }
  const formData = new FormData(form);
  const data = Object.fromEntries(formData);
  try {
    switch (form.id) {
      case "login":
        await login(data.username, data.password);
        break;
      case "plan": {
        draft(form);
        const result = await api("/plans", {method: "POST", data: state.draft});
        state.plan = result;
        if ($("#plan-output")) $("#plan-output").innerHTML = planOutput(result);
        notice("方案已生成，并保存到规划历史");
        break;
      }
      case "profile":
        for (const key of ["age", "height_cm", "weight_kg"]) data[key] = Number(data[key]);
        delete data.exclude;
        data.excluded_ingredients = formData.getAll("exclude").map(Number);
        await api("/profile", {method: "PUT", data});
        await loadProfile();
        state.plan = null;
        await render();
        notice("个人画像已保存");
        break;
      case "filter":
        state.pages.catalog = 1;
        state.filter = {q: data.q, meal: data.meal};
        await render();
        break;
      case "record":
        await api("/records", {method: "POST", data: {...data, dish_id: Number(form.dataset.id), portions: Number(data.portions)}});
        dialog.close();
        notice("就餐记录已保存");
        break;
      case "add-dish": {
        const ingredients = formData.getAll("ingredient").map((id, i) =>
          ({id: Number(id), grams: Number(formData.getAll("grams")[i])}));
        await api("/dishes", {method: "POST", data: {
          name: data.name, flavor: data.flavor, meal: data.meal, description: data.description, ingredients,
        }});
        dialog.close();
        state.filter = {q: data.name, meal: ""};
        state.pages.catalog = 1;
        await render();
        notice("菜品已加入菜库");
        break;
      }
      case "upload": {
        const file = formData.get("photo");
        if (file.size > 5 * 1024 * 1024) throw new Error("图片不能超过 5 MB。");
        await api("/dishes/" + form.dataset.id + "/image", {method: "PUT", data: file});
        dialog.close();
        await render();
        notice("菜品图片已更新");
        break;
      }
      case "delete":
        await api("/records/" + form.dataset.id, {method: "DELETE"});
        dialog.close();
        await render();
        notice("就餐记录已删除");
        break;
    }
  } catch (error) {
    if (errorLine?.isConnected) errorLine.textContent = error.message;
    else notice(error.message);
  } finally {
    if (submit) { submit.disabled = false; submit.innerHTML = original; }
  }
});

document.addEventListener("click", async (e) => {
  const button = e.target.closest("[data-action]");
  if (!button || button.disabled) return;
  const {action, id, value, page, scope, meal} = button.dataset;
  try {
    switch (action) {
      case "demo": {
        button.disabled = true;
        const submit = $("#login [type=submit]");
        submit.disabled = true;
        try { await login("demo", "food-demo"); }
        finally { button.disabled = false; submit.disabled = false; }
        break;
      }
      case "logout":
        await api("/auth/logout", {method: "POST"});
        clearSession();
        showLogin();
        break;
      case "prompt": {
        const input = $("#plan textarea");
        input.value = value;
        draft(input.form);
        input.focus();
        break;
      }
      case "page":
        state.pages[scope] = Number(page);
        await render();
        break;
      case "reload":
        await render();
        break;
      case "close":
        dialog.close();
        break;
      case "log-plan":
        recordMeal(state.plan.meals.find(d => d.meal === meal));
        break;
      case "log-dish":
        recordMeal(state.catalog.find(d => d.id === Number(id)));
        break;
      case "delete-record":
        openDialog("删除就餐记录", `<form id="delete" data-id="${id}"><p>删除「${escape(value)}」的这条记录？</p>
          <p class="error" role="alert"></p><button class="button danger" type="submit">删除记录</button></form>`);
        break;
      case "open-plan":
        state.plan = await api("/plans/" + id);
        if (route() === "planner") await render(); else location.hash = "planner";
        break;
      case "create-dish":
        openDialog("添加菜品", dishForm(state.ingredients));
        break;
      case "add-ingredient":
        if ($("#recipe-rows").children.length < 25) $("#recipe-rows").insertAdjacentHTML("beforeend", recipeRow(state.ingredients));
        break;
      case "remove-ingredient":
        if ($("#recipe-rows").children.length > 1) button.closest(".ingredient-row").remove();
        break;
      case "image":
        openDialog("上传菜品图片", `<form id="upload" data-id="${id}">
          <label class="field">图片（最多 5 MB）<input type="file" name="photo" accept="image/jpeg,image/png,image/webp" required></label>
          <p class="caption">JPG、PNG 或 WebP，会自动裁正方向并按比例缩小。</p>
          <p class="error" role="alert"></p><button class="button primary" type="submit">上传</button></form>`);
        break;
    }
  } catch (error) {
    notice(error.message);
  }
});

window.addEventListener("hashchange", render);
if (state.token) {
  try {
    state.user = await api("/me");
    await initUser();
    await render();
  } catch (error) {
    clearSession();
    showLogin();
    notice(error.message);
  }
} else showLogin();
