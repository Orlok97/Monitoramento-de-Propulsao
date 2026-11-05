const URL_ULTIMOS = '/api/ultimos';
const URL_HISTORICO = '/api/historico';
const INTERVALO_MS = 1000;
const OFFLINE_MS = 10000;
const MAX_PONTOS = 3600;
const MAX_LINHAS = 20;
const MOTORES = ['bb', 'be'];
const COR = { bb: '#3b82f6', be: '#ef4444' };
const ESTADOS = {
  online: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  offline: 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300',
  aguardando: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
};
const BASE_BADGE_MOTOR = 'rounded-full px-2.5 py-0.5 text-xs font-medium ';
const BASE_BADGE_CONEXAO = 'inline-flex items-center gap-2 rounded-full px-3 py-1 font-medium ';
const BADGE_MOTOR = {
  bb: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  be: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
};
const $ = id => document.getElementById(id);
const buffer = { bb: [], be: [] };
const ultimoRecebido = { bb: null, be: null };
const ultimoVisto = { bb: 0, be: 0 };
const linhas = [];
let offsetServidor = 0;
const agoraServidor = () => Date.now() / 1000 + offsetServidor;
const hora = epochSeg => new Date(epochSeg * 1000).toLocaleTimeString('pt-BR');
const janelaMin = () => Number($('select-janela').value);
const fmt = (v, casas=3) => v == null || !Number.isFinite(Number(v)) ? '--' : Number(v).toFixed(casas);

const escuro = window.matchMedia('(prefers-color-scheme: dark)').matches;
Chart.defaults.color = escuro ? '#94a3b8' : '#475569';
Chart.defaults.borderColor = escuro ? '#1e293b' : '#e2e8f0';

function criarGrafico(canvasId, comLinha, xTitulo, yTitulo, xFmt) {
  return new Chart($(canvasId), {
    type: 'scatter',
    data: { datasets: MOTORES.map(m => ({
      label: m.toUpperCase(), data: [], borderColor: COR[m],
      backgroundColor: COR[m], showLine: comLinha,
      pointRadius: comLinha ? 0 : 3, borderWidth: 2, tension: 0.2,
    })) },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { type: 'linear', title: { display: true, text: xTitulo },
             ticks: { callback: xFmt || (v => v), maxTicksLimit: 8 } },
        y: { title: { display: true, text: yTitulo }, beginAtZero: true },
      },
    },
  });
}

const chartRms = criarGrafico('chart-rms', true, 'tempo', 'Aceleração RMS (m/s²)', hora);
const chartPz = criarGrafico('chart-pz', true, 'tempo', 'Piezo RMS (contagens ADC)', hora);
const chartRpm = criarGrafico('chart-rpm', true, 'tempo', 'RPM', hora);
const chartDisp = criarGrafico('chart-disp', false, 'RPM', 'Aceleração RMS MPU (m/s²)');

function normalizar(p) {
  return {
    x: p.t, rms: p.rms, pico: p.pico, rpm: p.rpm,
    rx: p.rx, ry: p.ry, rz: p.rz, mpu_ok: !!p.mpu_ok,
    mpu_erros: p.mpu_erros, pz_rms: p.pz_rms, pz_pico: p.pz_pico,
    pz_crista: p.pz_crista, pz_dc: p.pz_dc, pz_fs: p.pz_fs,
    pz_clip: p.pz_clip, pz_ok: !!p.pz_ok,
    recebido_em: p.recebido_em,
  };
}

async function carregarHistorico() {
  try {
    const resp = await fetch(`${URL_HISTORICO}?minutos=${janelaMin()}`, { cache: 'no-store' });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const dados = await resp.json();
    offsetServidor = dados.agora - Date.now() / 1000;
    linhas.length = 0;
    const todos = [];
    MOTORES.forEach(m => {
      const pts = (dados[m] || []).map(normalizar);
      buffer[m] = pts.map(p => ({ ...p }));
      const ult = pts[pts.length - 1];
      if (ult) {
        ultimoRecebido[m] = ult.recebido_em;
        ultimoVisto[m] = (ult.recebido_em - offsetServidor) * 1000;
      }
      pts.forEach(p => todos.push({ ...p, motor: m }));
    });
    todos.sort((a, b) => b.x - a.x);
    linhas.push(...todos.slice(0, MAX_LINHAS));
  } catch (err) {
    console.error('Falha ao carregar o histórico:', err);
  }
  render();
}

function processar(motor, leitura) {
  if (!leitura) return;
  if (leitura.recebido_em === ultimoRecebido[motor]) return;
  ultimoRecebido[motor] = leitura.recebido_em;
  ultimoVisto[motor] = Date.now();
  const ponto = normalizar(leitura);
  buffer[motor].push(ponto);
  if (buffer[motor].length > MAX_PONTOS) buffer[motor].shift();
  linhas.unshift({ ...ponto, motor });
  if (linhas.length > MAX_LINHAS) linhas.pop();
}

