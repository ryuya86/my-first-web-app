// 仮想チーム司令塔 - Dashboard Application
(function () {
  'use strict';

  let orgData = null;

  // --- Data Loading ---
  async function loadOrganization() {
    const res = await fetch('./data/organization.json');
    orgData = await res.json();
    renderOrgChart();
    renderTemplateList();
    renderSkillList();
    initSimulator();
  }

  // --- Tab Switching ---
  function initTabs() {
    const links = document.querySelectorAll('[data-tab]');
    links.forEach(function (link) {
      link.addEventListener('click', function (e) {
        e.preventDefault();
        var tab = this.getAttribute('data-tab');
        switchTab(tab);
      });
    });
  }

  function switchTab(tabId) {
    document.querySelectorAll('.content-section').forEach(function (s) {
      s.classList.remove('active');
    });
    document.querySelectorAll('[data-tab]').forEach(function (l) {
      l.classList.remove('active');
    });
    var section = document.getElementById('section-' + tabId);
    if (section) section.classList.add('active');
    var link = document.querySelector('[data-tab="' + tabId + '"]');
    if (link) link.classList.add('active');
  }

  // --- Org Chart ---
  function renderOrgChart() {
    var container = document.getElementById('org-grid');
    if (!container || !orgData) return;
    container.innerHTML = '';

    orgData.departments.forEach(function (dept) {
      var card = document.createElement('div');
      card.className = 'dept-card';
      card.style.setProperty('--dept-color', dept.color);

      var header = '<div class="dept-card-header" style="background:' + dept.color + '">' +
        '<span class="' + dept.icon + '"></span> ' +
        '<span>' + dept.name_ja + '</span>' +
        '</div>';

      var agents = '<ul class="agent-list">';
      dept.agents.forEach(function (a) {
        agents += '<li class="agent-item" data-agent="' + a.id + '" data-dept="' + dept.id + '">' +
          '<span class="agent-emoji">' + a.avatar_emoji + '</span>' +
          '<div class="agent-info">' +
          '<span class="agent-name">' + a.name + '（' + a.name_ja + '）</span>' +
          '<span class="agent-role">' + a.role + '</span>' +
          '</div></li>';
      });
      agents += '</ul>';

      card.innerHTML = header + agents;
      container.appendChild(card);

      // Click agent to show detail
      card.querySelectorAll('.agent-item').forEach(function (item) {
        item.addEventListener('click', function () {
          var agentId = this.getAttribute('data-agent');
          var deptId = this.getAttribute('data-dept');
          showAgentDetail(deptId, agentId);
        });
      });
    });
  }

  function showAgentDetail(deptId, agentId) {
    var dept = orgData.departments.find(function (d) { return d.id === deptId; });
    var agent = dept.agents.find(function (a) { return a.id === agentId; });
    if (!agent) return;

    var modal = document.getElementById('agent-modal');
    var content = document.getElementById('agent-modal-content');

    var keywords = agent.keywords.map(function (k) {
      return '<span class="keyword-tag">' + k + '</span>';
    }).join('');

    var templates = agent.templates.length > 0
      ? agent.templates.map(function (t) { return '<span class="template-tag">' + t + '</span>'; }).join('')
      : '<span class="no-data">なし</span>';

    content.innerHTML =
      '<div class="modal-header" style="background:' + dept.color + '">' +
      '<span class="agent-emoji-large">' + agent.avatar_emoji + '</span>' +
      '<h2>' + agent.name + '（' + agent.name_ja + '）</h2>' +
      '<p>' + dept.name_ja + ' / ' + agent.role + '</p>' +
      '</div>' +
      '<div class="modal-body">' +
      '<h3>専門領域</h3><p>' + agent.specialty + '</p>' +
      '<h3>キーワード</h3><div class="keyword-list">' + keywords + '</div>' +
      '<h3>テンプレート</h3><div class="template-list">' + templates + '</div>' +
      '</div>';

    modal.classList.add('show');
  }

  function closeModal() {
    document.getElementById('agent-modal').classList.remove('show');
  }

  // --- Assignment Simulator ---
  function initSimulator() {
    var input = document.getElementById('sim-input');
    var btn = document.getElementById('sim-btn');
    if (!input || !btn) return;

    btn.addEventListener('click', function () {
      runSimulation(input.value);
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') runSimulation(input.value);
    });
  }

  function runSimulation(text) {
    var result = document.getElementById('sim-result');
    if (!text.trim() || !orgData) {
      result.innerHTML = '<p class="sim-placeholder">タスクを入力してください</p>';
      return;
    }

    var candidates = [];

    orgData.departments.forEach(function (dept) {
      dept.agents.forEach(function (agent) {
        var score = 0;
        agent.keywords.forEach(function (kw) {
          if (text.includes(kw)) score++;
        });
        if (score > 0) {
          candidates.push({
            agent: agent,
            dept: dept,
            score: score
          });
        }
      });
    });

    candidates.sort(function (a, b) { return b.score - a.score; });

    if (candidates.length === 0) {
      // Default to Haruto
      var defaultDept = orgData.departments.find(function (d) { return d.id === 'corporate-planning'; });
      var defaultAgent = defaultDept.agents.find(function (a) { return a.id === 'haruto'; });
      result.innerHTML =
        '<div class="sim-assignment">' +
        '<div class="sim-note">キーワードが一致しないため、デフォルトコーディネーターにアサイン</div>' +
        '<div class="sim-agent-card" style="border-left: 4px solid ' + defaultDept.color + '">' +
        '<span class="agent-emoji-large">' + defaultAgent.avatar_emoji + '</span>' +
        '<div><strong>' + defaultAgent.name + '（' + defaultAgent.name_ja + '）</strong>' +
        '<br><span class="sim-dept">' + defaultDept.name_ja + '</span> - ' + defaultAgent.role + '</div>' +
        '</div></div>';
      return;
    }

    var html = '<div class="sim-assignment">';

    // Lead
    var lead = candidates[0];
    html += '<div class="sim-label">Lead（主担当）</div>' +
      '<div class="sim-agent-card" style="border-left: 4px solid ' + lead.dept.color + '">' +
      '<span class="agent-emoji-large">' + lead.agent.avatar_emoji + '</span>' +
      '<div><strong>' + lead.agent.name + '（' + lead.agent.name_ja + '）</strong>' +
      '<br><span class="sim-dept">' + lead.dept.name_ja + '</span> - ' + lead.agent.role +
      '<br><span class="sim-score">マッチスコア: ' + lead.score + '</span></div></div>';

    // Support (remaining candidates from different departments)
    var supports = [];
    var seenDepts = {};
    seenDepts[lead.dept.id] = true;
    for (var i = 1; i < candidates.length && supports.length < 3; i++) {
      if (!seenDepts[candidates[i].dept.id]) {
        supports.push(candidates[i]);
        seenDepts[candidates[i].dept.id] = true;
      } else if (candidates[i].score === lead.score) {
        supports.push(candidates[i]);
      }
    }

    if (supports.length > 0) {
      html += '<div class="sim-label">Support（サポート）</div>';
      supports.forEach(function (s) {
        html += '<div class="sim-agent-card support" style="border-left: 4px solid ' + s.dept.color + '">' +
          '<span class="agent-emoji-large">' + s.agent.avatar_emoji + '</span>' +
          '<div><strong>' + s.agent.name + '（' + s.agent.name_ja + '）</strong>' +
          '<br><span class="sim-dept">' + s.dept.name_ja + '</span> - ' + s.agent.role +
          '<br><span class="sim-score">マッチスコア: ' + s.score + '</span></div></div>';
      });
    }

    html += '</div>';
    result.innerHTML = html;
  }

  // --- Templates List ---
  function renderTemplateList() {
    var container = document.getElementById('template-grid');
    if (!container) return;

    var templates = [
      { name: '事業計画書', icon: 'ri-file-text-line', desc: '中長期の事業計画をまとめる' },
      { name: 'YouTube企画書', icon: 'ri-youtube-line', desc: '動画コンテンツの企画書' },
      { name: 'YouTube台本', icon: 'ri-movie-line', desc: '動画の台本・スクリプト' },
      { name: 'プレスリリース', icon: 'ri-newspaper-line', desc: '公式プレスリリース' },
      { name: 'X投稿案', icon: 'ri-twitter-x-line', desc: 'X/SNSの投稿案' },
      { name: '求人票', icon: 'ri-user-add-line', desc: '採用のための求人票' },
      { name: '経費チェックリスト', icon: 'ri-money-yen-circle-line', desc: '経費精算のチェックリスト' },
      { name: '競合分析レポート', icon: 'ri-bar-chart-grouped-line', desc: '競合の分析レポート' },
      { name: 'KPIレポート', icon: 'ri-line-chart-line', desc: 'KPI進捗レポート' },
      { name: '月次振り返り', icon: 'ri-calendar-check-line', desc: '月次の振り返りレポート' },
      { name: '提案書', icon: 'ri-slideshow-line', desc: 'クライアント向け提案書' },
      { name: '見積書', icon: 'ri-calculator-line', desc: '案件の見積書' },
      { name: '契約書', icon: 'ri-file-shield-line', desc: '業務委託契約書' }
    ];

    container.innerHTML = '';
    templates.forEach(function (t) {
      var card = document.createElement('div');
      card.className = 'template-card';
      card.innerHTML = '<span class="' + t.icon + ' template-icon"></span>' +
        '<h3>' + t.name + '</h3>' +
        '<p>' + t.desc + '</p>';
      container.appendChild(card);
    });
  }

  // --- Skills List ---
  function renderSkillList() {
    var container = document.getElementById('skill-grid');
    if (!container) return;

    var skills = [
      { name: '会社概要', file: 'company-overview', icon: 'ri-building-2-line', desc: '事業内容・ミッション・ターゲット市場' },
      { name: 'CEOスタイルガイド', file: 'ceo-style-guide', icon: 'ri-user-star-line', desc: 'CEOのコミュニケーション・意思決定スタイル' },
      { name: 'ブランドガイドライン', file: 'brand-guidelines', icon: 'ri-palette-line', desc: 'トーン・ビジュアル・命名規則' },
      { name: '出力基準', file: 'output-standards', icon: 'ri-checkbox-circle-line', desc: '成果物の品質基準・フォーマット' },
      { name: 'ツールマニュアル', file: 'tools-manual', icon: 'ri-tools-line', desc: '使用ツール・連携方法' },
      { name: 'セキュリティポリシー', file: 'security-policy', icon: 'ri-shield-check-line', desc: '情報管理・機密保持' },
      { name: 'エスカレーションルール', file: 'escalation-rules', icon: 'ri-arrow-up-circle-line', desc: '自律判断 vs CEO確認の基準' },
      { name: 'コラボレーション規約', file: 'collaboration-protocol', icon: 'ri-team-line', desc: '部門横断の連携ルール' },
      { name: 'リサーチ規約', file: 'research-protocol', icon: 'ri-search-line', desc: '調査の品質基準・出典ルール' },
      { name: 'レポーティング基準', file: 'reporting-standards', icon: 'ri-file-chart-line', desc: 'レポート構成・KPI定義' }
    ];

    container.innerHTML = '';
    skills.forEach(function (s) {
      var card = document.createElement('div');
      card.className = 'skill-card';
      card.innerHTML = '<span class="' + s.icon + ' skill-icon"></span>' +
        '<h3>' + s.name + '</h3>' +
        '<p>' + s.desc + '</p>';
      container.appendChild(card);
    });
  }

  // --- Mobile Sidebar ---
  function initMobile() {
    var toggle = document.getElementById('mobile-toggle');
    var sidebar = document.querySelector('.sidebar');
    if (!toggle || !sidebar) return;

    toggle.addEventListener('click', function () {
      sidebar.classList.toggle('open');
    });

    // Close sidebar when clicking a nav link on mobile
    document.querySelectorAll('.nav-link').forEach(function (link) {
      link.addEventListener('click', function () {
        if (window.innerWidth <= 768) {
          sidebar.classList.remove('open');
        }
      });
    });
  }

  // --- Init ---
  document.addEventListener('DOMContentLoaded', function () {
    initTabs();
    initMobile();
    loadOrganization();

    // Modal close
    var modalOverlay = document.getElementById('agent-modal');
    if (modalOverlay) {
      modalOverlay.addEventListener('click', function (e) {
        if (e.target === modalOverlay) closeModal();
      });
    }
    var closeBtn = document.getElementById('modal-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', closeModal);
    }
  });
})();
