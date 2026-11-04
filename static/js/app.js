// Cloud-Based Lost & Found Matcher Frontend Controller
let currentUser = null;
let allItems = [];
let allMatches = [];
let currentCategory = 'all';
let currentType = 'all';
let searchQuery = '';

document.addEventListener('DOMContentLoaded', async () => {
    await checkAuth();
    setupEventListeners();
    await loadInitialData();
});

// ==========================================
// AUTHENTICATION & SESSION
// ==========================================
async function checkAuth() {
    try {
        const res = await fetch('/api/auth/me');
        const data = await res.json();
        if (data.authenticated && data.user) {
            currentUser = data.user;
            renderNavUser();
            loadNotifications();
        } else {
            currentUser = null;
            renderNavGuest();
        }
    } catch (e) {
        console.error('Auth check error:', e);
    }
}

function renderNavUser() {
    const navAuth = document.getElementById('nav-auth-container');
    const roleBadge = currentUser.role === 'admin' 
        ? '<span class="badge bg-danger ms-1">Admin</span>' 
        : '<span class="badge bg-primary ms-1">Student</span>';
        
    navAuth.innerHTML = `
        <div class="d-flex align-items-center gap-2">
            <div class="dropdown">
                <button class="btn btn-outline-dark btn-sm rounded-pill dropdown-toggle d-flex align-items-center gap-2" data-bs-toggle="dropdown">
                    <i class="bi bi-person-circle"></i>
                    <span>${escapeHtml(currentUser.name)}</span>
                    ${roleBadge}
                </button>
                <ul class="dropdown-menu dropdown-menu-end shadow">
                    <li><h6 class="dropdown-header">${escapeHtml(currentUser.email)}</h6></li>
                    <li><button class="dropdown-item" onclick="switchTab('my-reports')"><i class="bi bi-folder2 me-2"></i>My Reports & Claims</button></li>
                    ${currentUser.role === 'admin' ? '<li><button class="dropdown-item text-danger" onclick="switchTab(\'admin-panel\')"><i class="bi bi-shield-lock me-2"></i>Admin Dashboard</button></li>' : ''}
                    <li><hr class="dropdown-divider"></li>
                    <li><button class="dropdown-item text-danger" onclick="logout()"><i class="bi bi-box-arrow-right me-2"></i>Sign Out</button></li>
                </ul>
            </div>
            
            <button class="btn btn-light position-relative btn-sm rounded-circle p-2" onclick="toggleNotificationModal()">
                <i class="bi bi-bell fs-6"></i>
                <span id="nav-notif-badge" class="position-absolute top-0 start-100 translate-middle p-1 bg-danger border border-light rounded-circle d-none">
                    <span class="visually-hidden">New alerts</span>
                </span>
            </button>
        </div>
    `;
    
    // Show/hide admin tab
    const adminNavTab = document.getElementById('nav-admin-tab');
    if (adminNavTab) {
        adminNavTab.classList.toggle('d-none', currentUser.role !== 'admin');
    }
}

function renderNavGuest() {
    const navAuth = document.getElementById('nav-auth-container');
    navAuth.innerHTML = `
        <div class="d-flex align-items-center gap-2">
            <div class="dropdown">
                <button class="btn btn-outline-primary btn-sm rounded-pill dropdown-toggle" data-bs-toggle="dropdown">
                    <i class="bi bi-lightning-charge me-1"></i> Quick Demo Login
                </button>
                <ul class="dropdown-menu dropdown-menu-end shadow">
                    <li><h6 class="dropdown-header">1-Click Examiner Demo</h6></li>
                    <li><button class="dropdown-item" onclick="demoLogin('student')"><i class="bi bi-person me-2"></i>Log in as Student (Rahul)</button></li>
                    <li><button class="dropdown-item" onclick="demoLogin('admin')"><i class="bi bi-shield-check me-2"></i>Log in as Admin (Campus)</button></li>
                </ul>
            </div>
            <button class="btn btn-primary btn-sm rounded-pill px-3" onclick="openLoginModal()">Sign In</button>
        </div>
    `;
    const adminNavTab = document.getElementById('nav-admin-tab');
    if (adminNavTab) adminNavTab.classList.add('d-none');
}

async function demoLogin(role) {
    try {
        const res = await fetch('/api/auth/demo-login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role })
        });
        const data = await res.json();
        if (data.success) {
            currentUser = data.user;
            renderNavUser();
            showToast('success', data.message);
            await loadInitialData();
        } else {
            showToast('danger', data.detail || 'Demo login failed');
        }
    } catch (e) {
        showToast('danger', 'Error performing demo login');
    }
}

async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    currentUser = null;
    renderNavGuest();
    switchTab('browse');
    showToast('info', 'Signed out successfully.');
    await loadInitialData();
}

// ==========================================
// DATA LOADING & TAB NAVIGATION
// ==========================================
async function loadInitialData() {
    await Promise.all([
        loadItems(),
        loadMatches(),
        loadAdminStats()
    ]);
}

async function loadItems() {
    try {
        let url = `/api/items?type=${currentType === 'all' ? '' : currentType}&category=${currentCategory}&query=${encodeURIComponent(searchQuery)}`;
        const res = await fetch(url);
        const data = await res.json();
        if (data.success) {
            allItems = data.items;
            renderItemsFeed(allItems);
        }
    } catch (e) {
        console.error('Error loading items:', e);
    }
}

