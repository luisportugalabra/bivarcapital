/*  Bivar Capital — shared auth (sign in / sign up / sign out)
    Include on every page AFTER the Supabase UMD script:
      <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.js"></script>
      <script src="/auth.js"></script>
    Required in HTML:
      - nav link  id="nav-signin"
      - nav link  id="nav-signup"
      - nav span  id="nav-user"  (hidden by default)
        └ span    id="nav-email"
        └ a       id="nav-signout"
*/

const supabaseClient = supabase.createClient(
  'https://efiyeiwdywodjxxnslvu.supabase.co',
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVmaXllaXdkeXdvZGp4eG5zbHZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5MzkzNDksImV4cCI6MjA5MTUxNTM0OX0.nZvXoWgnJdXhhJ4-kWD2iCDIADZ8K16ElzlSoRxEOxg'
);

// ── inject modal HTML ──
const modalHTML = `
<div id="auth-modal" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.7);backdrop-filter:blur(8px);z-index:1000;align-items:center;justify-content:center">
  <div style="background:#0c0c10;border:1px solid #1a1a22;border-radius:12px;padding:32px;max-width:380px;width:90%;position:relative">
    <button id="auth-close" style="position:absolute;top:12px;right:16px;background:none;border:none;color:#5a5a68;font-size:1.2rem;cursor:pointer;padding:4px">&times;</button>

    <div id="view-signin">
      <div style="font-family:'DM Serif Display',Georgia,serif;font-size:1.2rem;margin-bottom:4px">Sign In</div>
      <p style="font-size:.78rem;color:#9898a4;margin-bottom:20px">Access your account.</p>
      <input id="signin-email" type="email" placeholder="Email" style="width:100%;padding:10px 14px;background:#060608;border:1px solid #1a1a22;border-radius:6px;color:#e8e8ec;font-family:'JetBrains Mono',monospace;font-size:.8rem;margin-bottom:10px;outline:none">
      <input id="signin-password" type="password" placeholder="Password" style="width:100%;padding:10px 14px;background:#060608;border:1px solid #1a1a22;border-radius:6px;color:#e8e8ec;font-family:'JetBrains Mono',monospace;font-size:.8rem;margin-bottom:14px;outline:none">
      <div id="signin-error" style="color:#f87171;font-size:.7rem;font-family:'JetBrains Mono',monospace;margin-bottom:10px;display:none"></div>
      <button id="signin-submit" style="width:100%;padding:11px;background:#c4a265;color:#060608;font-family:'JetBrains Mono',monospace;font-size:.78rem;font-weight:700;border:none;border-radius:6px;cursor:pointer">Sign In</button>
      <p style="text-align:center;margin-top:14px;font-size:.72rem;color:#5a5a68">Don't have an account? <a href="#" id="goto-signup" style="color:#c4a265;text-decoration:none">Sign Up</a></p>
    </div>

    <div id="view-signup-email" style="display:none">
      <div style="font-family:'DM Serif Display',Georgia,serif;font-size:1.2rem;margin-bottom:4px">Sign Up</div>
      <p style="font-size:.78rem;color:#9898a4;margin-bottom:20px">Enter your email to get started.</p>
      <input id="signup-email" type="email" placeholder="Email" style="width:100%;padding:10px 14px;background:#060608;border:1px solid #1a1a22;border-radius:6px;color:#e8e8ec;font-family:'JetBrains Mono',monospace;font-size:.8rem;margin-bottom:14px;outline:none">
      <div id="signup-email-error" style="color:#f87171;font-size:.7rem;font-family:'JetBrains Mono',monospace;margin-bottom:10px;display:none"></div>
      <button id="signup-continue" style="width:100%;padding:11px;background:#c4a265;color:#060608;font-family:'JetBrains Mono',monospace;font-size:.78rem;font-weight:700;border:none;border-radius:6px;cursor:pointer">Continue</button>
      <p style="text-align:center;margin-top:14px;font-size:.72rem;color:#5a5a68">Already have an account? <a href="#" id="goto-signin" style="color:#c4a265;text-decoration:none">Sign In</a></p>
    </div>

    <div id="view-signup-password" style="display:none">
      <div style="font-family:'DM Serif Display',Georgia,serif;font-size:1.2rem;margin-bottom:4px">Create password</div>
      <p id="signup-email-display" style="font-size:.78rem;color:#9898a4;margin-bottom:20px"></p>
      <input id="signup-password" type="password" placeholder="Password (min 6 characters)" style="width:100%;padding:10px 14px;background:#060608;border:1px solid #1a1a22;border-radius:6px;color:#e8e8ec;font-family:'JetBrains Mono',monospace;font-size:.8rem;margin-bottom:14px;outline:none">
      <div id="signup-pass-error" style="color:#f87171;font-size:.7rem;font-family:'JetBrains Mono',monospace;margin-bottom:10px;display:none"></div>
      <button id="signup-submit" style="width:100%;padding:11px;background:#c4a265;color:#060608;font-family:'JetBrains Mono',monospace;font-size:.78rem;font-weight:700;border:none;border-radius:6px;cursor:pointer">Create Account</button>
      <p style="margin-top:14px"><a href="#" id="signup-back" style="font-family:'JetBrains Mono',monospace;font-size:.7rem;color:#5a5a68;text-decoration:none">&larr; Back</a></p>
    </div>

    <div id="view-signup-done" style="display:none;text-align:center;padding:12px 0">
      <div style="font-size:2rem;margin-bottom:12px;color:#4ade80">&#10003;</div>
      <div style="font-family:'DM Serif Display',Georgia,serif;font-size:1.2rem;margin-bottom:8px">Account created</div>
      <p style="font-size:.78rem;color:#9898a4;margin-bottom:20px">Your account is pending activation.<br>You'll receive access shortly.</p>
      <button id="done-close" style="width:100%;padding:11px;background:#c4a265;color:#060608;font-family:'JetBrains Mono',monospace;font-size:.78rem;font-weight:700;border:none;border-radius:6px;cursor:pointer">Done</button>
    </div>

  </div>
</div>`;

