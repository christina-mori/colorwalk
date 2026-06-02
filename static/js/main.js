/* ── State ── */
let currentFile = null;
let croppedFile = null;   // set after user confirms a crop
let previewBlob = null;
let lastParams = { dot: null, colorwalk: null };
let currentMode = 'dot';
let debounceTimers = { dot: null, colorwalk: null };
let activeRequest = { dot: null, colorwalk: null };
let selectedPreset = null;
let currentDotSeed = createRandomSeed();
let previewScale = 1;
let currentLang = 'en';
let currentAutoColorHex = '';
let currentSourceSize = null;
let currentPreviewSize = null;
let hasExplicitBlockDecoupleState = false;
let playbookItems = [];
let playbookLoading = false;
let lastPlaybookFilter = 'all';

const PREVIEW_MAX_PX = 800;

function createRandomSeed() {
  return Math.floor(Math.random() * 2147483647);
}

function normalizeHex(hex) {
  return (hex || '').trim().toUpperCase();
}

function autoTextColorHex(hex) {
  const [r, g, b] = hexToRgb(hex);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.5 ? '#1E1E1E' : '#F0F0F0';
}

function setColorPairValue(colorId, hexId, hex) {
  if (!hex) return;
  const normalized = normalizeHex(hex);
  const colorEl = document.getElementById(colorId);
  const hexEl = document.getElementById(hexId);
  if (colorEl) colorEl.value = normalized;
  if (hexEl) hexEl.value = normalized;
}

function escapeHtml(text) {
  return String(text || '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[ch]));
}

function getCurrentFilter() {
  return document.querySelector('.pb-tab.active')?.dataset.filter || 'all';
}

function updateExtractedColorHint() {
  const hintEl = document.getElementById('cw-extracted-hint');
  if (!hintEl) return;
  hintEl.textContent = currentAutoColorHex
    ? (currentLang === 'zh'
      ? `自动提取颜色：${currentAutoColorHex}`
      : `Auto color extracted: ${currentAutoColorHex}`)
    : '';
}

function getResolvedColorwalkColorHex() {
  const manualHex = normalizeHex(document.getElementById('cw-color').value);
  if (!document.getElementById('cw-auto-color').checked) return manualHex;
  return normalizeHex(currentAutoColorHex || manualHex);
}

function syncUploadPresetState() {
  const titleEl = document.getElementById('uploadTitle');
  const hintEl = document.getElementById('uploadHint');
  if (!titleEl || !hintEl) return;

  if (selectedPreset && !currentFile) {
    const presetLabel = getPresetLabel(selectedPreset);
    titleEl.textContent = currentLang === 'zh'
      ? `已选择 ${presetLabel} 同款，点击上传你的照片`
      : `Selected ${presetLabel}. Click to upload your photo`;
    hintEl.textContent = currentLang === 'zh'
      ? '上传后会自动套用这组参数并进入编辑器'
      : 'Your photo will be styled with this preset automatically';
    uploadHero.classList.add('preset-pending');
  } else {
    titleEl.textContent = currentLang === 'zh'
      ? '点击上传图片，或直接拖拽到此处'
      : 'Click to upload an image, or drag it here';
    hintEl.textContent = currentLang === 'zh'
      ? '支持 JPG / PNG，最大 20MB'
      : 'JPG / PNG supported, up to 20MB';
    uploadHero.classList.remove('preset-pending');
  }
}

function makePreviewBlob(file) {
  return new Promise(resolve => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      currentSourceSize = { width: img.width, height: img.height };
      previewScale = Math.min(1, PREVIEW_MAX_PX / Math.max(img.width, img.height));
      const w = Math.round(img.width * previewScale);
      const h = Math.round(img.height * previewScale);
      currentPreviewSize = { width: w, height: h };
      const canvas = document.createElement('canvas');
      canvas.width = w; canvas.height = h;
      canvas.getContext('2d').drawImage(img, 0, 0, w, h);
      canvas.toBlob(blob => resolve(blob), 'image/jpeg', 0.88);
    };
    img.src = url;
  });
}

/* ── Debounce ── */
function debounce(mode, fn, delay = 150) {
  clearTimeout(debounceTimers[mode]);
  debounceTimers[mode] = setTimeout(fn, delay);
}

/* ── Step navigation ── */
function goToStep(n) {
  document.querySelectorAll('.step').forEach((s, i) => {
    s.style.display = i + 1 === n ? 'block' : 'none';
  });

  const ts1 = document.getElementById('ts1');
  const ts2 = document.getElementById('ts2');
  const ts3 = document.getElementById('ts3');
  ts1.className = 'tstep' + (n > 1 ? ' done' : n === 1 ? ' active' : '');
  ts2.className = 'tstep' + (n > 2 ? ' done' : n === 2 ? ' active' : '');
  ts3.className = 'tstep' + (n === 3 ? ' active' : '');

  document.getElementById('topbarSteps').style.display = n > 1 ? 'flex' : 'none';
}

/* ── Upload ── */
const uploadHero = document.getElementById('uploadHero');
const uploadInner = document.getElementById('uploadInner');
const fileInput = document.getElementById('fileInput');

uploadHero.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', e => handleFile(e.target.files[0]));

uploadHero.addEventListener('dragover', e => { e.preventDefault(); uploadHero.classList.add('dragover'); });
uploadHero.addEventListener('dragleave', () => uploadHero.classList.remove('dragover'));
uploadHero.addEventListener('drop', e => {
  e.preventDefault();
  uploadHero.classList.remove('dragover');
  handleFile(e.dataTransfer.files[0]);
});

document.getElementById('changeFileBtn').addEventListener('click', () => {
  fileInput.value = '';
  fileInput.click();
});

