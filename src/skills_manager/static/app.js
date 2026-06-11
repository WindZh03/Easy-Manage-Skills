const stateFileInput = document.querySelector("#state-file");
const stateFileForm = document.querySelector("#state-file-form");
const libraryInput = document.querySelector("#library");
const libraryForm = document.querySelector("#library-form");
const summary = document.querySelector("#summary");
const searchInput = document.querySelector("#search");
const tagFilters = document.querySelector("#tag-filters");
const batchSelectToggle = document.querySelector("#batch-select-toggle");
const batchEditor = document.querySelector("#batch-editor");
const content = document.querySelector("#content");
const message = document.querySelector("#message");
const refreshButton = document.querySelector("#refresh");

const expandedProjects = new Set();
const detailCache = new Map();
const selectedProjects = new Set();
const batchTags = new Set();
let selectedTag = "";
let selectionMode = false;
let currentState = null;

const stateLabels = {
  enabled: "已启用",
  disabled: "未启用",
  missing: "链接丢失",
  conflict: "目标冲突",
  external: "外部链接",
};

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (response.status === 404 && data.error === "接口不存在") {
    throw new Error("服务仍在运行旧版本，请重启 skills-manager serve 后重试");
  }
  if (!response.ok) throw new Error(data.error || "操作失败");
  return data;
}

function setMessage(text = "", kind = "error") {
  message.textContent = text;
  message.className = text ? kind : "";
}

function createElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

async function openFolder(project, skill, button) {
  button.disabled = true;
  setMessage();
  try {
    const result = await request("/api/open-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project, skill }),
    });
    setMessage(`已打开：${result.opened}`, "success");
  } catch (error) {
    setMessage(error.message);
  } finally {
    button.disabled = false;
  }
}

function renderSummary(state) {
  const projects = state.projects || [];
  const connected = projects.filter((project) =>
    Object.values(project.agents).some((status) => status.enabled)
  ).length;
  const conflicts = projects.filter((project) =>
    Object.values(project.agents).some((status) =>
      ["conflict", "missing"].includes(status.state)
    )
  ).length;
  const items = [
    ["项目", projects.length],
    ["已连接", connected],
    ["需要处理", conflicts],
    ["标签", (state.tags || []).length],
  ];
  summary.replaceChildren();
  for (const [label, value] of items) {
    const item = createElement("div", "summary-item");
    item.append(
      createElement("strong", "", String(value)),
      createElement("span", "", label),
    );
    summary.append(item);
  }
}

function renderTagFilters(state) {
  tagFilters.replaceChildren();
  const options = ["", ...(state.tags || [])];
  for (const tag of options) {
    const button = createElement("button", "filter-chip", tag || "全部");
    button.type = "button";
    button.classList.toggle("active", tag === selectedTag);
    button.addEventListener("click", () => {
      selectedTag = tag;
      renderTagFilters(currentState);
      renderProjects();
    });
    tagFilters.append(button);
  }
}

function addBatchTag(value) {
  const tag = value.trim();
  if (!tag || batchTags.has(tag)) return;
  if (tag.length > 30) {
    setMessage("每个标签最多 30 个字符");
    return;
  }
  batchTags.add(tag);
  renderBatchEditor();
}

async function applyBatchTags(action, button) {
  if (!batchTags.size) {
    setMessage("请先选择或创建至少一个标签");
    return;
  }
  button.disabled = true;
  setMessage();
  try {
    const state = await request("/api/tags/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        projects: [...selectedProjects],
        tags: [...batchTags],
        action,
      }),
    });
    batchTags.clear();
    render(state);
    setMessage(
      `已为 ${selectedProjects.size} 个项目批量${action === "add" ? "添加" : "移除"}标签`,
      "success",
    );
  } catch (error) {
    button.disabled = false;
    setMessage(error.message);
  }
}

