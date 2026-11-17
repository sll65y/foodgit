export const $ = (selector, node = document) => node.querySelector(selector);
export const MEALS = { breakfast: "早餐", lunch: "午餐", dinner: "晚餐" };
export const GOALS = { maintain: "维持体重", lose: "减脂", gain: "增重" };
export const ACTIVITY = { low: "久坐", light: "轻度活动", moderate: "中度活动", high: "高活动量" };
export const FLAVORS = { 清淡: "清淡", 家常: "家常", 微辣: "微辣" };
export const NUTRIENTS = { kcal: ["能量", "kcal"], protein: ["蛋白质", "g"], carbs: ["碳水", "g"], fat: ["脂肪", "g"] };
export const escape = (value = "") => String(value).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
export const num = (n) => Number(n).toLocaleString("zh-CN", { maximumFractionDigits: 1 });
const imageUrl = (value) => /^\/images\/dish-[0-9]+\.jpg$/.test(value || "") ? escape(value) : "";
export const options = (object, current) => Object.entries(object).map(([value, name]) =>
  `<option value="${escape(value)}" ${String(current) === value ? "selected" : ""}>${escape(name)}</option>`).join("");
const empty = (title, subtitle) => `<div class="empty"><h3>${title}</h3><p>${subtitle}</p></div>`;
const head = (title, description, extra = "") => `<div class="pagehead"><div><h1>${title}</h1><p>${description}</p></div>${extra}</div>`;
const error = '<p class="error" role="alert"></p>';

export const hero = (signedIn = true) => `<section class="hero"><div class="hero-copy">
    <div class="eyebrow">${signedIn ? "MEAL PLANNING" : "SHIXU · MEAL PLANNER"}</div>
    <h1>${signedIn ? "安排适合你的一日三餐" : "给下一餐一个好计划"}</h1>
    <p>结合你的营养目标、忌口和近期餐桌记录，给出一份能看懂、能记录的饮食方案。</p>
    ${signedIn ? "" : '<div class="actions"><button class="button primary" data-action="demo">进入演示 ↗</button></div>'}
  </div><img src="/plate.svg" alt=""></section>`;

export function loginView() {
  return `${hero(false)}<section class="card login-area">
    <h2>登录工作台</h2><p class="caption">演示账号 demo · 管理员 admin · 通用密码 food-demo</p>
    <form id="login"><div class="form-grid">
      <label class="field">账号<input name="username" value="demo" autocomplete="username" maxlength="40" required></label>
      <label class="field">密码<input name="password" type="password" autocomplete="current-password" maxlength="128" required></label>
    </div>${error}<button class="button primary" type="submit">登录</button></form>
  </section>`;
}

const exclusions = (ingredients, selected = []) => `<details>
  <summary>从食材库选择忌口 <span class="caption" data-count>${selected.length ? `· ${selected.length} 项` : ""}</span></summary>
  <div class="options">${ingredients.map(({id, name}) => `<label class="choice">
    <input type="checkbox" name="exclude" value="${id}" ${selected.includes(id) ? "checked" : ""}>${escape(name)}</label>`).join("")}
  </div></details>`;

function ranges(targets) {
  return `<dl class="ranges">${Object.values(targets.ranges).map((target) => `<div><dt>${target.label}</dt>
    <dd>${num(target.min)}–${num(target.max)} ${target.unit}</dd></div>`).join("")}</dl>`;
}

function metrics(totals, bands = null) {
  return `<div class="metrics">${Object.entries(NUTRIENTS).map(([key, [label, unit]]) => {
    const range = bands?.[key];
    const outside = range && (totals[key] < range.min || totals[key] > range.max);
    return `<div class="metric"><span>${label}</span><strong>${num(totals[key])}<small>${unit}</small></strong>
      ${range ? `<em class="${outside ? "warn" : ""}">${num(range.min)}–${num(range.max)}${outside ? " · 偏离" : ""}</em>` : ""}</div>`;
  }).join("")}</div>`;
}