async function loadMatches() {
    try {
        const res = await fetch('/api/matches?min_score=50.0');
        const data = await res.json();
        if (data.success) {
            allMatches = data.matches;
            renderMatchesFeed(allMatches);
            updateMatchCounter(allMatches.length);
        }
    } catch (e) {
        console.error('Error loading matches:', e);
    }
}

async function loadAdminStats() {
    try {
        const res = await fetch('/api/admin/stats');
        if (res.ok) {
            const data = await res.json();
            if (data.success) {
                renderHeroStats(data.stats);
                renderCloudStatusWidget(data.cloud);
            }
        }
    } catch (e) {
        // user might not be admin
    }
}

function renderHeroStats(stats) {
    document.getElementById('stat-lost-count').innerText = stats.total_lost;
    document.getElementById('stat-found-count').innerText = stats.total_found;
    document.getElementById('stat-matches-count').innerText = stats.total_matches;
    document.getElementById('stat-resolved-count').innerText = stats.resolved_items;
}

function updateMatchCounter(count) {
    const badge = document.getElementById('tab-matches-badge');
    if (badge) badge.innerText = count;
}

// ==========================================
// RENDER ITEMS FEED
// ==========================================
function renderItemsFeed(items) {
    const container = document.getElementById('items-grid-container');
    if (!items || items.length === 0) {
        container.innerHTML = `
            <div class="col-12 text-center py-5">
                <i class="bi bi-inbox fs-1 text-muted"></i>
                <h5 class="mt-3 text-secondary">No reports match your filters</h5>
                <p class="text-muted">Try clearing the search or category filters, or report a new item.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = items.map(item => {
        const isLost = item.type === 'lost';
        const typeBadge = isLost 
            ? `<span class="badge-status badge-lost"><i class="bi bi-question-circle me-1"></i>LOST</span>`
            : `<span class="badge-status badge-found"><i class="bi bi-check2-circle me-1"></i>FOUND</span>`;
            
        const imgUrl = item.image_url || '/static/img/placeholder.svg';
        
        return `
            <div class="col-md-6 col-lg-4 col-xl-3 mb-4">
                <div class="item-card shadow-sm">
                    <div class="item-card-img-wrap">
                        ${typeBadge}
                        <span class="badge-category text-capitalize">${escapeHtml(item.category)}</span>
                        <img src="${imgUrl}" alt="${escapeHtml(item.title)}" onerror="this.src='https://placehold.co/400x300/e2e8f0/475569?text=${encodeURIComponent(item.title)}'">
                    </div>
                    <div class="p-3 d-flex flex-column flex-grow-1">
                        <div class="d-flex justify-content-between align-items-start mb-1">
                            <h6 class="fw-bold mb-0 text-truncate" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</h6>
                        </div>
                        <p class="text-muted small mb-2 text-truncate-2" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:38px;">
                            ${escapeHtml(item.description)}
                        </p>
                        
                        <div class="mt-auto pt-2 border-top">
                            <div class="d-flex align-items-center text-muted small mb-1">
                                <i class="bi bi-geo-alt me-1 text-danger"></i>
                                <span class="text-truncate">${escapeHtml(item.location)}</span>
                            </div>
                            <div class="d-flex align-items-center justify-content-between text-muted small">
                                <span><i class="bi bi-calendar3 me-1"></i>${escapeHtml(item.item_date)}</span>
                                ${item.brand ? `<span class="badge bg-light text-dark border">${escapeHtml(item.brand)}</span>` : ''}
                            </div>
                        </div>

                        <div class="mt-3 pt-2 d-flex gap-2">
                            <button class="btn btn-sm btn-outline-primary flex-grow-1" onclick="viewItemDetails('${item.id}')">
                                <i class="bi bi-eye me-1"></i> Details
                            </button>
                            <button class="btn btn-sm btn-light border" onclick="findMatchesFor('${item.id}')" title="Scan Matches">
                                <i class="bi bi-search-heart text-primary"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// ==========================================
// RENDER SMART MATCHES FEED ⭐
// ==========================================
function renderMatchesFeed(matches) {
    const container = document.getElementById('matches-list-container');
    if (!matches || matches.length === 0) {
        container.innerHTML = `
            <div class="text-center py-5 bg-white rounded-3 shadow-sm border p-4">
                <i class="bi bi-lightning-charge fs-1 text-warning"></i>
                <h5 class="mt-3">No Potential Matches Above 50% Threshold Yet</h5>
                <p class="text-muted">The AI Matching Engine scans automatically when students submit lost or found reports.</p>
                <button class="btn btn-primary btn-sm rounded-pill" onclick="rerunEngine()">
                    <i class="bi bi-arrow-clockwise me-1"></i> Recalculate Matching Engine
                </button>
            </div>
        `;
        return;
    }

    container.innerHTML = matches.map(m => {
        const score = m.overall_score;
        let gaugeClass = 'gauge-low';
        let confidenceBadge = '<span class="badge bg-secondary">Moderate Match</span>';
        
        if (score >= 80) {
            gaugeClass = 'gauge-high';
            confidenceBadge = '<span class="badge bg-success">High Confidence Match (>=80%)</span>';
        } else if (score >= 65) {
            gaugeClass = 'gauge-moderate';
            confidenceBadge = '<span class="badge bg-warning text-dark">Likely Match (65-79%)</span>';
        }

        const exp = m.explanation || {};
        const lostImg = m.lost_image || 'https://placehold.co/100x100/e2e8f0/475569?text=Lost';
        const foundImg = m.found_image || 'https://placehold.co/100x100/e2e8f0/475569?text=Found';

        return `
            <div class="match-card">
                <div class="row align-items-center">
                    <!-- Score Meter -->
                    <div class="col-md-2 text-center mb-3 mb-md-0">
                        <div class="match-gauge-circle ${gaugeClass} mx-auto">
                            <span class="fs-4 mb-0">${score}%</span>
                            <span style="font-size: 0.65rem; opacity: 0.85;">MATCH</span>
                        </div>
                        <div class="mt-2">${confidenceBadge}</div>
                    </div>

                    <!-- Comparison Summary -->
                    <div class="col-md-7 mb-3 mb-md-0">
                        <div class="row g-2 align-items-center">
                            <!-- Lost item preview -->
                            <div class="col-6 border-end pe-3">
                                <div class="d-flex align-items-center gap-2">
                                    <img src="${lostImg}" class="rounded" style="width: 48px; height: 48px; object-fit: cover;">
                                    <div class="overflow-hidden">
                                        <span class="badge-lost small px-2 py-0">LOST REPORT</span>
                                        <h6 class="mb-0 text-truncate fw-bold mt-1">${escapeHtml(m.lost_title)}</h6>
                                        <div class="small text-muted text-truncate"><i class="bi bi-geo-alt"></i> ${escapeHtml(m.lost_location)}</div>
                                    </div>
                                </div>
                            </div>
                            <!-- Found item preview -->
                            <div class="col-6 ps-3">
                                <div class="d-flex align-items-center gap-2">
                                    <img src="${foundImg}" class="rounded" style="width: 48px; height: 48px; object-fit: cover;">
                                    <div class="overflow-hidden">
                                        <span class="badge-found small px-2 py-0">FOUND REPORT</span>
                                        <h6 class="mb-0 text-truncate fw-bold mt-1">${escapeHtml(m.found_title)}</h6>
                                        <div class="small text-muted text-truncate"><i class="bi bi-geo-alt"></i> ${escapeHtml(m.found_location)}</div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Mini Factor Bars -->
                        <div class="row mt-3 g-2 text-muted small">
                            <div class="col-3">
                                <div class="d-flex justify-content-between"><span>Text:</span> <b>${m.text_score}%</b></div>
                                <div class="factor-bar-container"><div class="factor-bar-fill bg-primary" style="width: ${m.text_score}%"></div></div>
                            </div>
                            <div class="col-3">
                                <div class="d-flex justify-content-between"><span>Location:</span> <b>${m.location_score}%</b></div>
                                <div class="factor-bar-container"><div class="factor-bar-fill bg-info" style="width: ${m.location_score}%"></div></div>
                            </div>
                            <div class="col-3">
                                <div class="d-flex justify-content-between"><span>Date:</span> <b>${m.date_score}%</b></div>
                                <div class="factor-bar-container"><div class="factor-bar-fill bg-warning" style="width: ${m.date_score}%"></div></div>
                            </div>
                            <div class="col-3">
                                <div class="d-flex justify-content-between"><span>Visual:</span> <b>${m.image_score !== null ? m.image_score + '%' : 'N/A'}</b></div>
                                <div class="factor-bar-container"><div class="factor-bar-fill bg-success" style="width: ${m.image_score || 0}%"></div></div>
                            </div>
                        </div>
                    </div>

                    <!-- Actions -->
                    <div class="col-md-3 text-md-end">
                        <button class="btn btn-outline-primary btn-sm mb-2 w-100" onclick="openMatchDetailModal('${m.id}')">
                            <i class="bi bi-bar-chart-fill me-1"></i> Inspect Breakdown
                        </button>
                        <button class="btn btn-success btn-sm w-100" onclick="openClaimModal('${m.id}')">
                            <i class="bi bi-check-circle me-1"></i> Claim / Confirm Item
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function viewItemDetails(itemId) {
    const item = allItems.find(x => x.id === itemId);
    if (!item) return;

    const modalBody = document.getElementById('item-modal-body');
    const isLost = item.type === 'lost';
    const badge = isLost 
        ? '<span class="badge bg-danger">LOST REPORT</span>' 
        : '<span class="badge bg-success">FOUND REPORT</span>';

    modalBody.innerHTML = `
        <div class="row g-4">
            <div class="col-md-5 text-center">
                <img src="${item.image_url || '/static/img/placeholder.svg'}" class="img-fluid rounded shadow-sm mb-3" style="max-height: 240px; width: 100%; object-fit: cover;">
                <div>${badge}</div>
                <div class="text-muted small mt-1 text-capitalize">Category: <b>${escapeHtml(item.category)}</b></div>
            </div>
            <div class="col-md-7">
                <h4 class="fw-bold mb-1">${escapeHtml(item.title)}</h4>
                <div class="text-muted small mb-3"><i class="bi bi-geo-alt-fill text-danger me-1"></i>${escapeHtml(item.location)}</div>
                
                <div class="p-3 bg-light rounded-3 mb-3">
                    <h6 class="fw-bold mb-1 small text-uppercase text-muted">Item Description</h6>
                    <p class="mb-0 small">${escapeHtml(item.description)}</p>
                </div>

                <div class="row g-2 small mb-3">
                    <div class="col-6"><b>Brand:</b> ${escapeHtml(item.brand || 'Unspecified')}</div>
                    <div class="col-6"><b>Color:</b> ${escapeHtml(item.color || 'Unspecified')}</div>
                    <div class="col-6"><b>Date:</b> ${escapeHtml(item.item_date)}</div>
                    <div class="col-6"><b>Status:</b> <span class="badge bg-secondary">${escapeHtml(item.status)}</span></div>
                    ${item.safekeeping_location ? `<div class="col-12 mt-2"><b>Safekeeping:</b> <span class="badge bg-info text-dark">${escapeHtml(item.safekeeping_location)}</span></div>` : ''}
                </div>

                <div class="border-top pt-2 text-muted small">
                    Reported by: <b>${escapeHtml(item.user_name)}</b> (${escapeHtml(item.user_email)})
                </div>
            </div>
        </div>
    `;

    document.getElementById('item-modal-scan-btn').onclick = () => {
        bootstrap.Modal.getInstance(document.getElementById('itemDetailModal')).hide();
        findMatchesFor(itemId);
    };

    const modal = new bootstrap.Modal(document.getElementById('itemDetailModal'));
    modal.show();
}

function findMatchesFor(itemId) {
    const item = allItems.find(x => x.id === itemId);
    if (!item) return;

    switchTab('matches');
    
    // Filter matches that involve this item
    const related = allMatches.filter(m => m.lost_item_id === itemId || m.found_item_id === itemId);
    renderMatchesFeed(related);
    showToast('info', `Displaying ${related.length} match(es) for '${item.title}'`);
}

// ==========================================
// DETAILED MATCH MODAL BREAKDOWN
// ==========================================
function openMatchDetailModal(matchId) {
    const m = allMatches.find(x => x.id === matchId);
    if (!m) return;

    const modalBody = document.getElementById('match-modal-body');
    const breakdown = m.explanation || {};
    
    modalBody.innerHTML = `
        <div class="row g-4">
            <!-- Lost Item Side -->
            <div class="col-md-6 border-end">
                <div class="p-3 bg-light rounded-3">
                    <span class="badge bg-danger mb-2">LOST REPORT</span>
                    <h5 class="fw-bold">${escapeHtml(m.lost_title)}</h5>
                    <img src="${m.lost_image || 'https://placehold.co/400x250'}" class="img-fluid rounded mb-3" style="max-height: 200px; width: 100%; object-fit: cover;">
                    <p class="small text-secondary mb-2">${escapeHtml(m.lost_description)}</p>
                    <ul class="list-unstyled small mb-0">
                        <li><b>Location:</b> ${escapeHtml(m.lost_location)}</li>
                        <li><b>Date:</b> ${escapeHtml(m.lost_date)}</li>
                        <li><b>Brand/Color:</b> ${escapeHtml(m.lost_brand || 'N/A')} / ${escapeHtml(m.lost_color || 'N/A')}</li>
                        <li><b>Reported By:</b> ${escapeHtml(m.lost_user_name)}</li>
                    </ul>
                </div>
            </div>

            <!-- Found Item Side -->
            <div class="col-md-6">
                <div class="p-3 bg-light rounded-3">
                    <span class="badge bg-success mb-2">FOUND REPORT</span>
                    <h5 class="fw-bold">${escapeHtml(m.found_title)}</h5>
                    <img src="${m.found_image || 'https://placehold.co/400x250'}" class="img-fluid rounded mb-3" style="max-height: 200px; width: 100%; object-fit: cover;">
                    <p class="small text-secondary mb-2">${escapeHtml(m.found_description)}</p>
                    <ul class="list-unstyled small mb-0">
                        <li><b>Location Found:</b> ${escapeHtml(m.found_location)}</li>
                        <li><b>Date Found:</b> ${escapeHtml(m.found_date)}</li>
                        <li><b>Brand/Color:</b> ${escapeHtml(m.found_brand || 'N/A')} / ${escapeHtml(m.found_color || 'N/A')}</li>
                        <li><b>Safekeeping At:</b> ${escapeHtml(m.found_safekeeping || 'Not specified')}</li>
                        <li><b>Found By:</b> ${escapeHtml(m.found_user_name)}</li>
                    </ul>
                </div>
            </div>
        </div>

        <!-- Factor Breakdown Table & Visualization -->
        <div class="mt-4 p-3 border rounded-3 bg-white">
            <h6 class="fw-bold mb-3 d-flex align-items-center justify-content-between">
                <span><i class="bi bi-cpu me-2 text-primary"></i> Multi-Factor Cloud Matching Breakdown</span>
                <span class="badge bg-primary fs-6">${m.overall_score}% Match Score</span>
            </h6>
            
            <table class="table table-sm table-bordered align-middle">
                <thead class="table-light">
                    <tr>
                        <th>Matching Factor</th>
                        <th>Algorithm Applied</th>
                        <th>Calculated Score</th>
                        <th>Score Meter</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><b>Item Description & Title</b></td>
                        <td class="small text-muted">TF-IDF Vectorizer + Cosine Similarity & Token Jaccard</td>
                        <td><span class="badge bg-primary">${m.text_score}%</span></td>
                        <td><div class="progress" style="height: 10px;"><div class="progress-bar bg-primary" style="width: ${m.text_score}%"></div></div></td>
                    </tr>
                    <tr>
                        <td><b>Location Proximity</b></td>
                        <td class="small text-muted">Campus Zone Semantics & Token Invariance</td>
                        <td><span class="badge bg-info text-dark">${m.location_score}%</span></td>
                        <td><div class="progress" style="height: 10px;"><div class="progress-bar bg-info" style="width: ${m.location_score}%"></div></div></td>
                    </tr>
                    <tr>
                        <td><b>Date & Time Proximity</b></td>
                        <td class="small text-muted">Temporal Loss-to-Discovery Decay Window</td>
                        <td><span class="badge bg-warning text-dark">${m.date_score}%</span></td>
                        <td><div class="progress" style="height: 10px;"><div class="progress-bar bg-warning" style="width: ${m.date_score}%"></div></div></td>
                    </tr>
                    <tr>
                        <td><b>Brand & Color Similarity</b></td>
                        <td class="small text-muted">Canonical Brand Normalization & Color Family Mapping</td>
                        <td><span class="badge bg-secondary">${m.brand_color_score}%</span></td>
                        <td><div class="progress" style="height: 10px;"><div class="progress-bar bg-secondary" style="width: ${m.brand_color_score}%"></div></div></td>
                    </tr>
                    <tr>
                        <td><b>Visual Image Similarity</b></td>
                        <td class="small text-muted">64-bit Perceptual dHash + RGB Color Distribution</td>
                        <td><span class="badge bg-success">${m.image_score !== null ? m.image_score + '%' : 'N/A (No Photos)'}</span></td>
                        <td><div class="progress" style="height: 10px;"><div class="progress-bar bg-success" style="width: ${m.image_score || 0}%"></div></div></td>
                    </tr>
                </tbody>
            </table>
        </div>
    `;

    const modal = new bootstrap.Modal(document.getElementById('matchDetailModal'));
    modal.show();
}

// ==========================================
// LIVE SIMULATOR FOR VIVA & DEMO
// ==========================================
async function runLiveSimulator() {
    const payload = {
        lost_title: document.getElementById('sim-lost-title').value,
        lost_description: document.getElementById('sim-lost-desc').value,
        lost_location: document.getElementById('sim-lost-loc').value,
        lost_date: document.getElementById('sim-lost-date').value,
        lost_brand: document.getElementById('sim-lost-brand').value,
        lost_color: document.getElementById('sim-lost-color').value,
        
        found_title: document.getElementById('sim-found-title').value,
        found_description: document.getElementById('sim-found-desc').value,
        found_location: document.getElementById('sim-found-loc').value,
        found_date: document.getElementById('sim-found-date').value,
        found_brand: document.getElementById('sim-found-brand').value,
        found_color: document.getElementById('sim-found-color').value
    };

    try {
        const res = await fetch('/api/matches/test-simulator', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            renderSimulatorResults(data.calculation);
        }
    } catch (e) {
        showToast('danger', 'Error calculating simulator score');
    }
}

function renderSimulatorResults(calc) {
    const resultBox = document.getElementById('sim-result-box');
    resultBox.classList.remove('d-none');
    
    document.getElementById('sim-score-total').innerText = `${calc.overall_score}%`;
    document.getElementById('sim-score-text').innerText = `${calc.text_score}%`;
    document.getElementById('sim-score-loc').innerText = `${calc.location_score}%`;
    document.getElementById('sim-score-date').innerText = `${calc.date_score}%`;
    document.getElementById('sim-score-brand').innerText = `${calc.brand_color_score}%`;
    
    const badge = document.getElementById('sim-score-badge');
    if (calc.overall_score >= 80) {
        badge.className = 'badge bg-success';
        badge.innerText = 'High Confidence Match';
    } else if (calc.overall_score >= 65) {
        badge.className = 'badge bg-warning text-dark';
        badge.innerText = 'Moderate Match';
    } else {
        badge.className = 'badge bg-secondary';
        badge.innerText = 'Low Match (<65%)';
    }
}

// Preset test cases for simulator
function loadSimulatorPreset(type) {
    if (type === 'earbuds') {
        document.getElementById('sim-lost-title').value = 'Black Samsung earbud case';
        document.getElementById('sim-lost-desc').value = 'Samsung Galaxy Buds black case lost near library';
        document.getElementById('sim-lost-loc').value = 'College Library';
        document.getElementById('sim-lost-date').value = '2026-08-18';
        document.getElementById('sim-lost-brand').value = 'Samsung';
        document.getElementById('sim-lost-color').value = 'Black';

        document.getElementById('sim-found-title').value = 'Black wireless-earbud case';
        document.getElementById('sim-found-desc').value = 'Black wireless earbud case found outside library entrance';
        document.getElementById('sim-found-loc').value = 'Outside the library';
        document.getElementById('sim-found-date').value = '2026-08-18';
        document.getElementById('sim-found-brand').value = 'Samsung';
        document.getElementById('sim-found-color').value = 'Black';
    } else if (type === 'wallet') {
        document.getElementById('sim-lost-title').value = 'Wallet';
        document.getElementById('sim-lost-desc').value = 'Brown leather wallet with three cards';
        document.getElementById('sim-lost-loc').value = 'College Library';
        document.getElementById('sim-lost-date').value = '2026-08-18';
        document.getElementById('sim-lost-brand').value = 'Wildcraft';
        document.getElementById('sim-lost-color').value = 'Brown';

        document.getElementById('sim-found-title').value = 'Wallet';
        document.getElementById('sim-found-desc').value = 'Brown wallet found near reading section';
        document.getElementById('sim-found-loc').value = 'Library';
        document.getElementById('sim-found-date').value = '2026-08-18';
        document.getElementById('sim-found-brand').value = 'Wildcraft';
        document.getElementById('sim-found-color').value = 'Brown';
    } else if (type === 'bottle') {
        document.getElementById('sim-lost-title').value = 'Blue water bottle';
        document.getElementById('sim-lost-desc').value = 'Blue insulated bottle left in canteen';
        document.getElementById('sim-lost-loc').value = 'College Canteen';
        document.getElementById('sim-lost-date').value = '2026-08-19';
        document.getElementById('sim-lost-brand').value = 'Milton';
        document.getElementById('sim-lost-color').value = 'Blue';

        document.getElementById('sim-found-title').value = 'Blue Milton bottle';
        document.getElementById('sim-found-desc').value = 'Blue bottle found on lunch table';
        document.getElementById('sim-found-loc').value = 'Canteen';
        document.getElementById('sim-found-date').value = '2026-08-19';
        document.getElementById('sim-found-brand').value = 'Milton';
        document.getElementById('sim-found-color').value = 'Blue';
    }
    runLiveSimulator();
}

// ==========================================
// CLAIM WORKFLOW
// ==========================================
function openClaimModal(matchId) {
    if (!currentUser) {
        showToast('warning', 'Please sign in or use 1-Click Demo Login to claim an item.');
        openLoginModal();
        return;
    }
    document.getElementById('claim-match-id').value = matchId;
    const modal = new bootstrap.Modal(document.getElementById('claimModal'));
    modal.show();
}

async function submitClaimForm(e) {
    e.preventDefault();
    const matchId = document.getElementById('claim-match-id').value;
    const proofDetails = document.getElementById('claim-proof-details').value;
    const contactInfo = document.getElementById('claim-contact-info').value;

    try {
        const res = await fetch('/api/claims/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                match_id: matchId,
                proof_details: proofDetails,
                contact_info: contactInfo
            })
        });
        const data = await res.json();
        if (data.success) {
            bootstrap.Modal.getInstance(document.getElementById('claimModal')).hide();
            showToast('success', data.message);
            await loadInitialData();
        } else {
            showToast('danger', data.detail || 'Failed to submit claim.');
        }
    } catch (err) {
        showToast('danger', 'Error submitting claim.');
    }
}

// ==========================================
// REPORT ITEM SUBMISSIONS
// ==========================================
async function submitReportLost(e) {
    e.preventDefault();
    if (!currentUser) {
        showToast('warning', 'Please sign in to report a lost item.');
        openLoginModal();
        return;
    }

    const form = document.getElementById('report-lost-form');
    const formData = new FormData(form);

    try {
        const res = await fetch('/api/items/report-lost', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            form.reset();
            bootstrap.Modal.getInstance(document.getElementById('reportLostModal')).hide();
            showToast('success', `${data.message}`);
            await loadInitialData();
            if (data.matched_count > 0) {
                switchTab('matches');
            }
        } else {
            showToast('danger', data.detail || 'Submission failed');
        }
    } catch (e) {
        showToast('danger', 'Error submitting lost report');
    }
}

async function submitReportFound(e) {
    e.preventDefault();
    if (!currentUser) {
        showToast('warning', 'Please sign in to report a found item.');
        openLoginModal();
        return;
    }

    const form = document.getElementById('report-found-form');
    const formData = new FormData(form);

    try {
        const res = await fetch('/api/items/report-found', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            form.reset();
            bootstrap.Modal.getInstance(document.getElementById('reportFoundModal')).hide();
            showToast('success', `${data.message}`);
            await loadInitialData();
            if (data.matched_count > 0) {
                switchTab('matches');
            }
        } else {
            showToast('danger', data.detail || 'Submission failed');
        }
    } catch (e) {
        showToast('danger', 'Error submitting found report');
    }
}

// ==========================================
// ADMIN DASHBOARD & CLOUD SYNC
// ==========================================
function renderCloudStatusWidget(cloud) {
    const el = document.getElementById('cloud-status-badge');
    const latencyEl = document.getElementById('cloud-latency-text');
    if (!el) return;

    if (cloud && cloud.connected) {
        el.className = 'cloud-badge-online';
        el.innerHTML = '<i class="bi bi-cloud-check-fill me-1"></i> Supabase Cloud Active';
        if (latencyEl) latencyEl.innerText = `${cloud.latency_ms} ms`;
    } else {
        el.className = 'cloud-badge-offline';
        el.innerHTML = '<i class="bi bi-cloud-slash me-1"></i> Local Cloud-Ready Mode';
        if (latencyEl) latencyEl.innerText = 'Local SQLite';
    }
}

async function testSupabaseConnection() {
    try {
        const res = await fetch('/api/admin/cloud-status');
        const data = await res.json();
        if (data.success) {
            renderCloudStatusWidget(data.cloud);
            showToast('info', data.cloud.message);
        }
    } catch (e) {
        showToast('danger', 'Failed to test Supabase cloud connection');
    }
}

async function syncLocalToSupabase() {
    try {
        showToast('info', 'Synchronizing reports and matches to Supabase Cloud...');
        const res = await fetch('/api/admin/cloud-sync', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast('success', data.message);
        } else {
            showToast('danger', data.detail || 'Sync failed');
        }
    } catch (e) {
        showToast('danger', 'Error executing cloud sync');
    }
}

async function rerunEngine() {
    try {
        showToast('info', 'Running Matching Engine across all reports...');
        const res = await fetch('/api/matches/rerun', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast('success', data.message);
            await loadMatches();
        }
    } catch (e) {
        showToast('danger', 'Error rerunning matching engine');
    }
}

async function deleteReportAsAdmin(itemId) {
    if (!confirm('Are you sure you want to remove this report as spam/fake?')) return;
    try {
        const res = await fetch(`/api/admin/items/${itemId}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            showToast('success', data.message);
            await loadInitialData();
        } else {
            showToast('danger', data.detail || 'Deletion failed');
        }
    } catch (e) {
        showToast('danger', 'Error deleting report');
    }
}

// ==========================================
// NOTIFICATIONS
// ==========================================
async function loadNotifications() {
    if (!currentUser) return;
    try {
        const res = await fetch('/api/notifications');
        const data = await res.json();
        if (data.success) {
            const badge = document.getElementById('nav-notif-badge');
            if (badge) {
                if (data.unread_count > 0) {
                    badge.classList.remove('d-none');
                } else {
                    badge.classList.add('d-none');
                }
            }
            renderNotificationList(data.notifications);
        }
    } catch (e) {}
}

function renderNotificationList(notifs) {
    const list = document.getElementById('notif-modal-list');
    if (!list) return;

    if (!notifs || notifs.length === 0) {
        list.innerHTML = '<li class="list-group-item text-center text-muted py-4">No notifications yet</li>';
        return;
    }

    list.innerHTML = notifs.map(n => `
        <li class="list-group-item p-3 ${n.read_status ? '' : 'bg-light'}">
            <div class="d-flex justify-content-between align-items-center mb-1">
                <h6 class="fw-bold mb-0">${escapeHtml(n.title)}</h6>
                ${n.score ? `<span class="badge bg-primary">${n.score}% Match</span>` : ''}
            </div>
            <p class="small text-secondary mb-1">${escapeHtml(n.message)}</p>
            <span class="text-muted" style="font-size: 0.75rem;">${new Date(n.created_at).toLocaleString()}</span>
        </li>
    `).join('');
}

function toggleNotificationModal() {
    const modal = new bootstrap.Modal(document.getElementById('notificationModal'));
    modal.show();
    // Mark read
    fetch('/api/notifications/mark-read', { method: 'POST' });
    const badge = document.getElementById('nav-notif-badge');
    if (badge) badge.classList.add('d-none');
}

// ==========================================
// UTILITY FUNCTIONS & EVENT LISTENERS
// ==========================================
function switchTab(tabId) {
    document.querySelectorAll('.tab-content-pane').forEach(el => el.classList.add('d-none'));
    document.querySelectorAll('.nav-link-tab').forEach(el => el.classList.remove('active'));

    const targetPane = document.getElementById(`tab-pane-${tabId}`);
    const targetLink = document.getElementById(`tab-link-${tabId}`);
    
    if (targetPane) targetPane.classList.remove('d-none');
    if (targetLink) targetLink.classList.add('active');

    if (tabId === 'admin-panel') {
        loadAdminTableReports();
    } else if (tabId === 'my-reports') {
        loadMyReports();
    }
}

async function loadMyReports() {
    if (!currentUser) {
        showToast('warning', 'Please sign in to view your reports.');
        openLoginModal();
        return;
    }

    try {
        // Load items
        const res = await fetch('/api/items?my_items=true');
        const data = await res.json();
        const container = document.getElementById('my-items-grid');
        
        if (data.success && data.items.length > 0) {
            container.innerHTML = data.items.map(it => `
                <div class="col-md-6 col-lg-4 mb-3">
                    <div class="card h-100 shadow-sm border">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <span class="badge ${it.type === 'lost' ? 'bg-danger' : 'bg-success'} text-uppercase">${it.type}</span>
                                <span class="badge bg-secondary">${it.status}</span>
                            </div>
                            <h6 class="fw-bold mb-1">${escapeHtml(it.title)}</h6>
                            <p class="small text-muted mb-2 text-truncate">${escapeHtml(it.description)}</p>
                            <div class="small text-muted mb-3"><i class="bi bi-geo-alt me-1"></i>${escapeHtml(it.location)}</div>
                            <button class="btn btn-sm btn-outline-primary w-100" onclick="findMatchesFor('${it.id}')">
                                <i class="bi bi-search me-1"></i> Scan Matches
                            </button>
                        </div>
                    </div>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<div class="col-12 text-center text-muted py-4">You have not submitted any reports yet.</div>';
        }

        // Load claims
        const cRes = await fetch('/api/claims');
        const cData = await cRes.json();
        const cTbody = document.getElementById('my-claims-table-body');
        
        if (cData.success && cData.claims.length > 0) {
            cTbody.innerHTML = cData.claims.map(c => {
                const canResolve = (currentUser.id === c.finder_id || currentUser.role === 'admin') && c.status === 'pending';
                const statusBadge = c.status === 'approved' 
                    ? '<span class="badge bg-success">Approved</span>' 
                    : c.status === 'rejected' 
                    ? '<span class="badge bg-danger">Rejected</span>' 
                    : '<span class="badge bg-warning text-dark">Pending</span>';

                return `
                    <tr>
                        <td class="small font-monospace">${c.id.substring(0, 8)}...</td>
                        <td>${escapeHtml(c.claimant_name)}</td>
                        <td>${escapeHtml(c.finder_name)}</td>
                        <td class="small">${escapeHtml(c.proof_details)}</td>
                        <td class="small">${escapeHtml(c.contact_info || 'N/A')}</td>
                        <td>${statusBadge}</td>
                        <td>
                            ${canResolve ? `
                                <div class="btn-group btn-group-sm">
                                    <button class="btn btn-outline-success" onclick="resolveClaimAction('${c.id}', true)">Approve</button>
                                    <button class="btn btn-outline-danger" onclick="resolveClaimAction('${c.id}', false)">Reject</button>
                                </div>
                            ` : `<span class="text-muted small">No action needed</span>`}
                        </td>
                    </tr>
                `;
            }).join('');
        } else {
            cTbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-3">No claims filed yet.</td></tr>';
        }
    } catch (e) {
        console.error('Error loading my reports:', e);
    }
}

async function resolveClaimAction(claimId, approve) {
    try {
        const res = await fetch(`/api/claims/${claimId}/resolve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ approve })
        });
        const data = await res.json();
        if (data.success) {
            showToast('success', data.message);
            await loadMyReports();
            await loadInitialData();
        }
    } catch (e) {
        showToast('danger', 'Error resolving claim');
    }
}