function renderBatchEditor() {
  batchEditor.replaceChildren();
  batchEditor.hidden = !selectionMode;
  batchSelectToggle.classList.toggle("active", selectionMode);
  batchSelectToggle.textContent = selectionMode ? "完成选择" : "批量选择";
  if (!selectionMode) return;

  const header = createElement("div", "batch-header");
  const title = createElement("div", "batch-title");
  title.append(
    createElement("span", "batch-step", "1"),
    createElement("strong", "", "选择要编辑的项目"),
    createElement("span", "batch-count", `已选择 ${selectedProjects.size} 个`),
  );
  const selectionActions = createElement("div", "batch-selection-actions");
  const selectVisible = createElement("button", "secondary", "全选当前结果");
  selectVisible.type = "button";
  selectVisible.addEventListener("click", () => {
    for (const project of currentState.projects.filter(matchesProject)) {
      selectedProjects.add(project.name);
    }
    renderBatchEditor();
    renderProjects();
  });
  const clear = createElement("button", "secondary", "清空选择");
  clear.type = "button";
  clear.addEventListener("click", () => {
    selectedProjects.clear();
    batchTags.clear();
    renderBatchEditor();
    renderProjects();
  });
  selectionActions.append(selectVisible, clear);
  header.append(title, selectionActions);

  const selectedProjectsView = createElement("div", "batch-projects");
  if (!selectedProjects.size) {
    selectedProjectsView.append(
      createElement("span", "batch-empty", "请勾选下方需要批量编辑标签的项目"),
    );
  } else {
    for (const project of selectedProjects) {
      const chip = createElement("button", "batch-project-chip", "");
      chip.type = "button";
      chip.title = `取消选择 ${project}`;
      chip.append(
        createElement("span", "", project),
        createElement("span", "tag-remove", "×"),
      );
      chip.addEventListener("click", () => {
        selectedProjects.delete(project);
        renderBatchEditor();
        renderProjects();
      });
      selectedProjectsView.append(chip);
    }
  }

  const editorHeading = createElement("div", "batch-editor-heading");
  editorHeading.append(
    createElement("span", "batch-step", "2"),
    createElement("strong", "", "设置本次操作的标签"),
    createElement("span", "batch-editor-hint", "可同时选择多个标签"),
  );

  const body = createElement("div", "batch-body");
  const tagsSection = createElement("div", "batch-tags-section");
  tagsSection.append(createElement("p", "tag-editor-label", "选择已有标签"));
  const choices = createElement("div", "batch-tag-choices");
  if (!(currentState.tags || []).length) {
    choices.append(createElement("span", "tag-editor-empty", "暂时没有已有标签"));
  } else {
    for (const tag of currentState.tags) {
      const chip = createElement("button", "batch-tag-choice", tag);
      chip.type = "button";
      chip.classList.toggle("active", batchTags.has(tag));
      chip.addEventListener("click", () => {
        if (batchTags.has(tag)) batchTags.delete(tag);
        else batchTags.add(tag);
        renderBatchEditor();
      });
      choices.append(chip);
    }
  }
  tagsSection.append(choices);

  const createSection = createElement("div", "batch-create-section");
  createSection.append(createElement("p", "tag-editor-label", "创建并选择新标签"));
  const createForm = document.createElement("form");
  createForm.className = "batch-create-form";
  const input = document.createElement("input");
  input.placeholder = "输入新标签";
  const add = createElement("button", "secondary", "加入");
  add.type = "submit";
  createForm.append(input, add);
  createForm.addEventListener("submit", (event) => {
    event.preventDefault();
    addBatchTag(input.value);
  });
  createSection.append(createForm);
  body.append(tagsSection, createSection);

  const selected = createElement("div", "batch-selected-tags");
  selected.append(createElement("span", "tag-editor-label", "本次操作标签"));
  const selectedList = createElement("div", "selected-tags");
  if (!batchTags.size) {
    selectedList.append(createElement("span", "tag-editor-empty", "请选择标签"));
  } else {
    for (const tag of batchTags) {
      const chip = createElement("button", "selected-tag", "");
      chip.type = "button";
      chip.append(
        createElement("span", "", tag),
        createElement("span", "tag-remove", "×"),
      );
      chip.addEventListener("click", () => {
        batchTags.delete(tag);
        renderBatchEditor();
      });
      selectedList.append(chip);
    }
  }
  selected.append(selectedList);

  const footer = createElement("div", "batch-footer");
  const remove = createElement("button", "danger-button", "批量移除");
  remove.type = "button";
  remove.disabled = !selectedProjects.size;
  remove.addEventListener("click", () => applyBatchTags("remove", remove));
  const addSelected = createElement("button", "", "批量添加");
  addSelected.type = "button";
  addSelected.disabled = !selectedProjects.size;
  addSelected.addEventListener("click", () => applyBatchTags("add", addSelected));
  footer.append(
    createElement("span", "field-help", "批量操作不会覆盖项目原有的其他标签。"),
    remove,
    addSelected,
  );

  batchEditor.append(
    header,
    selectedProjectsView,
    editorHeading,
    body,
    selected,
    footer,
  );
}

