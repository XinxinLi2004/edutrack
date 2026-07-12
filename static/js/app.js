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
  const overlay = document.querySelector('.sidebar-overlay');
  if (overlay) overlay.classList.toggle('open');
}

function closeMobileMenu() {
  document.querySelector('.sidebar').classList.remove('open');
  const overlay = document.querySelector('.sidebar-overlay');
  if (overlay) overlay.classList.remove('open');
}

// 确认删除
function confirmDelete(message) {
  return confirm(message || '确定要删除吗？此操作不可恢复。');
}

// 滚动揭示动效：入场时自底部淡入，元素离开视口后不再重复
function initReveal() {
  const revealElements = document.querySelectorAll('.reveal');
  if (!revealElements.length) return;

  let observer;

  const revealOnce = (entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('in-view');
        if (observer) observer.unobserve(entry.target);
      }
    });
  };

  if ('IntersectionObserver' in window) {
    observer = new IntersectionObserver(revealOnce, {
      threshold: 0.1,
      rootMargin: '0px 0px -40px 0px'
    });
    revealElements.forEach(el => observer.observe(el));
  } else {
    // 不支持 IO 时直接全部展示
    revealElements.forEach(el => el.classList.add('in-view'));
  }

  // 2.5s 安全兜底：无论是否滚动，确保内容可见
  setTimeout(() => {
    revealElements.forEach(el => el.classList.add('in-view'));
  }, 2500);
}

// 窗口宽度变化到桌面端时关闭移动菜单
function handleResize() {
  if (window.innerWidth > 1024) {
    closeMobileMenu();
  }
}

// 初始化
document.addEventListener('DOMContentLoaded', function() {
  initTheme();
  initReveal();

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

  // 遮罩层点击关闭
  const overlay = document.querySelector('.sidebar-overlay');
  if (overlay) {
    overlay.addEventListener('click', closeMobileMenu);
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

  // 尺寸变化监听
  window.addEventListener('resize', handleResize);
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