async function loadAdminTableReports() {
    try {
        const res = await fetch('/api/items');
        const data = await res.json();
        if (data.success) {
            const tbody = document.getElementById('admin-reports-table-body');
            tbody.innerHTML = data.items.map(it => `
                <tr>
                    <td><span class="badge ${it.type === 'lost' ? 'bg-danger' : 'bg-success'} text-uppercase">${it.type}</span></td>
                    <td class="fw-semibold">${escapeHtml(it.title)}</td>
                    <td>${escapeHtml(it.category)}</td>
                    <td>${escapeHtml(it.location)}</td>
                    <td>${escapeHtml(it.user_name)}</td>
                    <td><span class="badge bg-secondary">${it.status}</span></td>
                    <td>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteReportAsAdmin('${it.id}')">
                            <i class="bi bi-trash"></i> Remove Fake
                        </button>
                    </td>
                </tr>
            `).join('');
        }
    } catch (e) {}
}

function filterCategory(cat, element) {
    currentCategory = cat;
    document.querySelectorAll('.filter-pill').forEach(el => el.classList.remove('active'));
    element.classList.add('active');
    loadItems();
}

function filterType(type) {
    currentType = type;
    loadItems();
}

function handleSearchInput(val) {
    searchQuery = val;
    loadItems();
}

