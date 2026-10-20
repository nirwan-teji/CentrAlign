const goal = document.querySelector('#goal');
const trace = document.querySelector('#trace');
const outcome = document.querySelector('#outcome');
const approval = document.querySelector('#approval');
let activeRun;
document.querySelector('#start').addEventListener('click', async () => {
  trace.textContent = 'Starting…'; outcome.textContent = 'Running…';
  const response = await fetch('/api/runs', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({goal: goal.value})});
  const run = await response.json();
  activeRun = run.run_id;
  const stream = new EventSource(`/api/runs/${run.run_id}/events`);
  stream.onmessage = event => { const data = JSON.parse(event.data); trace.textContent += `\n${JSON.stringify(data, null, 2)}`; if (data.type === 'approval_required') { approval.classList.remove('hidden'); document.querySelector('#approval-reason').textContent = data.request.reason; document.querySelector('#approval-data').textContent = JSON.stringify(data.request.relevant_data, null, 2); } if (data.type === 'complete') { approval.classList.add('hidden'); outcome.textContent = JSON.stringify(data, null, 2); stream.close(); } };
});
document.querySelectorAll('[data-decision]').forEach(button => button.addEventListener('click', async () => {
  await fetch(`/api/runs/${activeRun}/approval`, {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({decision: button.dataset.decision, comment: document.querySelector('#approval-comment').value})});
  approval.classList.add('hidden');
}));