function agentControl(project, agent) {
  const status = project.agents[agent.id];
  const control = createElement("div", "agent-control");
  const line = createElement("label", "toggle-line");
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "toggle";
  checkbox.checked = status.enabled;
  checkbox.disabled = !status.controllable;
  checkbox.setAttribute("aria-label", `${project.name} - ${agent.label}`);
  checkbox.addEventListener("change", async () => {
    checkbox.disabled = true;
    setMessage();
    try {
      render(await request("/api/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project: project.name,
          agent: agent.id,
          enabled: checkbox.checked,
        }),
      }));
    } catch (error) {
      checkbox.checked = !checkbox.checked;
      checkbox.disabled = false;
      setMessage(error.message);
    }
  });
  line.append(checkbox, createElement("span", "", agent.label));

  const badge = createElement("span", `state ${status.state}`, stateLabels[status.state] || status.state);
  badge.title = status.detail;
  control.append(line, badge);
  return control;
}

function tagList(project) {
  const tags = createElement("div", "project-tags");
  if (!project.tags.length) {
    tags.append(createElement("span", "tag-placeholder", "尚未添加标签"));
    return tags;
  }
  for (const tag of project.tags) tags.append(createElement("span", "tag", tag));
  return tags;
}

function tagEditor(project) {
  const wrapper = createElement("div", "tag-editor");
  const selected = [...project.tags];
  const header = createElement("div", "tag-editor-header");
  const count = createElement("span", "tag-count");
  header.append(createElement("strong", "", "项目标签"), count);

  const selectedSection = createElement("div", "tag-editor-section");
  const selectedTags = createElement("div", "selected-tags");
  selectedSection.append(
    createElement("p", "tag-editor-label", "当前标签"),
    selectedTags,
  );

  const suggestionSection = createElement("div", "tag-editor-section");
  const suggestions = createElement("div", "tag-suggestions");
  suggestionSection.append(
    createElement("p", "tag-editor-label", "已有标签 · 点击添加"),
    suggestions,
  );

  const createSection = createElement("div", "tag-editor-section");
  const createForm = document.createElement("form");
  createForm.className = "tag-create-form";
  const input = document.createElement("input");
  input.placeholder = "输入新标签";
  input.setAttribute("aria-label", `${project.name} 新标签`);
  const addButton = createElement("button", "secondary", "添加");
  addButton.type = "submit";
  createForm.append(input, addButton);
  createSection.append(
    createElement("p", "tag-editor-label", "创建新标签"),
    createForm,
  );

  const footer = createElement("div", "tag-editor-footer");
  const saveButton = createElement("button", "tag-save-button", "保存更改");
  saveButton.type = "button";
  footer.append(
    createElement("span", "field-help", "最多 12 个标签，每个不超过 30 个字符。"),
    saveButton,
  );

  function addTag(value) {
    const tag = value.trim();
    if (!tag || selected.includes(tag)) return;
    if (tag.length > 30) {
      setMessage("每个标签最多 30 个字符");
      return;
    }
    if (selected.length >= 12) {
      setMessage("每个项目最多设置 12 个标签");
      return;
    }
    selected.push(tag);
    input.value = "";
    renderEditor();
  }

  function renderEditor() {
    count.textContent = `${selected.length} / 12`;
    selectedTags.replaceChildren();
    if (!selected.length) {
      selectedTags.append(createElement("span", "tag-editor-empty", "暂未选择标签"));
    } else {
      for (const tag of selected) {
        const chip = createElement("button", "selected-tag", "");
        chip.type = "button";
        chip.title = `移除 ${tag}`;
        chip.setAttribute("aria-label", `移除标签 ${tag}`);
        chip.append(
          createElement("span", "", tag),
          createElement("span", "tag-remove", "×"),
        );
        chip.addEventListener("click", () => {
          selected.splice(selected.indexOf(tag), 1);
          renderEditor();
        });
        selectedTags.append(chip);
      }
    }

    suggestions.replaceChildren();
    const available = (currentState.tags || []).filter((tag) => !selected.includes(tag));
    suggestionSection.hidden = !available.length;
    for (const tag of available) {
      const chip = createElement("button", "suggested-tag", `+ ${tag}`);
      chip.type = "button";
      chip.addEventListener("click", () => addTag(tag));
      suggestions.append(chip);
    }
  }

  createForm.addEventListener("submit", (event) => {
    event.preventDefault();
    setMessage();
    addTag(input.value);
  });

  saveButton.addEventListener("click", async () => {
    saveButton.disabled = true;
    setMessage();
    try {
      render(await request("/api/tags", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project: project.name, tags: selected }),
      }));
      setMessage("标签已保存", "success");
    } catch (error) {
      saveButton.disabled = false;
      setMessage(error.message);
    }
  });

  wrapper.append(
    header,
    selectedSection,
    suggestionSection,
    createSection,
    footer,
  );
  renderEditor();
  return wrapper;
}

