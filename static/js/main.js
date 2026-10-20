(() => {
  'use strict';
  const $ = (sel) => document.querySelector(sel);
  const form = $('#simulationForm');
  if (form) {
    const radios = form.querySelectorAll('[name="calibration_mode"]');
    const setMode = () => {
      const derived = form.querySelector('[name="calibration_mode"]:checked').value === 'derived';
      $('#manualCal').classList.toggle('hidden', derived);
      $('#derivedCal').classList.toggle('hidden', !derived);
    };
    radios.forEach((r) => r.addEventListener('change', setMode));
    setMode();
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const status = $('#formStatus');
      const button = $('#submitSim');
      status.classList.remove('success');
      const payload = {};
      try {
        for (const [key, val] of new FormData(form).entries()) {
          if (['patient_name', 'patient_id', 'notes', 'calibration_mode'].includes(key)) payload[key] = val;
          else if (key === 'dose_days') {
            if (!/^\s*\d+(\s*,\s*\d+)*\s*$/.test(val)) throw Error('Dose days must be comma-separated, e.g. 1, 8, 15');
            payload[key] = val.split(',').map(Number);
          } else {
            if (!val.trim() || !Number.isFinite(Number(val))) throw Error('Please enter a valid numeric value for: ' + key);
            payload[key] = Number(val);
          }
        }
        if (payload.dose_days.some((n) => n > payload.T_days || n < 1)) throw Error('Each dose day must fall within the simulation window');
        button.disabled = true;
        button.textContent = 'Solving equations...';
        status.textContent = 'Calculating the scenario and saving the results.';
        const resp = await fetch('/simulate', {method:'POST', headers: {
          'Content-Type':'application/json', 'X-CSRF-Token': $('meta[name="csrf-token"]').content
        }, body:JSON.stringify(payload)});
        const data = await resp.json();
        if (!resp.ok) {
          const extra = (data.details || []).map(x => `${x.field}: ${x.message}`).join(' | ');
          throw Error((data.error || 'Simulation failed') + (extra ? ' — ' + extra : ''));
        }
        status.classList.add('success');
        status.textContent = 'Simulation completed. Opening the results...';
        window.location.assign(data.url);
      } catch (error) {
        status.textContent = error.message || 'An unexpected error occurred';
        button.disabled = false;
        button.textContent = 'Run simulation ←';
      }
    });
  }

  const dataElement = $('#chart-data');
  if (!dataElement) return;
  let result;
  try { result = JSON.parse(dataElement.textContent); } catch { return; }
  const charts = [
    {id:'cellsChart', keys:['S','R'], colors:['#5e74ce','#f09b8b']},
    {id:'immuneChart', keys:['I'], colors:['#4ab49f']},
    {id:'drugChart', keys:['C_eff'], colors:['#9169db']},
  ];
  function numberLabel(n) {
    if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + 'm';
    if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'k';
    if (Math.abs(n) >= 10) return n.toFixed(0);
    return n.toFixed(n < 1 ? 3 : 1);
  }
  function draw(chart) {
    const canvas = document.getElementById(chart.id);
    if (!canvas) return;
    const box = canvas.getBoundingClientRect(), ratio = window.devicePixelRatio || 1;
    if (!box.width || !box.height) return;
    canvas.width = Math.floor(box.width * ratio);
    canvas.height = Math.floor(box.height * ratio);
    const c = canvas.getContext('2d');
    c.scale(ratio, ratio);
    const w=box.width,h=box.height,p={left:65,right:15,top:12,bottom:32};
    const cw = w - p.left - p.right, ch = h - p.top - p.bottom;
    if (cw <= 0 || ch <= 0) return;
    const xs = result.day;
    const xMax = Math.max(...xs, 1);
    let yMax = Math.max(0, ...chart.keys.flatMap(key => result[key]));
    if (yMax === 0) yMax = 1;
    yMax *= 1.08;
    c.font='11px Arial';c.textAlign='right';c.textBaseline='middle';
    for(let i=0;i<=4;i++){
      const y = p.top+ch-i*ch/4;
      c.beginPath();c.moveTo(p.left,y);c.lineTo(w-p.right,y);c.strokeStyle='#ecf0f5';c.stroke();
      c.fillStyle='#8a98ac';c.fillText(numberLabel(yMax*i/4),p.left-9,y);
    }
    c.textAlign='center';c.textBaseline='top';
    for (let i=0;i<=5;i++) {
      const x=p.left+i*cw/5;
      c.fillStyle='#8a98ac';c.fillText(Math.round(xMax*i/5),x,h-p.bottom+10);
    }
    chart.keys.forEach((key,index) => {
      c.beginPath();
      result[key].forEach((v,i) => {
        const x = p.left + xs[i]/xMax*cw, y=p.top+ch-(v/yMax)*ch;
        if (i===0) c.moveTo(x,y);else c.lineTo(x,y);
      });
      c.strokeStyle=chart.colors[index];c.lineWidth=2.6;c.lineJoin='round';c.stroke();
    });
  }
  let timer;
  function redraw() {charts.forEach(draw)}
  window.addEventListener('resize', () => {clearTimeout(timer);timer=setTimeout(redraw,100)});
  redraw();
})();