async function handleFile(file) {
  if (!file || !file.type.startsWith('image/')) return;
  currentFile = file;
  croppedFile = null;  // reset any previous crop
  currentDotSeed = createRandomSeed();
  currentAutoColorHex = '';

  // Topbar thumbnail
  const thumbImg = document.getElementById('thumbImg');
  thumbImg.src = URL.createObjectURL(file);
  document.getElementById('topbarFile').style.display = 'flex';

  previewBlob = await makePreviewBlob(file);
  await extractColor(previewBlob);

  if (selectedPreset) {
    applyPresetSettings(selectedPreset);
    currentMode = selectedPreset.mode;
    showSettings(currentMode);
    goToStep(3);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    triggerPreview(currentMode, 0);
  } else {
    goToStep(2);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  syncUploadPresetState();
  showSubmitButton();
}

/* ── Mode card selection ── */
document.querySelectorAll('.mode-card').forEach(card => {
  card.addEventListener('click', () => {
    currentMode = card.dataset.mode;
    showSettings(currentMode);
    goToStep(3);
    setTimeout(() => {
      document.getElementById('step3').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 50);
    triggerPreview(currentMode, 0);
  });
});

function showSettings(mode) {
  document.getElementById('settingsDot').style.display = mode === 'dot' ? 'block' : 'none';
  document.getElementById('settingsCw').style.display = mode === 'colorwalk' ? 'block' : 'none';
}

/* ── Back button ── */
document.getElementById('btnBack').addEventListener('click', () => {
  goToStep(2);
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

/* ── Sliders display value ── */
function bindSlider(id, valId, suffix = '') {
  const el = document.getElementById(id);
  const val = document.getElementById(valId);
  el.addEventListener('input', () => { val.textContent = el.value + suffix; });
}
bindSlider('dp-block-ratio', 'dp-block-ratio-val', '%');
bindSlider('dp-dot-size', 'dp-dot-size-val', 'px');
bindSlider('dp-dot-count', 'dp-dot-count-val', '');
bindSlider('cw-ratio', 'cw-ratio-val', '%');

/* ── DOT PUZZLE: block type toggle ── */
document.getElementById('dp-block-type').addEventListener('change', function () {
  const v = this.value;
  document.getElementById('dp-color-solid').style.display = v === 'solid' || v === 'vintage' ? 'flex' : 'none';
  document.getElementById('dp-color-gradient').style.display = v === 'gradient' ? 'block' : 'none';
  document.getElementById('dp-color-stripe').style.display = v === 'stripe' ? 'block' : 'none';
  redrawBlockCanvas();
});

/* ── DOT PUZZLE: distribution mode toggle ── */
let manualDots = [];
let blockManualDots = [];
let dotCanvasImg = null;

function getPreviewCanvasSize() {
  if (!dotCanvasImg) return null;
  return { width: dotCanvasImg.naturalWidth, height: dotCanvasImg.naturalHeight };
}

function computeBlockCanvasSize() {
  const previewSize = getPreviewCanvasSize();
  if (!previewSize) return null;
  const ratio = (parseInt(document.getElementById('dp-block-ratio').value, 10) || 40) / 100;
  const position = document.getElementById('dp-position').value;
  if (position === 'top' || position === 'bottom') {
    return {
      width: previewSize.width,
      height: Math.max(60, Math.floor(previewSize.height * ratio)),
    };
  }
  return {
    width: Math.max(60, Math.floor(previewSize.width * ratio)),
    height: previewSize.height,
  };
}

function drawPointMarkers(ctx, points, width, height) {
  const r = Math.max(10, Math.min(width, height) * 0.03);
  points.forEach(({ nx, ny }) => {
    const x = nx * width;
    const y = ny * height;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255,255,255,0.5)';
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2.5;
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x - r * 0.45, y); ctx.lineTo(x + r * 0.45, y);
    ctx.moveTo(x, y - r * 0.45); ctx.lineTo(x, y + r * 0.45);
    ctx.strokeStyle = 'rgba(0,0,0,0.75)';
    ctx.lineWidth = 2;
    ctx.stroke();
  });
}

function getStripeStep(length) {
  return Math.max(1, Math.floor(length / 8));
}

function buildCanvasGradient(ctx, width, height, dir, c1, c2) {
  const gradient = dir === 'horizontal'
    ? ctx.createLinearGradient(0, 0, width, 0)
    : ctx.createLinearGradient(0, 0, 0, height);
  gradient.addColorStop(0, c1);
  gradient.addColorStop(1, c2);
  return gradient;
}

function drawBlockCanvasBackground(ctx, width, height) {
  const blockType = document.getElementById('dp-block-type').value;
  if (blockType === 'gradient') {
    ctx.fillStyle = buildCanvasGradient(
      ctx,
      width,
      height,
      document.getElementById('dp-grad-dir').value,
      document.getElementById('dp-grad1').value,
      document.getElementById('dp-grad2').value
    );
    ctx.fillRect(0, 0, width, height);
    return;
  }

  if (blockType === 'stripe') {
    const c1 = document.getElementById('dp-stripe1').value;
    const c2 = document.getElementById('dp-stripe2').value;
    const dir = document.getElementById('dp-stripe-dir').value;
    if (dir === 'horizontal') {
      const stripeH = getStripeStep(height);
      for (let y = 0; y < height; y += stripeH) {
        ctx.fillStyle = Math.floor(y / stripeH) % 2 === 0 ? c1 : c2;
        ctx.fillRect(0, y, width, stripeH);
      }
    } else {
      const stripeW = getStripeStep(width);
      for (let x = 0; x < width; x += stripeW) {
        ctx.fillStyle = Math.floor(x / stripeW) % 2 === 0 ? c1 : c2;
        ctx.fillRect(x, 0, stripeW, height);
      }
    }
    return;
  }

  ctx.fillStyle = document.getElementById('dp-color1').value;
  ctx.fillRect(0, 0, width, height);
}

function getCurrentBlockDistributionValue() {
  const el = document.getElementById('dp-block-distribution');
  return el ? el.value : 'linked';
}

function hasStoredBlockManualState() {
  return getCurrentBlockDistributionValue() !== 'linked' || blockManualDots.length > 0 || hasExplicitBlockDecoupleState;
}

function initDotCanvas() {
  if (!previewBlob) return;
  const canvas = document.getElementById('dp-dot-canvas');
  const img = new Image();
  img.onload = () => {
    dotCanvasImg = img;
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    redrawDotCanvas();
    redrawBlockCanvas();
  };
  img.src = URL.createObjectURL(previewBlob);
}

function initBlockCanvas() {
  if (!dotCanvasImg) {
    initDotCanvas();
    return;
  }
  const canvas = document.getElementById('dp-block-dot-canvas');
  const size = computeBlockCanvasSize();
  if (!canvas || !size) return;
  canvas.width = size.width;
  canvas.height = size.height;
  redrawBlockCanvas();
}

function redrawDotCanvas() {
  const canvas = document.getElementById('dp-dot-canvas');
  if (!dotCanvasImg || canvas.width === 0) return;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(dotCanvasImg, 0, 0, canvas.width, canvas.height);
  drawPointMarkers(ctx, manualDots, canvas.width, canvas.height);
}

function redrawBlockCanvas() {
  const canvas = document.getElementById('dp-block-dot-canvas');
  const size = computeBlockCanvasSize();
  if (!canvas || !size) return;
  if (canvas.width !== size.width || canvas.height !== size.height) {
    canvas.width = size.width;
    canvas.height = size.height;
  }
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawBlockCanvasBackground(ctx, canvas.width, canvas.height);
  drawPointMarkers(ctx, blockManualDots, canvas.width, canvas.height);
}

function toggleManualPoint(collection, nx, ny) {
  const threshold = 0.05;
  const idx = collection.findIndex(d => Math.hypot(d.nx - nx, d.ny - ny) < threshold);
  if (idx >= 0) collection.splice(idx, 1);
  else collection.push({ nx, ny });
}

function makeRandomNormalizedPoints(count, width, height) {
  const dotSizePx = parseInt(document.getElementById('dp-dot-size').value, 10) || 60;
  const padX = Math.min(0.45, (dotSizePx / 2) / Math.max(width, 1));
  const padY = Math.min(0.45, (dotSizePx / 2) / Math.max(height, 1));
  return Array.from({ length: count }, () => ({
    nx: padX + Math.random() * Math.max(0.01, 1 - padX * 2),
    ny: padY + Math.random() * Math.max(0.01, 1 - padY * 2),
  }));
}

function syncDotDistributionUI() {
  const isManual = document.getElementById('dp-distribution').value === 'manual';
  document.getElementById('dp-manual-wrap').style.display = isManual ? 'block' : 'none';
  if (isManual) initDotCanvas();
  else redrawDotCanvas();
}

function syncBlockDistributionUI() {
  const decoupled = document.getElementById('dp-decouple').checked;
  const row = document.getElementById('dp-block-distribution-row');
  const wrap = document.getElementById('dp-block-manual-wrap');
  const emptyHint = document.getElementById('dpBlockManualEmptyHint');
  if (!row || !wrap) return;
  row.style.display = decoupled ? 'flex' : 'none';

  const blockMode = getCurrentBlockDistributionValue();
  const isManual = decoupled && blockMode === 'manual';
  wrap.style.display = isManual ? 'block' : 'none';
  if (emptyHint) emptyHint.style.display = isManual && blockManualDots.length === 0 ? 'block' : 'none';
  if (isManual) initBlockCanvas();
}

function handleDecoupleToggle() {
  const decoupleEl = document.getElementById('dp-decouple');
  const turnedOn = decoupleEl.checked;

  if (turnedOn) {
    if (!hasStoredBlockManualState()) {
      document.getElementById('dp-block-distribution').value = 'manual';
      blockManualDots = [];
      hasExplicitBlockDecoupleState = true;
    }
  }

  syncBlockDistributionUI();
  redrawBlockCanvas();
  triggerPreview('dot', 0);
}

document.getElementById('dp-distribution').addEventListener('change', function () {
  syncDotDistributionUI();
});

document.getElementById('dp-decouple').addEventListener('change', () => {
  handleDecoupleToggle();
});

document.getElementById('dp-block-distribution').addEventListener('change', () => {
  hasExplicitBlockDecoupleState = true;
  syncBlockDistributionUI();
  triggerPreview('dot', 0);
});

[
  'dp-position',
  'dp-block-ratio',
  'dp-color1',
  'dp-grad1',
  'dp-grad2',
  'dp-grad-dir',
  'dp-stripe1',
  'dp-stripe2',
  'dp-stripe-dir',
].forEach(id => {
  const el = document.getElementById(id);
  if (!el) return;
  const refresh = () => redrawBlockCanvas();
  el.addEventListener('input', refresh);
  el.addEventListener('change', refresh);
});

document.getElementById('dp-dot-canvas').addEventListener('click', function (e) {
  const rect = this.getBoundingClientRect();
  const nx = (e.clientX - rect.left) / rect.width;
  const ny = (e.clientY - rect.top) / rect.height;
  toggleManualPoint(manualDots, nx, ny);
  redrawDotCanvas();
  triggerPreview('dot', 0);
});

document.getElementById('dp-block-dot-canvas').addEventListener('click', function (e) {
  const rect = this.getBoundingClientRect();
  const nx = (e.clientX - rect.left) / rect.width;
  const ny = (e.clientY - rect.top) / rect.height;
  toggleManualPoint(blockManualDots, nx, ny);
  hasExplicitBlockDecoupleState = true;
  redrawBlockCanvas();
  triggerPreview('dot', 0);
});

document.getElementById('dp-seed-random').addEventListener('click', () => {
  const count = parseInt(document.getElementById('dp-dot-count').value, 10) || 12;
  const previewSize = getPreviewCanvasSize() || { width: PREVIEW_MAX_PX, height: PREVIEW_MAX_PX };
  manualDots = makeRandomNormalizedPoints(count, previewSize.width, previewSize.height);
  if (document.getElementById('dp-dot-canvas').width === 0) {
    initDotCanvas();
    setTimeout(() => redrawDotCanvas(), 150);
  } else {
    redrawDotCanvas();
  }
  triggerPreview('dot', 0);
});

document.getElementById('dp-block-seed-random').addEventListener('click', () => {
  const count = parseInt(document.getElementById('dp-dot-count').value, 10) || 12;
  const size = computeBlockCanvasSize();
  if (!size) return;
  blockManualDots = makeRandomNormalizedPoints(count, size.width, size.height);
  hasExplicitBlockDecoupleState = true;
  initBlockCanvas();
  triggerPreview('dot', 0);
});

document.getElementById('dp-clear-dots').addEventListener('click', () => {
  manualDots = [];
  redrawDotCanvas();
  triggerPreview('dot', 0);
});

document.getElementById('dp-block-clear-dots').addEventListener('click', () => {
  blockManualDots = [];
  hasExplicitBlockDecoupleState = true;
  redrawBlockCanvas();
  triggerPreview('dot', 0);
});

/* ── DOT PUZZLE: shape text toggle ── */
document.getElementById('dp-shape').addEventListener('change', function () {
  document.getElementById('dp-custom-text-wrap').style.display = this.value === 'text' ? 'flex' : 'none';
});

/* ── COLORWALK: auto color toggle ── */
document.getElementById('cw-auto-color').addEventListener('change', function () {
  document.getElementById('cw-manual-color').style.display = this.checked ? 'none' : 'flex';
});

/* ── COLORWALK: auto text color toggle ── */
document.getElementById('cw-auto-text-color').addEventListener('change', function () {
  document.getElementById('cw-manual-text-color').style.display = this.checked ? 'none' : 'flex';
});

/* ── Color picker ↔ hex input sync ── */
function bindColorHex(colorId, hexId, mode) {
  const colorEl = document.getElementById(colorId);
  const hexEl = document.getElementById(hexId);
  if (!colorEl || !hexEl) return;

  colorEl.addEventListener('input', () => {
    hexEl.value = colorEl.value.toUpperCase();
    triggerPreview(mode, 300);
  });

  hexEl.addEventListener('input', () => {
    const val = hexEl.value.trim();
    if (/^#[0-9a-fA-F]{6}$/.test(val)) {
      colorEl.value = val;
      triggerPreview(mode, 300);
    }
  });
}
bindColorHex('cw-color', 'cw-color-hex', 'colorwalk');
bindColorHex('cw-text-color', 'cw-text-color-hex', 'colorwalk');
bindColorHex('dp-text-color', 'dp-text-color-hex', 'dot');

/* ── Watch all controls → auto preview ── */
function watchControls(ids, mode, delay = 650) {
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('input', () => triggerPreview(mode, delay));
    if (el.tagName === 'SELECT' || el.type === 'checkbox') {
      el.addEventListener('change', () => triggerPreview(mode, 0));
    }
  });
}