function showToast(type, message) {
    const toastEl = document.getElementById('liveToast');
    const toastBody = document.getElementById('toast-body');
    const toastHeader = document.getElementById('toast-header');
    
    toastBody.innerText = message;
    toastHeader.className = `toast-header text-white bg-${type === 'danger' ? 'danger' : type === 'success' ? 'success' : 'primary'}`;
    
    const toast = new bootstrap.Toast(toastEl);
    toast.show();
}

function openLoginModal() {
    const modal = new bootstrap.Modal(document.getElementById('authModal'));
    modal.show();
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function setupEventListeners() {
    // Form submits
    const lostForm = document.getElementById('report-lost-form');
    if (lostForm) lostForm.addEventListener('submit', submitReportLost);

    const foundForm = document.getElementById('report-found-form');
    if (foundForm) foundForm.addEventListener('submit', submitReportFound);

    const claimForm = document.getElementById('claim-form');
    if (claimForm) claimForm.addEventListener('submit', submitClaimForm);

    const authForm = document.getElementById('login-form');
    if (authForm) {
        authForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('login-email').value;
            const password = document.getElementById('login-password').value;
            try {
                const res = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password })
                });
                const data = await res.json();
                if (data.success) {
                    currentUser = data.user;
                    renderNavUser();
                    bootstrap.Modal.getInstance(document.getElementById('authModal')).hide();
                    showToast('success', data.message);
                    await loadInitialData();
                } else {
                    showToast('danger', data.detail || 'Login failed');
                }
            } catch (err) {
                showToast('danger', 'Error connecting to auth service');
            }
        });
    }

    const regForm = document.getElementById('register-form');
    if (regForm) {
        regForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const name = document.getElementById('reg-name').value;
            const email = document.getElementById('reg-email').value;
            const password = document.getElementById('reg-password').value;
            const role = document.getElementById('reg-role').value;
            const studentId = document.getElementById('reg-studentid').value;
            
            try {
                const res = await fetch('/api/auth/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, email, password, role, student_id: studentId })
                });
                const data = await res.json();
                if (data.success) {
                    currentUser = data.user;
                    renderNavUser();
                    bootstrap.Modal.getInstance(document.getElementById('authModal')).hide();
                    showToast('success', 'Account created! Welcome to Lost & Found Matcher.');
                    await loadInitialData();
                } else {
                    showToast('danger', data.detail || 'Registration failed');
                }
            } catch (err) {
                showToast('danger', 'Error registering user');
            }
        });
    }
}
