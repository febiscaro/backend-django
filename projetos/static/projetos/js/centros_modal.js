(function () {
  const form = document.getElementById('createCentroForm');
  const grid = document.querySelector('.page-centros .grid');
  const modalEl = document.getElementById('modalCreateCentro');

  function buildCard(c) {
    const a = document.createElement('a');
    a.className = 'card square';
    a.href = `/projetos/centros/${c.id}/tarefas/nova/`;
    a.title = `Criar tarefa para ${c.nome}`;
    if (c.background_image_url) {
      a.style.backgroundImage =
        `linear-gradient(to top, rgba(0,0,0,0.55), rgba(0,0,0,0.15)), url('${c.background_image_url}')`;
    }
    a.innerHTML = `
      <div class="card-content">
        <h3 class="card-title">${c.nome}</h3>
        <div class="card-subtle">Código: ${c.codigo}${c.cliente ? " • Cliente: " + c.cliente : ""}</div>
      </div>
    `;
    a.addEventListener('click', (e) => { e.preventDefault(); window.location.href = a.href; });
    return a;
  }

  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const data = new FormData(form);

      try {
        const resp = await fetch("/projetos/centros/novo/", {
          method: "POST",
          body: data,
          headers: { "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin",
        });
        const json = await resp.json();

        if (!resp.ok || !json.ok) {
          const errs = json.errors || {};
          const first = Object.keys(errs)[0];
          const msg = first ? `${first}: ${errs[first].join(" ")}` : "Erro ao salvar.";
          alert(msg);
          return;
        }

        if (grid) grid.prepend(buildCard(json.center));

        // Fecha o modal Bootstrap e limpa o form
        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.hide();
        form.reset();
      } catch (err) {
        console.error(err);
        alert("Falha na comunicação com o servidor.");
      }
    });
  }
})();