watchControls([
  'dp-position', 'dp-block-ratio', 'dp-block-type', 'dp-color1',
  'dp-grad1', 'dp-grad2', 'dp-grad-dir', 'dp-stripe1', 'dp-stripe2', 'dp-stripe-dir',
  'dp-shape', 'dp-custom-text',
  'dp-dot-size', 'dp-dot-count', 'dp-distribution', 'dp-block-distribution',
  'dp-size-random', 'dp-decouple',
  'dp-text', 'dp-text-size', 'dp-text-color',
], 'dot');

watchControls([
  'cw-ratio', 'cw-auto-color', 'cw-color',
  'cw-text', 'cw-font-size', 'cw-auto-text-color', 'cw-text-color',
], 'colorwalk');

function triggerPreview(mode, delay = 150) {
  if (!currentFile) return;
  debounce(mode, () => {
    if (mode === 'dot') applyDotPuzzle();
    else applyColorwalk();
  }, delay);
}

/* ── Color extraction ── */
async function extractColor(blob) {
  const fd = new FormData();
  fd.append('image', blob, 'preview.jpg');
  try {
    const res = await fetch('/api/extract-color', { method: 'POST', body: fd });
    const data = await res.json();
    if (data.color) {
      const hex = rgbToHex(...data.color);
      currentAutoColorHex = normalizeHex(hex);
      if (document.getElementById('cw-auto-color').checked) {
        document.getElementById('cw-color').value = hex;
        document.getElementById('cw-color-hex').value = hex.toUpperCase();
      }
      updateExtractedColorHint();
    }
  } catch {}
}

