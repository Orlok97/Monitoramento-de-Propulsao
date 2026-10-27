const URL_API       = '/api/ultimos';
const INTERVALO_MS  = 1000;
const OFFLINE_MS    = 10000;
const MAX_PONTOS    = 3600;
const MAX_LINHAS    = 20;
const MOTORES       = ['bb', 'be'];
const COR           = { bb: '#3b82f6', be: '#ef4444' };

const ESTADOS = {
  online:     'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  offline:    'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300',
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

const hora = epochSeg => new Date(epochSeg * 1000).toLocaleTimeString('pt-BR');

// ------------------------------------------------------------ Gráficos
const escuro = window.matchMedia('(prefers-color-scheme: dark)').matches;
Chart.defaults.color = escuro ? '#94a3b8' : '#475569';
Chart.defaults.borderColor = escuro ? '#1e293b' : '#e2e8f0';

function criarGrafico(canvasId, comLinha, xTitulo, yTitulo, xFmt) {
  return new Chart($(canvasId), {
    type: 'scatter',
    data: {
      datasets: MOTORES.map(m => ({
        label: m.toUpperCase(),
        data: [],
        borderColor: COR[m],
        backgroundColor: COR[m],
        showLine: comLinha,
        pointRadius: comLinha ? 0 : 3,
        borderWidth: 2,
        tension: 0.2,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { type: 'linear', title: { display: true, text: xTitulo },
             ticks: { callback: xFmt || (v => v), maxTicksLimit: 8 } },
        y: { title: { display: true, text: yTitulo }, beginAtZero: true },
      },
    },
  });
}

const chartRms  = criarGrafico('chart-rms',  true,  'tempo', 'RMS (m/s²)', hora);
const chartRpm  = criarGrafico('chart-rpm',  true,  'tempo', 'RPM', hora);
const chartDisp = criarGrafico('chart-disp', false, 'RPM', 'RMS (m/s²)');

function processar(motor, leitura) {
  if (!leitura) return;
  if (leitura.recebido_em === ultimoRecebido[motor]) return;

  ultimoRecebido[motor] = leitura.recebido_em;
  ultimoVisto[motor] = Date.now();

  const x = Date.now() / 1000;
  buffer[motor].push({ x, rms: leitura.rms, pico: leitura.pico, rpm: leitura.rpm });
  if (buffer[motor].length > MAX_PONTOS) buffer[motor].shift();

  linhas.unshift({ x, motor, rms: leitura.rms, pico: leitura.pico, rpm: leitura.rpm });
  if (linhas.length > MAX_LINHAS) linhas.pop();
}

async function atualizar() {
  try {
    const resp = await fetch(URL_API, { cache: 'no-store' });
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
  if (ok) $('ultima-atualizacao').textContent = 'Última atualização: ' + hora(Date.now() / 1000);
}

function janelaMin() {
  return Number($('select-janela').value);
}

function renderCards() {
  MOTORES.forEach(m => {
    const ult = buffer[m][buffer[m].length - 1];
    const agora = Date.now();

    let estado = 'aguardando', texto = 'Aguardando';
    if (ultimoVisto[m]) {
      const ativo = agora - ultimoVisto[m] < OFFLINE_MS;
      estado = ativo ? 'online' : 'offline';
      texto = ativo ? 'Online' : 'Sem sinal';
    }
    $(m + '-status').className = BASE_BADGE_MOTOR + ESTADOS[estado];
    $(m + '-status').textContent = texto;

    if (ult) {
      $(m + '-rpm').textContent = Math.round(ult.rpm);
      $(m + '-rms').textContent = ult.rms.toFixed(3);
      $(m + '-pico').textContent = ult.pico != null ? ult.pico.toFixed(3) : '--';
      $(m + '-atualizado').textContent = hora(ult.x);
    }
  });
}

function renderGraficos() {
  const limite = Date.now() / 1000 - janelaMin() * 60;
  MOTORES.forEach((m, i) => {
    const pts = buffer[m].filter(p => p.x >= limite);
    chartRms.data.datasets[i].data  = pts.map(p => ({ x: p.x,   y: p.rms }));
    chartRpm.data.datasets[i].data  = pts.map(p => ({ x: p.x,   y: p.rpm }));
    chartDisp.data.datasets[i].data = pts.map(p => ({ x: p.rpm, y: p.rms }));
  });
  [chartRms, chartRpm, chartDisp].forEach(c => c.update('none'));
}

function renderTabela() {
  const tbody = $('tabela-leituras');
  const vazia = $('tabela-vazia');
  if (!linhas.length) { tbody.replaceChildren(vazia); return; }

  const trs = linhas.map(l => {
    const tr = document.createElement('tr');
    const celula = (txt, cls) => {
      const td = document.createElement('td');
      td.className = 'px-4 py-2 ' + (cls || '');
      td.textContent = txt;
      return td;
    };
    const tdMotor = celula('', '');
    const tag = document.createElement('span');
    tag.className = 'rounded px-2 py-0.5 text-xs font-medium ' + BADGE_MOTOR[l.motor];
    tag.textContent = l.motor.toUpperCase();
    tdMotor.appendChild(tag);

    tr.append(
      celula(hora(l.x)),
      tdMotor,
      celula(Math.round(l.rpm), 'text-right tabular-nums'),
      celula(l.rms.toFixed(3), 'text-right tabular-nums'),
      celula(l.pico != null ? l.pico.toFixed(3) : '--', 'text-right tabular-nums'),
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

$('select-janela').addEventListener('change', render);
atualizar();
setInterval(atualizar, INTERVALO_MS);