const glyph = {
  breakfast: '<path d="M7 20h22c0 5-4.7 9-11 9s-11-4-11-9Zm7 12h8M13 14c-3-4 4-4 2-9m5 9c-3-4 4-4 2-9m4 9c-2-3 3-4 2-7"/>',
  lunch: '<circle cx="18" cy="18" r="12"/><circle cx="18" cy="18" r="8"/><path d="M16 21c-1-4 1-7 7-8 0 5-2 8-7 8Zm0 0-3 3"/>',
  dinner: '<path d="M28 23c-7 2-15-4-15-11 0-2 .5-4 1.5-5.5a12 12 0 1 0 13.5 16.5Z M25 8v7m-3.5-3.5h7"/>',
};
function visual(dish) {
  const src = imageUrl(dish.image_url);
  return `<div class="meal-visual" data-meal="${dish.meal}">${src ? `<img src="${src}" alt="" loading="lazy">` :
    `<svg viewBox="0 0 36 36" fill="none" stroke="currentColor" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${glyph[dish.meal]}</svg>`}</div>`;
}

export function planOutput(plan) {
  if (!plan) return `<section class="card"><div class="sectionhead"><h2>本次饮食方案</h2><span class="badge">一日三餐</span></div>
    ${empty("你的三餐计划将在这里出现", "输入你今天想怎么吃，或选择一个示例开始。")}</section>`;
  const closest = plan.status === "closest";
  return `<section class="card"><div class="sectionhead"><h2>一日三餐方案</h2>
    <span class="badge ${closest ? "warning" : ""}">${closest ? "近似方案" : "营养区间达标"}</span></div>
    ${metrics(plan.totals, plan.targets.ranges)}
    ${plan.meals.map((dish) => `<article class="meal">${visual(dish)}<div>
      <p class="caption">${MEALS[dish.meal]} · ${dish.flavor}</p><h3>${escape(dish.name)}</h3>
      <p class="caption">${dish.ingredients.map((i) => escape(i.name) + " " + num(i.grams) + "g").join(" · ")}</p>
      <p class="caption">${num(dish.portions)} 份 · ${num(dish.grams)} g · ${num(dish.nutrients.kcal)} kcal</p>
    </div><button class="button" data-action="log-plan" data-meal="${dish.meal}">记一餐</button></article>`).join("")}
    </section><section class="card"><h2 class="card-title">为什么这么搭配</h2>
    <p class="caption">筛选后有 ${plan.search.eligible_dishes} 道候选菜，比较了 ${num(plan.search.combinations)} 种组合。</p>
    <ul class="explanation">${plan.explanation.map((line) => `<li>${escape(line)}</li>`).join("")}</ul></section>`;
}

export function plannerView(state) {
  const { profile, targets, ingredients, plan } = state;
  return `${hero()}<div class="layout">
    <div class="stack"><section class="card"><p class="eyebrow overline">01 / YOUR REQUEST</p><h2 class="card-title">这一餐，你想怎么吃？</h2>
      <p class="caption">可直接输入需求。留空时按个人画像规划。</p>
      <form id="plan" style="margin-top:14px">
        <label class="field">饮食需求<textarea name="message" maxlength="300" rows="3"
          placeholder="例如：清淡一点，不吃花生，想减脂">${escape(state.draft.message)}</textarea></label>
        <div class="chips" aria-label="示例需求">${["清淡一点，不吃花生", "高蛋白，微辣", "蛋奶素，不吃辣"].map((p) =>
          `<button type="button" class="chip" data-action="prompt" data-value="${p}">${p}</button>`).join("")}</div>
        <label class="choice"><input type="checkbox" name="vegetarian" ${state.draft.vegetarian ? "checked" : ""}>蛋奶素（可含蛋、奶）</label>
        ${exclusions(ingredients, state.draft.exclude)}
        ${error}
        <button class="button primary wide" type="submit">生成三餐方案 <span aria-hidden="true">↗</span></button>
      </form></section>
      <section class="card"><p class="eyebrow overline">02 / DAILY TARGETS</p>
        <div class="sectionhead"><h2>画像目标</h2><a href="#profile" class="caption">修改画像 ↗</a></div>
        <p class="caption">${GOALS[profile.goal]} · ${ACTIVITY[profile.activity]} · ${profile.preferred_flavor}</p>
        ${ranges(targets)}</section></div>
    <div id="plan-output" class="stack" aria-live="polite">${planOutput(plan)}</div>
  </div>`;
}