function rgbToHex(r, g, b) {
  return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('');
}
function hexToRgb(hex) {
  return [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
}

/* ── Preview box loading state ── */
function setBoxLoading(boxId, on) {
  const box = document.getElementById(boxId);
  if (on) box.classList.add('loading-box');
  else box.classList.remove('loading-box');
}

function showFullLoading(v) {
  document.getElementById('loading').style.display = v ? 'flex' : 'none';
}

function showSubmitButton() {
  const btn = document.getElementById('btnSubmitCommunity');
  if (!btn) return;
  btn.style.display = currentFile ? 'block' : 'none';
}

/* ── Build params ── */
function buildDotParams() {
  const blockType = document.getElementById('dp-block-type').value;
  let blockColor;
  if (blockType === 'gradient') {
    blockColor = [hexToRgb(document.getElementById('dp-grad1').value), hexToRgb(document.getElementById('dp-grad2').value)];
  } else if (blockType === 'stripe') {
    blockColor = [hexToRgb(document.getElementById('dp-stripe1').value), hexToRgb(document.getElementById('dp-stripe2').value)];
  } else {
    blockColor = hexToRgb(document.getElementById('dp-color1').value);
  }
  const distribution = document.getElementById('dp-distribution').value;
  const decouple = document.getElementById('dp-decouple').checked;
  const blockDistribution = decouple ? getCurrentBlockDistributionValue() : 'linked';
  const params = {
    position: document.getElementById('dp-position').value,
    block_ratio: document.getElementById('dp-block-ratio').value / 100,
    block_type: blockType,
    block_color: JSON.stringify(blockColor),
    gradient_dir: document.getElementById('dp-grad-dir').value,
    stripe_dir: document.getElementById('dp-stripe-dir').value,
    size_random: document.getElementById('dp-size-random').checked,
    decouple,
    shape: document.getElementById('dp-shape').value,
    custom_text: document.getElementById('dp-custom-text').value,
    dot_size: document.getElementById('dp-dot-size').value,
    dot_count: document.getElementById('dp-dot-count').value,
    distribution,
    block_distribution: blockDistribution,
    text_overlay: document.getElementById('dp-text').value,
    text_font_size: document.getElementById('dp-text-size').value,
    text_color: JSON.stringify(hexToRgb(document.getElementById('dp-text-color').value)),
    seed: currentDotSeed,
    format: 'PNG',
  };
  if (distribution === 'manual') {
    params.manual_positions = JSON.stringify(manualDots.map(d => [d.nx, d.ny]));
  }
  if (params.decouple && params.block_distribution === 'manual') {
    params.block_manual_positions = JSON.stringify(blockManualDots.map(d => [d.nx, d.ny]));
  }
  return params;
}

function buildColorwalkParams() {
  const autoTextColor = document.getElementById('cw-auto-text-color').checked;
  const params = {
    color: JSON.stringify(hexToRgb(getResolvedColorwalkColorHex())),
    color_ratio: document.getElementById('cw-ratio').value / 100,
    text: document.getElementById('cw-text').value,
    font_size: document.getElementById('cw-font-size').value,
    format: 'PNG',
  };
  if (!autoTextColor) params.text_color = JSON.stringify(hexToRgb(document.getElementById('cw-text-color').value));
  return params;
}

function buildBaseRenderParams(mode) {
  return mode === 'dot' ? buildDotParams() : buildColorwalkParams();
}

function scaleParamsForSourceRender(mode, params) {
  if (!params) return params;

  const scaleUp = currentSourceSize && currentPreviewSize
    ? Math.max(
      currentSourceSize.width / Math.max(currentPreviewSize.width, 1),
      currentSourceSize.height / Math.max(currentPreviewSize.height, 1)
    )
    : (previewScale > 0 ? 1 / previewScale : 1);
  const scaled = { ...params };

  if (mode === 'dot' && scaled.dot_size !== undefined) {
    scaled.dot_size = String(Math.max(1, Math.round(Number(scaled.dot_size) * scaleUp)));
  }
  if (mode === 'dot' && scaled.text_font_size !== undefined) {
    scaled.text_font_size = String(Math.max(1, Math.round(Number(scaled.text_font_size) * scaleUp)));
  }
  if (mode === 'colorwalk' && scaled.font_size !== undefined) {
    scaled.font_size = String(Math.max(1, Math.round(Number(scaled.font_size) * scaleUp)));
  }

  return scaled;
}

function buildSourceRenderParams(mode, overrides = {}) {
  const baseParams = buildBaseRenderParams(mode);
  return { ...scaleParamsForSourceRender(mode, baseParams), ...overrides };
}

function applyLanguage(lang) {
  currentLang = lang === 'zh' ? 'zh' : 'en';
  try { localStorage.setItem('cw_lang', currentLang); } catch {}
  document.documentElement.lang = currentLang === 'zh' ? 'zh-CN' : 'en';
  document.getElementById('langEnBtn').classList.toggle('active', currentLang === 'en');
  document.getElementById('langZhBtn').classList.toggle('active', currentLang === 'zh');

  document.getElementById('ts1').textContent = currentLang === 'zh' ? '① 上传' : '① Upload';
  document.getElementById('ts2').textContent = currentLang === 'zh' ? '② 选效果' : '② Effect';
  document.getElementById('ts3').textContent = currentLang === 'zh' ? '③ 调整' : '③ Edit';
  document.getElementById('playbookTitle').textContent = currentLang === 'zh' ? '大家都在做' : 'Popular Playbooks';
  document.getElementById('playbookHint').textContent = currentLang === 'zh'
    ? '浏览大家都在做的案例，再把同样的参数套用到你的图片上。'
    : 'Browse popular looks, then try the same parameters on your own image.';
  document.getElementById('step2Heading').textContent = currentLang === 'zh' ? '选择效果' : 'Choose an effect';
  document.getElementById('previewPlaceholder').textContent = currentLang === 'zh' ? '预览生成中…' : 'Generating preview…';
  document.getElementById('btn-dl-png').textContent = currentLang === 'zh' ? '↓ 下载 PNG' : '↓ Download PNG';
  document.getElementById('btn-dl-jpg').textContent = currentLang === 'zh' ? '↓ 下载 JPG' : '↓ Download JPG';
  document.getElementById('btnSubmitCommunity').textContent = currentLang === 'zh' ? '投稿到社区' : 'Submit to Community';
  document.getElementById('btnBack').textContent = currentLang === 'zh' ? '← 换效果' : '← Change effect';
  document.getElementById('btnCopyParams').textContent = currentLang === 'zh' ? '复制参数' : 'Copy params';
  document.getElementById('presetBarText').textContent = currentLang === 'zh' ? '✦ 已选' : '✦ Selected';
  document.getElementById('presetBarHint').textContent = currentLang === 'zh' ? '· 上传图片即可体验' : '· Upload your image to try it';
  document.getElementById('presetBarClear').textContent = currentLang === 'zh' ? '✕ 取消' : '✕ Clear';
  document.getElementById('pbLbTry').textContent = currentLang === 'zh' ? '做同款 →' : 'Try this look →';
  document.getElementById('pbLbHint').innerHTML = currentLang === 'zh'
    ? '换上你的照片，<br>一键体验同款效果'
    : 'Use your own photo,<br>then try the same look in one click.';
  document.getElementById('loadingText').textContent = currentLang === 'zh' ? '生成中…' : 'Generating…';

  const tabs = document.querySelectorAll('.pb-tab');
  if (tabs[0]) tabs[0].textContent = currentLang === 'zh' ? '全部' : 'All';
  if (tabs[2]) tabs[2].textContent = currentLang === 'zh' ? '波点拼图' : 'Dot Puzzle';

  document.getElementById('cropBtn').textContent = currentLang === 'zh' ? '裁剪' : 'Crop';
  document.getElementById('changeFileBtn').textContent = currentLang === 'zh' ? '换图' : 'Replace';
  document.getElementById('dpManualHint').textContent = currentLang === 'zh'
    ? '点击图片可添加或删除点位。'
    : 'Click the photo to add or remove a dot.';
  document.getElementById('dp-seed-random').textContent = currentLang === 'zh' ? '随机生成初始点' : 'Generate starter points';
  document.getElementById('dp-clear-dots').textContent = currentLang === 'zh' ? '清除图片点位' : 'Clear photo points';
  document.getElementById('dpBlockManualHint').textContent = currentLang === 'zh'
    ? '在色块侧独立摆放点位。'
    : 'Place dots on the block side independently.';
  document.getElementById('dpBlockManualEmptyHint').textContent = currentLang === 'zh'
    ? '当前色块侧还没有点位，点击下方画布添加。'
    : 'No block dots yet. Click on the block canvas to add points.';
  document.getElementById('dp-block-seed-random').textContent = currentLang === 'zh' ? '随机生成色块点' : 'Generate block points';
  document.getElementById('dp-block-clear-dots').textContent = currentLang === 'zh' ? '清除色块点位' : 'Clear block points';
  document.getElementById('dpDecoupleText').textContent = currentLang === 'zh' ? '色块与图片独立' : 'Decouple block and photo';
  document.getElementById('dpSizeRandomText').textContent = currentLang === 'zh' ? '随机大小' : 'Random sizes';
  document.getElementById('cwAutoColorText').textContent = currentLang === 'zh' ? '自动提取颜色' : 'Auto color';
  document.getElementById('cwAutoTextColorText').textContent = currentLang === 'zh' ? '自动文字颜色' : 'Auto text color';
  document.getElementById('dpPositionLabel').textContent = currentLang === 'zh' ? '位置' : 'Side';
  document.getElementById('dpBlockRatioLabel').textContent = currentLang === 'zh' ? '比例' : 'Size';
  document.getElementById('dpBlockTypeLabel').textContent = currentLang === 'zh' ? '样式' : 'Style';
  document.getElementById('dpColor1Label').textContent = currentLang === 'zh' ? '颜色' : 'Color';
  document.getElementById('dpGradDirLabel').textContent = currentLang === 'zh' ? '方向' : 'Flow';
  document.getElementById('dpGrad1Label').textContent = currentLang === 'zh' ? '起色' : 'Start';
  document.getElementById('dpGrad2Label').textContent = currentLang === 'zh' ? '终色' : 'End';
  document.getElementById('dpStripe1Label').textContent = currentLang === 'zh' ? '色1' : 'Color A';
  document.getElementById('dpStripe2Label').textContent = currentLang === 'zh' ? '色2' : 'Color B';
  document.getElementById('dpStripeDirLabel').textContent = currentLang === 'zh' ? '方向' : 'Flow';
  document.getElementById('dpShapeLabel').textContent = currentLang === 'zh' ? '形态' : 'Shape';
  document.getElementById('dpCustomTextLabel').textContent = currentLang === 'zh' ? '文字' : 'Text';
  document.getElementById('dpDotSizeLabel').textContent = currentLang === 'zh' ? '大小' : 'Size';
  document.getElementById('dpDotCountLabel').textContent = currentLang === 'zh' ? '数量' : 'Count';
  document.getElementById('dpDistributionLabel').textContent = currentLang === 'zh' ? '图片' : 'Photo';
  document.getElementById('dpBlockDistributionLabel').textContent = currentLang === 'zh' ? '色块' : 'Block';
  document.getElementById('dpTextLabel').textContent = currentLang === 'zh' ? '内容' : 'Text';
  document.getElementById('dpTextSizeLabel').textContent = currentLang === 'zh' ? '字号' : 'Size';
  document.getElementById('dpTextColorLabel').textContent = currentLang === 'zh' ? '颜色' : 'Color';
  document.getElementById('cwRatioLabel').textContent = currentLang === 'zh' ? '比例' : 'Size';
  document.getElementById('cwColorLabel').textContent = currentLang === 'zh' ? '颜色' : 'Color';
  document.getElementById('cwTextLabel').textContent = currentLang === 'zh' ? '内容' : 'Text';
  document.getElementById('cwFontSizeLabel').textContent = currentLang === 'zh' ? '字号' : 'Size';
  document.getElementById('cwTextColorLabel').textContent = currentLang === 'zh' ? '颜色' : 'Color';
  document.getElementById('cropLabel').textContent = currentLang === 'zh' ? '裁剪图片' : 'Crop image';
  document.getElementById('cropFreeBtn').textContent = currentLang === 'zh' ? '自由' : 'Free';
  document.getElementById('cropReset').textContent = currentLang === 'zh' ? '重置' : 'Reset';
  document.getElementById('cropCancel').textContent = currentLang === 'zh' ? '取消' : 'Cancel';
  document.getElementById('cropConfirm').textContent = currentLang === 'zh' ? '确认裁剪' : 'Confirm crop';
  document.getElementById('communitySubmitTitle').textContent = currentLang === 'zh' ? '投稿到社区' : 'Submit to Community';
  document.getElementById('communitySubmitCopy').textContent = currentLang === 'zh'
    ? '提交你当前完成的作品。审核通过前，它不会公开显示。'
    : 'Share your current finished work. It will stay hidden until you approve it in admin.';
  document.getElementById('communityDisplayNameLabel').textContent = currentLang === 'zh' ? '昵称' : 'Display name';
  document.getElementById('communityDescriptionLabel').textContent = currentLang === 'zh' ? '作品说明' : 'Description';
  document.getElementById('communityDisplayName').placeholder = currentLang === 'zh' ? '你的名字或昵称' : 'Your name or nickname';
  document.getElementById('communityDescription').placeholder = currentLang === 'zh' ? '给这件作品补一句简短说明' : 'Add one short line about this work';
  document.getElementById('communitySubmitCancel').textContent = currentLang === 'zh' ? '取消' : 'Cancel';
  document.getElementById('communitySubmitConfirm').textContent = currentLang === 'zh' ? '确认投稿' : 'Submit';
  document.querySelector('#dp-position option[value="right"]').textContent = currentLang === 'zh' ? '右' : 'Right';
  document.querySelector('#dp-position option[value="left"]').textContent = currentLang === 'zh' ? '左' : 'Left';
  document.querySelector('#dp-position option[value="top"]').textContent = currentLang === 'zh' ? '上' : 'Top';
  document.querySelector('#dp-position option[value="bottom"]').textContent = currentLang === 'zh' ? '下' : 'Bottom';
  document.querySelector('#dp-block-type option[value="solid"]').textContent = currentLang === 'zh' ? '纯色' : 'Solid';
  document.querySelector('#dp-block-type option[value="gradient"]').textContent = currentLang === 'zh' ? '渐变' : 'Gradient';
  document.querySelector('#dp-block-type option[value="stripe"]').textContent = currentLang === 'zh' ? '条纹' : 'Stripe';
  document.querySelector('#dp-block-type option[value="vintage"]').textContent = currentLang === 'zh' ? '复古纹理' : 'Vintage';
  document.querySelector('#dp-grad-dir option[value="vertical"]').textContent = currentLang === 'zh' ? '上→下' : 'Top → Bottom';
  document.querySelector('#dp-grad-dir option[value="horizontal"]').textContent = currentLang === 'zh' ? '左→右' : 'Left → Right';
  document.querySelector('#dp-stripe-dir option[value="vertical"]').textContent = currentLang === 'zh' ? '竖向' : 'Vertical';
  document.querySelector('#dp-stripe-dir option[value="horizontal"]').textContent = currentLang === 'zh' ? '横向' : 'Horizontal';
  document.querySelector('#dp-shape option[value="circle"]').textContent = currentLang === 'zh' ? '圆点' : 'Circle';
  document.querySelector('#dp-shape option[value="star"]').textContent = currentLang === 'zh' ? '星星' : 'Star';
  document.querySelector('#dp-shape option[value="teardrop"]').textContent = currentLang === 'zh' ? '水滴' : 'Teardrop';
  document.querySelector('#dp-shape option[value="moon"]').textContent = currentLang === 'zh' ? '月亮' : 'Moon';
  document.querySelector('#dp-shape option[value="heart"]').textContent = currentLang === 'zh' ? '心形' : 'Heart';
  document.querySelector('#dp-shape option[value="text"]').textContent = currentLang === 'zh' ? '文字' : 'Text';
  document.querySelector('#dp-distribution option[value="random"]').textContent = currentLang === 'zh' ? '随机' : 'Random';
  document.querySelector('#dp-distribution option[value="grid"]').textContent = currentLang === 'zh' ? '网格' : 'Grid';
  document.querySelector('#dp-distribution option[value="edge"]').textContent = currentLang === 'zh' ? '边缘' : 'Edge';
  document.querySelector('#dp-distribution option[value="manual"]').textContent = currentLang === 'zh' ? '手动选点' : 'Manual';
  document.querySelector('#dp-block-distribution option[value="linked"]').textContent = currentLang === 'zh' ? '跟随图片' : 'Follow photo';
  document.querySelector('#dp-block-distribution option[value="random"]').textContent = currentLang === 'zh' ? '随机' : 'Random';
  document.querySelector('#dp-block-distribution option[value="grid"]').textContent = currentLang === 'zh' ? '网格' : 'Grid';
  document.querySelector('#dp-block-distribution option[value="edge"]').textContent = currentLang === 'zh' ? '边缘' : 'Edge';
  document.querySelector('#dp-block-distribution option[value="manual"]').textContent = currentLang === 'zh' ? '手动选点' : 'Manual';
  document.querySelector('#cw-text').placeholder = currentLang === 'zh' ? '例如：Summer 2025' : 'e.g. Summer 2025';
  document.querySelector('#dp-text').placeholder = currentLang === 'zh' ? '留空则不显示' : 'Leave empty to hide';
  document.querySelector('#dp-custom-text').placeholder = currentLang === 'zh' ? '最多4字' : 'Up to 4 chars';

  document.querySelectorAll('.mode-name')[0].textContent = currentLang === 'zh' ? '波点拼图' : 'Dot Puzzle';
  document.querySelectorAll('.mode-name')[1].textContent = 'ColorWalk';
  document.querySelectorAll('.mode-desc')[0].textContent = currentLang === 'zh'
    ? '将图片切割成趣味波点拼图，支持自定义波点大小、形状与分布方式。'
    : 'Turn your image into a playful dot collage with custom dot size, shape, and distribution.';
  document.querySelectorAll('.mode-desc')[1].textContent = currentLang === 'zh'
    ? '提取主色，生成色块与照片组合，并可叠加文字。'
    : 'Extract a dominant color, pair it with your photo, and add text in one composition.';
  document.querySelectorAll('.settings-title')[0].textContent = currentLang === 'zh' ? '色块' : 'Block';
  document.querySelectorAll('.settings-title')[1].textContent = currentLang === 'zh' ? '波点' : 'Dots';
  document.querySelectorAll('.settings-title')[2].textContent = currentLang === 'zh' ? '文字叠加' : 'Text Overlay';
  document.querySelectorAll('.settings-title')[3].textContent = currentLang === 'zh' ? '色块' : 'Block';
  document.querySelectorAll('.settings-title')[4].textContent = currentLang === 'zh' ? '文字' : 'Text';

  updateExtractedColorHint();
  syncUploadPresetState();
  renderPlaybook(getCurrentFilter());
}

function getPresetLabel(entry) {
  if (currentLang === 'en') {
    if (entry.mode === 'dot') return 'Dot Puzzle';
    if (entry.mode === 'colorwalk') return 'ColorWalk';
  }
  if (entry.mode === 'dot') return '波点拼图';
  if (entry.mode === 'colorwalk') return 'ColorWalk';
  return entry.label;
}

function collectCurrentPreset() {
  return currentMode === 'dot' ? collectDotPreset() : collectColorwalkPreset();
}

function collectDotPreset() {
  const blockType = document.getElementById('dp-block-type').value;
  const settings = {
    dpPosition: document.getElementById('dp-position').value,
    dpBlockRatio: parseInt(document.getElementById('dp-block-ratio').value, 10),
    dpBlockType: blockType,
    dpColor1: normalizeHex(document.getElementById('dp-color1').value),
    dpGrad1: normalizeHex(document.getElementById('dp-grad1').value),
    dpGrad2: normalizeHex(document.getElementById('dp-grad2').value),
    dpStripe1: normalizeHex(document.getElementById('dp-stripe1').value),
    dpStripe2: normalizeHex(document.getElementById('dp-stripe2').value),
    dpGradDir: document.getElementById('dp-grad-dir').value,
    dpStripeDir: document.getElementById('dp-stripe-dir').value,
    dpShape: document.getElementById('dp-shape').value,
    dpCustomText: document.getElementById('dp-custom-text').value,
    dpDotSize: parseInt(document.getElementById('dp-dot-size').value, 10),
    dpDotCount: parseInt(document.getElementById('dp-dot-count').value, 10),
    dpDistribution: document.getElementById('dp-distribution').value,
    dpBlockDistribution: document.getElementById('dp-decouple').checked
      ? getCurrentBlockDistributionValue()
      : 'linked',
    dpSizeRandom: document.getElementById('dp-size-random').checked,
    dpDecouple: document.getElementById('dp-decouple').checked,
    dpText: document.getElementById('dp-text').value,
    dpTextSize: parseInt(document.getElementById('dp-text-size').value, 10),
    dpTextColor: normalizeHex(document.getElementById('dp-text-color').value),
    dpSeed: currentDotSeed,
  };

  if (settings.dpDistribution === 'manual') {
    settings.dpManualPositions = manualDots.map(({ nx, ny }) => [
      Number(nx.toFixed(6)),
      Number(ny.toFixed(6)),
    ]);
  }
  if (settings.dpDecouple && settings.dpBlockDistribution === 'manual') {
    settings.dpBlockManualPositions = blockManualDots.map(({ nx, ny }) => [
      Number(nx.toFixed(6)),
      Number(ny.toFixed(6)),
    ]);
  }

  return {
    mode: 'dot',
    label: '波点拼图',
    settings,
  };
}

function collectColorwalkPreset() {
  const autoColor = document.getElementById('cw-auto-color').checked;
  const autoTextColor = document.getElementById('cw-auto-text-color').checked;
  const colorHex = getResolvedColorwalkColorHex();
  const settings = {
    cwRatio: parseInt(document.getElementById('cw-ratio').value, 10),
    cwAutoColor: autoColor,
    cwText: document.getElementById('cw-text').value,
    cwFontSize: parseInt(document.getElementById('cw-font-size').value, 10),
    cwAutoTextColor: autoTextColor,
  };
  if (!autoColor) settings.cwColor = colorHex;
  if (!autoTextColor) settings.cwTextColor = normalizeHex(document.getElementById('cw-text-color').value);

  return {
    mode: 'colorwalk',
    label: 'ColorWalk',
    settings,
  };
}

function syncDotBlockTypeUI(value) {
  document.getElementById('dp-color-solid').style.display = value === 'solid' || value === 'vintage' ? 'flex' : 'none';
  document.getElementById('dp-color-gradient').style.display = value === 'gradient' ? 'block' : 'none';
  document.getElementById('dp-color-stripe').style.display = value === 'stripe' ? 'block' : 'none';
  redrawBlockCanvas();
}

function syncDotShapeUI(value) {
  document.getElementById('dp-custom-text-wrap').style.display = value === 'text' ? 'flex' : 'none';
}

function setSliderValue(inputId, valueId, value, suffix = '') {
  document.getElementById(inputId).value = value;
  document.getElementById(valueId).textContent = value + suffix;
}

function applyPresetSettings(entry) {
  const s = entry.settings || {};
  if (entry.mode === 'colorwalk') {
    setSliderValue('cw-ratio', 'cw-ratio-val', s.cwRatio ?? 45, '%');

    const autoColor = s.cwAutoColor ?? !s.cwColor;
    document.getElementById('cw-auto-color').checked = autoColor;
    document.getElementById('cw-manual-color').style.display = autoColor ? 'none' : 'flex';
    if (s.cwColor) setColorPairValue('cw-color', 'cw-color-hex', s.cwColor);

    document.getElementById('cw-text').value = s.cwText ?? '';
    document.getElementById('cw-font-size').value = s.cwFontSize ?? 45;

    const autoTextColor = s.cwAutoTextColor ?? !s.cwTextColor;
    document.getElementById('cw-auto-text-color').checked = autoTextColor;
    document.getElementById('cw-manual-text-color').style.display = autoTextColor ? 'none' : 'flex';
    if (s.cwTextColor) setColorPairValue('cw-text-color', 'cw-text-color-hex', s.cwTextColor);
    return;
  }

  document.getElementById('dp-position').value = s.dpPosition || 'right';
  setSliderValue('dp-block-ratio', 'dp-block-ratio-val', s.dpBlockRatio ?? 40, '%');

  const blockType = s.dpBlockType || 'solid';
  document.getElementById('dp-block-type').value = blockType;
  syncDotBlockTypeUI(blockType);

  document.getElementById('dp-color1').value = normalizeHex(s.dpColor1 || '#C8B4A0');
  document.getElementById('dp-grad1').value = normalizeHex(s.dpGrad1 || '#F5D0A9');
  document.getElementById('dp-grad2').value = normalizeHex(s.dpGrad2 || '#9FC8E0');
  document.getElementById('dp-stripe1').value = normalizeHex(s.dpStripe1 || '#F5C0CC');
  document.getElementById('dp-stripe2').value = normalizeHex(s.dpStripe2 || '#A8C8E8');
  document.getElementById('dp-grad-dir').value = s.dpGradDir || 'vertical';
  document.getElementById('dp-stripe-dir').value = s.dpStripeDir || 'vertical';

  const shape = s.dpShape || 'circle';
  document.getElementById('dp-shape').value = shape;
  syncDotShapeUI(shape);
  document.getElementById('dp-custom-text').value = s.dpCustomText ?? '';

  setSliderValue('dp-dot-size', 'dp-dot-size-val', s.dpDotSize ?? 60, 'px');
  setSliderValue('dp-dot-count', 'dp-dot-count-val', s.dpDotCount ?? 12);

  const distribution = s.dpDistribution || 'random';
  document.getElementById('dp-distribution').value = distribution;
  syncDotDistributionUI();

  document.getElementById('dp-size-random').checked = Boolean(s.dpSizeRandom);
  document.getElementById('dp-decouple').checked = Boolean(s.dpDecouple);
  document.getElementById('dp-block-distribution').value = s.dpBlockDistribution || 'linked';
  hasExplicitBlockDecoupleState = Boolean(s.dpDecouple) || Boolean(s.dpBlockDistribution && s.dpBlockDistribution !== 'linked');
  syncBlockDistributionUI();
  document.getElementById('dp-text').value = s.dpText ?? '';
  document.getElementById('dp-text-size').value = s.dpTextSize ?? 32;
  setColorPairValue('dp-text-color', 'dp-text-color-hex', s.dpTextColor || '#FFFFFF');

  currentDotSeed = Number.isInteger(s.dpSeed) ? s.dpSeed : createRandomSeed();
  manualDots = Array.isArray(s.dpManualPositions)
    ? s.dpManualPositions.map(([nx, ny]) => ({ nx, ny }))
    : [];
  blockManualDots = Array.isArray(s.dpBlockManualPositions)
    ? s.dpBlockManualPositions.map(([nx, ny]) => ({ nx, ny }))
    : [];
  if (blockManualDots.length > 0) hasExplicitBlockDecoupleState = true;

  if (distribution === 'manual') {
    if (document.getElementById('dp-dot-canvas').width === 0) {
      initDotCanvas();
      setTimeout(() => redrawDotCanvas(), 60);
    } else {
      redrawDotCanvas();
    }
  } else {
    redrawDotCanvas();
  }
  redrawBlockCanvas();
}

/* ── Apply ── */
async function applyDotPuzzle() {
  const params = buildDotParams();
  lastParams.dot = params;
  await renderPreview('dot', params, 'main-preview-box', 'main-dl-row');
}

async function applyColorwalk() {
  const params = buildColorwalkParams();
  lastParams.colorwalk = params;
  await renderPreview('colorwalk', params, 'main-preview-box', 'main-dl-row');
}

/* ── Render preview ── */
async function renderPreview(mode, params, boxId, dlRowId) {
  if (activeRequest[mode]) activeRequest[mode].abort();
  const controller = new AbortController();
  activeRequest[mode] = controller;

  setBoxLoading(boxId, true);
  const endpoint = mode === 'dot' ? '/api/dot-puzzle' : '/api/colorwalk';
  const fd = new FormData();
  fd.append('image', previewBlob, 'preview.jpg');
  for (const [k, v] of Object.entries(params)) fd.append(k, v);

  try {
    const res = await fetch(endpoint, { method: 'POST', body: fd, signal: controller.signal });
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const box = document.getElementById(boxId);
    box.innerHTML = `<img src="${url}" alt="preview" />`;
    document.getElementById(dlRowId).style.display = 'flex';
    return true;
  } catch (err) {
    if (err.name !== 'AbortError') console.error('Preview error:', err.message);
    return false;
  } finally {
    if (activeRequest[mode] === controller) {
      setBoxLoading(boxId, false);
      activeRequest[mode] = null;
    }
  }
}

/* ── Download ── */
async function renderFinalImageBlob(mode, format = 'PNG') {
  if (!currentFile) return null;
  const src = croppedFile ?? currentFile;
  const endpoint = mode === 'dot' ? '/api/dot-puzzle' : '/api/colorwalk';
  const params = buildSourceRenderParams(mode, { format });
  const fd = new FormData();
  fd.append('image', src);
  for (const [k, v] of Object.entries(params)) fd.append(k, v);

  const res = await fetch(endpoint, { method: 'POST', body: fd });
  if (!res.ok) throw new Error(await res.text());
  return await res.blob();
}

async function downloadFile(fmt) {
  if (!currentFile) return;
  clearTimeout(debounceTimers[currentMode]);
  const baseParams = buildBaseRenderParams(currentMode);
  lastParams[currentMode] = baseParams;
  const previewReady = await renderPreview(currentMode, baseParams, 'main-preview-box', 'main-dl-row');
  if (!previewReady) return;

  showFullLoading(true);
  try {
    const blob = await renderFinalImageBlob(currentMode, fmt);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${currentMode === 'dot' ? 'dot_puzzle' : 'colorwalk'}.${fmt.toLowerCase()}`;
    a.click();
  } catch (err) {
    alert(currentLang === 'zh' ? `下载失败：${err.message}` : `Download failed: ${err.message}`);
  } finally {
    showFullLoading(false);
  }
}

document.getElementById('btn-dl-png').addEventListener('click', () => downloadFile('PNG'));
document.getElementById('btn-dl-jpg').addEventListener('click', () => downloadFile('JPG'));

/* ── Crop ── */
let cropImgEl = null;
let cropScale = 1;
let cropStart = null;
let cropEnd = null;
let cropRatio = 'free';
let cropDragging = false;

function openCrop() {
  const src = croppedFile ?? currentFile;
  if (!src) return;
  document.getElementById('cropModal').style.display = 'flex';
  cropStart = null; cropEnd = null;

  const img = new Image();
  const url = URL.createObjectURL(src);
  img.onload = () => {
    URL.revokeObjectURL(url);
    cropImgEl = img;
    const canvas = document.getElementById('cropCanvas');
    const maxW = Math.min(820, window.innerWidth * 0.88);
    const maxH = window.innerHeight * 0.72;
    cropScale = Math.min(maxW / img.width, maxH / img.height, 1);
    canvas.width = Math.round(img.width * cropScale);
    canvas.height = Math.round(img.height * cropScale);
    drawCrop();
  };
  img.src = url;
}

function closeCrop() {
  document.getElementById('cropModal').style.display = 'none';
  cropStart = null; cropEnd = null;
}

function drawCrop() {
  const canvas = document.getElementById('cropCanvas');
  if (!cropImgEl || !canvas.width) return;
  const ctx = canvas.getContext('2d');
  const cw = canvas.width, ch = canvas.height;
  ctx.clearRect(0, 0, cw, ch);

  // Dimmed base image
  ctx.save();
  ctx.globalAlpha = 0.38;
  ctx.drawImage(cropImgEl, 0, 0, cw, ch);
  ctx.globalAlpha = 1;
  ctx.restore();

  if (cropStart && cropEnd) {
    const x = Math.min(cropStart.x, cropEnd.x);
    const y = Math.min(cropStart.y, cropEnd.y);
    const w = Math.abs(cropEnd.x - cropStart.x);
    const h = Math.abs(cropEnd.y - cropStart.y);
    if (w < 2 || h < 2) return;

    // Full-brightness crop area
    ctx.save();
    ctx.beginPath();
    ctx.rect(x, y, w, h);
    ctx.clip();
    ctx.drawImage(cropImgEl, 0, 0, cw, ch);
    ctx.restore();

    // Dashed border
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 3]);
    ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
    ctx.setLineDash([]);

    // Rule-of-thirds grid
    ctx.strokeStyle = 'rgba(255,255,255,0.28)';
    ctx.lineWidth = 0.8;
    ctx.beginPath();
    for (let i = 1; i < 3; i++) {
      ctx.moveTo(x + w * i / 3, y); ctx.lineTo(x + w * i / 3, y + h);
      ctx.moveTo(x, y + h * i / 3); ctx.lineTo(x + w, y + h * i / 3);
    }
    ctx.stroke();

    // Corner handles
    const hs = 8;
    ctx.fillStyle = '#fff';
    [[x, y], [x + w - hs, y], [x, y + h - hs], [x + w - hs, y + h - hs]]
      .forEach(([hx, hy]) => ctx.fillRect(hx, hy, hs, hs));

    // Size hint
    const srcW = Math.round(w / cropScale);
    const srcH = Math.round(h / cropScale);
    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    ctx.fillRect(x, y + h - 22, 90, 22);
    ctx.fillStyle = '#fff';
    ctx.font = '11px monospace';
    ctx.fillText(`${srcW} × ${srcH}`, x + 6, y + h - 7);
  }
}

function getCanvasPos(canvas, e) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;
  return {
    x: Math.max(0, Math.min(canvas.width, (e.clientX - rect.left) * scaleX)),
    y: Math.max(0, Math.min(canvas.height, (e.clientY - rect.top) * scaleY)),
  };
}

function applyRatioConstraint(rawX, rawY) {
  if (cropRatio === 'free' || !cropStart) return { x: rawX, y: rawY };
  const ratio = parseFloat(cropRatio);
  const dx = rawX - cropStart.x;
  const dy = rawY - cropStart.y;
  const absDx = Math.abs(dx), absDy = Math.abs(dy);
  let w, h;
  if (absDx / ratio >= absDy) { w = absDx; h = absDx / ratio; }
  else { h = absDy; w = absDy * ratio; }
  return {
    x: cropStart.x + (dx >= 0 ? w : -w),
    y: cropStart.y + (dy >= 0 ? h : -h),
  };
}

const cropCanvas = document.getElementById('cropCanvas');
cropCanvas.addEventListener('mousedown', (e) => {
  cropStart = getCanvasPos(cropCanvas, e);
  cropEnd = { ...cropStart };
  cropDragging = true;
});
cropCanvas.addEventListener('mousemove', (e) => {
  if (!cropDragging) return;
  const raw = getCanvasPos(cropCanvas, e);
  cropEnd = applyRatioConstraint(raw.x, raw.y);
  // Clamp
  cropEnd.x = Math.max(0, Math.min(cropCanvas.width, cropEnd.x));
  cropEnd.y = Math.max(0, Math.min(cropCanvas.height, cropEnd.y));
  drawCrop();
});
cropCanvas.addEventListener('mouseup', () => { cropDragging = false; });
cropCanvas.addEventListener('mouseleave', () => { cropDragging = false; });

document.querySelectorAll('.crop-ratio-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.crop-ratio-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    cropRatio = btn.dataset.ratio;
    cropStart = null; cropEnd = null;
    drawCrop();
  });
});

document.getElementById('cropReset').addEventListener('click', () => {
  cropStart = null; cropEnd = null;
  drawCrop();
});

document.getElementById('cropCancel').addEventListener('click', closeCrop);

document.getElementById('cropConfirm').addEventListener('click', () => {
  if (!cropStart || !cropEnd || !cropImgEl) return;
  const x = Math.min(cropStart.x, cropEnd.x) / cropScale;
  const y = Math.min(cropStart.y, cropEnd.y) / cropScale;
  const w = Math.abs(cropEnd.x - cropStart.x) / cropScale;
  const h = Math.abs(cropEnd.y - cropStart.y) / cropScale;
  if (w < 10 || h < 10) return;

  const off = document.createElement('canvas');
  off.width = Math.round(w);
  off.height = Math.round(h);
  off.getContext('2d').drawImage(cropImgEl, x, y, w, h, 0, 0, w, h);
  off.toBlob(async (blob) => {
    croppedFile = blob;
    document.getElementById('thumbImg').src = URL.createObjectURL(blob);
    previewBlob = await makePreviewBlob(blob);
    if (document.getElementById('dp-distribution').value === 'manual') initDotCanvas();
    if (document.getElementById('dp-decouple').checked && getCurrentBlockDistributionValue() === 'manual') initBlockCanvas();
    await extractColor(previewBlob);
    triggerPreview(currentMode, 0);
    showSubmitButton();
    closeCrop();
  }, 'image/jpeg', 0.92);
});

document.getElementById('cropBtn').addEventListener('click', openCrop);

/* ── Playbook ── */
const DOT_PRESET_DEFAULTS = {
  dpPosition: 'right',
  dpBlockRatio: 40,
  dpBlockType: 'solid',
  dpColor1: '#C8B4A0',
  dpGrad1: '#F5D0A9',
  dpGrad2: '#9FC8E0',
  dpStripe1: '#F5C0CC',
  dpStripe2: '#A8C8E8',
  dpGradDir: 'vertical',
  dpStripeDir: 'vertical',
  dpShape: 'circle',
  dpCustomText: '',
  dpDotSize: 60,
  dpDotCount: 12,
  dpDistribution: 'random',
  dpBlockDistribution: 'linked',
  dpSizeRandom: false,
  dpDecouple: false,
  dpText: '',
  dpTextSize: 32,
  dpTextColor: '#FFFFFF',
};

const COLORWALK_PRESET_DEFAULTS = {
  cwRatio: 45,
  cwAutoColor: true,
  cwText: '',
  cwFontSize: 45,
  cwAutoTextColor: false,
  cwTextColor: '#FFFFFF',
};

function normalizePlaybookEntry(entry) {
  const baseSettings = entry.mode === 'dot' ? DOT_PRESET_DEFAULTS : COLORWALK_PRESET_DEFAULTS;
  return {
    ...entry,
    settings: {
      ...baseSettings,
      ...(entry.settings || {}),
    },
  };
}

function rgbArrayToHex(arr, fallback = '#FFFFFF') {
  return Array.isArray(arr) && arr.length >= 3 ? normalizeHex(rgbToHex(arr[0], arr[1], arr[2])) : fallback;
}

function renderParamsToPresetSettings(mode, params) {
  if (mode === 'colorwalk') {
    return {
      cwRatio: Math.round((Number(params.color_ratio ?? 0.45) || 0.45) * 100),
      cwAutoColor: !params.color,
      cwColor: Array.isArray(params.color) ? rgbArrayToHex(params.color) : undefined,
      cwText: params.text || '',
      cwFontSize: parseInt(params.font_size ?? 45, 10),
      cwAutoTextColor: !params.text_color,
      cwTextColor: Array.isArray(params.text_color) ? rgbArrayToHex(params.text_color) : undefined,
    };
  }

  return {
    dpPosition: params.position || 'right',
    dpBlockRatio: Math.round((Number(params.block_ratio ?? 0.4) || 0.4) * 100),
    dpBlockType: params.block_type || 'solid',
    dpColor1: Array.isArray(params.block_color) && !Array.isArray(params.block_color[0])
      ? rgbArrayToHex(params.block_color, '#C8B4A0')
      : '#C8B4A0',
    dpGrad1: Array.isArray(params.block_color) && Array.isArray(params.block_color[0])
      ? rgbArrayToHex(params.block_color[0], '#F5D0A9')
      : '#F5D0A9',
    dpGrad2: Array.isArray(params.block_color) && Array.isArray(params.block_color[1])
      ? rgbArrayToHex(params.block_color[1], '#9FC8E0')
      : '#9FC8E0',
    dpStripe1: Array.isArray(params.block_color) && Array.isArray(params.block_color[0])
      ? rgbArrayToHex(params.block_color[0], '#F5C0CC')
      : '#F5C0CC',
    dpStripe2: Array.isArray(params.block_color) && Array.isArray(params.block_color[1])
      ? rgbArrayToHex(params.block_color[1], '#A8C8E8')
      : '#A8C8E8',
    dpGradDir: params.gradient_dir || 'vertical',
    dpStripeDir: params.stripe_dir || 'vertical',
    dpShape: params.shape || 'circle',
    dpCustomText: params.custom_text || '',
    dpDotSize: parseInt(params.dot_size ?? 60, 10),
    dpDotCount: parseInt(params.dot_count ?? 12, 10),
    dpDistribution: params.distribution || 'random',
    dpBlockDistribution: params.block_distribution || 'linked',
    dpSizeRandom: Boolean(params.size_random),
    dpDecouple: Boolean(params.decouple),
    dpText: params.text_overlay || '',
    dpTextSize: parseInt(params.text_font_size ?? 32, 10),
    dpTextColor: Array.isArray(params.text_color) ? rgbArrayToHex(params.text_color) : '#FFFFFF',
    dpSeed: params.seed != null ? parseInt(params.seed, 10) : undefined,
    dpManualPositions: Array.isArray(params.manual_positions) ? params.manual_positions : undefined,
    dpBlockManualPositions: Array.isArray(params.block_manual_positions) ? params.block_manual_positions : undefined,
  };
}

function normalizePlaybookItem(entry) {
  return normalizePlaybookEntry({
    ...entry,
    img: entry.image_url,
    source: entry.source_type,
    label: entry.label || (entry.mode === 'dot' ? '波点拼图' : 'ColorWalk'),
  });
}

async function loadPlaybookItems(filter = 'all', force = false) {
  const normalizedFilter = filter || 'all';
  if (!force && playbookItems.length > 0 && lastPlaybookFilter === normalizedFilter) return;
  playbookLoading = true;
  lastPlaybookFilter = normalizedFilter;
  const grid = document.getElementById('playbookGrid');
  grid.innerHTML = `<div class="pb-empty">${currentLang === 'zh' ? '加载案例中…' : 'Loading playbooks…'}</div>`;
  try {
    const res = await fetch(`/api/playbooks?mode=${encodeURIComponent(normalizedFilter)}`);
    const data = await res.json();
    playbookItems = Array.isArray(data.items) ? data.items.map(normalizePlaybookItem) : [];
  } catch (err) {
    playbookItems = [];
  } finally {
    playbookLoading = false;
  }
}

function renderPlaybook(filter = 'all') {
  const grid = document.getElementById('playbookGrid');
  document.getElementById('playbookTitle').textContent = currentLang === 'zh' ? '大家都在做' : 'Popular Playbooks';
  grid.innerHTML = '';
  const entries = playbookItems.filter(p => filter === 'all' || p.mode === filter);
  if (entries.length === 0) {
    grid.innerHTML = `<div class="pb-empty">${currentLang === 'zh' ? '当前分类下还没有案例。' : 'No playbooks in this category yet.'}</div>`;
    return;
  }
  entries.forEach(entry => {
    const card = document.createElement('div');
    card.className = 'pb-card' + (selectedPreset?.id === entry.id ? ' selected' : '');
    const label = getPresetLabel(entry);
    const meta = entry.source === 'community'
      ? `<div class="pb-card-meta">${escapeHtml(entry.display_name || '')}</div>`
      : '';
    card.innerHTML = `
      <img src="${entry.img}" alt="" loading="lazy" />
      <div class="pb-card-overlay">
        <span class="pb-badge">${label}</span>
      </div>
      ${meta}`;
    card.addEventListener('click', () => openLightbox(entry));
    grid.appendChild(card);
  });
}

function applyPreset(entry) {
  selectedPreset = entry;
  document.getElementById('presetBarName').textContent = getPresetLabel(entry);
  document.getElementById('presetBar').style.display = 'flex';
  renderPlaybook(getCurrentFilter());
  syncUploadPresetState();

  if (currentFile) {
    applyPresetSettings(entry);
    currentMode = entry.mode;
    showSettings(currentMode);
    goToStep(3);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    triggerPreview(currentMode, 0);
  } else {
    goToStep(1);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

/* ── Playbook Lightbox ── */
let lightboxEntry = null;

function openLightbox(entry) {
  lightboxEntry = entry;
  document.getElementById('pbLbImg').src = entry.img;
  document.getElementById('pbLbBadge').textContent = getPresetLabel(entry);
  const metaEl = document.getElementById('pbLbMeta');
  if (entry.source === 'community') {
    const line1 = entry.display_name || '';
    const line2 = entry.description || '';
    metaEl.innerHTML = `${line1 ? `<strong>${escapeHtml(line1)}</strong>` : ''}${line2 ? `<br>${escapeHtml(line2)}` : ''}`;
    metaEl.style.display = 'block';
  } else {
    metaEl.textContent = '';
    metaEl.style.display = 'none';
  }
  document.getElementById('pbLightbox').style.display = 'flex';
}

function closeLightbox() {
  document.getElementById('pbLightbox').style.display = 'none';
  lightboxEntry = null;
}

document.getElementById('pbLbBackdrop').addEventListener('click', closeLightbox);
document.getElementById('pbLbClose').addEventListener('click', closeLightbox);
document.getElementById('pbLbTry').addEventListener('click', () => {
  if (lightboxEntry) applyPreset(lightboxEntry);
  closeLightbox();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && document.getElementById('pbLightbox').style.display !== 'none') closeLightbox();
});

document.querySelectorAll('.pb-tab').forEach(tab => {
  tab.addEventListener('click', async () => {
    document.querySelectorAll('.pb-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    await loadPlaybookItems(tab.dataset.filter, true);
    renderPlaybook(tab.dataset.filter);
  });
});

document.getElementById('presetBarClear').addEventListener('click', () => {
  selectedPreset = null;
  document.getElementById('presetBar').style.display = 'none';
  renderPlaybook(getCurrentFilter());
  syncUploadPresetState();
});

document.getElementById('langEnBtn').addEventListener('click', () => applyLanguage('en'));
document.getElementById('langZhBtn').addEventListener('click', () => applyLanguage('zh'));

/* ── Copy params (for updating playbook data) ── */
document.getElementById('btnCopyParams').addEventListener('click', () => {
  const params = collectCurrentPreset();
  const json = JSON.stringify(params, null, 2);
  const btn = document.getElementById('btnCopyParams');
  navigator.clipboard.writeText(json).then(() => {
    btn.textContent = currentLang === 'zh' ? '✓ 已复制' : '✓ Copied';
    setTimeout(() => {
      btn.textContent = currentLang === 'zh' ? '复制参数' : 'Copy params';
    }, 2000);
  }).catch(() => {
    prompt(currentLang === 'zh' ? '复制以下参数：' : 'Copy these params:', json);
  });
});

function openSubmitModal() {
  document.getElementById('communitySubmitModal').style.display = 'flex';
  document.getElementById('communitySubmitStatus').textContent = '';
}

function closeSubmitModal() {
  document.getElementById('communitySubmitModal').style.display = 'none';
}

function getSubmissionCooldownUntil() {
  try {
    return Number(localStorage.getItem('cw_submit_cooldown_until') || '0');
  } catch {
    return 0;
  }
}

function setSubmissionCooldown() {
  try {
    localStorage.setItem('cw_submit_cooldown_until', String(Date.now() + 60000));
  } catch {}
}

async function submitCurrentWork() {
  const statusEl = document.getElementById('communitySubmitStatus');
  const displayName = document.getElementById('communityDisplayName').value.trim();
  const description = document.getElementById('communityDescription').value.trim();
  const website = document.getElementById('communityWebsite').value.trim();
  if (!currentFile) return;

  const cooldownUntil = getSubmissionCooldownUntil();
  if (cooldownUntil > Date.now()) {
    statusEl.textContent = currentLang === 'zh'
      ? '刚提交过一次，请稍后再试。'
      : 'You just submitted recently. Please wait a little and try again.';
    return;
  }

  const params = buildSourceRenderParams(currentMode);
  const fd = new FormData();
  fd.append('image', croppedFile ?? currentFile);
  fd.append('mode', currentMode);
  fd.append('display_name', displayName);
  fd.append('description', description);
  fd.append('website', website);
  fd.append('params_json', JSON.stringify(params));
  statusEl.textContent = currentLang === 'zh' ? '提交中…' : 'Submitting…';

  try {
    const renderedBlob = await renderFinalImageBlob(currentMode, 'PNG');
    fd.append('rendered_image', renderedBlob, `${currentMode}_submission.png`);
    const res = await fetch('/api/community/submit', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) {
      statusEl.textContent = data.error || (currentLang === 'zh' ? '投稿失败，请重试。' : 'Submission failed.');
      return;
    }
    setSubmissionCooldown();
    document.getElementById('communityDisplayName').value = '';
    document.getElementById('communityDescription').value = '';
    statusEl.textContent = currentLang === 'zh' ? '已提交，等待审核。' : 'Submitted for review.';
    await loadPlaybookItems(getCurrentFilter(), true);
    setTimeout(closeSubmitModal, 900);
  } catch (err) {
    statusEl.textContent = currentLang === 'zh' ? '投稿失败，请重试。' : 'Submission failed.';
  }
}

document.getElementById('btnSubmitCommunity').addEventListener('click', openSubmitModal);
document.getElementById('communitySubmitBackdrop').addEventListener('click', closeSubmitModal);
document.getElementById('communitySubmitClose').addEventListener('click', closeSubmitModal);
document.getElementById('communitySubmitCancel').addEventListener('click', closeSubmitModal);
document.getElementById('communitySubmitConfirm').addEventListener('click', submitCurrentWork);

/* ── Init ── */
goToStep(1);
loadPlaybookItems().then(() => renderPlaybook()).catch(() => renderPlaybook());
let savedLang = 'en';
try { savedLang = localStorage.getItem('cw_lang') || 'en'; } catch {}
applyLanguage(savedLang);
syncUploadPresetState();
showSubmitButton();
