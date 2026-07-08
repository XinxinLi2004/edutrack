// 主题切换
function initTheme() {
  const savedTheme = localStorage.getItem('theme') || 'system';
  setTheme(savedTheme);
  updateThemeButtons(savedTheme);
}

function setTheme(theme) {
  const html = document.documentElement;
  if (theme === 'system') {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    html.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
  } else {
    html.setAttribute('data-theme', theme);
  }
  localStorage.setItem('theme', theme);
}

function updateThemeButtons(theme) {
  document.querySelectorAll('.theme-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.theme === theme);
  });
}

function toggleTheme(theme) {
  setTheme(theme);
  updateThemeButtons(theme);
}

// 移动端菜单
function toggleMobileMenu() {
  document.querySelector('.sidebar').classList.toggle('open');
}

// 确认删除
function confirmDelete(message) {
  return confirm(message || '确定要删除吗？此操作不可恢复。');
}

// 初始化
document.addEventListener('DOMContentLoaded', function() {
  initTheme();
  
  // 主题按钮事件
  document.querySelectorAll('.theme-btn').forEach(btn => {
    btn.addEventListener('click', () => toggleTheme(btn.dataset.theme));
  });
  
  // 系统主题变化监听
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    if (localStorage.getItem('theme') === 'system') {
      setTheme('system');
    }
  });
  
  // 菜单切换
  const menuToggle = document.querySelector('.menu-toggle');
  if (menuToggle) {
    menuToggle.addEventListener('click', toggleMobileMenu);
  }
  
  // 删除确认
  document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('submit', function(e) {
      const message = el.dataset.confirm;
      if (!confirmDelete(message)) {
        e.preventDefault();
      }
    });
  });
  
  // 表格行点击跳转
  document.querySelectorAll('.data-table tbody tr[data-href]').forEach(row => {
    row.style.cursor = 'pointer';
    row.addEventListener('click', function(e) {
      if (!e.target.closest('a') && !e.target.closest('button')) {
        window.location.href = row.dataset.href;
      }
    });
  });
});

// 显示 Toast 提示
function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.className = 'toast show';
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// 导出 CSV
function exportTableToCSV(tableId, filename) {
  const table = document.getElementById(tableId);
  if (!table) return;
  
  let csv = [];
  const rows = table.querySelectorAll('tr');
  
  rows.forEach(row => {
    let rowData = [];
    row.querySelectorAll('td, th').forEach(cell => {
      rowData.push('"' + cell.textContent.replace(/"/g, '""') + '"');
    });
    csv.push(rowData.join(','));
  });
  
  const csvContent = '\uFEFF' + csv.join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
}