function skillList(project) {
  const wrapper = createElement("div", "skill-section");
  const cached = detailCache.get(project.name);
  if (!cached) {
    wrapper.append(createElement("p", "loading", "正在扫描 SKILL.md…"));
    return wrapper;
  }
  const heading = createElement("div", "skill-heading");
  heading.append(
    createElement("strong", "", "包含的 Skills"),
    createElement("span", "", `${cached.skills.length} 个`),
  );
  wrapper.append(heading);
  if (!cached.skills.length) {
    wrapper.append(createElement("p", "empty-detail", "项目中未发现 SKILL.md。"));
    return wrapper;
  }
  const list = createElement("div", "skill-list");
  for (const skill of cached.skills) {
    const row = createElement("div", "skill-row");
    const open = createElement("button", "skill-open-button secondary", "打开");
    open.type = "button";
    open.setAttribute("aria-label", `打开 ${skill.name} 文件夹`);
    open.addEventListener("click", () => openFolder(project.name, skill.path, open));
    row.append(
      createElement("strong", "", skill.name),
      createElement("code", "", skill.path),
      open,
    );
    list.append(row);
  }
  wrapper.append(list);
  return wrapper;
}

function projectCard(project) {
  const card = createElement("article", "project-card");
  card.classList.toggle("selected", selectedProjects.has(project.name));
  card.classList.toggle("selection-mode", selectionMode);
  const top = createElement("div", "project-top");
  const identity = createElement("div", "project-identity");
  const title = createElement("div", "project-title-line");
  if (selectionMode) {
    const selection = createElement("label", "project-selection");
    const select = document.createElement("input");
    select.type = "checkbox";
    select.checked = selectedProjects.has(project.name);
    select.setAttribute("aria-label", `选择项目 ${project.name}`);
    select.addEventListener("change", () => {
      if (select.checked) selectedProjects.add(project.name);
      else selectedProjects.delete(project.name);
      renderBatchEditor();
      renderProjects();
    });
    selection.append(select);
    card.append(selection);
  }
  const open = createElement("button", "project-open-button secondary", "打开文件夹");
  open.type = "button";
  open.setAttribute("aria-label", `打开 ${project.name} 项目文件夹`);
  open.addEventListener("click", () => openFolder(project.name, null, open));
  title.append(createElement("h2", "", project.name), open);
  identity.append(
    title,
    createElement("p", "project-path", project.path),
    tagList(project),
  );

  const controls = createElement("div", "agent-controls");
  for (const agent of currentState.agents) controls.append(agentControl(project, agent));

  const expand = createElement(
    "button",
    "expand-button secondary",
    expandedProjects.has(project.name) ? "收起" : "查看 Skills",
  );
  expand.type = "button";
  expand.setAttribute("aria-expanded", String(expandedProjects.has(project.name)));
  expand.addEventListener("click", () => toggleProject(project.name));
  top.append(identity, controls, expand);
  card.append(top);

  if (expandedProjects.has(project.name)) {
    const details = createElement("div", "project-details");
    details.append(skillList(project), tagEditor(project));
    card.append(details);
  }
  return card;
}

