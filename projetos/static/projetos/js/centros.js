// Abre/fecha modal e envia para o backend
(function () {
  const modal = document.getElementById('createCentroModal');
  const openBtn = document.getElementById('btn-open-create');
  const closeEls = modal ? modal.querySelectorAll('[data-close]') : [];
  const form = document.getElementById('createCentroForm');
  const grid = document.querySelector('.grid');

  function openModal() {
    if (!modal) return;
    modal.setAttribute('aria-hidden', 'false');
    const first = modal.querySelector('input[name="nome"]');
    if (first) setTimeout(() => first.focus(), 50);
  }
  function closeModal() {
    if (!modal) return;
    modal.setAttribute('aria-hidden', 'true');
  }

  if (openBtn) openBtn.addEventListener('click', openModal);
  closeEls.forEach(el => el.addEventListener('click', closeModal));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal && modal.getAttribute('aria-hidden') === 'false') {
      closeModal();
    }
  });

  // Helper: cria o HTML do novo card
  function buildCard(c) {
    const a = document.createElement('a');
    a.className = 'card square';
    a.href = `/projetos/centros/${c.id}/tarefas/nova/`;
    a.setAttribute('data-code', (c.codigo || '').toLowerCase().replace(/\s+/g, '-'));
    a.setAttribute('data-href', a.href);
    a.title = `Criar tarefa para ${c.nome}`;
    // Se houver imagem, aplica inline junto do degradê
    if (c.background_image_url) {
      a.style.backgroundImage = `linear-gradient(to top, rgba(0,0,0,0.55), rgba(0,0,0,0.15)), url('${c.background_image_url}')`;
    }
    a.innerHTML = `
      <div class="card-content">
        <h3 class="card-title">${c.nome}</h3>
        <div class="card-subtle">Código: ${c.codigo}${c.cliente ? " • Cliente: " + c.cliente : ""}</div>
      </div>
    `;
    // comportamento de clique (igual centros.js)
    a.addEventListener('click', (e) => {
      e.preventDefault();
      window.location.href = a.href;
    });
    return a;
  }

  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      const actionUrl = "/projetos/centros/novo/"; // rota backend
      const data = new FormData(form);             // inclui arquivo + csrf
      try {
        const resp = await fetch(actionUrl, {
          method: "POST",
          body: data,
          headers: { "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin",
        });

        const json = await resp.json();

        if (!resp.ok || !json.ok) {
          // Mostra primeiro erro simples (poderíamos destacar campo por campo depois)
          const errs = json.errors || {};
          const firstField = Object.keys(errs)[0];
          const msg = firstField ? `${firstField}: ${errs[firstField].join(" ")}` : "Erro ao salvar.";
          alert(msg);
          return;
        }

        // Sucesso: adiciona o novo card no topo da grade
        if (grid) {
          const card = buildCard(json.center);
          grid.prepend(card);
        }

        closeModal();
        form.reset();
      } catch (err) {
        console.error(err);
        alert("Falha na comunicação com o servidor.");
      }
    });
  }
})();
