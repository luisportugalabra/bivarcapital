/**
 * Shared auth nav — checks localStorage for login token and updates the Sign In link.
 * Include this script on every page EXCEPT invest.html (which has its own full auth).
 */
(function() {
  const SUPABASE_URL = 'https://efiyeiwdywodjxxnslvu.supabase.co';
  const SUPABASE_KEY = 'sb_publishable_IccFybhqHU9RM5rc-Em1KA_G5Dsrqha';

  // Migrate old localStorage keys
  if (localStorage.getItem('rtw_token') && !localStorage.getItem('bc_token')) {
    localStorage.setItem('bc_token', localStorage.getItem('rtw_token'));
    if (localStorage.getItem('rtw_refresh')) localStorage.setItem('bc_refresh', localStorage.getItem('rtw_refresh'));
    localStorage.removeItem('rtw_token'); localStorage.removeItem('rtw_refresh');
  }

  const link = document.querySelector('.btn-sub');
  if (!link) return;

  const token = localStorage.getItem('bc_token');
  if (!token) return;

  fetch(SUPABASE_URL + '/auth/v1/user', {
    headers: { 'Authorization': 'Bearer ' + token, 'apikey': SUPABASE_KEY }
  })
  .then(r => { if (!r.ok) throw new Error(); return r.json(); })
  .then(user => {
    const name = user.email.split('@')[0];
    const isPaid = user.user_metadata && user.user_metadata.is_paid === true;
    var parent = link.parentNode;
    link.innerHTML = name.toUpperCase() + (isPaid ? ' <span style="font-family:var(--font-mono,monospace);font-size:0.5rem;font-weight:700;padding:2px 6px;background:var(--accent,#c4a265);color:var(--bg,#060608);border-radius:4px;letter-spacing:0.08em;margin-left:4px;vertical-align:middle">PRO</span>' : '');
    link.href = '#';
    link.onclick = function(e) { e.preventDefault(); };
    link.style.cursor = 'default';
    link.style.borderColor = isPaid ? 'var(--accent,#c4a265)' : 'var(--border-light,#2a2a35)';
    var signout = document.createElement('a');
    signout.textContent = 'Sign Out';
    signout.href = '#';
    signout.style.cssText = 'font-family:var(--font-mono,monospace);font-size:0.62rem;font-weight:500;letter-spacing:0.1em;text-transform:uppercase;color:var(--text-muted,#5a5a68);cursor:pointer;margin-left:12px;transition:color 0.2s;';
    signout.onmouseover = function() { this.style.color = 'var(--text,#e8e8ec)'; };
    signout.onmouseout = function() { this.style.color = 'var(--text-muted,#5a5a68)'; };
    signout.onclick = function(e) {
      e.preventDefault();
      localStorage.removeItem('bc_token');
      localStorage.removeItem('bc_refresh');
      window.location.reload();
    };
    parent.appendChild(signout);
  })
  .catch(() => {
    var refreshToken = localStorage.getItem('bc_refresh');
    if (refreshToken) {
      fetch(SUPABASE_URL + '/auth/v1/token?grant_type=refresh_token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'apikey': SUPABASE_KEY },
        body: JSON.stringify({ refresh_token: refreshToken })
      })
      .then(function(r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function(data) {
        localStorage.setItem('bc_token', data.access_token);
        if (data.refresh_token) localStorage.setItem('bc_refresh', data.refresh_token);
        window.location.reload();
      })
      .catch(function() {
        localStorage.removeItem('bc_token');
        localStorage.removeItem('bc_refresh');
      });
    } else {
      localStorage.removeItem('bc_token');
      localStorage.removeItem('bc_refresh');
    }
  });
})();