async function atualizar() {
  try {
    const resp = await fetch(URL_ULTIMOS, { cache: 'no-store' });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const dados = await resp.json();
    MOTORES.forEach(m => processar(m, dados[m]));
    definirConexao(true);
  } catch (err) {
    console.error('Falha ao consultar a API:', err);
    definirConexao(false);
  }
  render();
}

function definirConexao(ok) {
  $('conexao-status').className = BASE_BADGE_CONEXAO + (ok ? ESTADOS.online : ESTADOS.offline);
  $('conexao-texto').textContent = ok ? 'Servidor conectado' : 'Servidor offline';
  if (ok) $('ultima-atualizacao').textContent = 'Última atualização: ' + hora(agoraServidor());
}

function renderCards() {
  MOTORES.forEach(m => {
    const ult = buffer[m][buffer[m].length - 1];
    const ativo = ultimoVisto[m] && Date.now() - ultimoVisto[m] < OFFLINE_MS;
    const estado = !ultimoVisto[m] ? 'aguardando' : (ativo ? 'online' : 'offline');
    $(m + '-status').className = BASE_BADGE_MOTOR + ESTADOS[estado];
    $(m + '-status').textContent = estado === 'online' ? 'Online' : (estado === 'offline' ? 'Sem sinal' : 'Aguardando');
    if (!ult) return;

    $(m + '-rpm').textContent = ult.rpm != null ? Math.round(ult.rpm) : '--';
    $(m + '-rms').textContent = ult.mpu_ok ? fmt(ult.rms) : '--';
    $(m + '-pico').textContent = ult.mpu_ok ? fmt(ult.pico) : '--';
    $(m + '-pz-rms').textContent = ult.pz_ok ? fmt(ult.pz_rms, 1) : '--';
    $(m + '-pz-crista').textContent = ult.pz_ok ? fmt(ult.pz_crista, 2) : '--';
    $(m + '-mpu-status').textContent = ult.mpu_ok ? 'válido' : 'sem leitura válida';
    $(m + '-pz-status').textContent = ult.pz_ok ? 'válido' : 'sem leitura válida';
    $(m + '-atualizado').textContent = hora(ult.x);
  });
}

function renderGraficos() {
  const limite = agoraServidor() - janelaMin() * 60;
  MOTORES.forEach((m, i) => {
    const pts = buffer[m].filter(p => p.x >= limite);
    chartRms.data.datasets[i].data = pts.filter(p => p.mpu_ok && p.rms != null).map(p => ({ x: p.x, y: p.rms }));
    chartPz.data.datasets[i].data = pts.filter(p => p.pz_ok && p.pz_rms != null).map(p => ({ x: p.x, y: p.pz_rms }));
    chartRpm.data.datasets[i].data = pts.filter(p => p.rpm != null).map(p => ({ x: p.x, y: p.rpm }));
    chartDisp.data.datasets[i].data = pts.filter(p => p.mpu_ok && p.rpm != null && p.rms != null).map(p => ({ x: p.rpm, y: p.rms }));
  });
  [chartRms, chartPz, chartRpm, chartDisp].forEach(c => c.update('none'));
}

function renderTabela() {
  const tbody = $('tabela-leituras');
  const vazia = $('tabela-vazia');
  if (!linhas.length) { tbody.replaceChildren(vazia); return; }
  const trs = linhas.map(l => {
    const tr = document.createElement('tr');
    const celula = (txt, cls='') => {
      const td = document.createElement('td');
      td.className = 'px-4 py-2 ' + cls;
      td.textContent = txt;
      return td;
    };
    const tdMotor = celula('');
    const tag = document.createElement('span');
    tag.className = 'rounded px-2 py-0.5 text-xs font-medium ' + BADGE_MOTOR[l.motor];
    tag.textContent = l.motor.toUpperCase();
    tdMotor.appendChild(tag);
    const validade = `MPU: ${l.mpu_ok ? 'OK' : 'inválido'} · Piezo: ${l.pz_ok ? 'OK' : 'inválido'}`;
    tr.append(
      celula(hora(l.x)), tdMotor,
      celula(l.rpm != null ? Math.round(l.rpm) : '--', 'text-right tabular-nums'),
      celula(l.mpu_ok ? fmt(l.rms) : '--', 'text-right tabular-nums'),
      celula(l.mpu_ok ? fmt(l.pico) : '--', 'text-right tabular-nums'),
      celula(l.pz_ok ? fmt(l.pz_rms, 1) : '--', 'text-right tabular-nums'),
      celula(l.pz_ok ? fmt(l.pz_crista, 2) : '--', 'text-right tabular-nums'),
      celula(validade, 'text-xs'),
    );
    return tr;
  });
  tbody.replaceChildren(...trs);
}

function render() {
  renderCards();
  renderGraficos();
  renderTabela();
}

$('select-janela').addEventListener('change', carregarHistorico);
(async () => {
  await carregarHistorico();
  await atualizar();
  setInterval(atualizar, INTERVALO_MS);
})();