function matchesProject(project) {
  if (selectedTag && !project.tags.includes(selectedTag)) return false;
  const query = searchInput.value.trim().toLowerCase();
  if (!query) return true;
  const details = detailCache.get(project.name);
  const values = [project.name, project.path, ...project.tags];
  if (details) {
    for (const skill of details.skills) values.push(skill.name, skill.path);
  }
  return values.some((value) => value.toLowerCase().includes(query));
}

function renderProjects() {
  content.replaceChildren();
  if (!currentState?.library_path) {
    content.append(createElement("div", "empty", "请先在设置中填写 Skills 中央目录。"));
    return;
  }
  const projects = currentState.projects.filter(matchesProject);
  if (!projects.length) {
    content.append(createElement("div", "empty", "没有符合当前筛选条件的项目。"));
    return;
  }
  for (const project of projects) content.append(projectCard(project));
}

async function toggleProject(projectName) {
  if (expandedProjects.has(projectName)) {
    expandedProjects.delete(projectName);
    renderProjects();
    return;
  }
  expandedProjects.add(projectName);
  renderProjects();
  if (detailCache.has(projectName)) return;
  try {
    const details = await request(`/api/project-details?project=${encodeURIComponent(projectName)}`);
    detailCache.set(projectName, details);
    renderProjects();
  } catch (error) {
    expandedProjects.delete(projectName);
    setMessage(error.message);
    renderProjects();
  }
}

function render(state) {
  currentState = state;
  const projectNames = new Set(state.projects.map((project) => project.name));
  for (const project of selectedProjects) {
    if (!projectNames.has(project)) selectedProjects.delete(project);
  }
  if (selectedTag && !(state.tags || []).includes(selectedTag)) selectedTag = "";
  stateFileInput.value = state.state_file_path || "";
  libraryInput.value = state.library_path || "";
  if (state.error) setMessage(state.error);
  renderSummary(state);
  renderTagFilters(state);
  renderBatchEditor();
  renderProjects();
}

async function load() {
  setMessage();
  detailCache.clear();
  expandedProjects.clear();
  selectedProjects.clear();
  batchTags.clear();
  try {
    render(await request("/api/state"));
  } catch (error) {
    setMessage(error.message);
  }
}

stateFileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage();
  detailCache.clear();
  expandedProjects.clear();
  selectedProjects.clear();
  batchTags.clear();
  selectionMode = false;
  try {
    render(await request("/api/state-file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: stateFileInput.value }),
    }));
  } catch (error) {
    setMessage(error.message);
  }
});

libraryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage();
  detailCache.clear();
  expandedProjects.clear();
  selectedProjects.clear();
  batchTags.clear();
  selectionMode = false;
  try {
    render(await request("/api/library", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: libraryInput.value }),
    }));
  } catch (error) {
    setMessage(error.message);
  }
});

searchInput.addEventListener("input", renderProjects);
batchSelectToggle.addEventListener("click", () => {
  selectionMode = !selectionMode;
  if (!selectionMode) {
    selectedProjects.clear();
    batchTags.clear();
  }
  renderBatchEditor();
  renderProjects();
});
refreshButton.addEventListener("click", load);
load();
