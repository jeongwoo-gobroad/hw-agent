const $ = id => document.getElementById(id);
let folder = '', query = '', offset = 0, total = 0, authorized = false;
const preview = /\.(pdf|jpe?g|png|webp|gif|mp4|webm|mov|mp3|wav|txt|py|json|md|csv)$/i;
function icon(name) { const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); const use = document.createElementNS(svg.namespaceURI, 'use'); use.setAttribute('href', '#' + name); svg.append(use); return svg; }
function note(message, error = false) { $('notice').textContent = message; $('notice').classList.toggle('error', error); }
async function api(path, options) {
  const response = await fetch(path, {cache: 'no-store', ...options});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '접근 상태를 확인할 수 없습니다.');
  return data;
}
function size(bytes) { return bytes >= 1073741824 ? (bytes / 1073741824).toFixed(2) + ' GiB' : bytes >= 1048576 ? (bytes / 1048576).toFixed(1) + ' MiB' : bytes.toLocaleString() + ' B'; }
function action(entry, label, symbol, download) {
  const a = document.createElement('a'); a.className = 'action';
  a.href = '/api/file/' + entry.id + (download ? '?download=1' : '');
  a.target = '_blank'; a.rel = 'noopener'; a.append(icon(symbol), document.createTextNode(label));
  return a;
}
async function load() {
  $('refresh').disabled = true;
  try {
    const data = await api('/api/list?' + new URLSearchParams({folder, q: query, offset}));
    total = data.total; $('welcome').hidden = true; $('browser').hidden = false; $('list').replaceChildren(); $('breadcrumbs').replaceChildren();
    for (const crumb of data.breadcrumbs) {
      const button = document.createElement('button'); button.textContent = crumb.name;
      button.onclick = () => { folder = crumb.id; query = ''; offset = 0; $('query').value = ''; load(); };
      $('breadcrumbs').append(button);
    }
    for (const entry of data.items) {
      const row = document.createElement('div'); row.className = 'row'; row.append(icon(entry.kind));
      const details = document.createElement('div'); details.className = 'details';
      const name = document.createElement(entry.kind === 'folder' ? 'button' : 'div'); name.className = 'name'; name.textContent = entry.name;
      if (entry.kind === 'folder') { name.classList.add('folder-name'); name.onclick = () => {folder = entry.id; offset = 0; load();}; }
      details.append(name);
      if (entry.kind === 'file') {
        const meta = document.createElement('div'); meta.className = 'meta'; meta.textContent = size(entry.size) + (query && entry.folder ? ' · ' + entry.folder : ''); details.append(meta);
      }
      row.append(details);
      if (entry.kind === 'file') { const actions = document.createElement('div'); actions.className = 'actions'; if (preview.test(entry.name)) actions.append(action(entry, '보기', 'eye', false)); actions.append(action(entry, '다운로드', 'download', true)); row.append(actions); }
      $('list').append(row);
    }
    if (!data.items.length) { const empty = document.createElement('div'); empty.className = 'empty'; empty.textContent = query ? '파일명과 일치하는 준비된 파일이 없습니다.' : '이 폴더에 표시할 준비된 파일이 없습니다.'; $('list').append(empty); }
    $('count').textContent = (query ? '전체 파일명 검색 · ' : '') + total.toLocaleString() + '개 항목';
    $('page').textContent = (Math.floor(offset / 100) + 1) + ' / ' + Math.max(1, Math.ceil(total / 100));
    $('previous').disabled = offset === 0; $('next').disabled = offset + 100 >= total;
    note('원본 읽기 전용 · 사용 가능한 파일 ' + data.available_files.toLocaleString() + '개 · 미완료 파일은 자동 제외');
  } catch (error) { note(error.message, true); } finally { $('refresh').disabled = false; }
}
$('start').onclick = load; $('refresh').onclick = load;
$('search-form').onsubmit = event => {event.preventDefault(); query = $('query').value.trim(); folder = ''; offset = 0; load();};
$('clear').onclick = () => { query = ''; $('query').value = ''; offset = 0; load(); };
$('previous').onclick = () => {offset = Math.max(0, offset - 100); load();}; $('next').onclick = () => {offset += 100; load();};
document.documentElement.dataset.theme = localStorage.getItem('alter-reader-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
$('theme').onclick = () => {const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = theme; localStorage.setItem('alter-reader-theme', theme);};
(async () => {
  try {
    const token = new URLSearchParams(location.hash.slice(1)).get('token');
    history.replaceState(null, '', '/');
    if (token) await api('/api/session', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({token})});
    await api('/api/status'); authorized = true; $('start').disabled = false; note('준비되었습니다. 파일 탐색 시작을 누르면 폴더 목록을 표시합니다.');
  } catch (error) {note(error.message, true);}
})();
setInterval(async () => {if (!authorized) return; try {await api('/api/status');} catch {authorized = false; $('start').disabled = true; $('browser').hidden = true; $('welcome').hidden = false; note('임시 접근이 종료되었습니다. 공유 복구가 끝나면 기존 SMB를 이용해 주세요.', true);}}, 5000);