document.body.insertAdjacentHTML('beforeend', modalHTML);

// ── DOM refs ──
const modal = document.getElementById('auth-modal');
const views = {
  signin:      document.getElementById('view-signin'),
  signupEmail: document.getElementById('view-signup-email'),
  signupPass:  document.getElementById('view-signup-password'),
  signupDone:  document.getElementById('view-signup-done'),
};

function showView(name) {
  Object.values(views).forEach(function(v) { v.style.display = 'none'; });
  views[name].style.display = 'block';
}

function openModal(view) {
  showView(view);
  modal.style.display = 'flex';
  // Delay focus to avoid iOS Safari keyboard-scroll issues on fixed modals
  setTimeout(function() {
    if (view === 'signin') document.getElementById('signin-email').focus();
    if (view === 'signupEmail') document.getElementById('signup-email').focus();
  }, 300);
}

function closeModal() {
  modal.style.display = 'none';
  modal.querySelectorAll('input').forEach(function(i) { i.value = ''; });
  modal.querySelectorAll('[id$="-error"]').forEach(function(e) { e.style.display = 'none'; e.style.color = '#f87171'; });
}

// ── Nav wiring ──
var navSignin = document.getElementById('nav-signin');
var navSignup = document.getElementById('nav-signup');
if (navSignin) navSignin.addEventListener('click', function(e) { e.preventDefault(); openModal('signin'); });
if (navSignup) navSignup.addEventListener('click', function(e) {
  e.preventDefault();
  if (navSignup.dataset.busy) return;
  navSignup.dataset.busy = '1';
  var original = navSignup.textContent;
  navSignup.textContent = 'Coming Soon';
  navSignup.style.opacity = '.6';
  setTimeout(function() {
    navSignup.textContent = original;
    navSignup.style.opacity = '1';
    delete navSignup.dataset.busy;
  }, 1600);
});

// Wire all buttons with data-auth attribute (for strategy cards etc.)
document.querySelectorAll('[data-auth]').forEach(function(btn) {
  btn.addEventListener('click', function() { openModal(btn.dataset.auth); });
});

