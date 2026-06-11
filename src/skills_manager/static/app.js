const stateFileInput = document.querySelector("#state-file");
const stateFileForm = document.querySelector("#state-file-form");
const libraryInput = document.querySelector("#library");
const libraryForm = document.querySelector("#library-form");
const content = document.querySelector("#content");
const message = document.querySelector("#message");
const refreshButton = document.querySelector("#refresh");

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
  if (!response.ok) throw new Error(data.error || "操作失败");
  return data;
}

function setMessage(text = "") {
  message.textContent = text;
}

function agentCell(project, agent) {
  const status = project.agents[agent.id];
  const cell = document.createElement("div");
  cell.className = "agent-cell";

  const line = document.createElement("div");
  line.className = "toggle-line";
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
      const state = await request("/api/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project: project.name,
          agent: agent.id,
          enabled: checkbox.checked,
        }),
      });
      render(state);
    } catch (error) {
      checkbox.checked = !checkbox.checked;
      checkbox.disabled = false;
      setMessage(error.message);
    }
  });

  const label = document.createElement("span");
  label.textContent = agent.label;
  line.append(checkbox, label);

  const badge = document.createElement("span");
  badge.className = `state ${status.state}`;
  badge.textContent = stateLabels[status.state] || status.state;
  badge.title = status.detail;
  cell.append(line, badge);
  return cell;
}

function render(state) {
  stateFileInput.value = state.state_file_path || "";
  libraryInput.value = state.library_path || "";
  setMessage(state.error || "");
  content.replaceChildren();

  if (!state.library_path) {
    content.innerHTML = '<div class="projects empty">请先填写 Skills 中央目录。</div>';
    return;
  }
  if (!state.projects.length) {
    content.innerHTML = '<div class="projects empty">中央目录中没有一级文件夹。</div>';
    return;
  }

  const table = document.createElement("div");
  table.className = "projects";
  const heading = document.createElement("div");
  heading.className = "project-row";
  heading.innerHTML = '<div class="agent-heading">项目</div>';
  for (const agent of state.agents) {
    const cell = document.createElement("div");
    cell.className = "agent-cell agent-heading";
    cell.textContent = `${agent.label} · ${agent.path}`;
    cell.title = agent.path;
    heading.append(cell);
  }
  table.append(heading);

  for (const project of state.projects) {
    const row = document.createElement("div");
    row.className = "project-row";
    const info = document.createElement("div");
    info.innerHTML = `<div class="project-name"></div><div class="project-path"></div>`;
    info.querySelector(".project-name").textContent = project.name;
    info.querySelector(".project-path").textContent = project.path;
    row.append(info);
    for (const agent of state.agents) row.append(agentCell(project, agent));
    table.append(row);
  }
  content.append(table);
}

async function load() {
  setMessage();
  try {
    render(await request("/api/state"));
  } catch (error) {
    setMessage(error.message);
  }
}

stateFileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage();
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

refreshButton.addEventListener("click", load);
load();
