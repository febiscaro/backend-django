(function () {
  // Atualiza contador da coluna com base no DOM (defensivo)
  function refreshCounts() {
    document.querySelectorAll('.coluna').forEach(col => {
      const count = col.querySelectorAll('.task').length;
      const badge = col.querySelector('.coluna__count');
      if (badge) badge.textContent = count;
    });
  }

  // placeholder para futuras features (drag-and-drop, filtros, etc.)
  function initBoard() {
    refreshCounts();
    // Próximo passo: integrar SortableJS para arrastar e salvar status/posição.
  }

  document.addEventListener('DOMContentLoaded', initBoard);
})();