function pages(data, scope) {
  const max = Math.max(1, Math.ceil(data.total / data.size));
  return `<div class="pagination">
    <button class="button" data-action="page" data-scope="${scope}" data-page="${data.page - 1}" ${data.page <= 1 ? "disabled" : ""}>上一页</button>
    <span class="caption">第 ${data.page} / ${max} 页 · 共 ${data.total} 条</span>
    <button class="button" data-action="page" data-scope="${scope}" data-page="${data.page + 1}" ${data.page >= max ? "disabled" : ""}>下一页</button>
  </div>`;
}

export function catalogView(state, data) {
  const admin = state.user.role === "admin";
  return `${head("菜品库", "浏览不同餐次的菜品、食材配比与单份营养。", admin ?
    '<button class="button primary" data-action="create-dish">添加菜品</button>' : "")}
    <div class="stack"><section class="card"><form id="filter" class="filters">
      <label class="field">搜索菜名<input name="q" maxlength="48" value="${escape(state.filter.q)}" placeholder="例如：糙米饭"></label>
      <label class="field">餐次<select name="meal">${options({ "": "全部餐次", ...MEALS }, state.filter.meal)}</select></label>
      <button class="button primary" type="submit">搜索</button>
    </form></section>
    ${data.items.length ? `<div class="catalog-grid">${data.items.map((dish) => `<article class="card catalog-dish">
      ${visual(dish)}<div class="dish-copy"><span class="badge">${MEALS[dish.meal]} · ${dish.flavor}</span>
      <h3>${escape(dish.name)}</h3><p class="caption">${escape(dish.description)}</p>
      <p>${num(dish.kcal)} kcal / 份 · ${num(dish.grams)} g</p>
      <details><summary>食材与用量</summary><p class="caption">${dish.ingredients.map((i) =>
        `${escape(i.name)} ${num(i.grams)}g`).join(" · ")}</p>
        <p class="caption">蛋白质 ${num(dish.protein)}g · 碳水 ${num(dish.carbs)}g · 脂肪 ${num(dish.fat)}g</p></details>
      <div class="actions"><button class="button" data-action="log-dish" data-id="${dish.id}">记录这道菜</button>
        ${admin ? `<button class="button" data-action="image" data-id="${dish.id}">上传图片</button>` : ""}</div>
      </div></article>`).join("")}</div>` : empty("没有找到菜品", "试试其他菜名或餐次。")}
    </div>${pages(data, "catalog")}`;
}

export function profileView({profile, ingredients, targets}) {
  return `${head("个人画像", "营养目标根据当前画像计算；选择的忌口会应用到每次规划。")}
    <div class="layout"><section class="card"><h2 class="card-title">每日参考范围</h2>
      <p class="caption">静息能量估算：${num(targets.resting_energy)} kcal · 活动系数 ${targets.activity_factor}</p>
      ${ranges(targets)}</section>
    <section class="card"><form id="profile">
      <div class="form-grid">
        <label class="field">称呼<input name="display_name" maxlength="48" value="${escape(profile.display_name)}" required></label>
        <label class="field">年龄<input name="age" type="number" min="19" max="78" value="${profile.age}" required></label>
        <label class="field">计算用性别<select name="sex">${options({female:"女性", male:"男性"}, profile.sex)}</select></label>
        <label class="field">活动量<select name="activity">${options(ACTIVITY, profile.activity)}</select></label>
        <label class="field">身高 (cm)<input name="height_cm" type="number" min="130" max="220" step=".1" value="${profile.height_cm}" required></label>
        <label class="field">体重 (kg)<input name="weight_kg" type="number" min="40" max="200" step=".1" value="${profile.weight_kg}" required></label>
        <label class="field">目标<select name="goal">${options(GOALS, profile.goal)}</select></label>
        <label class="field">口味偏好<select name="preferred_flavor">${options(FLAVORS, profile.preferred_flavor)}</select></label>
      </div>
      ${exclusions(ingredients, profile.excluded_ingredients)}${error}
      <button class="button primary" type="submit">保存画像</button>
    </form></section></div>`;
}