// ── Modal navigation ──
document.getElementById('auth-close').addEventListener('click', closeModal);
modal.addEventListener('click', function(e) { if (e.target === modal) closeModal(); });
document.getElementById('goto-signup').addEventListener('click', function(e) { e.preventDefault(); showView('signupEmail'); document.getElementById('signup-email').focus(); });
document.getElementById('goto-signin').addEventListener('click', function(e) { e.preventDefault(); showView('signin'); document.getElementById('signin-email').focus(); });
document.getElementById('signup-back').addEventListener('click', function(e) { e.preventDefault(); showView('signupEmail'); });
document.getElementById('done-close').addEventListener('click', closeModal);

// ── Sign In ──
document.getElementById('signin-submit').addEventListener('click', function() {
  var email = document.getElementById('signin-email').value.trim();
  var password = document.getElementById('signin-password').value;
  var errEl = document.getElementById('signin-error');
  errEl.style.display = 'none';
  if (!email || !password) { errEl.textContent = 'Enter email and password.'; errEl.style.display = 'block'; return; }
  supabaseClient.auth.signInWithPassword({ email: email, password: password }).then(function(result) {
    if (result.error) { errEl.textContent = result.error.message; errEl.style.display = 'block'; return; }
    closeModal();
    onAuth(email);
  });
});
document.getElementById('signin-email').addEventListener('keydown', function(e) { if (e.key === 'Enter') document.getElementById('signin-password').focus(); });
document.getElementById('signin-password').addEventListener('keydown', function(e) { if (e.key === 'Enter') document.getElementById('signin-submit').click(); });

// ── Sign Up step 1 ──
document.getElementById('signup-continue').addEventListener('click', function() {
  var email = document.getElementById('signup-email').value.trim();
  var errEl = document.getElementById('signup-email-error');
  errEl.style.display = 'none';
  if (!email || !email.includes('@')) { errEl.textContent = 'Enter a valid email.'; errEl.style.display = 'block'; return; }
  document.getElementById('signup-email-display').textContent = email;
  showView('signupPass');
  document.getElementById('signup-password').focus();
});
document.getElementById('signup-email').addEventListener('keydown', function(e) { if (e.key === 'Enter') document.getElementById('signup-continue').click(); });

// ── Sign Up step 2 ──
document.getElementById('signup-submit').addEventListener('click', function() {
  var email = document.getElementById('signup-email').value.trim();
  var password = document.getElementById('signup-password').value;
  var errEl = document.getElementById('signup-pass-error');
  errEl.style.display = 'none';
  if (password.length < 6) { errEl.textContent = 'Password must be at least 6 characters.'; errEl.style.display = 'block'; return; }
  supabaseClient.auth.signUp({ email: email, password: password }).then(function(result) {
    if (result.error) { errEl.textContent = result.error.message; errEl.style.display = 'block'; return; }
    showView('signupDone');
  });
});
document.getElementById('signup-password').addEventListener('keydown', function(e) { if (e.key === 'Enter') document.getElementById('signup-submit').click(); });

// ── Auth state handler ──
function onAuth(email) {
  if (navSignin) navSignin.style.display = 'none';
  if (navSignup) navSignup.style.display = 'none';
  var navUser = document.getElementById('nav-user');
  if (navUser) {
    navUser.style.display = 'inline';
    var navEmail = document.getElementById('nav-email');
    if (navEmail) navEmail.textContent = email || '';
    var navSignout = document.getElementById('nav-signout');
    if (navSignout) navSignout.addEventListener('click', function(e) {
      e.preventDefault();
      supabaseClient.auth.signOut().then(function() { location.reload(); });
    });
  }
  if (typeof window.onUnlock === 'function') window.onUnlock(email);
}

// ── Check #signup hash ──
if (window.location.hash === '#signup') openModal('signupEmail');

// ── Check existing session ──
supabaseClient.auth.getSession().then(function(result) {
  var session = result.data.session;
  if (session) {
    onAuth(session.user.email);
    if (window.authRequired) document.body.style.display = 'block';
  } else if (window.authRequired) {
    window.location.href = '/strategies.html';
  }
});