export function recordsView(records, stats, plans) {
  const max = Math.max(1, ...stats.days.flatMap((day) => Object.values(day.meals).map((r) => r.kcal)));
  return `${head("饮食记录", "记录实际吃过的菜，了解近一周的摄入结构。", '<a href="#catalog" class="button primary">从菜品库记一餐</a>')}
  <div class="stack"><section class="card"><div class="sectionhead"><h2>近 7 天摄入汇总</h2>
    <span class="badge">${stats.recorded_days} 天有记录 · ${stats.records} 条记录</span></div>${metrics(stats.totals)}
    <div class="sectionhead" style="margin:18px 0 4px"><h3>日期 × 餐次</h3><span class="caption">格内为记录能量（kcal）</span></div>
    <div class="table-wrap"><table><thead><tr><th scope="col">日期</th>${Object.values(MEALS).map(m => `<th scope="col">${m}</th>`).join("")}
    <th scope="col">全天</th></tr></thead><tbody>
    ${[...stats.days].reverse().map((day) => `<tr><th scope="row">${day.date.slice(5)}</th>
      ${Object.values(day.meals).map((meal) => `<td class="heat"><span class="level-${meal.entries ? Math.max(1, Math.ceil(4 * meal.kcal / max)) : 0}">
      ${meal.entries ? num(meal.kcal) : "—"}</span></td>`).join("")}<td>${num(day.total.kcal)}</td></tr>`).join("")}
    </tbody></table></div></section>
  <section class="card"><h2 class="card-title">就餐明细</h2>${records.total ? `<div class="table-wrap"><table><thead>
    <tr><th>日期</th><th>餐次</th><th>菜品</th><th>份数</th><th>能量</th><th>操作</th></tr></thead><tbody>
    ${records.items.map((r) => `<tr><td>${r.eaten_on}</td><td>${MEALS[r.meal]}</td><td>${escape(r.dish_name)}</td>
      <td>${num(r.portions)}</td><td>${num(r.kcal)} kcal</td><td><button class="button plain danger" data-action="delete-record"
        data-id="${r.id}" data-value="${escape(r.dish_name)}">删除</button></td></tr>`).join("")}
    </tbody></table></div>${pages(records, "records")}` : empty("还没有就餐记录", "从已生成的饮食方案或菜品库记下实际吃过的一餐。")}</section>
  <section class="card"><h2 class="card-title">规划历史</h2>${plans.total ? `<div class="table-wrap"><table><thead>
    <tr><th>生成时间</th><th>需求</th><th>估算能量</th><th>操作</th></tr></thead><tbody>
    ${plans.items.map((p) => `<tr><td>${escape(new Date(p.created_at).toLocaleString("zh-CN", {hour12:false}))}</td>
      <td>${escape(p.request || "按画像规划")}</td><td>${num(p.totals.kcal)} kcal</td>
      <td><button class="button" data-action="open-plan" data-id="${p.id}">查看方案</button></td></tr>`).join("")}
    </tbody></table></div>${pages(plans, "plans")}` : empty("还没有生成的方案", "生成的饮食规划会自动保存。")}</section></div>`;
}

export function logForm(dish, today) {
  return `<form id="record" data-id="${dish.dish_id ?? dish.id}"><p>${escape(dish.name)}</p>
    <div class="form-grid"><label class="field">就餐日期<input name="eaten_on" type="date" value="${today}" max="${today}" required></label>
    <label class="field">餐次<select name="meal">${options(MEALS, dish.meal)}</select></label></div>
    <label class="field">实际吃了几份？<input name="portions" type="number" min=".05" max="5" step=".05" value="${dish.portions ?? 1}" required></label>
    ${error}<button class="button primary" type="submit">保存记录</button></form>`;
}

export function recipeRow(ingredients) {
  return `<div class="ingredient-row"><label class="field">食材<select name="ingredient" required>
    <option value="">选择食材</option>${options(Object.fromEntries(ingredients.map(i => [i.id, i.name])))}</select></label>
    <label class="field">克数<input name="grams" type="number" min="1" max="1000" required></label>
    <button class="button" type="button" data-action="remove-ingredient" aria-label="移除该食材">×</button></div>`;
}

export function dishForm(ingredients) {
  return `<form id="add-dish"><label class="field">菜名<input name="name" maxlength="48" required></label>
    <div class="form-grid"><label class="field">适用餐次<select name="meal">${options(MEALS)}</select></label>
    <label class="field">口味<select name="flavor">${options(FLAVORS)}</select></label></div>
    <label class="field">菜品描述<input name="description" maxlength="160"></label>
    <div id="recipe-rows" class="stack">${recipeRow(ingredients)}</div>
    <button class="button" type="button" data-action="add-ingredient">＋ 添加食材</button>
    ${error}<button class="button primary" type="submit">保存菜品</button></form>`;
}
